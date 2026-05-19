"""Pydantic schemas for Eval / Test Dataset endpoints."""

from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel


# ─────────────────────────────────────────────── dataset

class DatasetItem(BaseModel):
    id: int
    question: str
    category: str
    expected_type: str


class DatasetResponse(BaseModel):
    items: list[DatasetItem]
    total: int


# ─────────────────────────────────────────────── run

class RunSummary(BaseModel):
    """Lightweight run view used in /eval/runs and /progress."""
    id: int
    ran_at: Optional[str] = None
    status: str
    total: int
    completed: int
    note: Optional[str] = None
    dataset_name: Optional[str] = "synthetic"

    # Aggregates (only filled when status reaches completion or partial)
    avg_score: Optional[float] = None
    type_accuracy: Optional[float] = None
    error_count: Optional[int] = None
    error_rate: Optional[float] = None
    avg_latency_ms: Optional[int] = None
    avg_usefulness: Optional[float] = None  # LLM-judge 0-100, primary signal
    judged_count: Optional[int] = None
    quality_score: Optional[float] = None

    # Delta vs the previous run (only on /eval/runs list)
    delta_quality: Optional[float] = None
    delta_avg_score: Optional[float] = None
    delta_type_accuracy: Optional[float] = None
    previous_run_id: Optional[int] = None


class RunsListResponse(BaseModel):
    items: list[RunSummary]


class RunStartResponse(BaseModel):
    run_id: int


class EvalResultLite(BaseModel):
    """One question result without the heavy `answer` text."""
    id: int
    question_id: int
    question: str
    category: str
    expected_type: str
    actual_type: Optional[str] = None
    top_score: Optional[float] = None
    chunks_used: Optional[int] = None
    latency_ms: Optional[int] = None
    error: Optional[str] = None
    usefulness_score: Optional[int] = None
    usefulness_verdict: Optional[str] = None


class RunDetailResponse(RunSummary):
    """Run summary + full per-question results (without answer text)."""
    results: list[EvalResultLite]


class AnswerResponse(BaseModel):
    answer: Optional[str] = None
    error: Optional[str] = None


# ─────────────────────────────────────────────── compare

class CompareScore(BaseModel):
    score: Optional[float] = None
    type: Optional[str] = None
    latency_ms: Optional[int] = None


class CompareQuestion(BaseModel):
    id: int
    question: str
    category: str
    run_a: CompareScore
    run_b: CompareScore
    score_delta: Optional[float] = None
    type_changed: bool


class CompareSummary(BaseModel):
    avg_score_a: Optional[float] = None
    avg_score_b: Optional[float] = None
    quality_a: Optional[float] = None
    quality_b: Optional[float] = None
    quality_delta: Optional[float] = None
    improved: int
    degraded: int
    unchanged: int
    type_changes: int


class CompareResponse(BaseModel):
    run_a: RunSummary
    run_b: RunSummary
    questions: list[CompareQuestion]
    summary: CompareSummary
