"""One-shot idempotent knowledge-base fixes from the 01–14 Jul 👎 analysis
(the "🟢 quick, no-code" batch). Operates on the LIVE DB — safe to run twice.

  #3/#4  труба: correct external diameters — drop the non-existent 210 mm
  #6     add FAQ: «котлы на дизеле?» → чёткое «нет»
  #10    add FAQ: «как рассчитать дымоход?» → Теплодар не проектирует; АСЦ/спец.
  #8     synonyms: normalise the 'меге' misspelling → 'Мега' (Куппер Мега котёл)

Why a script (not the admin UI): faq_entries + synonyms live only in the prod
SQLite DB (not in git), so this is the reproducible way to apply the exact
wording. The running bot/admin pick up the changes within ~10 s
(SynonymStore / FaqMatcher reload poll) — no restart required.

Run on prod:
    docker compose exec admin python scripts/kb_fix_202607.py --dry-run   # preview
    docker compose exec admin python scripts/kb_fix_202607.py             # apply
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from sqlalchemy import select  # noqa: E402
from src.core.database import SessionLocal  # noqa: E402
from src.faq.models import FaqEntry  # noqa: E402
from src.synonyms.models import Synonym  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("kb_fix")

# ── #3/#4 труба: the wrong external-diameter enumeration → corrected ──────────
TRUBA_FIND = "200, 210, 280"
TRUBA_REPLACE = "200 и 280 (210 мм не производим)"

# ── #6, #10: new curated FAQ entries (question, answer) ───────────────────────
NEW_FAQ: list[tuple[str, str]] = [
    (
        "Котлы работают на дизеле / дизельном топливе?",
        "Нет. Котлы «Куппер» — твёрдотопливные, основное топливо — дрова. "
        "Опционально можно установить газовую или пеллетную горелку. Дизельных "
        "горелок мы не выпускаем, работа котлов на дизельном топливе не предусмотрена.",
    ),
    (
        "Как рассчитать или подобрать дымоход?",
        "На сайте Теплодар есть онлайн-калькулятор дымохода "
        "(teplodar.ru/help/calc_dymohod/) — он помогает подобрать элементы дымохода "
        "для монтажа. Проектированием и точным расчётом дымоходов Теплодар не "
        "занимается: за проектом обратитесь в Авторизованный Сервисный Центр "
        "(teplodar.ru/service/) или к профильному специалисту по системам отвода "
        "дымовых газов.",
    ),
]

# ── #8: safe synonyms — `term` must NOT appear inside `canonical` (else the
#       whole-word substitution would double the brand on re-application) ──────
NEW_SYNONYMS: list[tuple[str, str, str, str]] = [
    ("меге", "Мега", "model", "опечатка/склонение 'мега' — котёл Куппер Мега (👎 id211)"),
    ("меге-20", "Мега-20", "model", "опечатка — Куппер Мега-20"),
]


def run(dry: bool) -> None:
    changed = 0
    with SessionLocal() as s:
        # ── #3/#4 fix the existing труба FAQ entry ──
        rows = s.execute(
            select(FaqEntry).where(FaqEntry.answer.contains(TRUBA_FIND))
        ).scalars().all()
        if rows:
            for r in rows:
                log.info("труба: FAQ #%s — %r → %r", r.id, TRUBA_FIND, TRUBA_REPLACE)
                if not dry:
                    r.answer = r.answer.replace(TRUBA_FIND, TRUBA_REPLACE)
                changed += 1
        else:
            log.info(
                "труба: ⚠ FAQ-записи с %r не найдено — проверь вручную в админке → FAQ "
                "(возможно уже исправлено или сформулировано иначе)", TRUBA_FIND,
            )

        # ── #6 / #10 add curated FAQ entries (idempotent by exact question) ──
        for q, a in NEW_FAQ:
            if s.execute(select(FaqEntry).where(FaqEntry.question == q)).scalar_one_or_none():
                log.info("FAQ: уже есть — %r", q)
                continue
            log.info("FAQ: + добавить — %r", q)
            if not dry:
                s.add(FaqEntry(question=q, answer=a, active=True))
            changed += 1

        # ── #8 add safe synonyms (idempotent by term) ──
        for term, canonical, cat, note in NEW_SYNONYMS:
            assert term.lower() not in canonical.lower(), \
                f"unsafe synonym would double: {term!r}→{canonical!r}"
            if s.execute(select(Synonym).where(Synonym.term == term)).scalar_one_or_none():
                log.info("синоним: уже есть — %r", term)
                continue
            log.info("синоним: + добавить — %r → %r", term, canonical)
            if not dry:
                s.add(Synonym(term=term, canonical=canonical, category=cat, note=note, active=True))
            changed += 1

        if dry:
            s.rollback()
            log.info("\n(--dry-run) изменений было бы: %d — ничего не записано.", changed)
        else:
            s.commit()
            log.info(
                "\n✓ Применено (%d изменений). Бот/админка подхватят FAQ и синонимы "
                "в течение ~10 сек — рестарт не нужен.", changed,
            )


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Quick KB fixes from the Jul 👎 review")
    ap.add_argument("--dry-run", action="store_true", help="показать, ничего не записывая")
    run(ap.parse_args().dry_run)
