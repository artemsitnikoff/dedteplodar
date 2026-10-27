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


class CatalogSyncState(BaseModel):
    """Last catalog sync (base/catalog_sync_state.json) + whether one can be started."""
    configured: bool                 # YANDEX_YML_URL is set
    source: Optional[str] = None     # the feed URL (host only is enough for the UI)
    running: bool = False
    last: Optional[dict] = None      # SyncReport.to_dict() of the last run
    history: List[dict] = []


class FAQContent(BaseModel):
    """FAQ file content."""
    content: str