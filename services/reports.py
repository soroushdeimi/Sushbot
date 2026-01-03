"""Comprehensive reporting and statistics service."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import (
    Payment,
    PaymentStatus,
    Purchase,
    PurchaseStatus,
    Service,
    ServiceStatus,
    TrialAccount,
    User,
)
from database.models.purchase import PurchaseType


async def get_overall_stats(db: AsyncSession) -> dict[str, Any]:
    """Get overall bot statistics."""
    res = await db.execute(select(func.count(User.id)))
    total_users = int(res.scalar() or 0)

    res = await db.execute(select(func.count(Service.id)).where(Service.status == ServiceStatus.ACTIVE))
    active_services = int(res.scalar() or 0)

    res = await db.execute(
        select(func.coalesce(func.sum(Purchase.final_amount), 0)).where(Purchase.status == PurchaseStatus.COMPLETED)
    )
    total_revenue = int(res.scalar() or 0)

    res = await db.execute(select(func.count(Purchase.id)).where(Purchase.status == PurchaseStatus.COMPLETED))
    total_purchases = int(res.scalar() or 0)

    res = await db.execute(select(func.count(TrialAccount.id)).where(TrialAccount.is_used.is_(True)))
    total_trials = int(res.scalar() or 0)

    res = await db.execute(
        select(func.count(Payment.id)).where(Payment.status == PaymentStatus.PROCESSING)
    )
    pending_payments = int(res.scalar() or 0)

    return {
        "total_users": total_users,
        "active_services": active_services,
        "total_revenue": total_revenue,
        "total_purchases": total_purchases,
        "total_trials": total_trials,
        "pending_payments": pending_payments,
    }


async def get_purchase_report(
    db: AsyncSession,
    *,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
    product_id: int | None = None,
    user_id: int | None = None,
    purchase_type: PurchaseType | None = None,
) -> dict[str, Any]:
    """Get detailed purchase report with filters."""
    query = select(Purchase).where(Purchase.status == PurchaseStatus.COMPLETED)

    if start_date:
        query = query.where(Purchase.completed_at >= start_date)
    if end_date:
        query = query.where(Purchase.completed_at <= end_date)
    if product_id:
        query = query.where(Purchase.product_id == product_id)
    if user_id:
        query = query.where(Purchase.user_id == user_id)
    if purchase_type:
        query = query.where(Purchase.purchase_type == purchase_type)

    res = await db.execute(query.options(selectinload(Purchase.user), selectinload(Purchase.product)))
    purchases = list(res.scalars().all())

    total_amount = sum(int(p.final_amount) for p in purchases)
    count = len(purchases)

    # Group by product
    by_product: dict[int, dict[str, Any]] = {}
    for p in purchases:
        pid = p.product_id or 0
        if pid not in by_product:
            by_product[pid] = {"count": 0, "revenue": 0, "product_name": p.product.name if p.product else "N/A"}
        by_product[pid]["count"] += 1
        by_product[pid]["revenue"] += int(p.final_amount)

    # Group by gateway
    res = await db.execute(
        select(Payment.gateway, func.count(Payment.id), func.coalesce(func.sum(Purchase.final_amount), 0))
        .join(Purchase, Payment.purchase_id == Purchase.id)
        .where(Purchase.status == PurchaseStatus.COMPLETED)
        .group_by(Payment.gateway)
    )
    by_gateway: dict[str, dict[str, Any]] = {}
    for row in res.all():
        gw = str(row[0].value if hasattr(row[0], "value") else row[0])
        by_gateway[gw] = {"count": int(row[1]), "revenue": int(row[2])}

    return {
        "total_count": count,
        "total_revenue": total_amount,
        "purchases": [
            {
                "id": p.id,
                "user_id": p.user_id,
                "username": p.user.username if p.user else None,
                "product_id": p.product_id,
                "product_name": p.product.name if p.product else None,
                "amount": int(p.amount),
                "discount": int(p.discount_amount),
                "final_amount": int(p.final_amount),
                "purchase_type": p.purchase_type.value,
                "completed_at": p.completed_at.isoformat() if p.completed_at else None,
            }
            for p in purchases[:100]  # Limit to 100 for response size
        ],
        "by_product": by_product,
        "by_gateway": by_gateway,
    }


async def get_trial_report(
    db: AsyncSession,
    *,
    start_date: datetime | None = None,
    end_date: datetime | None = None,
) -> dict[str, Any]:
    """Get trial account report."""
    query = select(TrialAccount).where(TrialAccount.is_used.is_(True))

    if start_date:
        query = query.where(TrialAccount.created_at >= start_date)
    if end_date:
        query = query.where(TrialAccount.created_at <= end_date)

    res = await db.execute(query.options(selectinload(TrialAccount.user)))
    trials = list(res.scalars().all())

    total = len(trials)
    active = sum(1 for t in trials if t.expiry_date and t.expiry_date > datetime.utcnow())
    expired = total - active

    return {
        "total": total,
        "active": active,
        "expired": expired,
        "trials": [
            {
                "id": t.id,
                "user_id": t.user_id,
                "username": t.user.username if t.user else None,
                "duration_days": t.duration_days,
                "traffic_gb": t.traffic_gb,
                "start_date": t.start_date.isoformat() if t.start_date else None,
                "expiry_date": t.expiry_date.isoformat() if t.expiry_date else None,
                "is_active": t.expiry_date and t.expiry_date > datetime.utcnow(),
            }
            for t in trials[:100]
        ],
    }


async def get_user_stats(db: AsyncSession, *, user_id: int) -> dict[str, Any]:
    """Get detailed stats for a specific user."""
    user = await db.get(User, user_id)
    if not user:
        return {}

    res = await db.execute(
        select(func.count(Service.id)).where(Service.user_id == user_id, Service.status == ServiceStatus.ACTIVE)
    )
    active_services = int(res.scalar() or 0)

    res = await db.execute(
        select(func.count(Purchase.id)).where(Purchase.user_id == user_id, Purchase.status == PurchaseStatus.COMPLETED)
    )
    total_purchases = int(res.scalar() or 0)

    res = await db.execute(
        select(func.coalesce(func.sum(Purchase.final_amount), 0)).where(
            Purchase.user_id == user_id, Purchase.status == PurchaseStatus.COMPLETED
        )
    )
    total_spent = int(res.scalar() or 0)

    res = await db.execute(
        select(func.count(TrialAccount.id)).where(TrialAccount.user_id == user_id, TrialAccount.is_used.is_(True))
    )
    trials_used = int(res.scalar() or 0)

    return {
        "user_id": user_id,
        "username": user.username,
        "balance": int(user.balance),
        "total_spent": total_spent,
        "active_services": active_services,
        "total_purchases": total_purchases,
        "trials_used": trials_used,
        "phone_verified": user.phone_verified,
        "channel_member": user.channel_member,
        "created_at": user.created_at.isoformat() if user.created_at else None,
    }


async def get_revenue_breakdown(db: AsyncSession, *, days: int = 30) -> dict[str, Any]:
    """Get revenue breakdown by day for the last N days."""
    start = datetime.utcnow() - timedelta(days=days)
    res = await db.execute(
        select(
            func.date(Purchase.completed_at).label("date"),
            func.count(Purchase.id).label("count"),
            func.coalesce(func.sum(Purchase.final_amount), 0).label("revenue"),
        )
        .where(Purchase.status == PurchaseStatus.COMPLETED, Purchase.completed_at >= start)
        .group_by(func.date(Purchase.completed_at))
        .order_by(func.date(Purchase.completed_at).desc())
    )

    daily: list[dict[str, Any]] = []
    for row in res.all():
        daily.append({"date": str(row[0]), "count": int(row[1]), "revenue": int(row[2])})

    return {"period_days": days, "daily_breakdown": daily}

