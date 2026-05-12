"""SQLAlchemy model for query logs."""

from datetime import datetime
from typing import Optional
from sqlalchemy import String, Text, Integer, Float, DateTime, Index, inspect, text
from sqlalchemy.orm import Mapped, mapped_column

from src.core.database import Base, engine


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
    feedback_note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)    # free-text reason on 👎: "что не так + что ожидали"
    bot_message_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)


# ── Idempotent migration: add feedback_note to legacy DBs ──────────────
# SQLAlchemy create_all() never alters existing tables. Run a one-shot
# ALTER on import so existing prod DBs pick up the new column.
def _ensure_feedback_note_column() -> None:
    try:
        insp = inspect(engine)
        if "query_logs" not in insp.get_table_names():
            return  # create_all() will build it fresh with the column
        cols = {c["name"] for c in insp.get_columns("query_logs")}
        if "feedback_note" not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE query_logs ADD COLUMN feedback_note TEXT"))
    except Exception:
        # Best-effort — don't crash the bot if migration fails on import
        import logging
        logging.getLogger(__name__).exception("feedback_note migration failed")


_ensure_feedback_note_column()
