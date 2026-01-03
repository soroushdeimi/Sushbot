"""Reports and statistics API routes."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api.deps import CurrentAdmin, get_current_admin
from config.features import is_enabled
from database.models.purchase import PurchaseType
from database.session import get_db
from services.reports import (
    get_overall_stats,
    get_purchase_report,
    get_revenue_breakdown,
    get_trial_report,
    get_user_stats,
)

router = APIRouter()


@router.get("/overall")
async def get_overall_stats_endpoint(
    cur: CurrentAdmin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get overall bot statistics."""
    if not is_enabled("reporting"):
        return {"error": "Reporting feature disabled"}
    return await get_overall_stats(db)


@router.get("/purchases")
async def get_purchase_report_endpoint(
    cur: CurrentAdmin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
    start_date: datetime | None = Query(None),
    end_date: datetime | None = Query(None),
    product_id: int | None = Query(None),
    user_id: int | None = Query(None),
    purchase_type: str | None = Query(None),
) -> dict:
    """Get purchase report with filters."""
    if not is_enabled("reporting"):
        return {"error": "Reporting feature disabled"}

    ptype = None
    if purchase_type:
        try:
            ptype = PurchaseType(purchase_type)
        except ValueError:
            pass

    return await get_purchase_report(
        db,
        start_date=start_date,
        end_date=end_date,
        product_id=product_id,
        user_id=user_id,
        purchase_type=ptype,
    )


@router.get("/trials")
async def get_trial_report_endpoint(
    cur: CurrentAdmin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
    start_date: datetime | None = Query(None),
    end_date: datetime | None = Query(None),
) -> dict:
    """Get trial account report."""
    if not is_enabled("reporting"):
        return {"error": "Reporting feature disabled"}
    return await get_trial_report(db, start_date=start_date, end_date=end_date)


@router.get("/users/{user_id}")
async def get_user_stats_endpoint(
    user_id: int,
    cur: CurrentAdmin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Get detailed stats for a specific user."""
    if not is_enabled("reporting"):
        return {"error": "Reporting feature disabled"}
    return await get_user_stats(db, user_id=user_id)


@router.get("/revenue")
async def get_revenue_breakdown_endpoint(
    cur: CurrentAdmin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
    days: int = Query(30, ge=1, le=365),
) -> dict:
    """Get revenue breakdown by day."""
    if not is_enabled("reporting"):
        return {"error": "Reporting feature disabled"}
    return await get_revenue_breakdown(db, days=days)
