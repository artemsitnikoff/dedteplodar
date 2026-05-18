"""Bulk-import FAQ candidates produced by analyze_calls.py into the live DB.

Usage:
    python scripts/import_faq_from_mango.py [--source mango_analysis/faq_candidates.json] [--dry-run]

Idempotent: an entry whose `question` already exists in `faq_entries` is
skipped (we don't want to dedupe on embedding similarity — that's a job
for the LLM matcher).
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import select
from src.core.database import SessionLocal
from src.faq.models import FaqEntry

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("import_faq")


def _maybe_embed(question: str):
    """Compute E5 embedding for the question; return JSON string or None."""
    try:
        from src.rag.embedder import E5Embedder
        from src.core.config import settings
        embedder = E5Embedder(settings.embedding_model_name, device=settings.device)
        vec = embedder.embed_queries([question])[0]
        return json.dumps(vec.tolist())
    except Exception as e:
        log.warning("could not embed question %r: %s", question[:50], e)
        return None


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", default=str(ROOT / "mango_analysis" / "faq_candidates.json"))
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-embed", action="store_true",
                    help="skip embedding computation (faster — bot's LLM matcher works without it)")
    args = ap.parse_args()

    src = Path(args.source)
    if not src.exists():
        log.error("source not found: %s", src)
        sys.exit(1)

    candidates = json.loads(src.read_text(encoding="utf-8"))
    log.info("Loaded %d candidates from %s", len(candidates), src.name)

    embed_once = None
    if not args.no_embed:
        # Init embedder once (slow ~10s) then reuse
        try:
            from src.rag.embedder import E5Embedder
            from src.core.config import settings
            embed_once = E5Embedder(settings.embedding_model_name, device=settings.device)
            log.info("E5 embedder ready")
        except Exception as e:
            log.warning("Embedder unavailable, will store entries without embedding: %s", e)

    inserted, skipped = 0, 0
    with SessionLocal() as s:
        for c in candidates:
            q = c.get("question", "").strip()
            a = c.get("answer", "").strip()
            if not q or not a:
                continue

            existing = s.execute(
                select(FaqEntry).where(FaqEntry.question == q)
            ).scalar_one_or_none()
            if existing is not None:
                skipped += 1
                log.info("SKIP (exists): %s", q[:70])
                continue

            emb_json = None
            if embed_once is not None:
                try:
                    vec = embed_once.embed_queries([q])[0]
                    emb_json = json.dumps(vec.tolist())
                except Exception as e:
                    log.warning("embed failed for %r: %s", q[:50], e)

            row = FaqEntry(question=q, answer=a, embedding=emb_json, active=True)
            if not args.dry_run:
                s.add(row)
            inserted += 1
            log.info("ADD: %s", q[:70])

        if args.dry_run:
            log.info("DRY RUN — no commit. Would insert %d / skip %d", inserted, skipped)
        else:
            s.commit()
            log.info("Done — inserted %d, skipped %d", inserted, skipped)


if __name__ == "__main__":
    main()
