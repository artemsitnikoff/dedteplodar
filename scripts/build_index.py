#!/usr/bin/env python3
"""Build RAG index script."""

import logging
import sys
import time
import argparse
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.core.config import settings
from src.core.database import SessionLocal, create_tables
from src.rag.chunker import TextChunker
from src.rag.embedder import E5Embedder
from src.rag.simple_indexer import SimpleIndexBuilder
from src.rag.models import Chunk


def setup_logging():
    """Setup logging configuration."""
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper()),
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )


def main():
    """Build RAG index."""
    parser = argparse.ArgumentParser(description='Build RAG index for Teplodar knowledge base')
    parser.add_argument('--rebuild', action='store_true', help='Rebuild index (delete existing)')
    parser.add_argument('--version', type=str, help='Override index version')

    args = parser.parse_args()

    setup_logging()
    logger = logging.getLogger(__name__)

    # Override version if specified
    index_version = args.version or settings.index_version

    logger.info(f"Building RAG index version: {index_version}")
    start_time = time.time()

    try:
        # Ensure tables exist
        create_tables()

        # Initialize components
        chunker = TextChunker(
            model_name=settings.embedding_model_name,
            chunk_size_tokens=settings.chunk_size_tokens,
            chunk_overlap_tokens=settings.chunk_overlap_tokens
        )

        embedder = E5Embedder(
            model_name=settings.embedding_model_name,
            device=settings.device
        )

        indexer = SimpleIndexBuilder(
            chunker=chunker,
            embedder=embedder,
            index_version=index_version,
            batch_size=settings.batch_size_embedding,
            dedup_threshold=settings.pdf_dedup_threshold,
        )

        # Build index
        with SessionLocal() as session:
            indexer.build_full_index(session, rebuild=args.rebuild)

        elapsed_time = time.time() - start_time
        logger.info(f"Index building completed in {elapsed_time:.2f} seconds")

        # Print final statistics
        with SessionLocal() as session:
            total_chunks = session.query(Chunk).filter(Chunk.index_version == index_version).count()
            product_chunks = session.query(Chunk).filter(
                Chunk.index_version == index_version,
                Chunk.chunk_type == "product"
            ).count()
            pdf_chunks = session.query(Chunk).filter(
                Chunk.index_version == index_version,
                Chunk.chunk_type == "pdf"
            ).count()

        print(f"\n{'='*60}")
        print(f"RAG Index Built Successfully")
        print(f"{'='*60}")
        print(f"Version: {index_version}")
        print(f"Total chunks: {total_chunks}")
        print(f"Product chunks: {product_chunks}")
        print(f"PDF chunks: {pdf_chunks}")
        print(f"Embedding model: {settings.embedding_model_name}")
        print(f"Build time: {elapsed_time:.2f}s")
        print(f"{'='*60}")

    except Exception as e:
        logger.error(f"Error building index: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()