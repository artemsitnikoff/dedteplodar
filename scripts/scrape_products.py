#!/usr/bin/env python3
"""
CLI script to scrape product pages.

Usage: python scripts/scrape_products.py [--limit N] [--force]
"""

import sys
import asyncio
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import click
from src.core.logging import setup_logging
from src.ingestion.scraper import ProductScraper


@click.command()
@click.option('--limit', '-l', type=int, default=5, help='Limit number of products to scrape')
@click.option('--force', '-f', is_flag=True, help='Force scrape already scraped products')
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose logging')
def main(limit: int, force: bool, verbose: bool):
    """Scrape product pages for full descriptions and PDF links."""

    # Setup logging
    if verbose:
        import logging
        logging.getLogger().setLevel(logging.DEBUG)

    setup_logging()

    async def run_scraper():
        try:
            async with ProductScraper() as scraper:
                result = await scraper.scrape_products(limit=limit, force=force)

                click.echo(f"✅ Product scraping completed!")
                click.echo(f"📊 Total: {result['total']}")
                click.echo(f"✅ Success: {result['success']}")
                click.echo(f"❌ Failed: {result['failed']}")

        except Exception as e:
            click.echo(f"❌ Error during product scraping: {e}", err=True)
            sys.exit(1)

    # Run async scraper
    asyncio.run(run_scraper())


if __name__ == "__main__":
    main()