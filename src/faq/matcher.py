"""FAQ semantic matcher — fast path before RAG/classifier.

Loads all active FaqEntry rows, keeps question embeddings in memory as a
numpy matrix, and answers cosine-similarity queries in <1 ms.
Reloads from DB automatically every RELOAD_INTERVAL seconds so admin changes
propagate without restarting the bot.
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from typing import Optional

import numpy as np
from sqlalchemy.orm import Session

from src.core.database import SessionLocal
from src.faq.models import FaqEntry

logger = logging.getLogger(__name__)

THRESHOLD = 0.92          # minimum cosine similarity to consider a FAQ match
RELOAD_INTERVAL = 60.0    # seconds between DB reloads


@dataclass
class FaqMatch:
    entry_id: int
    question: str
    answer: str
    score: float


class FaqMatcher:
    """Semantic FAQ lookup backed by E5 embeddings."""

    def __init__(self, embedder):
        self.embedder = embedder
        self._entries: list[FaqEntry] = []
        self._matrix: Optional[np.ndarray] = None  # shape (N, dim)
        self._last_loaded: float = 0.0
        self._reload()

    # ──────────────────────────── public

    def find(self, query: str) -> Optional[FaqMatch]:
        """Return best FAQ match or None if nothing is above threshold."""
        self._maybe_reload()
        if self._matrix is None or len(self._entries) == 0:
            return None

        q_vec = self.embedder.embed_queries([query])[0]  # (dim,)
        scores = self._matrix @ q_vec                    # cosine, already normalized

        best_idx = int(np.argmax(scores))
        best_score = float(scores[best_idx])

        if best_score >= THRESHOLD:
            entry = self._entries[best_idx]
            logger.debug("FAQ hit: score=%.3f id=%d q=%r", best_score, entry.id, entry.question[:60])
            return FaqMatch(
                entry_id=entry.id,
                question=entry.question,
                answer=entry.answer,
                score=best_score,
            )
        return None

    def reload(self) -> None:
        """Force an immediate reload from DB (call after admin creates/updates entries)."""
        self._reload()

    # ──────────────────────────── internal

    def _maybe_reload(self) -> None:
        if time.monotonic() - self._last_loaded > RELOAD_INTERVAL:
            self._reload()

    def _reload(self) -> None:
        with SessionLocal() as s:
            entries = s.query(FaqEntry).filter(FaqEntry.active.is_(True)).all()
            # detach from session so we can use them after session closes
            s.expunge_all()

        valid: list[FaqEntry] = []
        vecs: list[np.ndarray] = []

        for e in entries:
            if e.embedding:
                try:
                    vec = np.array(json.loads(e.embedding), dtype=np.float32)
                    valid.append(e)
                    vecs.append(vec)
                except Exception:
                    pass  # corrupt embedding — skip silently

        if vecs:
            self._matrix = np.stack(vecs)   # (N, dim), already L2-normalised
        else:
            self._matrix = None

        self._entries = valid
        self._last_loaded = time.monotonic()
        logger.info("FaqMatcher loaded %d active entries", len(valid))

    # ──────────────────────────── embedding helpers (used by admin API on create/update)

    def embed_question(self, question: str) -> list[float]:
        """Compute and return L2-normalised embedding for a FAQ question."""
        vec = self.embedder.embed_queries([question])[0]
        return vec.tolist()
