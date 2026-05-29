"""Read recent dialog turns for a user from query_logs.

The bot is otherwise stateless; this is the only thing that makes
multi-turn conversations possible. Stored data is the same as what we
already log on every Q&A — no new table, no new infra.
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta
from typing import TypedDict

from sqlalchemy import select, update

from src.core.database import SessionLocal
from src.logs.models import QueryLog

logger = logging.getLogger(__name__)


class DialogTurn(TypedDict):
    role: str       # "user" | "assistant"
    content: str
    ts: datetime


def get_recent_dialog(
    user_id: int,
    max_turns: int = 3,
    max_age_minutes: int = 30,
) -> list[DialogTurn]:
    """Return the last `max_turns` Q&A pairs for `user_id` within `max_age_minutes`.

    Output is ordered oldest → newest and flattened into alternating
    user / assistant turns so it can be dropped into an LLM prompt as is.

    Returns [] if no recent activity or user_id is falsy.
    """
    if not user_id or max_turns <= 0:
        return []

    cutoff = datetime.utcnow() - timedelta(minutes=max_age_minutes)

    with SessionLocal() as session:
        rows = session.execute(
            select(QueryLog.question, QueryLog.answer, QueryLog.ts)
            .where(QueryLog.user_id == user_id)
            .where(QueryLog.ts >= cutoff)
            .order_by(QueryLog.ts.desc())
            .limit(max_turns)
        ).all()

    turns: list[DialogTurn] = []
    for question, answer, ts in reversed(rows):  # oldest first
        if question:
            turns.append({"role": "user", "content": question, "ts": ts})
        if answer:
            turns.append({"role": "assistant", "content": answer, "ts": ts})
    return turns


def synthetic_user_id(session_id: str) -> int:
    """Stable negative int derived from a web-chat session id.

    Telegram user_ids are positive; web sessions are mapped into the
    negative space so the two never collide in `query_logs`. 60 bits of
    SHA-256 make collisions negligible at our scale, while a *stable* id
    per session lets the Journal group a web session's turns and resolve
    dialog context (`/journal/{id}/context`) exactly as for Telegram users.
    """
    h = int(hashlib.sha256(session_id.encode("utf-8")).hexdigest()[:15], 16)
    return -h


def save_query_log(
    *,
    question: str,
    answer: str,
    query_type: str,
    session_id: str | None = None,
    user_id: int | None = None,
    username: str | None = None,
    top_score: float | None = None,
    chunks_used: int | None = None,
    city: str | None = None,
    reformulated_query: str | None = None,
    bot_message_id: int | None = None,
) -> int | None:
    """Persist one Q&A turn to `query_logs`; return the row id (or None).

    For web chat pass `session_id`: `user_id` is derived from it (negative,
    see `synthetic_user_id`) and `username` defaults to ``"web:<short>"`` so
    the Journal can distinguish web turns from Telegram ones. Best-effort —
    swallows DB errors and logs them, mirroring the bot's own logger.
    """
    if user_id is None and session_id:
        user_id = synthetic_user_id(session_id)
        if username is None:
            username = f"web:{session_id[:8]}"
    try:
        with SessionLocal() as s:
            row = QueryLog(
                user_id=user_id,
                username=username or None,
                question=question,
                answer=answer,
                query_type=query_type,
                top_score=top_score,
                chunks_used=chunks_used or None,
                city=city or None,
                reformulated_query=reformulated_query or None,
                bot_message_id=bot_message_id,
            )
            s.add(row)
            s.commit()
            s.refresh(row)
            return row.id
    except Exception as e:
        logger.warning("save_query_log failed: %s", e)
        return None


def set_feedback(log_id: int | None, feedback: str, note: str | None = None) -> None:
    """Targeted UPDATE of the feedback columns for one `query_logs` row.

    Explicit UPDATE (not ORM load+flush) so a concurrent LLM-judge write to
    the `usefulness_*` columns of the same row isn't clobbered — same
    reasoning as the bot's `_judge_in_background`.
    """
    if log_id is None:
        return
    values: dict = {"feedback": feedback}
    if note is not None:
        values["feedback_note"] = note
    try:
        with SessionLocal() as s:
            s.execute(update(QueryLog).where(QueryLog.id == log_id).values(**values))
            s.commit()
    except Exception as e:
        logger.warning("set_feedback failed: %s", e)
