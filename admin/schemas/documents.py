"""Pydantic schemas for documents."""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict


class DocumentListItem(BaseModel):
    """Document list item schema."""
    id: int
    product_id: Optional[int] = None
    product_name: Optional[str] = None
    doc_type: str
    source_url: str
    title: Optional[str] = None
    char_count: Optional[int] = None
    text_source: Optional[str] = None  # 'pdf' | 'ocr' | None
    fetched_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DocumentDetail(BaseModel):
    """Detailed document schema."""
    id: int
    product_id: Optional[int] = None
    product_name: Optional[str] = None
    doc_type: str
    source_url: str
    title: Optional[str] = None
    full_text_preview: Optional[str] = None  # First 2000 chars
    char_count: Optional[int] = None
    fetched_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DocumentList(BaseModel):
    """Paginated document list response."""
    items: List[DocumentListItem]
    total: int
    page: int
    per_page: int


class DocumentUploadResponse(BaseModel):
    """Response after document upload."""
    id: int
    filename: str
    product_id: Optional[int] = None
    doc_type: str
    source_url: str