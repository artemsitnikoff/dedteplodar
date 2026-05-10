"""Simple index building module without sqlite-vec."""

import logging
from typing import List, Iterator

import numpy as np
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import select, delete

from .chunker import TextChunker, ChunkData
from .embedder import E5Embedder
from .simple_retriever import SimpleRetriever
from src.rag.models import Chunk
from src.products.models import Product, ProductParam, Category
from src.documents.models import Document

logger = logging.getLogger(__name__)


class SimpleIndexBuilder:
    """Builds RAG index using regular database tables + numpy files."""

    def __init__(
        self,
        chunker: TextChunker,
        embedder: E5Embedder,
        index_version: str,
        batch_size: int = 32,
        dedup_threshold: float = 0.92,
    ):
        """Initialize index builder.

        Args:
            chunker: TextChunker instance
            embedder: E5Embedder instance
            index_version: Version string for this index
            batch_size: Batch size for embedding
            dedup_threshold: Cosine similarity threshold for near-duplicate PDF chunk removal
        """
        self.chunker = chunker
        self.embedder = embedder
        self.index_version = index_version
        self.batch_size = batch_size
        self.dedup_threshold = dedup_threshold

    def _chunk_products(self, session: Session) -> Iterator[ChunkData]:
        """Generate chunks for all products.

        Args:
            session: Database session

        Yields:
            ChunkData objects for each product chunk
        """
        # Query all products with their params and categories
        stmt = (
            select(Product)
            .options(
                selectinload(Product.params),
                selectinload(Product.category)
            )
        )

        logger.info("Chunking products...")
        products = session.execute(stmt).scalars().all()

        total_chunks = 0
        for product in products:
            chunks = self.chunker.chunk_product(
                product=product,
                params=product.params,
                category=product.category
            )
            total_chunks += len(chunks)
            yield from chunks

        logger.info(f"Generated {total_chunks} product chunks from {len(products)} products")

    def _chunk_documents(self, session: Session) -> Iterator[ChunkData]:
        """Generate chunks for all documents with content.

        Args:
            session: Database session

        Yields:
            ChunkData objects for each document chunk
        """
        # Query documents with content and their associated products
        stmt = (
            select(Document)
            .where(
                Document.char_count > 0,
                Document.full_text.isnot(None)
            )
            .options(selectinload(Document.product))
        )

        logger.info("Chunking documents...")
        documents = session.execute(stmt).scalars().all()

        total_chunks = 0
        for doc in documents:
            chunks = self.chunker.chunk_document(
                doc=doc,
                product=doc.product
            )
            total_chunks += len(chunks)
            yield from chunks

        logger.info(f"Generated {total_chunks} document chunks from {len(documents)} documents")

    def _save_chunks_batch(self, session: Session, chunks: List[ChunkData]) -> List[int]:
        """Save a batch of chunks to database.

        Args:
            session: Database session
            chunks: List of ChunkData to save

        Returns:
            List of assigned chunk IDs
        """
        chunk_models = []
        for chunk_data in chunks:
            chunk_model = Chunk(
                chunk_text=chunk_data.chunk_text,
                contextualized_text=chunk_data.contextualized_text,
                chunk_type=chunk_data.chunk_type,
                product_id=chunk_data.product_id,
                document_id=chunk_data.document_id,
                category_id=chunk_data.category_id,
                position=chunk_data.position,
                token_count=chunk_data.token_count,
                index_version=self.index_version
            )
            chunk_models.append(chunk_model)

        session.add_all(chunk_models)
        session.flush()  # Get IDs without committing

        return [chunk.id for chunk in chunk_models]

    def _deduplicate_pdf_chunks(
        self,
        chunks: List[ChunkData],
        embeddings: np.ndarray,
        threshold: float = 0.92,
    ) -> tuple[List[ChunkData], int]:
        """Return (kept_chunks, n_removed). Greedy: keep first occurrence, drop near-duplicates."""
        if len(chunks) == 0:
            return chunks, 0

        # Normalize
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        norms = np.where(norms < 1e-9, 1.0, norms)
        embs = embeddings / norms  # (N, D) normalized

        kept_mask = np.ones(len(chunks), dtype=bool)

        for i in range(len(chunks)):
            if not kept_mask[i]:
                continue
            if i + 1 >= len(chunks):
                break
            # Vectorized cosine similarity to all subsequent chunks
            sims = embs[i + 1:] @ embs[i]  # (N-i-1,)
            dup_positions = np.where(sims > threshold)[0] + i + 1
            kept_mask[dup_positions] = False

        kept = [c for c, k in zip(chunks, kept_mask) if k]
        n_removed = len(chunks) - len(kept)
        return kept, n_removed

    def build_full_index(self, session: Session, rebuild: bool = False) -> None:
        """Build complete RAG index.

        Args:
            session: Database session
            rebuild: If True, delete existing chunks for this version first
        """
        logger.info(f"Building RAG index version: {self.index_version}")

        # Clean up existing chunks if rebuild
        if rebuild:
            logger.info("Cleaning up existing chunks...")
            delete_stmt = delete(Chunk).where(Chunk.index_version == self.index_version)
            result = session.execute(delete_stmt)
            logger.info(f"Deleted {result.rowcount} existing chunks")
            session.commit()

        # Collect product and PDF chunks separately
        product_chunks = list(self._chunk_products(session))
        pdf_chunks = list(self._chunk_documents(session))

        if not product_chunks and not pdf_chunks:
            logger.warning("No chunks generated!")
            return

        # Deduplicate PDF chunks using embedding-based near-duplicate detection
        pdf_chunks_original_count = len(pdf_chunks)
        if pdf_chunks:
            logger.info(
                f"Embedding {len(pdf_chunks)} PDF chunks for deduplication "
                f"(threshold={self.dedup_threshold})..."
            )
            pdf_texts = [c.contextualized_text for c in pdf_chunks]
            pdf_embeddings_list = []
            for i in range(0, len(pdf_texts), self.batch_size):
                batch_texts = pdf_texts[i:i + self.batch_size]
                batch_embs = self.embedder.embed_passages(batch_texts, batch_size=self.batch_size)
                pdf_embeddings_list.append(batch_embs)
            pdf_embeddings = np.concatenate(pdf_embeddings_list, axis=0)

            pdf_chunks, n_removed = self._deduplicate_pdf_chunks(
                pdf_chunks, pdf_embeddings, threshold=self.dedup_threshold
            )
            logger.info(
                f"PDF dedup: kept {len(pdf_chunks)}/{pdf_chunks_original_count} chunks, "
                f"removed {n_removed} near-duplicates (threshold={self.dedup_threshold})"
            )

        all_chunks = product_chunks + pdf_chunks

        logger.info(f"Processing {len(all_chunks)} total chunks in batches of {self.batch_size}")

        # Save chunks to database first
        total_saved = 0
        all_chunk_ids = []

        for i in range(0, len(all_chunks), self.batch_size):
            batch = all_chunks[i:i + self.batch_size]
            logger.info(f"Saving chunk batch {i // self.batch_size + 1}/{(len(all_chunks) - 1) // self.batch_size + 1}")

            # Save chunks to database
            chunk_ids = self._save_chunks_batch(session, batch)
            all_chunk_ids.extend(chunk_ids)

            session.commit()
            total_saved += len(batch)

            logger.info(f"Saved {len(batch)} chunks (total: {total_saved}/{len(all_chunks)})")

        logger.info("All chunks saved to database")

        # Build vector index
        logger.info("Building vector search index...")
        retriever = SimpleRetriever(
            embedder=self.embedder,
            index_version=self.index_version
        )
        retriever.build_index_from_db(session)

        # Final statistics
        product_count = len(product_chunks)
        pdf_count = len(pdf_chunks)

        logger.info("Index building completed!")
        logger.info(f"Statistics:")
        logger.info(f"  - Total chunks: {len(all_chunks)}")
        logger.info(f"  - Product chunks: {product_count}")
        logger.info(f"  - PDF chunks: {pdf_count} (deduplicated from {pdf_chunks_original_count})")
        logger.info(f"  - Index version: {self.index_version}")
        logger.info(f"  - Embedding dimension: {self.embedder.get_embedding_dimension()}")