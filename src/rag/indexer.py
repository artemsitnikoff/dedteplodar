"""Index building module for RAG."""

import logging
import sqlite3
from typing import List, Iterator

import numpy as np
import sqlite_vec
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import select, delete, create_engine

from .chunker import TextChunker, ChunkData
from .embedder import E5Embedder
from src.rag.models import Chunk
from src.products.models import Product, ProductParam, Category
from src.documents.models import Document
from src.core.config import settings

logger = logging.getLogger(__name__)


def get_vec_connection():
    """Get a fresh connection with sqlite-vec extension loaded."""
    connection = sqlite3.connect(str(settings.database_path))
    connection.enable_load_extension(True)
    sqlite_vec.load(connection)
    connection.enable_load_extension(False)
    return connection


class IndexBuilder:
    """Builds RAG index by chunking and embedding all content."""

    def __init__(
        self,
        chunker: TextChunker,
        embedder: E5Embedder,
        index_version: str,
        batch_size: int = 32
    ):
        """Initialize index builder.

        Args:
            chunker: TextChunker instance
            embedder: E5Embedder instance
            index_version: Version string for this index
            batch_size: Batch size for embedding
        """
        self.chunker = chunker
        self.embedder = embedder
        self.index_version = index_version
        self.batch_size = batch_size

    def _init_vec_extension(self, session: Session) -> None:
        """Initialize sqlite-vec extension and create vector table."""
        connection = get_vec_connection()

        try:
            cursor = connection.cursor()

            # Drop existing table if it exists
            cursor.execute("DROP TABLE IF EXISTS chunks_vec")

            # Create vector table
            cursor.execute(f"""
                CREATE VIRTUAL TABLE chunks_vec
                USING vec0(embedding float[{self.embedder.get_embedding_dimension()}])
            """)
            connection.commit()
            cursor.close()

            logger.info("sqlite-vec extension initialized")
        except Exception as e:
            logger.error(f"Failed to initialize sqlite-vec: {e}")
            raise
        finally:
            connection.close()

    def _chunk_products(self, session: Session) -> Iterator[ChunkData]:
        """Generate chunks for all products.

        Args:
            session: Database session

        Yields:
            ChunkData objects for each product chunk
        """
        # Query all products with their params and categories
        stmt = (
            select(Product)
            .options(
                selectinload(Product.params),
                selectinload(Product.category)
            )
        )

        logger.info("Chunking products...")
        products = session.execute(stmt).scalars().all()

        total_chunks = 0
        for product in products:
            chunks = self.chunker.chunk_product(
                product=product,
                params=product.params,
                category=product.category
            )
            total_chunks += len(chunks)
            yield from chunks

        logger.info(f"Generated {total_chunks} product chunks from {len(products)} products")

    def _chunk_documents(self, session: Session) -> Iterator[ChunkData]:
        """Generate chunks for all documents with content.

        Args:
            session: Database session

        Yields:
            ChunkData objects for each document chunk
        """
        # Query documents with content and their associated products
        stmt = (
            select(Document)
            .where(
                Document.char_count > 0,
                Document.full_text.isnot(None)
            )
            .options(selectinload(Document.product))
        )

        logger.info("Chunking documents...")
        documents = session.execute(stmt).scalars().all()

        total_chunks = 0
        for doc in documents:
            chunks = self.chunker.chunk_document(
                doc=doc,
                product=doc.product
            )
            total_chunks += len(chunks)
            yield from chunks

        logger.info(f"Generated {total_chunks} document chunks from {len(documents)} documents")

    def _save_chunks_batch(self, session: Session, chunks: List[ChunkData]) -> List[int]:
        """Save a batch of chunks to database.

        Args:
            session: Database session
            chunks: List of ChunkData to save

        Returns:
            List of assigned chunk IDs
        """
        chunk_models = []
        for chunk_data in chunks:
            chunk_model = Chunk(
                chunk_text=chunk_data.chunk_text,
                contextualized_text=chunk_data.contextualized_text,
                chunk_type=chunk_data.chunk_type,
                product_id=chunk_data.product_id,
                document_id=chunk_data.document_id,
                category_id=chunk_data.category_id,
                position=chunk_data.position,
                token_count=chunk_data.token_count,
                index_version=self.index_version
            )
            chunk_models.append(chunk_model)

        session.add_all(chunk_models)
        session.flush()  # Get IDs without committing

        return [chunk.id for chunk in chunk_models]

    def _save_embeddings_batch(
        self,
        session: Session,
        chunk_ids: List[int],
        embeddings: np.ndarray
    ) -> None:
        """Save embeddings to vector table.

        Args:
            session: Database session
            chunk_ids: List of chunk IDs
            embeddings: Embedding matrix
        """
        connection = get_vec_connection()

        try:
            cursor = connection.cursor()

            # Insert embeddings
            for chunk_id, embedding in zip(chunk_ids, embeddings):
                cursor.execute(
                    "INSERT INTO chunks_vec(rowid, embedding) VALUES (?, ?)",
                    (chunk_id, embedding.tobytes())
                )

            connection.commit()
            cursor.close()
        except Exception as e:
            logger.error(f"Failed to save embeddings batch: {e}")
            connection.rollback()
            raise
        finally:
            connection.close()

    def build_full_index(self, session: Session, rebuild: bool = False) -> None:
        """Build complete RAG index.

        Args:
            session: Database session
            rebuild: If True, delete existing chunks for this version first
        """
        logger.info(f"Building RAG index version: {self.index_version}")

        # Initialize vector extension
        self._init_vec_extension(session)

        # Clean up existing chunks if rebuild
        if rebuild:
            logger.info("Cleaning up existing chunks...")
            delete_stmt = delete(Chunk).where(Chunk.index_version == self.index_version)
            result = session.execute(delete_stmt)
            logger.info(f"Deleted {result.rowcount} existing chunks")

            # Clean up orphaned vectors
            connection = get_vec_connection()
            try:
                cursor = connection.cursor()
                cursor.execute("DELETE FROM chunks_vec WHERE rowid NOT IN (SELECT id FROM chunks)")
                connection.commit()
                cursor.close()
            finally:
                connection.close()

            session.commit()

        # Collect all chunks
        all_chunks = []

        # Add product chunks
        all_chunks.extend(list(self._chunk_products(session)))

        # Add document chunks
        all_chunks.extend(list(self._chunk_documents(session)))

        if not all_chunks:
            logger.warning("No chunks generated!")
            return

        logger.info(f"Processing {len(all_chunks)} total chunks in batches of {self.batch_size}")

        # Process in batches
        total_saved = 0
        for i in range(0, len(all_chunks), self.batch_size):
            batch = all_chunks[i:i + self.batch_size]
            logger.info(f"Processing batch {i // self.batch_size + 1}/{(len(all_chunks) - 1) // self.batch_size + 1}")

            # Extract contextualized text for embedding
            texts_to_embed = [chunk.contextualized_text for chunk in batch]

            # Generate embeddings
            embeddings = self.embedder.embed_passages(texts_to_embed, batch_size=len(batch))

            # Save chunks to database
            chunk_ids = self._save_chunks_batch(session, batch)

            # Save embeddings to vector table
            self._save_embeddings_batch(session, chunk_ids, embeddings)

            session.commit()
            total_saved += len(batch)

            logger.info(f"Saved {len(batch)} chunks (total: {total_saved}/{len(all_chunks)})")

        # Final statistics
        product_count = sum(1 for chunk in all_chunks if chunk.chunk_type == "product")
        pdf_count = sum(1 for chunk in all_chunks if chunk.chunk_type == "pdf")

        logger.info("Index building completed!")
        logger.info(f"Statistics:")
        logger.info(f"  - Total chunks: {len(all_chunks)}")
        logger.info(f"  - Product chunks: {product_count}")
        logger.info(f"  - PDF chunks: {pdf_count}")
        logger.info(f"  - Index version: {self.index_version}")
        logger.info(f"  - Embedding dimension: {self.embedder.get_embedding_dimension()}")