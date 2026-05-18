"""Seed the synonyms table with the dictionary mined from Mango call analysis.

Idempotent: rows whose `term` already exists are skipped.
Run once after deploy to populate the new feature, then maintain via admin UI.

Usage:
    python scripts/seed_synonyms.py [--dry-run]
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import select
from src.core.database import SessionLocal
from src.synonyms.models import Synonym

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("seed_synonyms")


# (term, canonical, category, note)
SEED: list[tuple[str, str, str, str]] = [
    # ── Модели ──
    ("трус двенадцать", "Русь-12",      "model", "автотранскрибация Mango"),
    ("трус 12",         "Русь-12",      "model", "автотранскрибация Mango"),
    ("трус восемнадцать", "Русь-18",    "model", "автотранскрибация Mango"),
    ("трус 18",         "Русь-18",      "model", "автотранскрибация Mango"),
    ("спичка",          "Русь-9",       "model", "клиентский сленг — компактная"),
    ("купер про шестнадцать", "Купер ПРО 16", "model", "акцент"),
    ("куппер 22",       "Купер ПРО 22", "model", "опечатка"),
    ("купер мега",      "ОВК Мега",     "model", "клиентское обиходное"),
    ("блин-24",         "Былина-24",    "model", "автотранскрибация Mango"),
    ("сибирка тридцать", "Сибирь-30",   "model", "клиентский сленг"),

    # ── Компоненты ──
    ("билетная горелка", "пеллетная горелка", "component", "автотранскрибация Mango"),
    ("юбка печки",      "кожух-конвектор",    "component", "клиентское обиходное"),
    ("четверник",       "крестовина дымохода", "component", "клиентское обиходное"),
    ("четверики",       "крестовина дымохода", "component", "клиентское обиходное"),
    ("самоварный бак",  "бак на патрубке дымохода", "component", "монтажный сленг"),
    ("выносной бак",    "бак через регистр-теплообменник", "component", "монтажный сленг"),
    ("сэндвич",         "двустенная утеплённая труба", "component", "монтажный сленг"),
    ("сэндвичи",        "двустенная утеплённая труба", "component", "монтажный сленг"),
    ("отбойник",        "искрогаситель",      "component", "клиентское обиходное"),
    ("зольник",         "поддон для золы",    "component", "клиентское обиходное"),
    ("шибер",           "заслонка дымохода",  "component", "клиентское обиходное"),

    # ── Снятые с производства → актуальные аналоги ──
    ("Русь-22",         "Русь-18 ЛНЗП Профи", "discontinued", "снято с производства, аналог"),
    ("Сиеста-25",       "Сахара-24 ЛК",       "discontinued", "снято с производства, аналог"),
    # Тайгинка: аналог уточняется у сервисного инженера — не подменяем
]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    inserted, skipped = 0, 0
    with SessionLocal() as s:
        for term, canonical, category, note in SEED:
            existing = s.execute(
                select(Synonym).where(Synonym.term == term)
            ).scalar_one_or_none()
            if existing is not None:
                skipped += 1
                log.info("SKIP (exists): %s", term)
                continue
            row = Synonym(
                term=term, canonical=canonical,
                category=category, note=note, active=True,
            )
            if not args.dry_run:
                s.add(row)
            inserted += 1
            log.info("ADD: %-30s → %s  [%s]", term, canonical, category)

        if args.dry_run:
            log.info("DRY RUN — no commit. Would insert %d / skip %d", inserted, skipped)
        else:
            s.commit()
            log.info("Done — inserted %d, skipped %d", inserted, skipped)


if __name__ == "__main__":
    main()
