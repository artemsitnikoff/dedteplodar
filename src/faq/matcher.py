"""FAQ semantic matcher — fast path before RAG/classifier.

Loads all active FaqEntry rows, keeps question embeddings in memory as a
numpy matrix, and answers cosine-similarity queries in <1 ms.
Reloads from DB automatically every RELOAD_INTERVAL seconds so admin changes
propagate without restarting the bot.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import time
from dataclasses import dataclass
from typing import Optional

import numpy as np

from src.core.database import SessionLocal
from src.faq.models import FaqEntry

logger = logging.getLogger(__name__)

THRESHOLD = 0.92          # minimum cosine similarity (legacy fast-path, unused by default)
RELOAD_INTERVAL = 10.0    # seconds between DB reloads — new admin FAQ entries
                          # show up to bot users within this window
LLM_TIMEOUT = 20          # seconds — LLM matcher subprocess timeout

_LLM_PROMPT = """Ты — классификатор вопросов. Дан список FAQ-записей и вопрос пользователя.

FAQ:
{faq_list}

Вопрос пользователя: {query}

Какая FAQ-запись по СМЫСЛУ отвечает на этот вопрос?

Правила:
- Если в вопросе названа конкретная модель/город/название — FAQ-запись должна быть про ту же сущность. Разные модели (Русь vs Былина, Русь-12 vs Русь-18) — НЕ матч.
- Если вопрос общий (доставка, гарантия, оплата, о компании) — подходит любая запись на ту же тему.
- Если ни одна запись не отвечает точно — ответ NONE.

Верни ТОЛЬКО номер записи (например "3") или слово NONE. Ничего больше, без объяснений."""

_DISALLOWED_TOOLS = (
    "Bash,BashOutput,KillShell,"
    "Read,Write,Edit,MultiEdit,NotebookEdit,"
    "Glob,Grep,"
    "WebFetch,WebSearch,"
    "Task,Agent,SlashCommand,TodoWrite,ExitPlanMode"
)


@dataclass
class FaqMatch:
    entry_id: int
    question: str
    answer: str
    score: float


class FaqMatcher:
    """FAQ lookup via LLM (Haiku) over the full FAQ list.

    Why LLM and not pure embeddings: E5 cosine matches question STRUCTURE
    ("Расскажи о X" → "Расскажи о Y") far too aggressively — it doesn't
    distinguish product families or model numbers. Asking the LLM to read
    all FAQ questions at once and return the matching entry id is slower
    (~1-2s with Haiku) but correct. Embeddings are kept on disk for the
    admin UI / future analytics; they are no longer used for matching.
    """

    def __init__(self, embedder, cli_path: str = "claude", llm_model: str = ""):
        self.embedder = embedder
        self.cli_path = cli_path
        self.llm_model = llm_model
        self._entries: list[FaqEntry] = []
        self._matrix: Optional[np.ndarray] = None  # shape (N, dim) — kept for analytics
        self._last_loaded: float = 0.0
        self._reload()

    # ──────────────────────────── public

    def find(self, query: str) -> Optional[FaqMatch]:
        """Return best FAQ match (LLM-decided) or None."""
        self._maybe_reload()
        if not self._entries:
            return None
        return self._find_via_llm(query)

    def reload(self) -> None:
        """Force an immediate reload from DB (call after admin creates/updates entries)."""
        self._reload()

    # ──────────────────────────── LLM matching

    def _find_via_llm(self, query: str) -> Optional[FaqMatch]:
        """Single LLM call: pick which FAQ entry (if any) answers `query`."""
        from src.core.claude_token import ensure_fresh_token_sync
        ensure_fresh_token_sync()

        faq_list = "\n".join(
            f"{i + 1}. {e.question.strip()}" for i, e in enumerate(self._entries)
        )
        prompt = _LLM_PROMPT.format(faq_list=faq_list, query=query.strip())

        env = os.environ.copy()
        env.pop("CLAUDECODE", None)
        env.pop("CLAUDE_CODE_ENTRYPOINT", None)
        args = [
            self.cli_path, "--print", "--output-format", "text",
            "--no-session-persistence",
            "--disallowed-tools", _DISALLOWED_TOOLS,
        ]
        if self.llm_model:
            args += ["--model", self.llm_model]

        try:
            result = subprocess.run(
                args,
                input=prompt.encode(),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=env,
                cwd="/tmp",
                timeout=LLM_TIMEOUT,
            )
            text = result.stdout.decode().strip().strip('"\'').strip()
        except Exception as exc:
            logger.warning("FAQ LLM match failed (%s) — falling through to RAG", exc)
            return None

        # Parse: either "NONE" or "<index>"
        if text.upper().startswith("NONE"):
            logger.debug("FAQ LLM: no match for %r", query[:60])
            return None

        # Pull leading integer (model may add trailing punctuation)
        digits = ""
        for ch in text:
            if ch.isdigit():
                digits += ch
            elif digits:
                break
        if not digits:
            logger.warning("FAQ LLM returned unparseable %r for %r", text[:50], query[:60])
            return None

        idx = int(digits) - 1
        if not (0 <= idx < len(self._entries)):
            logger.warning("FAQ LLM returned out-of-range index %d for %r", idx + 1, query[:60])
            return None

        entry = self._entries[idx]
        logger.debug("FAQ LLM hit: idx=%d id=%d q=%r", idx + 1, entry.id, entry.question[:60])
        return FaqMatch(
            entry_id=entry.id,
            question=entry.question,
            answer=entry.answer,
            score=1.0,  # LLM-decided binary match
        )

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

        prev_count = len(self._entries)
        self._entries = valid
        self._last_loaded = time.monotonic()
        if len(valid) != prev_count or prev_count == 0:
            logger.info(
                "FaqMatcher loaded %d active entries (was %d). Entries: %s",
                len(valid), prev_count,
                ", ".join(f"#{i+1}:{e.question[:50]!r}" for i, e in enumerate(valid[:20]))
                or "(empty)",
            )
        else:
            logger.info("FaqMatcher reloaded — same %d entries", len(valid))

    # ──────────────────────────── embedding helpers (used by admin API on create/update)

    def embed_question(self, question: str) -> list[float]:
        """Compute and return L2-normalised embedding for a FAQ question."""
        vec = self.embedder.embed_queries([question])[0]
        return vec.tolist()
