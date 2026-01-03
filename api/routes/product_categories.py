"""Product category management API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.audit import audit
from api.deps import AdminLevel, CurrentAdmin, require_level
from database.models import ProductCategory
from database.session import get_db

router = APIRouter()


class ProductCategoryOut(BaseModel):
    id: int
    name: str
    description: str | None
    slug: str | None
    sort_order: int
    parent_id: int | None
    is_active: bool
    created_at: str
    updated_at: str


class ProductCategoryCreate(BaseModel):
    name: str
    description: str | None = None
    slug: str | None = None
    sort_order: int = 0
    parent_id: int | None = None
    is_active: bool = True


class ProductCategoryUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    slug: str | None = None
    sort_order: int | None = None
    parent_id: int | None = None
    is_active: bool | None = None


@router.get("/")
async def list_categories(
    cur: CurrentAdmin = Depends(require_level(AdminLevel.SUPER_ADMIN, AdminLevel.MANAGEMENT)),
    db: AsyncSession = Depends(get_db),
    limit: int = 100,
    offset: int = 0,
) -> list[ProductCategoryOut]:
    """List all product categories."""
    res = await db.execute(
        select(ProductCategory)
        .order_by(ProductCategory.sort_order.asc(), ProductCategory.id.asc())
        .limit(limit)
        .offset(offset)
    )
    items = list(res.scalars().all())
    await audit(db, actor_user_id=cur.user.id, action="api.product_categories.list", meta={"limit": limit, "offset": offset})
    return [
        ProductCategoryOut(
            id=int(c.id),
            name=c.name,
            description=c.description,
            slug=c.slug,
            sort_order=int(c.sort_order),
            parent_id=int(c.parent_id) if c.parent_id is not None else None,
            is_active=bool(c.is_active),
            created_at=c.created_at.isoformat(),
            updated_at=c.updated_at.isoformat(),
        )
        for c in items
    ]


@router.post("/")
async def create_category(
    body: ProductCategoryCreate,
    cur: CurrentAdmin = Depends(require_level(AdminLevel.SUPER_ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> ProductCategoryOut:
    """Create a new product category."""
    # Validate parent_id if provided
    if body.parent_id:
        parent = await db.get(ProductCategory, body.parent_id)
        if not parent:
            raise HTTPException(status_code=400, detail=f"Parent category {body.parent_id} not found")

    category = ProductCategory(**body.model_dump())
    db.add(category)
    await db.commit()
    await db.refresh(category)
    await audit(db, actor_user_id=cur.user.id, action="api.product_categories.create", meta={"id": int(category.id)})
    return ProductCategoryOut(
        id=int(category.id),
        name=category.name,
        description=category.description,
        slug=category.slug,
        sort_order=int(category.sort_order),
        parent_id=int(category.parent_id) if category.parent_id is not None else None,
        is_active=bool(category.is_active),
        created_at=category.created_at.isoformat(),
        updated_at=category.updated_at.isoformat(),
    )


@router.patch("/{category_id}")
async def update_category(
    category_id: int,
    body: ProductCategoryUpdate,
    cur: CurrentAdmin = Depends(require_level(AdminLevel.SUPER_ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> ProductCategoryOut:
    """Update a product category."""
    category = await db.get(ProductCategory, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    # Validate parent_id if provided
    if body.parent_id is not None:
        if body.parent_id == category_id:
            raise HTTPException(status_code=400, detail="Category cannot be its own parent")
        if body.parent_id:
            parent = await db.get(ProductCategory, body.parent_id)
            if not parent:
                raise HTTPException(status_code=400, detail=f"Parent category {body.parent_id} not found")

    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(category, k, v)
    await db.commit()
    await db.refresh(category)
    await audit(db, actor_user_id=cur.user.id, action="api.product_categories.update", meta={"id": int(category.id), "fields": list(data.keys())})
    return ProductCategoryOut(
        id=int(category.id),
        name=category.name,
        description=category.description,
        slug=category.slug,
        sort_order=int(category.sort_order),
        parent_id=int(category.parent_id) if category.parent_id is not None else None,
        is_active=bool(category.is_active),
        created_at=category.created_at.isoformat(),
        updated_at=category.updated_at.isoformat(),
    )


@router.delete("/{category_id}")
async def delete_category(
    category_id: int,
    cur: CurrentAdmin = Depends(require_level(AdminLevel.SUPER_ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Delete a product category (soft delete)."""
    category = await db.get(ProductCategory, category_id)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    # Soft delete
    from datetime import datetime
    category.deleted_at = datetime.utcnow()
    await db.commit()
    await audit(db, actor_user_id=cur.user.id, action="api.product_categories.delete", meta={"id": int(category.id)})
    return {"status": "deleted", "id": category_id}

