"""Web chat router — browser front-end for the RAG consultant.

Mirrors the Telegram bot's flow (`bot/routers/consultant.py`) but over HTTP
for experts who don't have Telegram. The heavy `AnswerGenerator` is the same
singleton the eval runner uses (`admin.services.eval_service.get_eval_generator`),
so this is a thin layer — no new model loading.

Endpoints:
  POST /chat/stream    – Server-Sent Events: phase updates while the pipeline
                         runs, then one `done` event with the full answer.
  POST /chat/feedback  – store 👍/👎 (+ free-text note) on a query_logs row.
"""
from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from sqlalchemy import update

from admin.schemas.chat import ChatFeedbackRequest, ChatRequest
from admin.services.eval_service import get_eval_generator
from src.core.config import settings
from src.core.database import SessionLocal
from src.eval.judge import judge_answer
from src.logs.models import QueryLog
from src.logs.queries import save_query_log, set_feedback

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["Chat"])

_FALLBACK_TEXT = (
    "Извините, не удалось получить ответ. Попробуйте ещё раз или позвоните нам: "
    "<b>8 800 775-03-07</b> (бесплатно, ежедневно 10:00–21:00 МСК)."
)

# Background LLM-judge — same bounded-concurrency pattern as the bot so a
# traffic spike doesn't fan out into N parallel Claude CLI subprocesses.
# Lazily inited (no running loop at import time).
_judge_semaphore: asyncio.Semaphore | None = None
_background_tasks: set[asyncio.Task] = set()


def _get_judge_semaphore() -> asyncio.Semaphore:
    global _judge_semaphore
    if _judge_semaphore is None:
        _judge_semaphore = asyncio.Semaphore(2)
    return _judge_semaphore


def _sse(obj: dict) -> str:
    """Frame a dict as one Server-Sent Event line."""
    return f"data: {json.dumps(obj, ensure_ascii=False)}\n\n"


def _meta_dict(meta) -> dict:
    """Serialise AnswerMeta fields the UI shows in its debug chip."""
    return {
        "query_type": meta.query_type,
        "top_score": meta.top_score,
        "chunks_used": meta.chunks_used,
        "city": meta.city,
        "reformulated_query": meta.reformulated_query,
        "t_intent_ms": meta.t_intent_ms,
        "t_retrieval_ms": meta.t_retrieval_ms,
        "t_answer_ms": meta.t_answer_ms,
        "t_answer_model": meta.t_answer_model,
        "latency_ms": meta.latency_ms,
    }


async def _judge_in_background(log_id: int, question: str, answer: str) -> None:
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
        logger.info("[chat] judge log=%s score=%d", log_id, verdict["score"])
    except Exception as e:
        logger.warning("[chat] background judge failed for log=%s: %s", log_id, e)


def _spawn_judge(log_id: int, question: str, answer: str) -> None:
    # Strong-ref the task so the GC doesn't drop it before completion.
    task = asyncio.create_task(_judge_in_background(log_id, question, answer))
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


@router.post("/stream")
async def chat_stream(req: ChatRequest):
    """Run the RAG pipeline and stream progress as SSE.

    Claude CLI (Pro) does not stream tokens, so instead of fake per-token
    deltas we emit coarse phase events ("intent" → "retrieval" → "answer")
    while the blocking pipeline runs in a worker thread, then one final
    `done` event carrying the full HTML answer + metadata + log_id.
    """
    message = req.message.strip()
    session_id = req.session_id
    history = [{"role": t.role, "content": t.content} for t in req.history]

    async def event_stream():
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def on_phase_threadsafe(phase: str) -> None:
            # Called from the worker thread — hop back onto the loop.
            loop.call_soon_threadsafe(
                queue.put_nowait, {"type": "phase", "phase": phase}
            )

        try:
            generator = await get_eval_generator()
        except Exception as e:
            logger.error("[chat] generator init failed: %s", e, exc_info=True)
            yield _sse({"type": "error", "message": _FALLBACK_TEXT})
            return

        def worker():
            # Blocking — runs off the event loop. Fresh DB session per call
            # (retrieval + product-URL enrichment need it).
            with SessionLocal() as session:
                return generator.answer_with_meta(
                    session, message,
                    history=history,
                    on_phase=on_phase_threadsafe,
                )

        gen_task = asyncio.create_task(asyncio.to_thread(worker))
        try:
            # Forward phase events until the worker finishes (and the queue
            # is drained), then collect the result.
            while not gen_task.done() or not queue.empty():
                try:
                    ev = await asyncio.wait_for(queue.get(), timeout=0.3)
                except asyncio.TimeoutError:
                    continue
                yield _sse(ev)
            answer, meta = await gen_task
        except Exception as e:
            logger.error("[chat] answer generation failed: %s", e, exc_info=True)
            if not gen_task.done():
                gen_task.cancel()
            yield _sse({"type": "error", "message": _FALLBACK_TEXT})
            return

        # Persist the turn so it shows up in the Journal (+ feeds history /
        # judge), exactly like a Telegram turn.
        log_id = save_query_log(
            question=message,
            answer=answer,
            query_type=meta.query_type,
            session_id=session_id,
            top_score=meta.top_score,
            chunks_used=meta.chunks_used,
            city=meta.city,
            reformulated_query=meta.reformulated_query,
        )

        if log_id and answer and meta.query_type != "ERROR":
            _spawn_judge(log_id, message, answer)

        yield _sse({
            "type": "done",
            "answer_html": answer,
            "log_id": log_id,
            "meta": _meta_dict(meta),
        })

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # Disable proxy buffering (nginx) so events flush immediately.
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/feedback")
async def chat_feedback(req: ChatFeedbackRequest):
    """Store 👍/👎 (+ optional note) against a query_logs row."""
    note = (req.note or "").strip()[:4000] or None
    await asyncio.to_thread(set_feedback, req.log_id, req.feedback, note)
    return {"ok": True}
