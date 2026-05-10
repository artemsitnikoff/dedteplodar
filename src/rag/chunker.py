"""Text chunking module for RAG."""

import logging
from dataclasses import dataclass
from typing import Optional, List

from langchain_text_splitters import RecursiveCharacterTextSplitter
from transformers import AutoTokenizer

from src.products.models import Product, ProductParam, Category
from src.documents.models import Document

logger = logging.getLogger(__name__)


@dataclass
class ChunkData:
    """Data structure for chunk before saving to DB."""
    chunk_text: str
    contextualized_text: str
    chunk_type: str  # 'product' | 'pdf'
    product_id: Optional[int]
    document_id: Optional[int]
    category_id: Optional[int]
    position: int
    token_count: int


class TextChunker:
    """Text chunker using HuggingFace tokenizer for token counting."""

    def __init__(self, model_name: str, chunk_size_tokens: int, chunk_overlap_tokens: int):
        """Initialize chunker with tokenizer and parameters.

        Args:
            model_name: HuggingFace model name for tokenizer
            chunk_size_tokens: Maximum tokens per chunk
            chunk_overlap_tokens: Overlap between chunks in tokens
        """
        self.chunk_size_tokens = chunk_size_tokens
        self.chunk_overlap_tokens = chunk_overlap_tokens

        # Load tokenizer for token counting
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)

        # Initialize text splitter
        self.splitter = RecursiveCharacterTextSplitter.from_huggingface_tokenizer(
            tokenizer=self.tokenizer,
            chunk_size=chunk_size_tokens,
            chunk_overlap=chunk_overlap_tokens,
            separators=["\n\n\n", "\n\n", "\n", ". ", " ", ""]
        )

    def _count_tokens(self, text: str) -> int:
        """Count tokens in text."""
        return len(self.tokenizer.encode(text))

    def chunk_text(self, text: str) -> List[str]:
        """Split text into chunks using RecursiveCharacterTextSplitter.

        Args:
            text: Input text to chunk

        Returns:
            List of text chunks
        """
        if not text.strip():
            return []

        token_count = self._count_tokens(text)

        if token_count <= self.chunk_size_tokens:
            return [text]

        return self.splitter.split_text(text)

    def chunk_product(
        self,
        product: Product,
        params: List[ProductParam],
        category: Optional[Category]
    ) -> List[ChunkData]:
        """Chunk product data with structured header.

        Args:
            product: Product instance
            params: List of product parameters
            category: Product category

        Returns:
            List of ChunkData objects
        """
        # Build structured product text
        lines = [f"Товар: {product.name}"]

        if product.model:
            lines.append(f"Модель: {product.model}")

        if category:
            lines.append(f"Категория: {category.name}")

        if product.price:
            lines.append(f"Цена: {product.price} ₽")

        # Add parameters
        if params:
            lines.append("Параметры:")
            for param in params:
                lines.append(f"- {param.name}: {param.value}")

        # Add descriptions
        descriptions = []
        if product.description:
            descriptions.append(f"Описание: {product.description}")
        if product.scraped_full_description:
            descriptions.append(product.scraped_full_description)

        # Join structured header
        header = "\n".join(lines)
        body = "\n".join(descriptions) if descriptions else ""

        full_text = f"{header}\n{body}".strip()

        # Check if fits in one chunk
        if self._count_tokens(full_text) <= self.chunk_size_tokens:
            return [ChunkData(
                chunk_text=full_text,
                contextualized_text=full_text,  # For products, no additional prefix needed
                chunk_type="product",
                product_id=product.id,
                document_id=None,
                category_id=product.category_id,
                position=0,
                token_count=self._count_tokens(full_text)
            )]

        # Split into multiple chunks, ensuring header is in first chunk
        chunks = []

        # First chunk: header + as much body as fits
        header_tokens = self._count_tokens(header)
        remaining_tokens = self.chunk_size_tokens - header_tokens - 10  # buffer

        if remaining_tokens > 0 and body:
            # Try to fit some body in first chunk
            body_chunks = self.chunk_text(body)
            first_body = ""

            for body_chunk in body_chunks:
                test_text = f"{header}\n{first_body}\n{body_chunk}".strip()
                if self._count_tokens(test_text) <= self.chunk_size_tokens:
                    first_body = f"{first_body}\n{body_chunk}".strip() if first_body else body_chunk
                else:
                    break

            first_chunk_text = f"{header}\n{first_body}".strip() if first_body else header
            remaining_body = body[len(first_body):].strip() if first_body else body
        else:
            first_chunk_text = header
            remaining_body = body

        chunks.append(ChunkData(
            chunk_text=first_chunk_text,
            contextualized_text=first_chunk_text,
            chunk_type="product",
            product_id=product.id,
            document_id=None,
            category_id=product.category_id,
            position=0,
            token_count=self._count_tokens(first_chunk_text)
        ))

        # Additional chunks for remaining body
        if remaining_body:
            body_chunks = self.chunk_text(remaining_body)
            for i, chunk_text in enumerate(body_chunks, 1):
                chunks.append(ChunkData(
                    chunk_text=chunk_text,
                    contextualized_text=chunk_text,
                    chunk_type="product",
                    product_id=product.id,
                    document_id=None,
                    category_id=product.category_id,
                    position=i,
                    token_count=self._count_tokens(chunk_text)
                ))

        return chunks

    def chunk_document(
        self,
        doc: Document,
        product: Optional[Product] = None
    ) -> List[ChunkData]:
        """Chunk document text with context prefix.

        Args:
            doc: Document instance
            product: Optional product for context

        Returns:
            List of ChunkData objects
        """
        if not doc.full_text or not doc.full_text.strip():
            return []

        text_chunks = self.chunk_text(doc.full_text)
        chunks = []

        for i, chunk_text in enumerate(text_chunks):
            # Build context prefix
            if product:
                context_prefix = f"[Товар: {product.name} | Документ: {doc.title or 'Документ'}]"
            else:
                context_prefix = f"[Документ: {doc.title or 'Документ'}]"

            contextualized_text = f"{context_prefix} {chunk_text}"

            chunks.append(ChunkData(
                chunk_text=chunk_text,  # без префикса для отображения
                contextualized_text=contextualized_text,  # с префиксом для эмбеддинга
                chunk_type="pdf",
                product_id=doc.product_id,
                document_id=doc.id,
                category_id=None,  # Documents don't have direct category
                position=i,
                token_count=self._count_tokens(contextualized_text)
            ))

        return chunks