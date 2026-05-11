"""Eval / Test Dataset router.

Endpoints:
  GET  /eval/dataset              – list all preset questions
  POST /eval/run                  – start a background evaluation run
  GET  /eval/runs                 – list past runs
  GET  /eval/runs/{run_id}        – run detail with all results
  GET  /eval/runs/{run_id}/compare/{other_run_id}  – comparison delta
  DELETE /eval/runs/{run_id}      – delete run + results
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, defer

from admin.dependencies import get_db
from admin.eval_preset import EVAL_DATASET
from src.core.database import SessionLocal
from src.eval.models import EvalResult, EvalRun

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/eval", tags=["Eval"])

# ─────────────────────────────────────────────── generator singleton

_generator = None
_generator_lock = asyncio.Lock()


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
    faq_matcher = FaqMatcher(embedder=embedder)
    generator = AnswerGenerator(
        retriever=retriever,
        mode="cli",
        cli_path=settings.claude_cli_path,
        reformulation_model=settings.claude_reformulation_model,
        faq_matcher=faq_matcher,
    )
    logger.info("[eval] Eval generator ready.")
    return generator


async def get_eval_generator():
    """Return the module-level generator singleton, initialising it on first call."""
    global _generator
    if _generator is None:
        async with _generator_lock:
            # Double-check inside the lock to avoid double-init
            if _generator is None:
                _generator = await asyncio.to_thread(_init_generator_sync)
    return _generator


# ─────────────────────────────────────────────── background task

import os as _os

# Parallel Claude CLI subprocesses. Default lowered to 2 — a full Claude CLI
# call pegs a CPU core, so on small VPS 4 workers starve the HTTP server.
# Bump via EVAL_WORKERS env on a beefier host.
_EVAL_WORKERS = int(_os.getenv("EVAL_WORKERS", "2"))


def _eval_one(item: dict, run_id: int, generator, db_lock: threading.Lock) -> dict:
    """Process a single question. Each call runs in its own thread with its own DB session."""
    t0 = time.monotonic()
    actual_type = top_score = chunks_used = answer = error = None

    session = SessionLocal()
    try:
        answer_text, meta = generator.answer_with_meta(session, item["question"])
        actual_type = meta.query_type
        top_score = meta.top_score
        chunks_used = meta.chunks_used
        answer = answer_text
    except Exception as exc:
        error = str(exc)[:1000]
        logger.error("[eval] run=%s q=%s failed: %s", run_id, item["id"], exc)
    finally:
        session.close()

    latency_ms = int((time.monotonic() - t0) * 1000)

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
    )

    # Serialize DB writes — SQLite doesn't support concurrent writes
    with db_lock:
        write_session = SessionLocal()
        try:
            write_session.add(result_row)
            run = write_session.get(EvalRun, run_id)
            if run:
                run.completed += 1
            write_session.commit()
        except Exception as exc:
            logger.error("[eval] DB write failed for q=%s: %s", item["id"], exc)
            write_session.rollback()
        finally:
            write_session.close()

    logger.info("[eval] run=%s q=%s done in %dms", run_id, item["id"], latency_ms)
    return {"id": item["id"], "latency_ms": latency_ms, "error": error}


def _run_eval_background(run_id: int) -> None:
    """Execute the full eval dataset with parallel workers; called via BackgroundTasks."""
    global _generator
    if _generator is None:
        _generator = _init_generator_sync()
    generator = _generator

    db_lock = threading.Lock()

    try:
        with ThreadPoolExecutor(max_workers=_EVAL_WORKERS) as pool:
            futures = {
                pool.submit(_eval_one, item, run_id, generator, db_lock): item
                for item in EVAL_DATASET
            }
            for fut in as_completed(futures):
                try:
                    fut.result()
                except Exception as exc:
                    item = futures[fut]
                    logger.error("[eval] unhandled error q=%s: %s", item["id"], exc)

        # Mark run done
        with db_lock:
            session = SessionLocal()
            try:
                run = session.get(EvalRun, run_id)
                if run:
                    run.status = "done"
                    session.commit()
                logger.info("[eval] run=%s finished", run_id)
            finally:
                session.close()

    except Exception as exc:
        logger.exception("[eval] run=%s crashed: %s", run_id, exc)
        session = SessionLocal()
        try:
            run = session.get(EvalRun, run_id)
            if run:
                run.status = "error"
                session.commit()
        except Exception:
            pass
        finally:
            session.close()


# ─────────────────────────────────────────────── helper serialisers

def _compute_aggregates_batch(db: Session, run_ids: list[int]) -> dict[int, dict[str, Any]]:
    """Compute aggregates for multiple runs in a single SQL query."""
    if not run_ids:
        return {}

    from sqlalchemy import case, func as sql_func

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
            sql_func.max(EvalResult.top_score).label('max_score')
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

        # Calculate quality score
        if avg_score is not None and type_accuracy is not None:
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
            "quality_score": round(quality, 1) if quality is not None else None,
        }

    # Fill missing run_ids with empty aggregates
    for run_id in run_ids:
        if run_id not in aggregates:
            aggregates[run_id] = {
                "avg_score": None,
                "type_accuracy": None,
                "error_count": 0,
                "error_rate": None,
                "avg_latency_ms": None,
                "quality_score": None,
            }

    return aggregates


def _compute_aggregates(db: Session, run_id: int) -> dict[str, Any]:
    """Compute per-run aggregates: avg_score, type_accuracy, errors, latency, composite quality.

    Legacy wrapper for backward compatibility.
    """
    batch_result = _compute_aggregates_batch(db, [run_id])
    return batch_result.get(run_id, {
        "avg_score": None,
        "type_accuracy": None,
        "error_count": 0,
        "error_rate": None,
        "avg_latency_ms": None,
        "quality_score": None,
    })


def _serialise_run(run: EvalRun, aggregates: dict[str, Any] | None = None) -> dict[str, Any]:
    base = {
        "id": run.id,
        "ran_at": run.ran_at.isoformat() if run.ran_at else None,
        "status": run.status,
        "total": run.total,
        "completed": run.completed,
        "note": run.note,
    }
    if aggregates is not None:
        base.update(aggregates)
    return base


def _serialise_result(r: EvalResult) -> dict[str, Any]:
    return {
        "id": r.id,
        "question_id": r.question_id,
        "question": r.question,
        "category": r.category,
        "expected_type": r.expected_type,
        "actual_type": r.actual_type,
        "top_score": r.top_score,
        "chunks_used": r.chunks_used,
        "answer": r.answer,
        "latency_ms": r.latency_ms,
        "error": r.error,
    }


def _serialise_result_without_answer(r: EvalResult) -> dict[str, Any]:
    """Serialize result without the heavy answer field."""
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
        "has_answer": r.answer is not None,
    }


# ─────────────────────────────────────────────── endpoints

@router.get("/dataset")
async def get_dataset():
    """Return the full list of 50 preset questions (no DB access)."""
    return {"items": EVAL_DATASET, "total": len(EVAL_DATASET)}


@router.post("/run", status_code=202)
async def start_run(
    background_tasks: BackgroundTasks,
    note: str | None = None,
    db: Session = Depends(get_db),
):
    """Create a new eval run and schedule it as a background task."""
    # Ensure the generator is ready before handing off to background
    await get_eval_generator()

    run = EvalRun(
        total=len(EVAL_DATASET),
        completed=0,
        status="running",
        note=note,
    )
    db.add(run)
    db.commit()
    db.refresh(run)

    run_id = run.id
    background_tasks.add_task(_run_eval_background, run_id)

    return {"run_id": run_id}


@router.get("/runs")
async def list_runs(db: Session = Depends(get_db)):
    """List all past eval runs, newest first, with aggregates and delta vs previous run."""
    rows = db.execute(
        select(EvalRun).order_by(EvalRun.ran_at.desc())
    ).scalars().all()

    items: list[dict[str, Any]] = []

    # Batch compute aggregates for all runs in one query
    run_ids = [r.id for r in rows]
    aggregates_by_id = _compute_aggregates_batch(db, run_ids)

    # rows are newest-first; previous (older) run is the next index in the list
    for idx, run in enumerate(rows):
        agg = aggregates_by_id[run.id]
        prev = rows[idx + 1] if idx + 1 < len(rows) else None
        merged = {**agg, **_delta_vs(agg, aggregates_by_id.get(prev.id) if prev else None, prev.id if prev else None)}
        items.append(_serialise_run(run, aggregates=merged))

    return {"items": items}


def _delta_vs(cur: dict[str, Any], prev: dict[str, Any] | None, prev_id: int | None) -> dict[str, Any]:
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


@router.get("/runs/{run_id}/progress")
async def get_run_progress(run_id: int, db: Session = Depends(get_db)):
    """Return lightweight run progress info (for frequent polling)."""
    run = db.get(EvalRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    # Only compute aggregates if run is completed
    aggregates = {}
    if run.status == "done":
        aggregates = _compute_aggregates(db, run_id)

    return {
        **_serialise_run(run, aggregates=aggregates if aggregates else None),
    }


@router.get("/runs/{run_id}")
async def get_run(run_id: int, db: Session = Depends(get_db)):
    """Return a run with all its results (without answer text), aggregates, and delta vs the immediately preceding run."""
    run = db.get(EvalRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    # Don't load EvalResult.answer (heavy Text column) — this endpoint never
    # surfaces it; full answers come from /results/{qid}/answer on demand.
    results = db.execute(
        select(EvalResult)
        .options(defer(EvalResult.answer))
        .where(EvalResult.run_id == run_id)
        .order_by(EvalResult.question_id)
    ).scalars().all()

    # Find immediately preceding run (older, by ran_at)
    prev_run = db.execute(
        select(EvalRun)
        .where(EvalRun.ran_at < run.ran_at)
        .order_by(EvalRun.ran_at.desc())
        .limit(1)
    ).scalar_one_or_none()

    # Batch compute aggregates for both current and previous runs
    run_ids_to_compute = [run_id]
    if prev_run:
        run_ids_to_compute.append(prev_run.id)

    aggregates_by_id = _compute_aggregates_batch(db, run_ids_to_compute)
    cur_agg = aggregates_by_id[run_id]
    prev_agg = aggregates_by_id.get(prev_run.id) if prev_run else None
    aggregates = {**cur_agg, **_delta_vs(cur_agg, prev_agg, prev_run.id if prev_run else None)}

    return {
        **_serialise_run(run, aggregates=aggregates),
        "results": [_serialise_result_without_answer(r) for r in results],
    }


@router.get("/runs/{run_id}/results/{question_id}/answer")
async def get_result_answer(run_id: int, question_id: int, db: Session = Depends(get_db)):
    """Return answer text for a specific question result."""
    result = db.execute(
        select(EvalResult)
        .where(EvalResult.run_id == run_id)
        .where(EvalResult.question_id == question_id)
    ).scalar_one_or_none()

    if result is None:
        raise HTTPException(status_code=404, detail="Result not found")

    return {
        "answer": result.answer,
        "error": result.error,
    }


@router.get("/runs/{run_id}/compare/{other_run_id}")
async def compare_runs(run_id: int, other_run_id: int, db: Session = Depends(get_db)):
    """Return a per-question comparison between two runs."""
    run_a = db.get(EvalRun, run_id)
    run_b = db.get(EvalRun, other_run_id)

    if run_a is None or run_b is None:
        raise HTTPException(status_code=404, detail="One or both runs not found")

    # Per-question diff data — load only the columns we actually compare.
    # Skip heavy EvalResult.answer (Text) — we never surface it from this endpoint.
    cols = (
        EvalResult.question_id,
        EvalResult.top_score,
        EvalResult.actual_type,
        EvalResult.latency_ms,
    )
    results_a = {
        row.question_id: row
        for row in db.execute(
            select(*cols).where(EvalResult.run_id == run_id)
        ).all()
    }
    results_b = {
        row.question_id: row
        for row in db.execute(
            select(*cols).where(EvalResult.run_id == other_run_id)
        ).all()
    }

    questions = []
    improved = 0
    degraded = 0
    unchanged = 0
    type_changes = 0

    for item in EVAL_DATASET:
        qid = item["id"]
        ra = results_a.get(qid)
        rb = results_b.get(qid)

        score_a = ra.top_score if ra else None
        score_b = rb.top_score if rb else None
        type_a = ra.actual_type if ra else None
        type_b = rb.actual_type if rb else None
        latency_a = ra.latency_ms if ra else None
        latency_b = rb.latency_ms if rb else None

        score_delta = None
        if score_a is not None and score_b is not None:
            score_delta = round(score_b - score_a, 4)
            if score_delta > 0.001:
                improved += 1
            elif score_delta < -0.001:
                degraded += 1
            else:
                unchanged += 1
        else:
            unchanged += 1

        type_changed = (type_a != type_b)
        if type_changed:
            type_changes += 1

        questions.append({
            "id": qid,
            "question": item["question"],
            "category": item["category"],
            "run_a": {"score": score_a, "type": type_a, "latency_ms": latency_a},
            "run_b": {"score": score_b, "type": type_b, "latency_ms": latency_b},
            "score_delta": score_delta,
            "type_changed": type_changed,
        })

    # avg_score / quality come from the single GROUP-BY aggregate — no second pass
    aggs = _compute_aggregates_batch(db, [run_id, other_run_id])
    agg_a = aggs.get(run_id, {})
    agg_b = aggs.get(other_run_id, {})
    avg_a = agg_a.get("avg_score")
    avg_b = agg_b.get("avg_score")
    quality_a = agg_a.get("quality_score")
    quality_b = agg_b.get("quality_score")
    quality_delta = (
        round(quality_b - quality_a, 1)
        if quality_a is not None and quality_b is not None
        else None
    )

    return {
        "run_a": _serialise_run(run_a, aggregates=agg_a),
        "run_b": _serialise_run(run_b, aggregates=agg_b),
        "questions": questions,
        "summary": {
            "avg_score_a": avg_a,
            "avg_score_b": avg_b,
            "quality_a": quality_a,
            "quality_b": quality_b,
            "quality_delta": quality_delta,
            "improved": improved,
            "degraded": degraded,
            "unchanged": unchanged,
            "type_changes": type_changes,
        },
    }


@router.delete("/runs/{run_id}", status_code=204)
async def delete_run(run_id: int, db: Session = Depends(get_db)):
    """Delete a run and all its results (cascade)."""
    run = db.get(EvalRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    db.delete(run)
    db.commit()
