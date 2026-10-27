"""Incremental RAG index update for the catalog sync.

`build_index.py --rebuild` re-chunks and re-embeds everything (≈3 h on the
stand's CPU, dominated by the PDF near-duplicate pass over ~7.4k chunks).
A nightly feed sync touches a handful of products, so this module replaces
only their rows:

  1. drop the chunks of the affected products from `chunks` (this version),
  2. re-chunk the products that are still active (+ their parsed documents
     for new / reactivated ones; a changed price or name only refreshes the
     product chunk — the PDF rows stay as they are),
  3. drop new PDF chunks that near-duplicate what the index already holds
     (same boilerplate guard as the full build, but against the live index),
  4. embed the new rows, splice them into embeddings_*.npy / metadata_*.pkl,
  5. write both files atomically — bot/admin pick them up via maybe_reload().

Chunker and embedder are duck-typed (chunk_product / chunk_document and
embed_passages) so tests can run without the E5 model.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, asdict
from typing import Iterable, List, Optional

import numpy as np
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, selectinload

from src.documents.models import Document
from src.products.models import Product
from src.rag.chunker import ChunkData
from src.rag.models import Chunk
from src.rag.simple_retriever import SimpleRetriever

logger = logging.getLogger(__name__)


@dataclass
class IndexUpdateReport:
    products_reindexed: int = 0
    products_removed: int = 0
    chunks_removed: int = 0
    chunks_added: int = 0
    pdf_dups_dropped: int = 0
    index_size: int = 0
    skipped: bool = False
    reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _metadata_row(chunk: Chunk) -> dict:
    """Same shape as SimpleRetriever.build_index_from_db writes."""
    return {
        'chunk_id': chunk.id,
        'chunk_text': chunk.chunk_text,
        'chunk_type': chunk.chunk_type,
        'product_id': chunk.product_id,
        'document_id': chunk.document_id,
        'category_id': chunk.category_id,
        'position': chunk.position,
    }


def _l2_normalize(embs: np.ndarray) -> np.ndarray:
    if embs.size == 0:
        return embs.astype(np.float32)
    norms = np.linalg.norm(embs, axis=1, keepdims=True)
    norms = np.where(norms < 1e-9, 1.0, norms)
    return (embs / norms).astype(np.float32)


class IncrementalIndexer:
    def __init__(
        self,
        chunker,
        embedder,
        index_version: str,
        data_dir: str = "base",
        batch_size: int = 32,
        dedup_threshold: float = 0.92,
    ):
        self.chunker = chunker
        self.embedder = embedder
        self.index_version = index_version
        self.data_dir = data_dir
        self.batch_size = batch_size
        self.dedup_threshold = dedup_threshold

    # ------------------------------------------------------------ helpers
    def _embed(self, chunks: List[ChunkData]) -> np.ndarray:
        if not chunks:
            return np.zeros((0, 0), dtype=np.float32)
        texts = [c.contextualized_text for c in chunks]
        return _l2_normalize(self.embedder.embed_passages(texts, batch_size=self.batch_size))

    def _dedup_pdf(
        self,
        chunks: List[ChunkData],
        embs: np.ndarray,
        existing_pdf: Optional[np.ndarray],
    ) -> tuple[List[ChunkData], np.ndarray, int]:
        """Greedy near-duplicate filter: against the kept PDF rows of the live
        index first, then against the chunks accepted earlier in this batch."""
        if not chunks:
            return chunks, embs, 0
        keep: list[int] = []
        accepted: list[np.ndarray] = []
        thr = self.dedup_threshold
        for i in range(len(chunks)):
            e = embs[i]
            if existing_pdf is not None and existing_pdf.shape[0] and np.max(existing_pdf @ e) > thr:
                continue
            if accepted and np.max(np.stack(accepted) @ e) > thr:
                continue
            keep.append(i)
            accepted.append(e)
        kept_chunks = [chunks[i] for i in keep]
        kept_embs = embs[keep] if keep else np.zeros((0, embs.shape[1]), dtype=np.float32)
        return kept_chunks, kept_embs, len(chunks) - len(keep)

    # ------------------------------------------------------------ main
    def update(
        self,
        session: Session,
        reindex_ids: Iterable[int],
        remove_ids: Iterable[int],
        refresh_ids: Iterable[int] = (),
    ) -> IndexUpdateReport:
        """Re-index `reindex_ids` (new / reactivated products: product chunks
        AND their document chunks), refresh `refresh_ids` (changed products:
        product chunks only, PDF rows untouched) and drop `remove_ids`
        (products that left the feed). Commits the session."""
        reindex = set(reindex_ids)
        refresh = set(refresh_ids) - reindex
        remove = (set(remove_ids) - reindex) - refresh
        affected = reindex | refresh | remove
        report = IndexUpdateReport(products_reindexed=len(reindex | refresh), products_removed=len(remove))
        if not affected:
            report.skipped, report.reason = True, "nothing to reindex"
            return report

        retriever = SimpleRetriever(self.embedder, self.index_version, self.data_dir)
        old_emb, old_meta = retriever.embeddings, retriever.chunk_metadata
        if old_emb is None or old_meta is None:
            raise RuntimeError(
                f"No index files for version {self.index_version!r} in {self.data_dir}/ — "
                "run `python scripts/build_index.py --rebuild` once before incremental syncs."
            )
        report.index_size = len(old_meta)

        # 1. which existing chunks go away: every row of reindexed / removed
        #    products, only the product rows of refreshed ones
        old_ids = set(session.execute(
            select(Chunk.id).where(
                Chunk.index_version == self.index_version,
                Chunk.product_id.in_(reindex | remove),
            )
        ).scalars().all())
        if refresh:
            old_ids |= set(session.execute(
                select(Chunk.id).where(
                    Chunk.index_version == self.index_version,
                    Chunk.product_id.in_(refresh),
                    Chunk.chunk_type == "product",
                )
            ).scalars().all())
        keep_mask = np.fromiter((m["chunk_id"] not in old_ids for m in old_meta), dtype=bool, count=len(old_meta))
        kept_emb = old_emb[keep_mask]
        kept_meta = [m for m, k in zip(old_meta, keep_mask) if k]
        report.chunks_removed = len(old_meta) - len(kept_meta)

        # 2. re-chunk the active products among `reindex` + `refresh`
        products = session.execute(
            select(Product)
            .where(Product.id.in_(reindex | refresh), Product.is_active.is_(True))
            .options(
                selectinload(Product.params),
                selectinload(Product.category),
                selectinload(Product.documents),
            )
        ).scalars().all()
        product_chunks: List[ChunkData] = []
        pdf_chunks: List[ChunkData] = []
        for product in products:
            product_chunks.extend(self.chunker.chunk_product(product, product.params, product.category))
            if product.id not in reindex:
                continue  # refresh: keep the existing PDF rows
            for doc in product.documents:
                if doc.full_text and doc.full_text.strip():
                    pdf_chunks.extend(self.chunker.chunk_document(doc, product))
        logger.info(
            "[incremental] %d products → %d product chunks, %d pdf chunks (before dedup)",
            len(products), len(product_chunks), len(pdf_chunks),
        )

        # 3. embed (slow part, no side effects yet) + PDF dedup vs live index
        prod_emb = self._embed(product_chunks)
        pdf_emb = self._embed(pdf_chunks)
        if pdf_chunks:
            pdf_rows = [i for i, m in enumerate(kept_meta) if m.get("chunk_type") == "pdf"]
            existing_pdf = kept_emb[pdf_rows] if pdf_rows else None
            pdf_chunks, pdf_emb, dropped = self._dedup_pdf(pdf_chunks, pdf_emb, existing_pdf)
            report.pdf_dups_dropped = dropped

        new_chunks = product_chunks + pdf_chunks
        parts = [kept_emb]
        if len(product_chunks):
            parts.append(prod_emb)
        if len(pdf_chunks):
            parts.append(pdf_emb)

        # 4. DB: delete old rows, insert new ones (ids via flush), then files, then commit.
        #    A failure before commit rolls the DB back and leaves the old files in place.
        if old_ids:
            session.execute(delete(Chunk).where(Chunk.id.in_(old_ids)))
        models = [
            Chunk(
                chunk_text=c.chunk_text,
                contextualized_text=c.contextualized_text,
                chunk_type=c.chunk_type,
                product_id=c.product_id,
                document_id=c.document_id,
                category_id=c.category_id,
                position=c.position,
                token_count=c.token_count,
                index_version=self.index_version,
            )
            for c in new_chunks
        ]
        session.add_all(models)
        session.flush()
        new_meta = kept_meta + [_metadata_row(m) for m in models]
        dim = old_emb.shape[1]
        parts = [p for p in parts if p.size] or [np.zeros((0, dim), dtype=np.float32)]
        new_emb = np.concatenate(parts, axis=0).astype(np.float32)
        if new_emb.shape[0] != len(new_meta):
            session.rollback()
            raise RuntimeError(f"row count mismatch: {new_emb.shape[0]} embeddings vs {len(new_meta)} metadata")

        retriever.save_index(new_emb, new_meta)   # atomic replace of both files
        session.commit()

        report.chunks_added = len(new_chunks)
        report.index_size = len(new_meta)
        logger.info(
            "[incremental] done: -%d +%d chunks (pdf dups dropped %d), index size %d",
            report.chunks_removed, report.chunks_added, report.pdf_dups_dropped, report.index_size,
        )
        return report
