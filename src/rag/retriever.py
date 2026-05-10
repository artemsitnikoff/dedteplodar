"""Retrieval module for RAG using sqlite-vec."""

import logging
from typing import List, Optional
from dataclasses import dataclass

import numpy as np
from sqlalchemy.orm import Session

from .embedder import E5Embedder

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """Search result with metadata."""
    id: int
    score: float  # 1 - distance (higher is better)
    chunk_text: str
    chunk_type: str
    product_id: Optional[int]
    document_id: Optional[int]
    category_id: Optional[int]
    position: int


class Retriever:
    """Vector retriever using sqlite-vec for semantic search."""

    def __init__(self, embedder: E5Embedder, index_version: str):
        """Initialize retriever.

        Args:
            embedder: E5Embedder instance
            index_version: Index version to search in
        """
        self.embedder = embedder
        self.index_version = index_version

    def search(
        self,
        session: Session,
        query: str,
        k: int = 8,
        chunk_type: Optional[str] = None,
        category_id: Optional[int] = None,
        product_id: Optional[int] = None
    ) -> List[SearchResult]:
        """Search for relevant chunks.

        Args:
            session: Database session
            query: Search query
            k: Number of results to return
            chunk_type: Filter by chunk type ('product' or 'pdf')
            category_id: Filter by category
            product_id: Filter by product

        Returns:
            List of search results ordered by relevance
        """
        # Embed query
        query_embedding = self.embedder.embed_queries([query])[0]  # (embedding_dim,)

        # Build SQL with optional filters
        base_sql = """
        SELECT
            c.id, c.chunk_text, c.chunk_type, c.product_id, c.document_id,
            c.category_id, c.position,
            v.distance
        FROM chunks_vec v
        JOIN chunks c ON c.id = v.rowid
        WHERE v.embedding MATCH ?
          AND k = ?
          AND c.index_version = ?
        """

        params = [query_embedding.tobytes(), k, self.index_version]

        # Add filters
        if chunk_type:
            base_sql += " AND c.chunk_type = ?"
            params.append(chunk_type)

        if category_id:
            base_sql += " AND c.category_id = ?"
            params.append(category_id)

        if product_id:
            base_sql += " AND c.product_id = ?"
            params.append(product_id)

        base_sql += " ORDER BY v.distance"

        # Execute search
        result = session.execute(base_sql, params).fetchall()

        # Convert to SearchResult objects
        search_results = []
        for row in result:
            score = 1.0 - row.distance  # Convert distance to similarity score
            search_results.append(SearchResult(
                id=row.id,
                score=score,
                chunk_text=row.chunk_text,
                chunk_type=row.chunk_type,
                product_id=row.product_id,
                document_id=row.document_id,
                category_id=row.category_id,
                position=row.position
            ))

        logger.info(f"Found {len(search_results)} results for query: '{query[:50]}...'")
        return search_results