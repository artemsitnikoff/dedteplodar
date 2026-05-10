"""Pydantic schemas for categories."""

from typing import Optional, List
from pydantic import BaseModel, ConfigDict


class CategoryNode(BaseModel):
    """Category tree node schema."""
    id: int
    name: str
    parent_id: Optional[int] = None
    children: List["CategoryNode"] = []
    products_count: int = 0

    model_config = ConfigDict(from_attributes=True)


# Enable self-referencing for CategoryNode.children
CategoryNode.model_rebuild()