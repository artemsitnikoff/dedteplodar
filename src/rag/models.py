"""SQLAlchemy models for RAG (chunks and embeddings)."""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, Integer, DateTime, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class Chunk(Base):
    """Text chunk model for RAG retrieval."""

    __tablename__ = "chunks"

    id: Mapped[int] = mapped_column(primary_key=True)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)  # текст для отображения
    contextualized_text: Mapped[str] = mapped_column(Text, nullable=False)  # текст с префиксом для эмбеддинга
    chunk_type: Mapped[str] = mapped_column(String(20), nullable=False)  # 'product' | 'pdf'
    product_id: Mapped[Optional[int]] = mapped_column(ForeignKey("products.id"), index=True, nullable=True)
    document_id: Mapped[Optional[int]] = mapped_column(ForeignKey("documents.id"), index=True, nullable=True)
    category_id: Mapped[Optional[int]] = mapped_column(ForeignKey("categories.id"), index=True, nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False)  # порядок чанка в документе
    token_count: Mapped[int] = mapped_column(Integer, nullable=False)
    index_version: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)