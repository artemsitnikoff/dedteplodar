"""Pydantic schemas for chunks."""

from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, ConfigDict


class ChunkListItem(BaseModel):
    """Chunk list item schema."""
    id: int
    chunk_type: str
    chunk_text_preview: str  # First 100 chars
    product_id: Optional[int] = None
    product_name: Optional[str] = None
    token_count: int
    index_version: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ChunkDetail(BaseModel):
    """Detailed chunk schema."""
    id: int
    chunk_text: str
    contextualized_text: str
    chunk_type: str
    product_id: Optional[int] = None
    product_name: Optional[str] = None
    document_id: Optional[int] = None
    category_id: Optional[int] = None
    position: int
    token_count: int
    index_version: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ChunkList(BaseModel):
    """Paginated chunk list response."""
    items: List[ChunkListItem]
    total: int
    page: int
    per_page: int