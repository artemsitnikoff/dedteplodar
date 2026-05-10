"""Hybrid retriever: BM25 + dense vector search with score fusion."""
from __future__ import annotations

import logging
import re
from typing import List, Optional

import numpy as np
from rank_bm25 import BM25Okapi
from sqlalchemy.orm import Session

from .embedder import E5Embedder
from .simple_retriever import SearchResult, SimpleRetriever

logger = logging.getLogger(__name__)

_RU_STOP = frozenset(
    "и в на с по к о из за для не но а то как это при же уже так или от до"
    " бы со ли что её они он она мы вы я их".split()
)


def _tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[а-яёa-z0-9]+", text.lower())
    return [t for t in tokens if len(t) > 1 and t not in _RU_STOP]


class HybridRetriever:
    """BM25 + dense vector retrieval with reciprocal rank fusion.

    Score = alpha * dense_norm + (1 - alpha) * bm25_norm
    Both scores are min-max normalised across the candidate pool before fusion.
    BM25 index is built lazily from chunk_metadata on first call and cached.
    """

    def __init__(
        self,
        embedder: E5Embedder,
        index_version: str,
        data_dir: str = "base",
        alpha: float = 0.6,
        product_boost: float = 0.05,
    ):
        self._dense = SimpleRetriever(embedder, index_version, data_dir)
        self.alpha = alpha
        self.product_boost = product_boost
        self._bm25: Optional[BM25Okapi] = None
        self._bm25_ids: Optional[list[int]] = None  # chunk index → position in metadata

    # ------------------------------------------------------------------ BM25
    def _ensure_bm25(self) -> None:
        if self._bm25 is not None:
            return
        meta = self._dense.chunk_metadata
        if meta is None:
            raise RuntimeError("Dense index not loaded — run build_index first.")
        logger.info(f"Building BM25 index over {len(meta)} chunks…")
        corpus = [_tokenize(m["chunk_text"]) for m in meta]
        self._bm25 = BM25Okapi(corpus)
        self._bm25_ids = list(range(len(meta)))
        logger.info("BM25 index ready.")

    # ------------------------------------------------------------------ API
    def search(
        self,
        session: Session,
        query: str,
        k: int = 8,
        chunk_type: Optional[str] = None,
        category_id: Optional[int] = None,
        product_id: Optional[int] = None,
    ) -> List[SearchResult]:
        self._ensure_bm25()
        meta = self._dense.chunk_metadata
        embeddings = self._dense.embeddings

        # ── Dense scores ──────────────────────────────────────────────────
        q_emb = self._dense.embedder.embed_queries([query])[0]
        q_emb = q_emb / (np.linalg.norm(q_emb) + 1e-9)
        dense_scores = np.dot(embeddings, q_emb)           # (N,)

        # ── BM25 scores ────────────────────────────────────────────────────
        tokens = _tokenize(query)
        bm25_raw = np.array(self._bm25.get_scores(tokens), dtype=np.float32)

        # ── Min-max normalisation ──────────────────────────────────────────
        def _norm(arr: np.ndarray) -> np.ndarray:
            lo, hi = arr.min(), arr.max()
            if hi - lo < 1e-9:
                return np.zeros_like(arr)
            return (arr - lo) / (hi - lo)

        dense_norm = _norm(dense_scores)
        bm25_norm = _norm(bm25_raw)

        # ── Fusion ────────────────────────────────────────────────────────
        hybrid = self.alpha * dense_norm + (1.0 - self.alpha) * bm25_norm

        # ── Product chunk boost ───────────────────────────────────────────
        if self.product_boost > 0:
            for idx in range(len(meta)):
                if meta[idx].get("chunk_type") == "product":
                    hybrid[idx] = min(1.0, hybrid[idx] + self.product_boost)

        top_idx = np.argsort(hybrid)[::-1]

        # ── Collect results with optional filters ─────────────────────────
        results: List[SearchResult] = []
        for idx in top_idx:
            if len(results) >= k:
                break
            m = meta[idx]
            if chunk_type and m["chunk_type"] != chunk_type:
                continue
            if category_id and m.get("category_id") != category_id:
                continue
            if product_id and m.get("product_id") != product_id:
                continue
            results.append(SearchResult(
                id=m["chunk_id"],
                score=float(hybrid[idx]),
                chunk_text=m["chunk_text"],
                chunk_type=m["chunk_type"],
                product_id=m.get("product_id"),
                document_id=m.get("document_id"),
                category_id=m.get("category_id"),
                position=m["position"],
            ))

        logger.debug(f"Hybrid search '{query[:40]}': {len(results)} results")
        return results

    # ── Passthrough helpers ────────────────────────────────────────────────
    @property
    def embeddings(self):
        return self._dense.embeddings

    @property
    def chunk_metadata(self):
        return self._dense.chunk_metadata

    def build_index_from_db(self, session: Session):
        self._dense.build_index_from_db(session)
        self._bm25 = None  # invalidate cached BM25

    def save_index(self, embeddings, chunk_metadata):
        self._dense.save_index(embeddings, chunk_metadata)
        self._bm25 = None
