"""Pydantic schemas for query logs."""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


class QueryLogItem(BaseModel):
    id: int
    ts: datetime
    user_id: Optional[int] = None
    username: Optional[str] = None
    question: str
    answer: str
    query_type: str
    top_score: Optional[float] = None
    chunks_used: Optional[int] = None
    city: Optional[str] = None
    reformulated_query: Optional[str] = None
    feedback: Optional[str] = None
    feedback_note: Optional[str] = None

    model_config = {"from_attributes": True}


class QueryLogList(BaseModel):
    items: List[QueryLogItem]
    total: int
    page: int
    per_page: int
