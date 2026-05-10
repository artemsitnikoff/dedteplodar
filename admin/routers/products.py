"""Products API router."""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import func, select

from src.products.models import Product, Category, ProductParam
from src.rag.models import Chunk
from src.documents.models import Document
from admin.dependencies import get_db
from admin.schemas.products import ProductList, ProductListItem, ProductDetail, ProductUpdate
from admin.schemas.chunks import ChunkList, ChunkListItem
from admin.schemas.documents import DocumentList, DocumentListItem

router = APIRouter(prefix="/products", tags=["Products"])


@router.get("", response_model=ProductList)
async def list_products(
    category_id: Optional[int] = Query(None),
    search: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """List products with filtering and pagination."""
    query = select(Product).options(selectinload(Product.category))

    # Apply filters
    if category_id:
        query = query.where(Product.category_id == category_id)

    if search:
        query = query.where(Product.name.contains(search))

    # Count total
    count_query = select(func.count()).select_from(query.subquery())
    total = db.execute(count_query).scalar()

    # Apply pagination
    offset = (page - 1) * per_page
    query = query.offset(offset).limit(per_page)

    products = db.execute(query).scalars().all()

    # Get chunk counts for each product
    chunk_counts = {}
    if products:
        product_ids = [p.id for p in products]
        chunk_count_query = (
            select(Chunk.product_id, func.count(Chunk.id))
            .where(Chunk.product_id.in_(product_ids))
            .group_by(Chunk.product_id)
        )
        chunk_counts_result = db.execute(chunk_count_query).all()
        chunk_counts = {pid: count for pid, count in chunk_counts_result}

    items = []
    for product in products:
        items.append(ProductListItem(
            id=product.id,
            name=product.name,
            model=product.model,
            price=product.price,
            category_id=product.category_id,
            category_name=product.category.name if product.category else None,
            chunks_count=chunk_counts.get(product.id, 0),
            created_at=product.created_at,
            updated_at=product.updated_at,
        ))

    return ProductList(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
    )


@router.get("/{product_id}", response_model=ProductDetail)
async def get_product(product_id: int, db: Session = Depends(get_db)):
    """Get product details."""
    product = db.execute(
        select(Product)
        .options(
            selectinload(Product.category),
            selectinload(Product.params),
        )
        .where(Product.id == product_id)
    ).scalar_one_or_none()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Count chunks and documents
    chunks_count = db.execute(
        select(func.count(Chunk.id)).where(Chunk.product_id == product_id)
    ).scalar()

    documents_count = db.execute(
        select(func.count(Document.id)).where(Document.product_id == product_id)
    ).scalar()

    return ProductDetail(
        id=product.id,
        name=product.name,
        model=product.model,
        price=product.price,
        url=product.url,
        description=product.description,
        vendor=product.vendor,
        picture_url=product.picture_url,
        category_id=product.category_id,
        category_name=product.category.name if product.category else None,
        params=[{"name": p.name, "value": p.value} for p in product.params],
        chunks_count=chunks_count,
        documents_count=documents_count,
        created_at=product.created_at,
        updated_at=product.updated_at,
    )


@router.patch("/{product_id}", response_model=ProductDetail)
async def update_product(
    product_id: int,
    update_data: ProductUpdate,
    db: Session = Depends(get_db),
):
    """Update product fields."""
    product = db.execute(
        select(Product).where(Product.id == product_id)
    ).scalar_one_or_none()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Update only provided fields
    update_dict = update_data.model_dump(exclude_unset=True)
    for field, value in update_dict.items():
        setattr(product, field, value)

    db.commit()
    db.refresh(product)

    # Return updated product
    return await get_product(product_id, db)


@router.delete("/{product_id}")
async def delete_product(product_id: int, db: Session = Depends(get_db)):
    """Delete product and all related data."""
    product = db.execute(
        select(Product).where(Product.id == product_id)
    ).scalar_one_or_none()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    db.delete(product)
    db.commit()

    return {"message": "Product deleted successfully"}


@router.get("/{product_id}/chunks", response_model=ChunkList)
async def get_product_chunks(
    product_id: int,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Get chunks for a specific product."""
    # Verify product exists
    product = db.execute(
        select(Product).where(Product.id == product_id)
    ).scalar_one_or_none()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Count total chunks
    total = db.execute(
        select(func.count(Chunk.id)).where(Chunk.product_id == product_id)
    ).scalar()

    # Get chunks with pagination
    offset = (page - 1) * per_page
    chunks = db.execute(
        select(Chunk)
        .where(Chunk.product_id == product_id)
        .order_by(Chunk.position)
        .offset(offset)
        .limit(per_page)
    ).scalars().all()

    items = []
    for chunk in chunks:
        items.append(ChunkListItem(
            id=chunk.id,
            chunk_type=chunk.chunk_type,
            chunk_text_preview=chunk.chunk_text[:100],
            product_id=chunk.product_id,
            product_name=product.name,
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


@router.get("/{product_id}/documents", response_model=DocumentList)
async def get_product_documents(
    product_id: int,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Get documents linked to a specific product."""
    product = db.execute(
        select(Product).where(Product.id == product_id)
    ).scalar_one_or_none()

    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    total = db.execute(
        select(func.count(Document.id)).where(Document.product_id == product_id)
    ).scalar()

    offset = (page - 1) * per_page
    documents = db.execute(
        select(Document)
        .where(Document.product_id == product_id)
        .order_by(Document.created_at.desc())
        .offset(offset)
        .limit(per_page)
    ).scalars().all()

    items = [
        DocumentListItem(
            id=doc.id,
            product_id=doc.product_id,
            product_name=product.name,
            doc_type=doc.doc_type.value,
            source_url=doc.source_url,
            title=doc.title,
            char_count=doc.char_count,
            text_source=doc.text_source,
            fetched_at=doc.fetched_at,
            created_at=doc.created_at,
        )
        for doc in documents
    ]

    return DocumentList(items=items, total=total, page=page, per_page=per_page)