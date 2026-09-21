"""Background LLM-judge for answers already delivered to the user.

Shared by the web chat and the Bitrix24 channel (the Telegram bot has its
own copy in consultant.py with identical semantics). Bounded concurrency so
a traffic spike doesn't fan out into N parallel Claude CLI subprocesses.
"""
from __future__ import annotations

import asyncio
import logging

from sqlalchemy import update

from src.core.config import settings
from src.core.database import SessionLocal
from src.eval.judge import judge_answer
from src.logs.models import QueryLog

logger = logging.getLogger(__name__)

_judge_semaphore: asyncio.Semaphore | None = None
_background_tasks: set[asyncio.Task] = set()


def _get_judge_semaphore() -> asyncio.Semaphore:
    global _judge_semaphore
    if _judge_semaphore is None:  # lazily — no running loop at import time
        _judge_semaphore = asyncio.Semaphore(2)
    return _judge_semaphore


async def judge_in_background(log_id: int, question: str, answer: str, tag: str = "judge") -> None:
    """Score answer usefulness after the user already has it. Best-effort.

    Targeted UPDATE of only usefulness_* so a concurrent feedback write on
    the same row isn't clobbered (mirrors consultant._judge_in_background).
    """
    try:
        async with _get_judge_semaphore():
            verdict = await asyncio.to_thread(
                judge_answer, question, answer,
                settings.claude_cli_path,
                settings.claude_reformulation_model,  # Haiku — fast judge
            )
            if not verdict:
                return
            with SessionLocal() as s:
                s.execute(
                    update(QueryLog)
                    .where(QueryLog.id == log_id)
                    .values(
                        usefulness_score=verdict["score"],
                        usefulness_verdict=verdict["verdict"],
                    )
                )
                s.commit()
        logger.info("[%s] judge log=%s score=%d", tag, log_id, verdict["score"])
    except Exception as e:
        logger.warning("[%s] background judge failed for log=%s: %s", tag, log_id, e)


def spawn_judge(log_id: int, question: str, answer: str, tag: str = "judge") -> None:
    # Strong-ref the task so the GC doesn't drop it before completion.
    task = asyncio.create_task(judge_in_background(log_id, question, answer, tag))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)
