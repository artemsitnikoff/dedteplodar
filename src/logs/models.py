"""SQLAlchemy model for query logs."""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, Integer, Float, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base


class QueryLog(Base):
    """Log of every bot query with answer and retrieval metadata."""

    __tablename__ = "query_logs"

    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, index=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    username: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    query_type: Mapped[str] = mapped_column(String(32), nullable=False)
    top_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    chunks_used: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    city: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    reformulated_query: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    feedback: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)  # good | bad | operator
    bot_message_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
