"""In-memory cache of active synonyms with periodic reload from DB.

Why in-memory: substitution runs on every incoming bot message — must be
fast (microseconds). Reload poll keeps admin edits visible within a few
seconds without restart.
"""
from __future__ import annotations

import logging
import re
import time
from typing import Optional

from src.core.database import SessionLocal
from src.synonyms.models import Synonym

logger = logging.getLogger(__name__)

RELOAD_INTERVAL = 10.0   # seconds — match FaqMatcher cadence


class SynonymStore:
    """Loads active Synonym rows once, rebuilds them into a single compiled
    regex with word boundaries, applies `term → canonical` substitutions
    to incoming queries."""

    def __init__(self) -> None:
        self._rules: list[tuple[str, str]] = []  # (term, canonical), longest first
        self._regex: Optional[re.Pattern] = None
        self._term_to_canonical: dict[str, str] = {}
        self._last_loaded: float = 0.0
        self._reload()

    # ──────────────────────────── public

    def apply(self, text_in: str) -> str:
        """Replace every synonym `term` with its `canonical` form in `text_in`.

        Case-insensitive, whole-word matches (Cyrillic-friendly word boundaries).
        Idempotent — running twice changes nothing.
        """
        self._maybe_reload()
        if not self._regex or not text_in:
            return text_in
        return self._regex.sub(self._sub_callback, text_in)

    def reload(self) -> None:
        self._reload()

    def all_active(self) -> list[Synonym]:
        """Return cached entries (for read-only inspection)."""
        return self._entries_cache

    # ──────────────────────────── internal

    def _maybe_reload(self) -> None:
        if time.monotonic() - self._last_loaded > RELOAD_INTERVAL:
            self._reload()

    def _reload(self) -> None:
        try:
            with SessionLocal() as s:
                entries = s.query(Synonym).filter(Synonym.active.is_(True)).all()
                s.expunge_all()
        except Exception:
            logger.exception("SynonymStore: failed to reload from DB")
            return

        # Sort by term length DESC so longer multi-word terms match before
        # their substrings (e.g. "трус двенадцать" before "трус").
        entries.sort(key=lambda e: len(e.term), reverse=True)

        rules: list[tuple[str, str]] = []
        mapping: dict[str, str] = {}
        for e in entries:
            term = e.term.strip()
            canonical = e.canonical.strip()
            if not term or not canonical:
                continue
            rules.append((term, canonical))
            mapping[term.lower()] = canonical

        if rules:
            # Build one big alternation. (?i) for case-insensitive,
            # (?<!\w) and (?!\w) for unicode-aware word boundaries
            # (\b in re is ASCII-only for some libraries).
            pattern = (
                r"(?<!\w)(?i:"
                + "|".join(re.escape(term) for term, _ in rules)
                + r")(?!\w)"
            )
            self._regex = re.compile(pattern)
        else:
            self._regex = None

        prev_count = len(self._rules)
        self._rules = rules
        self._term_to_canonical = mapping
        self._entries_cache = entries
        self._last_loaded = time.monotonic()
        if len(rules) != prev_count or prev_count == 0:
            logger.info(
                "SynonymStore loaded %d active synonyms (was %d)",
                len(rules), prev_count,
            )

    def _sub_callback(self, m: re.Match) -> str:
        # Look up the matched term (any case) in our lowercased map
        return self._term_to_canonical.get(m.group(0).lower(), m.group(0))


# Module-level singleton (lazy)
_store: Optional[SynonymStore] = None


def get_synonym_store() -> SynonymStore:
    global _store
    if _store is None:
        _store = SynonymStore()
    return _store
