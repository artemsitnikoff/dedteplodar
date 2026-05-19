"""Embedding module for RAG using E5 model."""

import logging
from collections import OrderedDict
from threading import Lock
from typing import List

import numpy as np
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

# LRU cache for single-query embeddings. Each entry ~3 KB (768 f32),
# 1k entries = ~3 MB. Repeated/similar queries pay 0 inference cost.
_QUERY_CACHE_MAX = 1000


class E5Embedder:
    """E5 multilingual embedder for text passages and queries."""

    def __init__(self, model_name: str, device: str = "cpu"):
        """Initialize embedder with E5 model.

        Args:
            model_name: HuggingFace model name (e.g., 'intfloat/multilingual-e5-base')
            device: Device to run model on ('cpu' or 'cuda')
        """
        self.model_name = model_name
        self.device = device

        logger.info(f"Loading embedding model: {model_name} on {device}")
        self.model = SentenceTransformer(model_name, device=device)
        logger.info("Embedding model loaded successfully")

        # Per-instance query cache. Keyed by raw query string (post-strip);
        # value is the L2-normalised (768,) f32 vector. Bounded LRU.
        self._query_cache: "OrderedDict[str, np.ndarray]" = OrderedDict()
        self._query_cache_lock = Lock()

    def embed_passages(self, texts: List[str], batch_size: int = 32) -> np.ndarray:
        """Embed texts as passages for indexing.

        Args:
            texts: List of texts to embed
            batch_size: Batch size for processing

        Returns:
            Normalized embedding matrix (N, embedding_dim)
        """
        if not texts:
            return np.array([]).reshape(0, self.model.get_sentence_embedding_dimension())

        # Add passage prefix as required by E5
        prefixed_texts = [f"passage: {text}" for text in texts]

        logger.info(f"Embedding {len(texts)} passages in batches of {batch_size}")

        embeddings = self.model.encode(
            prefixed_texts,
            batch_size=batch_size,
            show_progress_bar=True,  # passages = bulk indexing, progress is useful
            normalize_embeddings=True,  # L2 normalization is crucial
            convert_to_numpy=True
        )

        return embeddings.astype(np.float32)

    def embed_queries(self, texts: List[str], batch_size: int = 32) -> np.ndarray:
        """Embed texts as queries for search.

        Args:
            texts: List of query texts to embed
            batch_size: Batch size for processing

        Returns:
            Normalized embedding matrix (N, embedding_dim)
        """
        if not texts:
            return np.array([]).reshape(0, self.model.get_sentence_embedding_dimension())

        # Cache hot path: repeated/similar Telegram queries are common
        # ("гарантия", "цена доставки", same product names). On CPU each
        # E5 embed is 300-700 ms — cache turns it into a dict lookup.
        #
        # Normalise the cache key: lowercase + collapse internal whitespace
        # so "Гарантия ", "гарантия" and "ГАРАНТИЯ" share a slot. The raw
        # `texts[i]` is still what we feed to the model so case/spacing
        # nuances reach E5 untouched — only the LOOKUP is normalised.
        cache_keys = [" ".join(t.lower().split()) for t in texts]
        hits: dict[int, np.ndarray] = {}
        misses: list[tuple[int, str]] = []  # (original_index, raw_text)
        with self._query_cache_lock:
            for i, key in enumerate(cache_keys):
                vec = self._query_cache.get(key)
                if vec is not None:
                    self._query_cache.move_to_end(key)
                    hits[i] = vec
                else:
                    misses.append((i, texts[i]))

        if misses:
            prefixed = [f"query: {raw}" for _, raw in misses]
            computed = self.model.encode(
                prefixed,
                batch_size=batch_size,
                show_progress_bar=False,  # single-query path — tqdm is pure overhead
                normalize_embeddings=True,
                convert_to_numpy=True,
            ).astype(np.float32)
            with self._query_cache_lock:
                for (idx, _), vec in zip(misses, computed):
                    hits[idx] = vec
                    self._query_cache[cache_keys[idx]] = vec
                    self._query_cache.move_to_end(cache_keys[idx])
                while len(self._query_cache) > _QUERY_CACHE_MAX:
                    self._query_cache.popitem(last=False)

        if hits and len(misses) < len(texts):
            logger.debug(
                "[embed_queries] cache hit=%d miss=%d", len(texts) - len(misses), len(misses)
            )

        return np.stack([hits[i] for i in range(len(texts))])

    def get_embedding_dimension(self) -> int:
        """Get embedding dimension."""
        return self.model.get_sentence_embedding_dimension()