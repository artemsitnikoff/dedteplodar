"""Chunks API router."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import func, select

from src.rag.models import Chunk
from src.products.models import Product
from admin.dependencies import get_db
from admin.schemas.chunks import ChunkList, ChunkListItem, ChunkDetail

router = APIRouter(prefix="/chunks", tags=["Chunks"])


@router.get("", response_model=ChunkList)
async def list_chunks(
    chunk_type: Optional[str] = Query(None),
    product_id: Optional[int] = Query(None),
    index_version: Optional[str] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """List chunks with filtering and pagination."""
    # Build base query
    query = select(Chunk)

    # Apply filters
    if chunk_type:
        query = query.where(Chunk.chunk_type == chunk_type)

    if product_id:
        query = query.where(Chunk.product_id == product_id)

    if index_version:
        query = query.where(Chunk.index_version == index_version)

    if search:
        query = query.where(
            Chunk.chunk_text.contains(search) | Chunk.contextualized_text.contains(search)
        )

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = db.execute(count_query).scalar()

    # Apply pagination and order by created_at desc
    offset = (page - 1) * per_page
    query = query.order_by(Chunk.created_at.desc()).offset(offset).limit(per_page)

    chunks = db.execute(query).scalars().all()

    # Get product names for chunks that have product_id
    product_ids = [c.product_id for c in chunks if c.product_id]
    product_names = {}
    if product_ids:
        products = db.execute(
            select(Product.id, Product.name).where(Product.id.in_(product_ids))
        ).all()
        product_names = {pid: name for pid, name in products}

    items = []
    for chunk in chunks:
        items.append(ChunkListItem(
            id=chunk.id,
            chunk_type=chunk.chunk_type,
            chunk_text_preview=chunk.chunk_text[:100],
            product_id=chunk.product_id,
            product_name=product_names.get(chunk.product_id),
            token_count=chunk.token_count,
            index_version=chunk.index_version,
            created_at=chunk.created_at,
        ))

    return ChunkList(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/{chunk_id}", response_model=ChunkDetail)
async def get_chunk(chunk_id: int, db: Session = Depends(get_db)):
    """Get chunk details with full text."""
    chunk = db.execute(
        select(Chunk).where(Chunk.id == chunk_id)
    ).scalar_one_or_none()

    if not chunk:
        raise HTTPException(status_code=404, detail="Chunk not found")

    # Get product name if chunk has product_id
    product_name = None
    if chunk.product_id:
        product = db.execute(
            select(Product).where(Product.id == chunk.product_id)
        ).scalar_one_or_none()
        if product:
            product_name = product.name

    return ChunkDetail(
        id=chunk.id,
        chunk_text=chunk.chunk_text,
        contextualized_text=chunk.contextualized_text,
        chunk_type=chunk.chunk_type,
        product_id=chunk.product_id,
        product_name=product_name,
        document_id=chunk.document_id,
        category_id=chunk.category_id,
        position=chunk.position,
        token_count=chunk.token_count,
        index_version=chunk.index_version,
        created_at=chunk.created_at,
    )


@router.delete("/{chunk_id}")
async def delete_chunk(chunk_id: int, db: Session = Depends(get_db)):
    """Delete chunk."""
    chunk = db.execute(
        select(Chunk).where(Chunk.id == chunk_id)
    ).scalar_one_or_none()

    if not chunk:
        raise HTTPException(status_code=404, detail="Chunk not found")

    db.delete(chunk)
    db.commit()

    return {"message": "Chunk deleted successfully"}