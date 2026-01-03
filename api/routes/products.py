"""Product management routes (admin)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.audit import audit
from api.deps import CurrentAdmin, require_level
from database.models import AdminLevel, Product, ProductStatus
from database.session import get_db

router = APIRouter()


class ProductOut(BaseModel):
    id: int
    panel_id: int
    test_panel_id: int | None
    category_id: int | None
    name: str
    description: str | None
    status: str
    price: int
    duration_days: int
    traffic_gb: int
    protocol: str
    stock_quantity: int | None
    sold_quantity: int
    reserved_quantity: int
    min_stock: int
    max_stock: int | None


class ProductCreate(BaseModel):
    panel_id: int
    test_panel_id: int | None = None
    category_id: int | None = None
    name: str
    description: str | None = None
    status: ProductStatus = ProductStatus.ACTIVE
    price: int = Field(ge=0)
    duration_days: int = Field(ge=0)
    traffic_gb: int = Field(ge=0)
    protocol: str = "vless"
    stock_quantity: int | None = Field(default=None, ge=0)
    min_stock: int = Field(default=0, ge=0)
    max_stock: int | None = Field(default=None, ge=0)
    auto_send_config: bool = True
    is_featured: bool = False
    sort_order: int = 0


class ProductUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    status: ProductStatus | None = None
    price: int | None = Field(default=None, ge=0)
    duration_days: int | None = Field(default=None, ge=0)
    traffic_gb: int | None = Field(default=None, ge=0)
    protocol: str | None = None
    test_panel_id: int | None = None
    category_id: int | None = None
    stock_quantity: int | None = Field(default=None, ge=0)
    min_stock: int | None = Field(default=None, ge=0)
    max_stock: int | None = Field(default=None, ge=0)
    auto_send_config: bool | None = None
    is_featured: bool | None = None
    sort_order: int | None = None


@router.get("/")
async def list_products(
    cur: CurrentAdmin = Depends(require_level(AdminLevel.SUPER_ADMIN, AdminLevel.MANAGEMENT)),
    db: AsyncSession = Depends(get_db),
    limit: int = 100,
    offset: int = 0,
    category_id: int | None = None,
) -> list[ProductOut]:
    query = select(Product)
    if category_id is not None:
        query = query.where(Product.category_id == category_id)
    query = query.order_by(Product.id.desc()).limit(limit).offset(offset)
    res = await db.execute(query)
    items = list(res.scalars().all())
    await audit(
        db,
        actor_user_id=cur.user.id,
        action="api.products.list",
        meta={"limit": limit, "offset": offset, "category_id": category_id},
    )
    return [
        ProductOut(
            id=int(p.id),
            panel_id=int(p.panel_id),
            test_panel_id=int(p.test_panel_id) if p.test_panel_id is not None else None,
            category_id=int(p.category_id) if p.category_id is not None else None,
            name=p.name,
            description=p.description,
            status=str(p.status.value if hasattr(p.status, "value") else p.status),
            price=int(p.price),
            duration_days=int(p.duration_days),
            traffic_gb=int(p.traffic_gb),
            protocol=str(p.protocol),
            stock_quantity=int(p.stock_quantity) if p.stock_quantity is not None else None,
            sold_quantity=int(p.sold_quantity),
            reserved_quantity=int(getattr(p, "reserved_quantity", 0)),
            min_stock=int(p.min_stock),
            max_stock=int(p.max_stock) if p.max_stock is not None else None,
        )
        for p in items
    ]


@router.post("/")
async def create_product(
    body: ProductCreate,
    cur: CurrentAdmin = Depends(require_level(AdminLevel.SUPER_ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> ProductOut:
    p = Product(**body.model_dump())
    db.add(p)
    await db.commit()
    await db.refresh(p)
    await audit(db, actor_user_id=cur.user.id, action="api.products.create", meta={"id": int(p.id)})
    return ProductOut(
        id=int(p.id),
        panel_id=int(p.panel_id),
        test_panel_id=int(p.test_panel_id) if p.test_panel_id is not None else None,
        category_id=int(p.category_id) if p.category_id is not None else None,
        name=p.name,
        description=p.description,
        status=str(p.status.value if hasattr(p.status, "value") else p.status),
        price=int(p.price),
        duration_days=int(p.duration_days),
        traffic_gb=int(p.traffic_gb),
        protocol=str(p.protocol),
        stock_quantity=int(p.stock_quantity) if p.stock_quantity is not None else None,
        sold_quantity=int(p.sold_quantity),
        reserved_quantity=int(getattr(p, "reserved_quantity", 0)),
        min_stock=int(p.min_stock),
        max_stock=int(p.max_stock) if p.max_stock is not None else None,
    )


@router.patch("/{product_id}")
async def update_product(
    product_id: int,
    body: ProductUpdate,
    cur: CurrentAdmin = Depends(require_level(AdminLevel.SUPER_ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> ProductOut:
    p = await db.get(Product, product_id)
    if not p:
        raise HTTPException(status_code=404, detail="Not found")
    data = body.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(p, k, v)
    await db.commit()
    await db.refresh(p)
    await audit(
        db,
        actor_user_id=cur.user.id,
        action="api.products.update",
        meta={"id": int(p.id), "fields": list(data.keys())},
    )
    return ProductOut(
        id=int(p.id),
        panel_id=int(p.panel_id),
        test_panel_id=int(p.test_panel_id) if p.test_panel_id is not None else None,
        category_id=int(p.category_id) if p.category_id is not None else None,
        name=p.name,
        description=p.description,
        status=str(p.status.value if hasattr(p.status, "value") else p.status),
        price=int(p.price),
        duration_days=int(p.duration_days),
        traffic_gb=int(p.traffic_gb),
        protocol=str(p.protocol),
        stock_quantity=int(p.stock_quantity) if p.stock_quantity is not None else None,
        sold_quantity=int(p.sold_quantity),
        reserved_quantity=int(getattr(p, "reserved_quantity", 0)),
        min_stock=int(p.min_stock),
        max_stock=int(p.max_stock) if p.max_stock is not None else None,
    )
