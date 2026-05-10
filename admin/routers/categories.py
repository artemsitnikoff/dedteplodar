"""Categories API router."""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, selectinload
from sqlalchemy import func, select

from src.products.models import Category, Product
from admin.dependencies import get_db
from admin.schemas.categories import CategoryNode
from admin.schemas.products import ProductList, ProductListItem

router = APIRouter(prefix="/categories", tags=["Categories"])


def build_category_tree(categories: List[Category], parent_id=None) -> List[CategoryNode]:
    """Build hierarchical category tree."""
    result = []
    for category in categories:
        if category.parent_id == parent_id:
            # Count products in this category
            products_count = len(category.products) if category.products else 0

            # Build children recursively
            children = build_category_tree(categories, category.id)

            result.append(CategoryNode(
                id=category.id,
                name=category.name,
                parent_id=category.parent_id,
                children=children,
                products_count=products_count,
            ))

    return result


@router.get("/tree", response_model=List[CategoryNode])
async def get_categories_tree(db: Session = Depends(get_db)):
    """Get categories as hierarchical tree."""
    categories = db.execute(
        select(Category).options(selectinload(Category.products))
    ).scalars().all()

    return build_category_tree(categories)


@router.get("/{category_id}/products", response_model=ProductList)
async def get_category_products(
    category_id: int,
    page: int = Query(1, ge=1),
    per_page: int = Query(50, ge=1, le=100),
    db: Session = Depends(get_db),
):
    """Get products in a specific category."""
    # Verify category exists
    category = db.execute(
        select(Category).where(Category.id == category_id)
    ).scalar_one_or_none()

    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    # Count total products
    total = db.execute(
        select(func.count(Product.id)).where(Product.category_id == category_id)
    ).scalar()

    # Get products with pagination
    offset = (page - 1) * per_page
    products = db.execute(
        select(Product)
        .options(selectinload(Product.category))
        .where(Product.category_id == category_id)
        .offset(offset)
        .limit(per_page)
    ).scalars().all()

    items = []
    for product in products:
        items.append(ProductListItem(
            id=product.id,
            name=product.name,
            model=product.model,
            price=product.price,
            category_id=product.category_id,
            category_name=product.category.name if product.category else None,
            chunks_count=0,  # Could add chunk count here if needed
            created_at=product.created_at,
            updated_at=product.updated_at,
        ))

    return ProductList(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
    )