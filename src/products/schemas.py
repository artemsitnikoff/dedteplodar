"""Pydantic schemas for YML parsing."""

from typing import Optional, List
from pydantic import BaseModel, ConfigDict


class YMLCategory(BaseModel):
    """Category from YML."""
    id: int
    name: str
    parent_id: Optional[int] = None


class YMLParam(BaseModel):
    """Product parameter from YML."""
    name: str
    value: str


class YMLOffer(BaseModel):
    """Offer from YML."""
    model_config = ConfigDict(from_attributes=True)

    id: int
    available: bool
    url: str
    price: Optional[float] = None
    currency_id: Optional[str] = None
    vendor: Optional[str] = None
    manufacturer_warranty: Optional[bool] = None
    country_of_origin: Optional[str] = None
    model: Optional[str] = None
    category_id: Optional[int] = None
    picture: Optional[str] = None
    name: str
    description: Optional[str] = None
    params: List[YMLParam] = []


class YMLCatalog(BaseModel):
    """Full YML catalog structure."""
    date: str
    shop_name: str
    categories: List[YMLCategory] = []
    offers: List[YMLOffer] = []