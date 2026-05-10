#!/usr/bin/env python3
"""
CLI script to parse and ingest Yandex YML data.

Usage: python scripts/ingest_yml.py [YML_FILE]
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

import click
from src.core.logging import setup_logging
from src.core.database import create_tables
from src.ingestion.yml_parser import YMLParser


@click.command()
@click.argument('yml_file', required=False, type=click.Path(exists=True))
@click.option('--verbose', '-v', is_flag=True, help='Enable verbose logging')
def main(yml_file: str | None, verbose: bool):
    """Parse and ingest Yandex YML data into database."""

    # Setup logging
    if verbose:
        import logging
        logging.getLogger().setLevel(logging.DEBUG)

    setup_logging()

    try:
        # Create tables if they don't exist
        create_tables()

        # Run parser
        parser = YMLParser()
        result = parser.run(yml_file)

        click.echo(f"✅ YML ingestion completed successfully!")
        click.echo(f"📁 File: {result['yml_file']}")
        click.echo(f"📂 Categories: {result['categories_count']}")
        click.echo(f"📦 Products: {result['products_count']}")

    except Exception as e:
        click.echo(f"❌ Error during YML ingestion: {e}", err=True)
        sys.exit(1)


if __name__ == "__main__":
    main()