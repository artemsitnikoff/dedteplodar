"""SQLAlchemy models for documents."""

from datetime import datetime
from typing import Optional
from enum import Enum
from sqlalchemy import String, Text, Integer, DateTime, ForeignKey, Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


class DocumentType(str, Enum):
    """Document type enumeration."""
    PDF = "pdf"
    HTML = "html"


class Document(Base):
    """Document model for PDF instructions and HTML content."""

    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[Optional[int]] = mapped_column(ForeignKey("products.id"), nullable=True)
    doc_type: Mapped[DocumentType] = mapped_column(SQLEnum(DocumentType), nullable=False)
    source_url: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    full_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    char_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    text_source: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)  # 'pdf' | 'ocr'
    fetched_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Relationships
    product: Mapped[Optional["Product"]] = relationship("Product", back_populates="documents")


# Import Product here to resolve the relationship
from src.products.models import Product  # noqa: E402