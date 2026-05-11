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

import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, defer

from admin.dependencies import get_db
from admin.eval_preset import EVAL_DATASET
from admin.schemas.eval import (
    AnswerResponse,
    CompareResponse,
    DatasetResponse,
    RunDetailResponse,
    RunStartResponse,
    RunSummary,
    RunsListResponse,
)
from admin.services.eval_compare import compute_compare
from admin.services.eval_service import (
    compute_aggregates_batch,
    compute_delta_vs,
    get_eval_generator,
    run_eval_background,
    serialise_result_without_answer,
    serialise_run,
)
from src.eval.models import EvalResult, EvalRun

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/eval", tags=["Eval"])


# ─────────────────────────────────────────────── endpoints

@router.get("/dataset", response_model=DatasetResponse)
async def get_dataset():
    """Return the full list of 50 preset questions (no DB access)."""
    return {"items": EVAL_DATASET, "total": len(EVAL_DATASET)}


@router.post("/run", status_code=202, response_model=RunStartResponse)
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
    background_tasks.add_task(run_eval_background, run_id)

    return {"run_id": run_id}


@router.get("/runs", response_model=RunsListResponse)
async def list_runs(db: Session = Depends(get_db)):
    """List all past eval runs, newest first, with aggregates and delta vs previous run."""
    rows = db.execute(
        select(EvalRun).order_by(EvalRun.ran_at.desc())
    ).scalars().all()

    # Batch compute aggregates for all runs in one query
    run_ids = [r.id for r in rows]
    aggregates_by_id = compute_aggregates_batch(db, run_ids)

    # rows are newest-first; previous (older) run is the next index in the list
    items = []
    for idx, run in enumerate(rows):
        agg = aggregates_by_id[run.id]
        prev = rows[idx + 1] if idx + 1 < len(rows) else None
        merged = {**agg, **compute_delta_vs(agg, aggregates_by_id.get(prev.id) if prev else None, prev.id if prev else None)}
        items.append(serialise_run(run, aggregates=merged))

    return {"items": items}


@router.get("/runs/{run_id}/progress", response_model=RunSummary)
async def get_run_progress(run_id: int, db: Session = Depends(get_db)):
    """Return lightweight run progress info (for frequent polling)."""
    run = db.get(EvalRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")

    # Compute aggregates for all non-running statuses (done, error).
    # Running runs have no meaningful averages yet, and we skip the SQL roundtrip during polling.
    aggregates = (
        compute_aggregates_batch(db, [run_id])[run_id]
        if run.status != "running"
        else None
    )

    return serialise_run(run, aggregates=aggregates)


@router.get("/runs/{run_id}", response_model=RunDetailResponse)
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

    aggregates_by_id = compute_aggregates_batch(db, run_ids_to_compute)
    cur_agg = aggregates_by_id[run_id]
    prev_agg = aggregates_by_id.get(prev_run.id) if prev_run else None
    aggregates = {**cur_agg, **compute_delta_vs(cur_agg, prev_agg, prev_run.id if prev_run else None)}

    return {
        **serialise_run(run, aggregates=aggregates),
        "results": [serialise_result_without_answer(r) for r in results],
    }


@router.get("/runs/{run_id}/results/{question_id}/answer", response_model=AnswerResponse)
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


@router.get("/runs/{run_id}/compare/{other_run_id}", response_model=CompareResponse)
async def compare_runs(run_id: int, other_run_id: int, db: Session = Depends(get_db)):
    """Return a per-question comparison between two runs."""
    run_a = db.get(EvalRun, run_id)
    run_b = db.get(EvalRun, other_run_id)

    if run_a is None or run_b is None:
        raise HTTPException(status_code=404, detail="One or both runs not found")

    return compute_compare(db, run_a, run_b)


@router.delete("/runs/{run_id}", status_code=204)
async def delete_run(run_id: int, db: Session = Depends(get_db)):
    """Delete a run and all its results (cascade)."""
    run = db.get(EvalRun, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    db.delete(run)
    db.commit()
