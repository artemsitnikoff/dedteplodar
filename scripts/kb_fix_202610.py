"""One-shot idempotent knowledge-base fix from the 22–28 Oct Bitrix24 review.
Operates on the LIVE DB — safe to run twice.

  FAQ «Как заказать запчасть … отдельно?» answered «Можно. Для подбора…» —
  sent word for word to any spare-part message («Нужна жаровня для АПГ-25»,
  «нужны шнеки…», «есть ответ по дверкам?»), so it opened with a «Можно» to a
  question nobody asked. The new wording stands on its own. Only the answer
  changes; the question (and its embedding) stays.

Why a script (not the admin UI): faq_entries live only in the prod SQLite DB
(not in git), so this is the reproducible way to apply the exact wording. The
running bot/admin pick it up within ~10 s (FaqMatcher reload poll).

Run on prod:
    docker compose exec admin python scripts/kb_fix_202610.py --dry-run   # preview
    docker compose exec admin python scripts/kb_fix_202610.py             # apply
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

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("kb_fix")

SPARE_PARTS_QUESTION = "Как заказать запчасть (ТЭН, дверцу, зольник, шибер) отдельно?"
SPARE_PARTS_OLD_PREFIX = "Можно. Для подбора"
SPARE_PARTS_ANSWER = (
    "Запчасти (ТЭН, дверцу, зольник, шибер и другие) заказывают отдельно — подбирает их "
    "сервисный инженер. Пришлите ему фото и замеры детали, модель и год выпуска изделия: "
    "Андрей, <b>8-999-303-09-27</b> (WhatsApp/Telegram/MAX, пн–пт 8:00–17:00 НСК). "
    "Доставка отдельных запчастей платная (~1500–2000 руб.), бесплатна только при заказе "
    "основного оборудования."
)


def run(dry: bool) -> None:
    changed = 0
    with SessionLocal() as s:
        rows = s.execute(
            select(FaqEntry).where(
                (FaqEntry.question == SPARE_PARTS_QUESTION)
                | FaqEntry.answer.startswith(SPARE_PARTS_OLD_PREFIX)
            )
        ).scalars().all()
        if not rows:
            log.info("запчасти: ⚠ FAQ-запись не найдена — проверь вручную в админке → FAQ")
        for r in rows:
            if r.answer == SPARE_PARTS_ANSWER:
                log.info("запчасти: FAQ #%s уже исправлена", r.id)
                continue
            log.info("запчасти: FAQ #%s %r\n  было:  %s\n  стало: %s", r.id, r.question, r.answer, SPARE_PARTS_ANSWER)
            if not dry:
                r.answer = SPARE_PARTS_ANSWER
            changed += 1

        if dry:
            s.rollback()
            log.info("\n(--dry-run) изменений было бы: %d — ничего не записано.", changed)
        else:
            s.commit()
            log.info(
                "\n✓ Применено (%d изменений). Бот/админка подхватят FAQ в течение ~10 сек — "
                "рестарт не нужен.", changed,
            )


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="KB fix from the Oct Bitrix24 review")
    ap.add_argument("--dry-run", action="store_true", help="показать, ничего не записывая")
    run(ap.parse_args().dry_run)
