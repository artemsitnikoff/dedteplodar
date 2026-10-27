"""Simple retriever using numpy for vector search without sqlite-vec."""

import logging
import pickle
from pathlib import Path
from typing import List, Optional
from dataclasses import dataclass

import os
import threading
import time

import numpy as np
from sqlalchemy.orm import Session
from sqlalchemy import select

from .embedder import E5Embedder
from .models import Chunk

logger = logging.getLogger(__name__)


@dataclass
class SearchResult:
    """Search result with metadata."""
    id: int
    score: float  # cosine similarity (higher is better)
    chunk_text: str
    chunk_type: str
    product_id: Optional[int]
    document_id: Optional[int]
    category_id: Optional[int]
    position: int


class SimpleRetriever:
    """Vector retriever using numpy for semantic search."""

    def __init__(self, embedder: E5Embedder, index_version: str, data_dir: str = "base"):
        """Initialize retriever.

        Args:
            embedder: E5Embedder instance
            index_version: Index version to search in
            data_dir: Directory to store embeddings
        """
        self.embedder = embedder
        self.index_version = index_version
        self.data_dir = Path(data_dir)
        self.embeddings_path = self.data_dir / f"embeddings_{index_version}.npy"
        self.metadata_path = self.data_dir / f"metadata_{index_version}.pkl"

        # Load precomputed embeddings if available
        self.embeddings = None
        self.chunk_metadata = None
        # (npy mtime_ns, npy size, pkl mtime_ns, pkl size) of the loaded files —
        # the catalog sync rewrites them in place and the long-running bot /
        # admin pick the new index up via maybe_reload() without a restart.
        self._index_stamp: Optional[tuple] = None
        self._last_reload_check = 0.0
        self._reload_lock = threading.Lock()
        self._load_index()

    # ------------------------------------------------------------ disk I/O
    def _stat_stamp(self) -> Optional[tuple]:
        try:
            a = os.stat(self.embeddings_path)
            b = os.stat(self.metadata_path)
        except FileNotFoundError:
            return None
        return (a.st_mtime_ns, a.st_size, b.st_mtime_ns, b.st_size)

    def _read_index_files(self) -> tuple[np.ndarray, List[dict]]:
        """Read both files; raise if they don't describe the same index."""
        embeddings = np.load(self.embeddings_path)
        with open(self.metadata_path, 'rb') as f:
            metadata = pickle.load(f)
        if embeddings.ndim != 2 or len(metadata) != embeddings.shape[0]:
            raise ValueError(
                f"index files disagree: embeddings {embeddings.shape} vs "
                f"{len(metadata)} metadata rows"
            )
        return embeddings, metadata

    def _load_index(self):
        """Load precomputed embeddings and metadata."""
        stamp = self._stat_stamp()
        if stamp is None:
            return
        try:
            self.embeddings, self.chunk_metadata = self._read_index_files()
            self._index_stamp = stamp
            logger.info(f"Loaded {len(self.chunk_metadata)} embeddings from cache")
        except Exception as e:
            logger.warning(f"Failed to load cached embeddings: {e}")
            self.embeddings = None
            self.chunk_metadata = None

    def maybe_reload(self, min_interval: float = 10.0, force: bool = False) -> bool:
        """Re-read the index files if they changed on disk.

        Called on the search path; the stat() check runs at most once per
        `min_interval` seconds. Returns True when a new index was swapped in
        (callers rebuild anything derived from it, e.g. BM25).
        """
        now = time.monotonic()
        if not force and now - self._last_reload_check < min_interval:
            return False
        with self._reload_lock:
            self._last_reload_check = now
            stamp = self._stat_stamp()
            if stamp is None or stamp == self._index_stamp:
                return False
            # The writer replaces the two files one after the other. If we
            # catch it in between, the row counts disagree — keep the current
            # index and try again at the next interval.
            try:
                embeddings, metadata = self._read_index_files()
            except Exception as e:
                logger.warning(f"Index reload skipped (will retry): {e}")
                return False
            if self._stat_stamp() != stamp:
                return False  # changed again while we were reading
            self.embeddings = embeddings
            self.chunk_metadata = metadata
            self._index_stamp = stamp
            logger.info(f"Index reloaded from disk: {len(metadata)} chunks")
            return True

    def save_index(self, embeddings: np.ndarray, chunk_metadata: List[dict]):
        """Save embeddings and metadata to disk (atomically — readers never
        see a half-written file; see maybe_reload).

        Args:
            embeddings: Array of shape (n_chunks, embedding_dim)
            chunk_metadata: List of metadata dicts for each chunk
        """
        if len(chunk_metadata) != embeddings.shape[0]:
            raise ValueError("embeddings and chunk_metadata have different lengths")
        self.data_dir.mkdir(exist_ok=True)

        tmp_npy = self.embeddings_path.with_name(self.embeddings_path.name + ".tmp")
        tmp_pkl = self.metadata_path.with_name(self.metadata_path.name + ".tmp")
        with open(tmp_npy, 'wb') as f:          # file object: np.save won't append ".npy"
            np.save(f, embeddings)
        with open(tmp_pkl, 'wb') as f:
            pickle.dump(chunk_metadata, f)
        os.replace(tmp_npy, self.embeddings_path)
        os.replace(tmp_pkl, self.metadata_path)

        self.embeddings = embeddings
        self.chunk_metadata = chunk_metadata
        self._index_stamp = self._stat_stamp()
        logger.info(f"Saved {len(chunk_metadata)} embeddings to cache")

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
        if self.embeddings is None or self.chunk_metadata is None:
            logger.error("No embeddings loaded. Run indexing first.")
            return []

        # Embed query
        query_embedding = self.embedder.embed_queries([query])[0]  # (embedding_dim,)
        query_embedding = query_embedding / np.linalg.norm(query_embedding)  # normalize

        # Compute cosine similarities
        similarities = np.dot(self.embeddings, query_embedding)

        # Get top-k indices
        top_indices = np.argsort(similarities)[::-1]

        # Apply filters and collect results
        results = []
        for idx in top_indices:
            if len(results) >= k:
                break

            metadata = self.chunk_metadata[idx]

            # Apply filters
            if chunk_type and metadata['chunk_type'] != chunk_type:
                continue
            if category_id and metadata.get('category_id') != category_id:
                continue
            if product_id and metadata.get('product_id') != product_id:
                continue

            results.append(SearchResult(
                id=metadata['chunk_id'],
                score=float(similarities[idx]),
                chunk_text=metadata['chunk_text'],
                chunk_type=metadata['chunk_type'],
                product_id=metadata.get('product_id'),
                document_id=metadata.get('document_id'),
                category_id=metadata.get('category_id'),
                position=metadata['position']
            ))

        logger.info(f"Found {len(results)} results for query: '{query[:50]}...'")
        return results

    def build_index_from_db(self, session: Session):
        """Build index from database chunks.

        Args:
            session: Database session
        """
        # Get all chunks for this index version
        stmt = select(Chunk).where(Chunk.index_version == self.index_version)
        chunks = session.execute(stmt).scalars().all()

        if not chunks:
            logger.warning(f"No chunks found for index version: {self.index_version}")
            return

        logger.info(f"Building index for {len(chunks)} chunks")

        # Prepare data for embedding
        texts = [chunk.contextualized_text for chunk in chunks]
        metadata = []

        for chunk in chunks:
            metadata.append({
                'chunk_id': chunk.id,
                'chunk_text': chunk.chunk_text,
                'chunk_type': chunk.chunk_type,
                'product_id': chunk.product_id,
                'document_id': chunk.document_id,
                'category_id': chunk.category_id,
                'position': chunk.position
            })

        # Generate embeddings
        embeddings = self.embedder.embed_passages(texts)

        # Normalize embeddings for cosine similarity
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True)
        embeddings = embeddings / norms

        # Save to disk
        self.save_index(embeddings, metadata)

        logger.info(f"Index built and saved for {len(chunks)} chunks")