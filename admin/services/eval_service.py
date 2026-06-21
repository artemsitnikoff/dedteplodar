"""Core evaluation service with aggregation and background processing logic."""

import asyncio
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from sqlalchemy import case, func as sql_func, select
from sqlalchemy.orm import Session

from admin.eval_preset import EVAL_DATASET, get_dataset
from src.core.database import SessionLocal
from src.eval.models import EvalResult, EvalRun

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────── generator singleton

_generator = None
_generator_lock = None
_init_lock = threading.Lock()  # One-shot guard for asyncio.Lock creation

# Parallel Claude CLI subprocesses. On a small VPS each call pegs a core
# for ~15-30s, so 4 workers starve uvicorn. Default 2, bump via env if host
# has more cores to spare.
_EVAL_WORKERS = int(os.getenv("EVAL_WORKERS", "2"))


def _mark_run_failed(run_id: int, note: str | None = None) -> None:
    """Mark EvalRun as 'error' status (and optionally set a note). Best-effort —
    swallows DB errors and logs them, so callers can use it from non-critical paths."""
    try:
        with SessionLocal() as session:
            run = session.get(EvalRun, run_id)
            if run:
                run.status = "error"
                if note:
                    run.note = note
                session.commit()
    except Exception:
        logger.exception("[eval] failed to mark run=%s as error", run_id)


def _init_generator_sync():
    """Initialise E5Embedder + HybridRetriever + AnswerGenerator (blocking, run once)."""
    from src.core.config import settings
    from src.faq.matcher import FaqMatcher
    from src.rag.answer_generator import AnswerGenerator
    from src.rag.embedder import E5Embedder
    from src.rag.hybrid_retriever import HybridRetriever

    logger.info("[eval] Loading embedding model for eval runner…")
    embedder = E5Embedder(settings.embedding_model_name, device=settings.device)
    retriever = HybridRetriever(
        embedder=embedder,
        index_version=settings.index_version,
        data_dir="base",
        product_boost=settings.product_boost,
    )
    faq_matcher = FaqMatcher(
        embedder=embedder,
        cli_path=settings.claude_cli_path,
        llm_model=settings.claude_reformulation_model,
    )
    generator = AnswerGenerator(
        retriever=retriever,
        mode="cli",
        cli_path=settings.claude_cli_path,
        model=settings.claude_model,                              # final answer (Sonnet 4.6)
        reformulation_model=settings.claude_reformulation_model,
        faq_matcher=faq_matcher,
    )
    logger.info("[eval] Eval generator ready.")
    return generator


async def get_eval_generator():
    """Return the module-level generator singleton, initialising it on first call."""
    global _generator, _generator_lock
    if _generator is None:
        # Explicit thread-level protection for asyncio.Lock creation
        with _init_lock:
            if _generator_lock is None:
                _generator_lock = asyncio.Lock()
        async with _generator_lock:
            # Double-check inside the lock to avoid double-init
            if _generator is None:
                _generator = await asyncio.to_thread(_init_generator_sync)
    return _generator


def compute_aggregates_batch(db: Session, run_ids: list[int]) -> dict[int, dict[str, Any]]:
    """Compute aggregates for multiple runs in a single SQL query."""
    if not run_ids:
        return {}

    # Single GROUP BY query for all runs
    query = (
        select(
            EvalResult.run_id,
            sql_func.count().label('total'),
            sql_func.avg(EvalResult.top_score).label('avg_score'),
            sql_func.sum(
                case(
                    (EvalResult.actual_type == EvalResult.expected_type, 1),
                    else_=0
                )
            ).label('matched_count'),
            sql_func.sum(
                case(
                    (EvalResult.error.is_not(None), 1),
                    else_=0
                )
            ).label('error_count'),
            sql_func.avg(EvalResult.latency_ms).label('avg_latency_ms'),
            sql_func.min(EvalResult.top_score).label('min_score'),
            sql_func.max(EvalResult.top_score).label('max_score'),
            # LLM-judge usefulness: primary quality signal
            sql_func.avg(EvalResult.usefulness_score).label('avg_usefulness'),
            sql_func.count(EvalResult.usefulness_score).label('judged_count'),
        )
        .where(EvalResult.run_id.in_(run_ids))
        .group_by(EvalResult.run_id)
    )

    results = db.execute(query).all()

    # Process results into aggregates format
    aggregates = {}
    for row in results:
        total = row.total or 0
        avg_score = round(float(row.avg_score), 4) if row.avg_score is not None else None
        type_accuracy = round(float(row.matched_count) / total, 4) if total > 0 else None
        error_count = int(row.error_count) if row.error_count else 0
        error_rate = round(error_count / total, 4) if total > 0 else None
        avg_latency_ms = int(row.avg_latency_ms) if row.avg_latency_ms is not None else None
        avg_usefulness = round(float(row.avg_usefulness), 1) if row.avg_usefulness is not None else None
        judged_count = int(row.judged_count or 0)

        # quality_score — single source of truth.
        # Prefer LLM-judge (avg_usefulness) when we have enough samples;
        # fall back to the legacy composite for old runs without judging.
        # Require ≥10 judgments AND ≥50% coverage — avoids the metric
        # flipping back and forth between formulas on tiny runs.
        if avg_usefulness is not None and judged_count >= 10 and judged_count >= total // 2:
            quality = avg_usefulness  # already 0-100
        elif avg_score is not None and type_accuracy is not None:
            quality = 100 * (0.7 * avg_score + 0.3 * type_accuracy)
        elif avg_score is not None:
            quality = 100 * avg_score
        elif type_accuracy is not None:
            quality = 100 * type_accuracy
        else:
            quality = None

        aggregates[row.run_id] = {
            "avg_score": avg_score,
            "type_accuracy": type_accuracy,
            "error_count": error_count,
            "error_rate": error_rate,
            "avg_latency_ms": avg_latency_ms,
            "avg_usefulness": avg_usefulness,
            "judged_count": judged_count,
            "quality_score": round(quality, 1) if quality is not None else None,
        }

    # Fill missing run_ids with empty aggregates (run exists but no results yet)
    for run_id in run_ids:
        if run_id not in aggregates:
            aggregates[run_id] = {
                "avg_score": None,
                "type_accuracy": None,
                "error_count": 0,
                "error_rate": None,
                "avg_latency_ms": None,
                "avg_usefulness": None,
                "judged_count": 0,
                "quality_score": None,
            }

    return aggregates


def compute_delta_vs(cur: dict[str, Any], prev: dict[str, Any] | None, prev_id: int | None) -> dict[str, Any]:
    """Calculate delta metrics between current and previous run aggregates."""
    out: dict[str, Any] = {
        "delta_quality": None,
        "delta_avg_score": None,
        "delta_type_accuracy": None,
        "previous_run_id": prev_id,
    }
    if prev is None:
        return out
    for cur_key, delta_key in (
        ("quality_score", "delta_quality"),
        ("avg_score", "delta_avg_score"),
        ("type_accuracy", "delta_type_accuracy"),
    ):
        cv, pv = cur.get(cur_key), prev.get(cur_key)
        if cv is not None and pv is not None:
            out[delta_key] = round(cv - pv, 4)
    return out


def serialise_run(run: EvalRun, aggregates: dict[str, Any] | None = None) -> dict[str, Any]:
    """Serialize EvalRun to dict with optional aggregates."""
    base = {
        "id": run.id,
        "ran_at": run.ran_at.isoformat() if run.ran_at else None,
        "status": run.status,
        "total": run.total,
        "completed": run.completed,
        "note": run.note,
        # Without this the Pydantic RunSummary schema fills the field with
        # its own default ("synthetic"), so every run displayed in History
        # would look like a synthetic one regardless of what it actually ran.
        "dataset_name": getattr(run, "dataset_name", None) or "synthetic",
    }
    if aggregates is not None:
        base.update(aggregates)
    return base


def serialise_result_without_answer(r: EvalResult) -> dict[str, Any]:
    """Serialize result without the heavy answer field.

    DO NOT touch r.answer here — the SELECT defer()s it, so attribute
    access would trigger a per-row lazy-load (N+1). Frontend checks
    `result.answer` directly after on-demand fetch via /results/{qid}/answer.
    """
    return {
        "id": r.id,
        "question_id": r.question_id,
        "question": r.question,
        "category": r.category,
        "expected_type": r.expected_type,
        "actual_type": r.actual_type,
        "top_score": r.top_score,
        "chunks_used": r.chunks_used,
        "latency_ms": r.latency_ms,
        "error": r.error,
        "usefulness_score": r.usefulness_score,
        "usefulness_verdict": r.usefulness_verdict,
    }


def _eval_one(item: dict, run_id: int, generator, db_lock: threading.Lock) -> dict:
    """Process a single question. Each call runs in its own thread with its own DB session."""
    from src.core.config import settings
    from src.eval.judge import judge_answer

    t0 = time.monotonic()
    actual_type = top_score = chunks_used = answer = error = None

    with SessionLocal() as session:
        try:
            answer_text, meta = generator.answer_with_meta(session, item["question"])
            actual_type = meta.query_type
            top_score = meta.top_score
            chunks_used = meta.chunks_used
            answer = answer_text
        except Exception as exc:
            error = str(exc)[:1000]
            logger.error("[eval] run=%s q=%s failed: %s", run_id, item["id"], exc)

    latency_ms = int((time.monotonic() - t0) * 1000)

    # LLM-as-judge: scored usefulness of the answer (0-100) — single source
    # of truth for quality_score going forward. Skip if there's no answer
    # (the run errored out).
    usefulness_score = None
    usefulness_verdict = None
    if answer and not error:
        verdict = judge_answer(
            item["question"], answer,
            cli_path=settings.claude_cli_path,
            model=settings.claude_reformulation_model,  # Haiku — fast judge
        )
        if verdict:
            usefulness_score = verdict["score"]
            usefulness_verdict = verdict["verdict"]
            logger.info(
                "[eval] run=%s q=%s usefulness=%d (%s)",
                run_id, item["id"], usefulness_score, usefulness_verdict[:80],
            )

    result_row = EvalResult(
        run_id=run_id,
        question_id=item["id"],
        question=item["question"],
        category=item["category"],
        expected_type=item["expected_type"],
        actual_type=actual_type,
        top_score=top_score,
        chunks_used=chunks_used,
        answer=answer,
        latency_ms=latency_ms,
        error=error,
        usefulness_score=usefulness_score,
        usefulness_verdict=usefulness_verdict,
    )

    # Serialize DB writes — SQLite doesn't support concurrent writes
    with db_lock:
        with SessionLocal() as write_session:
            try:
                write_session.add(result_row)
                run = write_session.get(EvalRun, run_id)
                if run:
                    run.completed += 1
                write_session.commit()
            except Exception as exc:
                logger.error("[eval] DB write failed for q=%s: %s", item["id"], exc)
                write_session.rollback()

    logger.info("[eval] run=%s q=%s done in %dms", run_id, item["id"], latency_ms)
    return {"id": item["id"], "latency_ms": latency_ms, "error": error}


def run_eval_background(run_id: int, dataset_name: str = "synthetic") -> None:
    """Execute the chosen eval dataset with parallel workers; called via BackgroundTasks."""
    global _generator
    if _generator is None:
        logger.error(
            "[eval] run=%s started without initialised generator — aborting",
            run_id,
        )
        # Mark run as failed so the UI doesn't show it as running forever
        _mark_run_failed(run_id, note="Generator not initialised")
        return
    generator = _generator

    items = get_dataset(dataset_name)
    logger.info("[eval] run=%s starting on dataset=%s (%d items)", run_id, dataset_name, len(items))

    db_lock = threading.Lock()

    try:
        with ThreadPoolExecutor(max_workers=_EVAL_WORKERS) as pool:
            futures = {
                pool.submit(_eval_one, item, run_id, generator, db_lock): item
                for item in items
            }
            for fut in as_completed(futures):
                try:
                    fut.result()
                except Exception as exc:
                    item = futures[fut]
                    logger.error("[eval] unhandled error q=%s: %s", item["id"], exc)

        # Mark run done
        with db_lock:
            with SessionLocal() as session:
                run = session.get(EvalRun, run_id)
                if run:
                    run.status = "done"
                    session.commit()
        logger.info("[eval] run=%s done", run_id)

    except Exception as exc:
        logger.exception("[eval] run=%s crashed: %s", run_id, exc)
        _mark_run_failed(run_id, note=f"Crashed: {str(exc)[:200]}")
