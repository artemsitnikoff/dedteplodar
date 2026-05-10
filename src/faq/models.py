"""SQLAlchemy model for FAQ entries."""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, Integer, Boolean, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class FaqEntry(Base):
    """Hand-curated FAQ entry with precomputed question embedding."""

    __tablename__ = "faq_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON float array
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    source_log_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
