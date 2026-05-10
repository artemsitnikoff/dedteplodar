#!/usr/bin/env python3
"""
CLI script to scrape company information pages from Teplodar website.

Usage:
    python scripts/scrape_company_info.py                    # discovery + scrape
    python scripts/scrape_company_info.py --urls urls.txt    # extra URLs from file
    python scripts/scrape_company_info.py --dry-run          # discovery only
"""

import argparse
import asyncio
import logging
import sys
from datetime import datetime
from pathlib import Path
from typing import List, Optional

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.orm import Session
from sqlalchemy import text

from src.core.config import settings
from src.core.database import get_session, engine
from src.documents.models import Document, DocumentType
from src.ingestion.company_info_scraper import CompanyInfoScraper


def setup_logging():
    """Setup logging configuration."""
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler('logs/company_scraping.log', encoding='utf-8')
        ]
    )


def load_extra_urls(file_path: str) -> List[str]:
    """Load additional URLs from text file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            urls = []
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    urls.append(line)
            return urls
    except Exception as e:
        logging.error(f"Error loading URLs from {file_path}: {e}")
        return []


def save_to_database(pages: List) -> int:
    """Save scraped pages to database."""
    saved_count = 0

    for session in get_session():
        try:
            for page in pages:
                # Check if document already exists
                existing = session.query(Document).filter(
                    Document.source_url == page.url
                ).first()

                if existing:
                    # Update existing document
                    existing.title = page.title
                    existing.full_text = page.content
                    existing.char_count = page.char_count
                    existing.fetched_at = datetime.utcnow()
                    logging.info(f"Updated existing document: {page.url}")
                else:
                    # Create new document
                    document = Document(
                        product_id=None,  # Company info pages are not tied to products
                        doc_type=DocumentType.HTML,
                        source_url=page.url,
                        title=page.title,
                        full_text=page.content,
                        char_count=page.char_count,
                        fetched_at=datetime.utcnow()
                    )
                    session.add(document)
                    logging.info(f"Created new document: {page.url}")

                saved_count += 1

            session.commit()
            logging.info(f"Successfully saved {saved_count} documents to database")

        except Exception as e:
            session.rollback()
            logging.error(f"Database error: {e}", exc_info=True)
            raise

    return saved_count


def show_database_status():
    """Show current status of HTML documents in database."""
    for session in get_session():
        try:
            # Get HTML documents stats
            result = session.execute(text("""
                SELECT
                    COUNT(*) as total_docs,
                    SUM(char_count) as total_chars,
                    AVG(char_count) as avg_chars
                FROM documents
                WHERE doc_type = 'HTML'
            """)).fetchone()

            print(f"\nDatabase Status:")
            print(f"HTML documents: {result.total_docs}")
            print(f"Total characters: {result.total_chars:,}" if result.total_chars else "Total characters: 0")
            print(f"Average per doc: {int(result.avg_chars):,}" if result.avg_chars else "Average per doc: 0")

            # Show sample documents
            docs = session.execute(text("""
                SELECT id, title, char_count, source_url
                FROM documents
                WHERE doc_type = 'HTML'
                ORDER BY char_count DESC
                LIMIT 10
            """)).fetchall()

            if docs:
                print(f"\nTop documents by size:")
                for doc in docs:
                    print(f"  {doc.id}: {doc.title} ({doc.char_count:,} chars) - {doc.source_url}")

        except Exception as e:
            logging.error(f"Error showing database status: {e}")


def show_content_samples(pages: List, limit: int = 3):
    """Show content samples from scraped pages."""
    print(f"\nContent samples (first {limit} pages):")
    print("=" * 80)

    for i, page in enumerate(pages[:limit]):
        print(f"\n{i+1}. {page.title}")
        print(f"   URL: {page.url}")
        print(f"   Length: {page.char_count:,} chars")
        print(f"   Sample: {page.content[:400]}...")
        print("-" * 80)


async def main():
    """Main function."""
    parser = argparse.ArgumentParser(description="Scrape Teplodar company information pages")
    parser.add_argument("--urls", help="File with additional URLs to scrape")
    parser.add_argument("--dry-run", action="store_true", help="Only discover URLs, don't scrape")
    parser.add_argument("--show-status", action="store_true", help="Show current database status")
    parser.add_argument("--samples", type=int, default=3, help="Number of content samples to show")

    args = parser.parse_args()

    setup_logging()
    logger = logging.getLogger(__name__)

    if args.show_status:
        show_database_status()
        return

    # Load extra URLs if provided
    extra_urls = []
    if args.urls:
        extra_urls = load_extra_urls(args.urls)
        logger.info(f"Loaded {len(extra_urls)} extra URLs from file")

    # Start scraping
    async with CompanyInfoScraper() as scraper:
        if args.dry_run:
            # Discovery only
            urls = await scraper.discover_pages(extra_urls)
            print(f"\nDiscovered {len(urls)} information pages:")
            for url in urls:
                print(f"  - {url}")
            return

        # Full scraping
        logger.info("Starting company information scraping...")
        result = await scraper.scrape_all(extra_urls)

        print(f"\nScraping Results:")
        print(f"Total pages processed: {result['total']}")
        print(f"Successfully scraped: {result['success']}")
        print(f"Failed: {result['failed']}")

        if result['pages']:
            # Save to database
            saved_count = save_to_database(result['pages'])
            print(f"Saved to database: {saved_count}")

            # Show content samples
            show_content_samples(result['pages'], args.samples)

            # Show database status
            show_database_status()

            print(f"\nNext steps:")
            print(f"1. Review scraped content above")
            print(f"2. Run re-indexing: python scripts/build_rag_index.py")
            print(f"3. Test bot with company questions")

        else:
            print("No pages were successfully scraped")


if __name__ == "__main__":
    asyncio.run(main())