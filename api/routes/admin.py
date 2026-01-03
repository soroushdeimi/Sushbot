"""Admin routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import CurrentAdmin, get_current_admin
from database.models import Purchase, PurchaseStatus, Service, User
from database.session import get_db

router = APIRouter()


@router.get("/stats")
async def get_stats(cur: CurrentAdmin = Depends(get_current_admin), db: AsyncSession = Depends(get_db)) -> dict:
    """Get bot statistics."""
    res = await db.execute(select(func.count()).select_from(User))
    total_users = int(res.scalar() or 0)
    res = await db.execute(select(func.count()).select_from(Service))
    total_services = int(res.scalar() or 0)
    res = await db.execute(
        select(func.coalesce(func.sum(Purchase.final_amount), 0))
        .where(Purchase.status == PurchaseStatus.COMPLETED)
    )
    total_revenue = int(res.scalar() or 0)
    return {"total_users": total_users, "total_services": total_services, "total_revenue": total_revenue}

