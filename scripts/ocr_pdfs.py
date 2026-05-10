#!/usr/bin/env python3
"""OCR processing for empty PDF documents."""

import asyncio
import logging
from typing import Optional

import click

from src.ingestion.ocr_parser import OCRParser

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@click.command()
@click.option('--all-empty', is_flag=True, help='Process all empty PDFs (including certificates)')
@click.option('--limit', type=int, help='Limit number of documents to process')
@click.option('--verbose', is_flag=True, help='Enable debug logging')
def main(all_empty: bool, limit: Optional[int], verbose: bool):
    """Process empty PDF documents with OCR."""
    if verbose:
        logging.getLogger().setLevel(logging.DEBUG)

    if all_empty:
        logger.info("Processing ALL empty PDFs (including certificates and declarations)")
    else:
        logger.info("Processing targeted empty PDFs (manuals, instructions, schemas only)")

    if limit:
        logger.info(f"Limited to {limit} documents")

    asyncio.run(_run_ocr(all_empty, limit))


async def _run_ocr(all_empty: bool, limit: Optional[int]):
    """Run OCR processing."""
    try:
        async with OCRParser() as parser:
            result = await parser.process_empty_pdfs(
                all_empty=all_empty,
                limit=limit
            )

        logger.info("=" * 60)
        logger.info("OCR Processing Summary:")
        logger.info(f"Total documents: {result['total']}")
        logger.info(f"Successfully processed: {result['success']}")
        logger.info(f"Failed: {result['failed']}")
        logger.info(f"Total characters extracted: {result['chars_extracted']:,}")
        if result['success'] > 0:
            logger.info(f"Average characters per document: {result['avg_chars']:,}")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"OCR processing failed: {e}")
        raise


if __name__ == "__main__":
    main()