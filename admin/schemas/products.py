"""Pydantic schemas for products."""

from datetime import datetime
from decimal import Decimal
from typing import Optional, List
from pydantic import BaseModel, ConfigDict


class ProductParam(BaseModel):
    """Product parameter schema."""
    name: str
    value: str

    model_config = ConfigDict(from_attributes=True)


class ProductBase(BaseModel):
    """Base product schema."""
    name: str
    model: Optional[str] = None
    price: Optional[Decimal] = None
    url: str
    description: Optional[str] = None
    vendor: Optional[str] = None
    picture_url: Optional[str] = None


class ProductUpdate(BaseModel):
    """Schema for updating product."""
    name: Optional[str] = None
    description: Optional[str] = None
    price: Optional[Decimal] = None
    model: Optional[str] = None


class ProductListItem(BaseModel):
    """Product list item schema."""
    id: int
    name: str
    model: Optional[str] = None
    price: Optional[Decimal] = None
    category_id: Optional[int] = None
    category_name: Optional[str] = None
    chunks_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProductDetail(ProductBase):
    """Detailed product schema."""
    id: int
    category_id: Optional[int] = None
    category_name: Optional[str] = None
    params: List[ProductParam] = []
    chunks_count: int = 0
    documents_count: int = 0
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class ProductList(BaseModel):
    """Paginated product list response."""
    items: List[ProductListItem]
    total: int
    page: int
    per_page: int