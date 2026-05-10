"""SQLAlchemy models for products and categories."""

from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, Text, Numeric, Boolean, ForeignKey, DateTime, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from src.core.database import Base


class Category(Base):
    """Product category model."""

    __tablename__ = "categories"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    parent_id: Mapped[Optional[int]] = mapped_column(ForeignKey("categories.id"), nullable=True)

    # Relationships
    parent: Mapped[Optional["Category"]] = relationship("Category", remote_side=[id], back_populates="children")
    children: Mapped[List["Category"]] = relationship("Category", back_populates="parent")
    products: Mapped[List["Product"]] = relationship("Product", back_populates="category")


class Product(Base):
    """Product model based on Yandex YML offer structure."""

    __tablename__ = "products"

    # Core fields from YML
    id: Mapped[int] = mapped_column(primary_key=True)  # offer id from YML
    url: Mapped[str] = mapped_column(String(512), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    model: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    price: Mapped[Optional[float]] = mapped_column(Numeric(10, 2), nullable=True)
    currency: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    vendor: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    country_of_origin: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    manufacturer_warranty: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    category_id: Mapped[Optional[int]] = mapped_column(ForeignKey("categories.id"), nullable=True)
    picture_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Scraped data
    scraped_html: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    scraped_full_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    scraped_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    # Timestamps
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    category: Mapped[Optional["Category"]] = relationship("Category", back_populates="products")
    params: Mapped[List["ProductParam"]] = relationship("ProductParam", back_populates="product", cascade="all, delete-orphan")
    documents: Mapped[List["Document"]] = relationship("Document", back_populates="product")


class ProductParam(Base):
    """Product parameters from YML."""

    __tablename__ = "product_params"

    id: Mapped[int] = mapped_column(primary_key=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    value: Mapped[str] = mapped_column(String(512), nullable=False)

    # Relationships
    product: Mapped["Product"] = relationship("Product", back_populates="params")

    # Index for efficient lookups
    __table_args__ = (
        Index("idx_product_param", "product_id", "name"),
    )


# Import Document model here to avoid circular imports
from src.documents.models import Document  # noqa: E402