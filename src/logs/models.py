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
    # LLM-as-judge usefulness score (0-100), filled asynchronously after the
    # user already got the answer. NULL = not judged yet (or judge failed).
    usefulness_score: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    usefulness_verdict: Mapped[Optional[str]] = mapped_column(Text, nullable=True)


# ── Idempotent migrations for legacy DBs ──────────────
# SQLAlchemy create_all() never alters existing tables. Run one-shot
# ALTERs on import so existing prod DBs pick up new columns.
#
# Two processes (bot + admin) import this module concurrently — both may
# check `cols` before either ALTERs. One ALTER wins, the other gets
# "duplicate column name", which we treat as success.
def _safe_alter(conn, sql: str) -> None:
    try:
        conn.execute(text(sql))
    except Exception as e:
        msg = str(e).lower()
        if "duplicate column" in msg or "already exists" in msg:
            return  # another process won the race — that's fine
        raise


def _ensure_migrations() -> None:
    try:
        insp = inspect(engine)
        if "query_logs" not in insp.get_table_names():
            return
        cols = {c["name"] for c in insp.get_columns("query_logs")}
        with engine.begin() as conn:
            if "feedback_note" not in cols:
                _safe_alter(conn, "ALTER TABLE query_logs ADD COLUMN feedback_note TEXT")
            if "usefulness_score" not in cols:
                _safe_alter(conn, "ALTER TABLE query_logs ADD COLUMN usefulness_score INTEGER")
            if "usefulness_verdict" not in cols:
                _safe_alter(conn, "ALTER TABLE query_logs ADD COLUMN usefulness_verdict TEXT")
    except Exception:
        import logging
        logging.getLogger(__name__).exception("query_logs migrations failed")


_ensure_migrations()
