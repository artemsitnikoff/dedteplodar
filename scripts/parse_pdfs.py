#!/usr/bin/env python3
"""
CLI script to parse PDF documents.

Usage: python scripts/parse_pdfs.py [--limit N]
"""

import sys
import asyncio
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import click
from src.core.logging import setup_logging
from src.ingestion.pdf_parser import PDFParser


@click.command()
@click.option('--limit', '-l', type=int, default=5, help='Limit number of PDFs to parse')
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose logging')
def main(limit: int, verbose: bool):
    """Parse PDF documents and extract text content."""

    # Setup logging
    if verbose:
        import logging
        logging.getLogger().setLevel(logging.DEBUG)

    setup_logging()

    async def run_parser():
        try:
            async with PDFParser() as parser:
                result = await parser.parse_pdfs(limit=limit)

                click.echo(f"✅ PDF parsing completed!")
                click.echo(f"📊 Total: {result['total']}")
                click.echo(f"✅ Success: {result['success']}")
                click.echo(f"❌ Failed: {result['failed']}")
                click.echo(f"🕳️  Empty: {result['empty']}")

        except Exception as e:
            click.echo(f"❌ Error during PDF parsing: {e}", err=True)
            sys.exit(1)

    # Run async parser
    asyncio.run(run_parser())


if __name__ == "__main__":
    main()