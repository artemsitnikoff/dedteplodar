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
from sqlalchemy.orm import Session

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

_EVAL_WORKERS = 4  # parallel Claude CLI subprocesses


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

def _compute_aggregates(db: Session, run_id: int) -> dict[str, Any]:
    """Compute per-run aggregates: avg_score, type_accuracy, errors, latency, composite quality.

    quality_score (0..100) = 70% retrieval quality (avg top_score) + 30% type-classification accuracy.
    Errors implicitly hurt avg_score (they have NULL score, excluded from mean).
    """
    rows = db.execute(
        select(EvalResult).where(EvalResult.run_id == run_id)
    ).scalars().all()

    if not rows:
        return {
            "avg_score": None,
            "type_accuracy": None,
            "error_count": 0,
            "error_rate": None,
            "avg_latency_ms": None,
            "quality_score": None,
        }

    total = len(rows)
    scored = [r.top_score for r in rows if r.top_score is not None]
    matched = sum(1 for r in rows if r.actual_type and r.actual_type == r.expected_type)
    errors = sum(1 for r in rows if r.error)
    latencies = [r.latency_ms for r in rows if r.latency_ms is not None]

    avg_score = round(sum(scored) / len(scored), 4) if scored else None
    type_accuracy = round(matched / total, 4) if total else None
    error_rate = round(errors / total, 4) if total else None
    avg_latency_ms = int(sum(latencies) / len(latencies)) if latencies else None

    if avg_score is not None and type_accuracy is not None:
        quality = 100 * (0.7 * avg_score + 0.3 * type_accuracy)
    elif avg_score is not None:
        quality = 100 * avg_score
    elif type_accuracy is not None:
        quality = 100 * type_accuracy
    else:
        quality = None

    return {
        "avg_score": avg_score,
        "type_accuracy": type_accuracy,
        "error_count": errors,
        "error_rate": error_rate,
        "avg_latency_ms": avg_latency_ms,
        "quality_score": round(quality, 1) if quality is not None else None,
    }


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
    aggregates_by_id: dict[int, dict[str, Any]] = {r.id: _compute_aggregates(db, r.id) for r in rows}

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


@router.get("/runs/{run_id}")
async def get_run(run_id: int, db: Session = Depends(get_db)):
    """Return a run with all its results, aggregates, and delta vs the immediately preceding run."""
    run = db.get(EvalRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    results = db.execute(
        select(EvalResult)
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

    cur_agg = _compute_aggregates(db, run_id)
    prev_agg = _compute_aggregates(db, prev_run.id) if prev_run else None
    aggregates = {**cur_agg, **_delta_vs(cur_agg, prev_agg, prev_run.id if prev_run else None)}

    return {
        **_serialise_run(run, aggregates=aggregates),
        "results": [_serialise_result(r) for r in results],
    }


@router.get("/runs/{run_id}/compare/{other_run_id}")
async def compare_runs(run_id: int, other_run_id: int, db: Session = Depends(get_db)):
    """Return a per-question comparison between two runs."""
    run_a = db.get(EvalRun, run_id)
    run_b = db.get(EvalRun, other_run_id)

    if run_a is None or run_b is None:
        raise HTTPException(status_code=404, detail="One or both runs not found")

    results_a = {
        r.question_id: r
        for r in db.execute(
            select(EvalResult).where(EvalResult.run_id == run_id)
        ).scalars().all()
    }
    results_b = {
        r.question_id: r
        for r in db.execute(
            select(EvalResult).where(EvalResult.run_id == other_run_id)
        ).scalars().all()
    }

    questions = []
    scores_a: list[float] = []
    scores_b: list[float] = []
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

        if score_a is not None:
            scores_a.append(score_a)
        if score_b is not None:
            scores_b.append(score_b)

        questions.append({
            "id": qid,
            "question": item["question"],
            "category": item["category"],
            "run_a": {"score": score_a, "type": type_a, "latency_ms": latency_a},
            "run_b": {"score": score_b, "type": type_b, "latency_ms": latency_b},
            "score_delta": score_delta,
            "type_changed": type_changed,
        })

    avg_a = round(sum(scores_a) / len(scores_a), 4) if scores_a else None
    avg_b = round(sum(scores_b) / len(scores_b), 4) if scores_b else None

    return {
        "run_a": _serialise_run(run_a),
        "run_b": _serialise_run(run_b),
        "questions": questions,
        "summary": {
            "avg_score_a": avg_a,
            "avg_score_b": avg_b,
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
