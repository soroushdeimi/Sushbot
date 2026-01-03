"""Reseller workflows: pricing, bulk purchases, quota management."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from config.features import is_enabled
from database.models import Product, Purchase, PurchaseStatus, User, UserRole
from database.models.purchase import PurchaseType
from database.models.reseller import ResellerPricing, ResellerQuota


async def get_reseller_discount(db: AsyncSession, *, user_id: int, product_id: int) -> int:
    """Get reseller discount percentage for a product (0-100)."""
    if not is_enabled("reseller"):
        return 0

    user = await db.get(User, user_id)
    if not user or user.role != UserRole.RESELLER:
        return 0

    # Query reseller_pricing table
    res = await db.execute(
        select(ResellerPricing.discount_percent)
        .where(
            ResellerPricing.reseller_id == user_id,
            ResellerPricing.product_id == product_id,
            ResellerPricing.is_active.is_(True),
        )
    )
    pricing = res.scalar_one_or_none()
    
    # Return configured discount or default 10%
    return pricing if pricing is not None else 10


async def calculate_reseller_price(db: AsyncSession, *, user_id: int, product_id: int, base_price: int) -> int:
    """Calculate final price for reseller (with discount)."""
    discount_pct = await get_reseller_discount(db, user_id=user_id, product_id=product_id)
    if discount_pct <= 0:
        return base_price
    discount_amount = int(base_price * discount_pct / 100)
    return max(0, base_price - discount_amount)


async def check_reseller_quota(db: AsyncSession, *, user_id: int, product_id: int, quantity: int = 1) -> tuple[bool, str | None]:
    """Check if reseller has quota for bulk purchase."""
    if not is_enabled("reseller"):
        return False, "Reseller feature disabled"

    user = await db.get(User, user_id)
    if not user or user.role != UserRole.RESELLER:
        return False, "User is not a reseller"

    # Check product-specific quota first, then global
    res = await db.execute(
        select(ResellerQuota)
        .where(
            ResellerQuota.reseller_id == user_id,
            ResellerQuota.product_id == product_id,
        )
    )
    quota = res.scalar_one_or_none()
    
    # If no product-specific quota, check global quota
    if not quota:
        res = await db.execute(
            select(ResellerQuota)
            .where(
                ResellerQuota.reseller_id == user_id,
                ResellerQuota.product_id.is_(None),
            )
        )
        quota = res.scalar_one_or_none()
    
    # No quota = unlimited
    if not quota or quota.monthly_limit is None:
        return True, None
    
    # Reset if new month
    now = datetime.utcnow()
    if quota.reset_date < now.replace(day=1, hour=0, minute=0, second=0, microsecond=0):
        quota.current_month_usage = 0
        quota.reset_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        await db.commit()
    
    # Check quota
    if quota.current_month_usage + quantity > quota.monthly_limit:
        return False, f"Monthly quota exceeded. Limit: {quota.monthly_limit}, Used: {quota.current_month_usage}, Requested: {quantity}"
    
    return True, None


async def create_bulk_purchase(
    db,
    *,
    user_id: int,
    product_id: int,
    quantity: int,
    discount_code: str | None = None,
) -> list[Purchase]:
    """Create multiple purchases for bulk order (idempotent by design)."""
    if not is_enabled("bulk_purchase"):
        raise ValueError("Bulk purchase feature disabled")

    ok, err = await check_reseller_quota(db, user_id=user_id, product_id=product_id, quantity=quantity)
    if not ok:
        raise ValueError(err or "Quota check failed")

    product = await db.get(Product, product_id)
    if not product:
        raise ValueError("Product not found")

    user = await db.get(User, user_id)
    if not user:
        raise ValueError("User not found")

    # Calculate price (with reseller discount if applicable)
    base_price = int(product.price)
    reseller_price = await calculate_reseller_price(db, user_id=user_id, product_id=product_id, base_price=base_price)
    
    # Apply discount code if provided
    discount_code_obj = None
    discount_amount_total = 0
    if discount_code:
        from services.discount import validate_and_apply_discount
        
        # Check if this is first purchase
        res = await db.execute(
            select(func.count(Purchase.id)).where(
                Purchase.user_id == user_id,
                Purchase.status == PurchaseStatus.COMPLETED,
            )
        )
        is_first_purchase = int(res.scalar() or 0) == 0
        
        # Validate discount code for total purchase amount
        total_purchase_amount = reseller_price * quantity
        discount_code_obj, discount_amount_total, error_msg = await validate_and_apply_discount(
            db,
            code=discount_code,
            user_id=user_id,
            purchase_amount=total_purchase_amount,
            is_first_purchase=is_first_purchase,
        )
        if not discount_code_obj:
            raise ValueError(f"Invalid discount code: {error_msg}")
    
    # Calculate per-item pricing
    # Discount is applied to total, so we distribute it across items
    total_final_amount = (reseller_price * quantity) - discount_amount_total
    per_item_final = total_final_amount // quantity
    per_item_reseller_discount = base_price - reseller_price
    per_item_code_discount = discount_amount_total // quantity if discount_code_obj else 0
    per_item_total_discount = per_item_reseller_discount + per_item_code_discount

    purchases: list[Purchase] = []
    for _ in range(quantity):
        purchase = Purchase(
            user_id=user_id,
            product_id=product_id,
            purchase_type=PurchaseType.NEW,
            status=PurchaseStatus.PENDING,
            amount=base_price,
            discount_amount=per_item_total_discount,
            final_amount=per_item_final,
            duration_days=product.duration_days,
            traffic_gb=product.traffic_gb,
            protocol=product.protocol,
            discount_code_id=discount_code_obj.id if discount_code_obj else None,
        )
        db.add(purchase)
        purchases.append(purchase)

    await db.commit()
    for p in purchases:
        await db.refresh(p)
    
    # Update quota usage after successful purchase creation
    if user.role == UserRole.RESELLER:
        # Find quota (product-specific or global)
        res = await db.execute(
            select(ResellerQuota)
            .where(
                ResellerQuota.reseller_id == user_id,
                ResellerQuota.product_id == product_id,
            )
        )
        quota = res.scalar_one_or_none()
        
        if not quota:
            res = await db.execute(
                select(ResellerQuota)
                .where(
                    ResellerQuota.reseller_id == user_id,
                    ResellerQuota.product_id.is_(None),
                )
            )
            quota = res.scalar_one_or_none()
        
        if quota:
            quota.current_month_usage += quantity
            await db.commit()

    return purchases


async def get_reseller_stats(db: AsyncSession, *, user_id: int) -> dict[str, Any]:
    """Get reseller statistics."""
    user = await db.get(User, user_id)
    if not user or user.role != UserRole.RESELLER:
        return {}

    res = await db.execute(
        select(func.count(Purchase.id)).where(
            Purchase.user_id == user_id, Purchase.status == PurchaseStatus.COMPLETED
        )
    )
    total_sales = int(res.scalar() or 0)

    res = await db.execute(
        select(func.coalesce(func.sum(Purchase.final_amount), 0)).where(
            Purchase.user_id == user_id, Purchase.status == PurchaseStatus.COMPLETED
        )
    )
    total_revenue = int(res.scalar() or 0)

    # Count referred users
    res = await db.execute(select(func.count(User.id)).where(User.referred_by_id == user_id))
    referrals = int(res.scalar() or 0)

    return {
        "user_id": user_id,
        "total_sales": total_sales,
        "total_revenue": total_revenue,
        "referrals": referrals,
        "balance": int(user.balance),
    }

