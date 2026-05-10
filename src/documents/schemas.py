"""Pydantic schemas for documents."""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, ConfigDict

from .models import DocumentType


class DocumentBase(BaseModel):
    """Base document schema."""
    product_id: Optional[int] = None
    doc_type: DocumentType
    source_url: str
    title: Optional[str] = None


class DocumentCreate(DocumentBase):
    """Schema for creating documents."""
    pass


class DocumentUpdate(BaseModel):
    """Schema for updating documents."""
    full_text: Optional[str] = None
    char_count: Optional[int] = None
    fetched_at: Optional[datetime] = None


class DocumentResponse(DocumentBase):
    """Schema for document response."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    full_text: Optional[str] = None
    char_count: Optional[int] = None
    fetched_at: Optional[datetime] = None
    created_at: datetime