#!/usr/bin/env python3
"""Evaluate RAG performance script."""

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
from src.rag.eval import RAGEvaluator


def setup_logging():
    """Setup logging configuration."""
    logging.basicConfig(
        level=logging.WARNING,  # Only show warnings/errors for cleaner output
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )


def main():
    """Run RAG evaluation."""
    parser = argparse.ArgumentParser(description='Evaluate Teplodar RAG performance')
    parser.add_argument(
        '--queries',
        type=str,
        default='eval/queries.yaml',
        help='Path to evaluation queries YAML file'
    )

    args = parser.parse_args()

    setup_logging()

    # Resolve query file path
    queries_path = Path(args.queries)
    if not queries_path.is_absolute():
        queries_path = Path(__file__).parent.parent / queries_path

    if not queries_path.exists():
        print(f"Error: Query file not found: {queries_path}")
        sys.exit(1)

    try:
        # Initialize components
        embedder = E5Embedder(
            model_name=settings.embedding_model_name,
            device=settings.device
        )

        retriever = SimpleRetriever(
            embedder=embedder,
            index_version=settings.index_version
        )

        evaluator = RAGEvaluator(retriever)

        # Load evaluation queries
        eval_queries = evaluator.load_queries_from_yaml(str(queries_path))

        # Run evaluation
        with SessionLocal() as session:
            report = evaluator.run_eval(session, eval_queries)

        # Print detailed results
        evaluator.print_detailed_results(report)

    except Exception as e:
        print(f"Error during evaluation: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()