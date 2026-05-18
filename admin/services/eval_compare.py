"""Evaluation comparison service for computing run deltas."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from admin.eval_preset import get_dataset
from admin.services.eval_service import compute_aggregates_batch, serialise_run
from src.eval.models import EvalResult, EvalRun


def compute_compare(db: Session, run_a: EvalRun, run_b: EvalRun) -> dict[str, Any]:
    """Compute comprehensive comparison between two evaluation runs.

    Returns a dict compatible with CompareResponse schema.
    """
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
            select(*cols).where(EvalResult.run_id == run_a.id)
        ).all()
    }
    results_b = {
        row.question_id: row
        for row in db.execute(
            select(*cols).where(EvalResult.run_id == run_b.id)
        ).all()
    }

    questions = []
    improved = 0
    degraded = 0
    unchanged = 0
    type_changes = 0

    # Use the dataset of run_a — if both runs share the same dataset (normal
    # case) this gives the right question metadata. Comparing across datasets
    # still works at the score-aggregate level but per-question rows will
    # naturally be sparse.
    dataset_items = get_dataset(getattr(run_a, "dataset_name", "synthetic"))
    for item in dataset_items:
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
    aggs = compute_aggregates_batch(db, [run_a.id, run_b.id])
    agg_a = aggs.get(run_a.id, {})
    agg_b = aggs.get(run_b.id, {})
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
        "run_a": serialise_run(run_a, aggregates=agg_a),
        "run_b": serialise_run(run_b, aggregates=agg_b),
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