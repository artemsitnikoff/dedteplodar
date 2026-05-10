"""Main entry point for Teplodar ingestion pipeline."""

from core.logging import setup_logging
from core.database import create_tables


def main():
    """Main entry point."""
    setup_logging()
    create_tables()

    print("Teplodar ingestion pipeline initialized.")
    print("Use scripts/ commands to run ingestion tasks:")
    print("- python scripts/ingest_yml.py")
    print("- python scripts/scrape_products.py --limit 5")
    print("- python scripts/parse_pdfs.py --limit 5")


if __name__ == "__main__":
    main()