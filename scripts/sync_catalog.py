#!/usr/bin/env python3
"""Sync the product catalog from the site's YML feed and update the RAG index.

Runs nightly from cron (scripts/cron/sync_catalog.sh) and from the admin
Pipeline page. Only new / changed / removed products are touched — see
src/ingestion/catalog_sync.py.

Usage:
    python scripts/sync_catalog.py                   # feed from YANDEX_YML_URL
    python scripts/sync_catalog.py --url https://…    # explicit URL
    python scripts/sync_catalog.py --file base/upload_latest.xml
    python scripts/sync_catalog.py --dry-run          # diff only, no writes
    python scripts/sync_catalog.py --full             # full index rebuild (~3 h on CPU)
    python scripts/sync_catalog.py --notify           # Telegram summary to OPERATOR_CHAT_ID

Exit code: 0 = ok / nothing to do / skipped (already running), 1 = error.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import click  # noqa: E402

from src.core.logging import setup_logging  # noqa: E402
from src.ingestion.catalog_sync import run_sync  # noqa: E402


@click.command()
@click.option("--url", "url", default=None, help="Feed URL (default: YANDEX_YML_URL from .env)")
@click.option("--file", "file_", default=None, type=click.Path(exists=True, dir_okay=False),
              help="Local YML file instead of a URL (one-off import)")
@click.option("--dry-run", is_flag=True, help="Fetch + diff only; write nothing")
@click.option("--skip-scrape", is_flag=True, help="Do not fetch product pages / PDFs of new products")
@click.option("--skip-pdf", is_flag=True, help="Scrape pages but do not parse their PDFs")
@click.option("--skip-index", is_flag=True, help="Update the DB only, leave the index alone")
@click.option("--full", "full_index", is_flag=True, help="Full index rebuild instead of incremental")
@click.option("--notify", is_flag=True, help="Send the summary to OPERATOR_CHAT_ID in Telegram")
@click.option("--verbose", "-v", is_flag=True)
def main(url, file_, dry_run, skip_scrape, skip_pdf, skip_index, full_index, notify, verbose):
    setup_logging()
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    if url and file_:
        raise click.UsageError("--url and --file are mutually exclusive")

    report = run_sync(
        file_ or url,
        dry_run=dry_run,
        skip_scrape=skip_scrape,
        skip_pdf=skip_pdf,
        skip_index=skip_index,
        full_index=full_index,
        notify=notify,
    )
    click.echo(report.summary())
    if report.status == "error":
        sys.exit(1)


if __name__ == "__main__":
    main()
