"""Pydantic schemas for synonym dictionary."""
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class SynonymBase(BaseModel):
    term: str = Field(..., min_length=1, max_length=256)
    canonical: str = Field(..., min_length=1, max_length=256)
    category: str = Field("general", max_length=32)
    note: Optional[str] = None
    active: bool = True


class SynonymCreate(SynonymBase):
    pass


class SynonymUpdate(BaseModel):
    term: Optional[str] = Field(None, min_length=1, max_length=256)
    canonical: Optional[str] = Field(None, min_length=1, max_length=256)
    category: Optional[str] = Field(None, max_length=32)
    note: Optional[str] = None
    active: Optional[bool] = None


class SynonymOut(SynonymBase):
    id: int
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class SynonymList(BaseModel):
    items: list[SynonymOut]
    total: int
