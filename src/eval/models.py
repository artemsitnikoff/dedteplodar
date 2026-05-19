"""SQLAlchemy models for evaluation runs and results."""

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func, inspect, text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base, engine


class EvalRun(Base):
    """A single evaluation run over the preset dataset."""

    __tablename__ = "eval_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ran_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, server_default=func.now(), nullable=False, index=True
    )
    total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    dataset_name: Mapped[str] = mapped_column(String(32), nullable=False, default="synthetic")

    results: Mapped[list["EvalResult"]] = relationship(
        "EvalResult", back_populates="run", cascade="all, delete-orphan"
    )


class EvalResult(Base):
    """One question result within an evaluation run."""

    __tablename__ = "eval_results"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    run_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("eval_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    question_id: Mapped[int] = mapped_column(Integer, nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    expected_type: Mapped[str] = mapped_column(String(32), nullable=False)
    actual_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    top_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    chunks_used: Mapped[int | None] = mapped_column(Integer, nullable=True)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    # LLM judge — measures whether the bot's answer was actually useful to
    # the client (0-100). Independent of expected_type matching. See
    # src/eval/judge.py.
    usefulness_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    usefulness_verdict: Mapped[str | None] = mapped_column(Text, nullable=True)

    run: Mapped["EvalRun"] = relationship("EvalRun", back_populates="results")


# Create tables if they don't exist yet (safe to call multiple times)
Base.metadata.create_all(bind=engine, checkfirst=True)


# Idempotent migrations for legacy DBs.
def _ensure_migrations() -> None:
    try:
        insp = inspect(engine)

        # eval_runs.dataset_name
        if "eval_runs" in insp.get_table_names():
            cols = {c["name"] for c in insp.get_columns("eval_runs")}
            if "dataset_name" not in cols:
                with engine.begin() as conn:
                    conn.execute(text(
                        "ALTER TABLE eval_runs ADD COLUMN dataset_name VARCHAR(32) "
                        "NOT NULL DEFAULT 'synthetic'"
                    ))

        # eval_results.usefulness_*
        if "eval_results" in insp.get_table_names():
            cols = {c["name"] for c in insp.get_columns("eval_results")}
            with engine.begin() as conn:
                if "usefulness_score" not in cols:
                    conn.execute(text(
                        "ALTER TABLE eval_results ADD COLUMN usefulness_score INTEGER"
                    ))
                if "usefulness_verdict" not in cols:
                    conn.execute(text(
                        "ALTER TABLE eval_results ADD COLUMN usefulness_verdict TEXT"
                    ))
    except Exception:
        import logging
        logging.getLogger(__name__).exception("eval migrations failed")


_ensure_migrations()
