"""Pydantic schemas for pipeline operations."""

from typing import List, Optional
from pydantic import BaseModel


class PipelineStats(BaseModel):
    """Database statistics."""
    products: int
    categories: int
    documents: int
    chunks: int
    index_versions: List[str]
    last_indexed: Optional[str] = None


class TaskStatus(BaseModel):
    """Background task status."""
    task_id: str
    status: str  # 'running', 'done', 'failed'
    returncode: Optional[int] = None
    stderr: Optional[str] = None


class TaskStartResponse(BaseModel):
    """Response when starting a background task."""
    task_id: str
    status: str


class FAQContent(BaseModel):
    """FAQ file content."""
    content: str