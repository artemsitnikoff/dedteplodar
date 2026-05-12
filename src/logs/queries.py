"""Read recent dialog turns for a user from query_logs.

The bot is otherwise stateless; this is the only thing that makes
multi-turn conversations possible. Stored data is the same as what we
already log on every Q&A — no new table, no new infra.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import TypedDict

from sqlalchemy import select

from src.core.database import SessionLocal
from src.logs.models import QueryLog


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
