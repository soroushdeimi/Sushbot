"""Reseller management API routes."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import AdminLevel, CurrentAdmin, require_level
from database.models import Product, User, UserRole
from database.models.reseller import ResellerPricing, ResellerQuota
from database.session import get_db
from services.reseller import get_reseller_stats

router = APIRouter()


class ResellerPricingCreate(BaseModel):
    product_id: int
    discount_percent: int
    is_active: bool = True


class ResellerPricingUpdate(BaseModel):
    discount_percent: int | None = None
    is_active: bool | None = None


class ResellerQuotaCreate(BaseModel):
    product_id: int | None = None  # None = global quota
    monthly_limit: int | None = None  # None = unlimited


class ResellerQuotaUpdate(BaseModel):
    monthly_limit: int | None = None
    current_month_usage: int | None = None


@router.get("/{user_id}/pricing")
async def get_reseller_pricing(
    user_id: int,
    cur: CurrentAdmin = Depends(require_level(AdminLevel.SUPER_ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """List all pricing rules for a reseller."""
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.role != UserRole.RESELLER:
        raise HTTPException(status_code=400, detail="User is not a reseller")

    res = await db.execute(
        select(ResellerPricing)
        .where(ResellerPricing.reseller_id == user_id)
        .order_by(ResellerPricing.product_id)
    )
    pricing_list = res.scalars().all()

    return [
        {
            "id": p.id,
            "product_id": p.product_id,
            "discount_percent": p.discount_percent,
            "is_active": p.is_active,
            "created_at": p.created_at.isoformat(),
            "updated_at": p.updated_at.isoformat(),
        }
        for p in pricing_list
    ]


@router.post("/{user_id}/pricing")
async def create_reseller_pricing(
    user_id: int,
    req: ResellerPricingCreate,
    cur: CurrentAdmin = Depends(require_level(AdminLevel.SUPER_ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Create or update pricing rule for a reseller."""
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.role != UserRole.RESELLER:
        raise HTTPException(status_code=400, detail="User is not a reseller")

    product = await db.get(Product, req.product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    if not 0 <= req.discount_percent <= 100:
        raise HTTPException(status_code=400, detail="Discount percent must be between 0 and 100")

    # Check if pricing already exists
    res = await db.execute(
        select(ResellerPricing).where(
            ResellerPricing.reseller_id == user_id,
            ResellerPricing.product_id == req.product_id,
        )
    )
    existing = res.scalar_one_or_none()

    if existing:
        existing.discount_percent = req.discount_percent
        existing.is_active = req.is_active
        await db.commit()
        await db.refresh(existing)
        return {
            "id": existing.id,
            "product_id": existing.product_id,
            "discount_percent": existing.discount_percent,
            "is_active": existing.is_active,
            "created_at": existing.created_at.isoformat(),
            "updated_at": existing.updated_at.isoformat(),
        }

    pricing = ResellerPricing(
        reseller_id=user_id,
        product_id=req.product_id,
        discount_percent=req.discount_percent,
        is_active=req.is_active,
    )
    db.add(pricing)
    await db.commit()
    await db.refresh(pricing)

    return {
        "id": pricing.id,
        "product_id": pricing.product_id,
        "discount_percent": pricing.discount_percent,
        "is_active": pricing.is_active,
        "created_at": pricing.created_at.isoformat(),
        "updated_at": pricing.updated_at.isoformat(),
    }


@router.delete("/{user_id}/pricing/{pricing_id}")
async def delete_reseller_pricing(
    user_id: int,
    pricing_id: int,
    cur: CurrentAdmin = Depends(require_level(AdminLevel.SUPER_ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Remove pricing rule for a reseller."""
    pricing = await db.get(ResellerPricing, pricing_id)
    if not pricing:
        raise HTTPException(status_code=404, detail="Pricing rule not found")
    if pricing.reseller_id != user_id:
        raise HTTPException(status_code=403, detail="Pricing rule does not belong to this reseller")

    await db.delete(pricing)
    await db.commit()

    return {"status": "deleted", "id": pricing_id}


@router.get("/{user_id}/quotas")
async def get_reseller_quotas(
    user_id: int,
    cur: CurrentAdmin = Depends(require_level(AdminLevel.SUPER_ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    """List all quota rules for a reseller."""
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.role != UserRole.RESELLER:
        raise HTTPException(status_code=400, detail="User is not a reseller")

    res = await db.execute(
        select(ResellerQuota)
        .where(ResellerQuota.reseller_id == user_id)
        .order_by(ResellerQuota.product_id.nulls_last())
    )
    quota_list = res.scalars().all()

    return [
        {
            "id": q.id,
            "product_id": q.product_id,
            "monthly_limit": q.monthly_limit,
            "current_month_usage": q.current_month_usage,
            "reset_date": q.reset_date.isoformat(),
            "created_at": q.created_at.isoformat(),
            "updated_at": q.updated_at.isoformat(),
        }
        for q in quota_list
    ]


@router.post("/{user_id}/quotas")
async def create_reseller_quota(
    user_id: int,
    req: ResellerQuotaCreate,
    cur: CurrentAdmin = Depends(require_level(AdminLevel.SUPER_ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Create or update quota rule for a reseller."""
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.role != UserRole.RESELLER:
        raise HTTPException(status_code=400, detail="User is not a reseller")

    if req.product_id:
        product = await db.get(Product, req.product_id)
        if not product:
            raise HTTPException(status_code=404, detail="Product not found")

    # Check if quota already exists
    res = await db.execute(
        select(ResellerQuota).where(
            ResellerQuota.reseller_id == user_id,
            ResellerQuota.product_id == req.product_id,
        )
    )
    existing = res.scalar_one_or_none()

    now = datetime.utcnow()
    reset_date = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    if existing:
        if req.monthly_limit is not None:
            existing.monthly_limit = req.monthly_limit
        await db.commit()
        await db.refresh(existing)
        return {
            "id": existing.id,
            "product_id": existing.product_id,
            "monthly_limit": existing.monthly_limit,
            "current_month_usage": existing.current_month_usage,
            "reset_date": existing.reset_date.isoformat(),
            "created_at": existing.created_at.isoformat(),
            "updated_at": existing.updated_at.isoformat(),
        }

    quota = ResellerQuota(
        reseller_id=user_id,
        product_id=req.product_id,
        monthly_limit=req.monthly_limit,
        current_month_usage=0,
        reset_date=reset_date,
    )
    db.add(quota)
    await db.commit()
    await db.refresh(quota)

    return {
        "id": quota.id,
        "product_id": quota.product_id,
        "monthly_limit": quota.monthly_limit,
        "current_month_usage": quota.current_month_usage,
        "reset_date": quota.reset_date.isoformat(),
        "created_at": quota.created_at.isoformat(),
        "updated_at": quota.updated_at.isoformat(),
    }


@router.get("/{user_id}/stats")
async def get_reseller_stats_endpoint(
    user_id: int,
    cur: CurrentAdmin = Depends(require_level(AdminLevel.SUPER_ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get reseller statistics."""
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if user.role != UserRole.RESELLER:
        raise HTTPException(status_code=400, detail="User is not a reseller")

    stats = await get_reseller_stats(db, user_id=user_id)
    return stats
