#!/usr/bin/env python3
"""Query RAG index script."""

import logging
import sys
import argparse
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from src.core.config import settings
from src.core.database import SessionLocal
from src.rag.embedder import E5Embedder
from src.rag.simple_retriever import SimpleRetriever


def setup_logging():
    """Setup logging configuration."""
    logging.basicConfig(
        level=logging.WARNING,  # Only show warnings/errors for cleaner output
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )


def main():
    """Query RAG index."""
    parser = argparse.ArgumentParser(description='Query Teplodar knowledge base')
    parser.add_argument('query', type=str, help='Search query')
    parser.add_argument('--top-k', type=int, default=settings.top_k, help='Number of results to return')
    parser.add_argument('--chunk-type', type=str, choices=['product', 'pdf'], help='Filter by chunk type')
    parser.add_argument('--category', type=int, help='Filter by category ID')
    parser.add_argument('--product-id', type=int, help='Filter by product ID')
    parser.add_argument('--verbose', action='store_true', help='Show full chunk text')

    args = parser.parse_args()

    setup_logging()

    try:
        # Initialize embedder and retriever
        embedder = E5Embedder(
            model_name=settings.embedding_model_name,
            device=settings.device
        )

        retriever = SimpleRetriever(
            embedder=embedder,
            index_version=settings.index_version
        )

        # Perform search
        with SessionLocal() as session:
            results = retriever.search(
                session=session,
                query=args.query,
                k=args.top_k,
                chunk_type=args.chunk_type,
                category_id=args.category,
                product_id=args.product_id
            )

        # Display results
        if not results:
            print("No results found.")
            return

        print(f"\nSearch results for: '{args.query}'")
        print(f"Found {len(results)} results")
        print("=" * 80)

        for i, result in enumerate(results, 1):
            print(f"\n{i}. Score: {result.score:.4f} | Type: {result.chunk_type}")

            # Show metadata
            if result.product_id:
                print(f"   Product ID: {result.product_id}")
            if result.document_id:
                print(f"   Document ID: {result.document_id}")
            if result.category_id:
                print(f"   Category ID: {result.category_id}")
            if result.position > 0:
                print(f"   Position: {result.position}")

            # Show text
            text_to_show = result.chunk_text if args.verbose else result.chunk_text[:300]
            if not args.verbose and len(result.chunk_text) > 300:
                text_to_show += "..."

            print(f"   Text: {text_to_show}")
            print("-" * 80)

    except Exception as e:
        print(f"Error during search: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()