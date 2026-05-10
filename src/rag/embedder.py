"""Embedding module for RAG using E5 model."""

import logging
from typing import List

import numpy as np
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)


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
            show_progress_bar=True,
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

        # Add query prefix as required by E5
        prefixed_texts = [f"query: {text}" for text in texts]

        logger.info(f"Embedding {len(texts)} queries")

        embeddings = self.model.encode(
            prefixed_texts,
            batch_size=batch_size,
            show_progress_bar=True,
            normalize_embeddings=True,  # L2 normalization is crucial
            convert_to_numpy=True
        )

        return embeddings.astype(np.float32)

    def get_embedding_dimension(self) -> int:
        """Get embedding dimension."""
        return self.model.get_sentence_embedding_dimension()