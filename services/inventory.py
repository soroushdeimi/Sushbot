"""Inventory reservation/consumption helpers for Products."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Product, ProductStatus


class InventoryError(RuntimeError):
    pass


async def reserve_stock(db: AsyncSession, *, product_id: int, qty: int = 1) -> None:
    """Reserve qty units for a product (for pending purchases)."""
    if qty <= 0:
        return
    # Lock row
    res = await db.execute(select(Product).where(Product.id == product_id).with_for_update())
    p = res.scalars().first()
    if not p:
        raise InventoryError("product_not_found")
    if p.status != ProductStatus.ACTIVE:
        raise InventoryError("product_not_active")
    if p.stock_quantity is not None:
        available = p.available_stock or 0
        if available < qty:
            raise InventoryError("out_of_stock")
    p.reserved_quantity = int(p.reserved_quantity) + int(qty)


async def release_stock(db: AsyncSession, *, product_id: int, qty: int = 1) -> None:
    """Release qty reserved units (on cancellation/expiry)."""
    if qty <= 0:
        return
    res = await db.execute(select(Product).where(Product.id == product_id).with_for_update())
    p = res.scalars().first()
    if not p:
        return
    p.reserved_quantity = max(0, int(p.reserved_quantity) - int(qty))


async def consume_stock(db: AsyncSession, *, product_id: int, qty: int = 1) -> None:
    """Move qty reserved units into sold units (on successful completion)."""
    if qty <= 0:
        return
    res = await db.execute(select(Product).where(Product.id == product_id).with_for_update())
    p = res.scalars().first()
    if not p:
        raise InventoryError("product_not_found")
    if int(p.reserved_quantity) < qty:
        # Prevent negative reserved; treat as invariant violation
        raise InventoryError("reserved_underflow")
    p.reserved_quantity = int(p.reserved_quantity) - int(qty)
    p.sold_quantity = int(p.sold_quantity) + int(qty)
