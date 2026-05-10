"""Pydantic schemas for FAQ entries."""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


class FaqEntryCreate(BaseModel):
    question: str
    answer: str
    source_log_id: Optional[int] = None


class FaqEntryUpdate(BaseModel):
    question: Optional[str] = None
    answer: Optional[str] = None
    active: Optional[bool] = None


class FaqEntryItem(BaseModel):
    id: int
    question: str
    answer: str
    active: bool
    source_log_id: Optional[int] = None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class FaqEntryList(BaseModel):
    items: List[FaqEntryItem]
    total: int
