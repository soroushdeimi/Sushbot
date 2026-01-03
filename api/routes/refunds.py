"""Refund and service removal API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.audit import audit
from api.deps import AdminLevel, CurrentAdmin, require_level
from config.features import is_enabled
from database.session import get_db
from services.refund import refund_purchase, remove_service

router = APIRouter()


class RefundRequest(BaseModel):
    purchase_id: int
    reason: str | None = None


class RemoveServiceRequest(BaseModel):
    service_id: int
    reason: str | None = None


@router.post("/refund")
async def refund_purchase_endpoint(
    req: RefundRequest,
    cur: CurrentAdmin = Depends(require_level(AdminLevel.SUPER_ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Refund a completed purchase."""
    if not is_enabled("refunds"):
        raise HTTPException(status_code=403, detail="Refunds feature disabled")

    try:
        result = await refund_purchase(
            db,
            purchase_id=req.purchase_id,
            admin_id=cur.user.id,
            reason=req.reason,
        )
        await audit(
            db,
            actor_user_id=cur.user.id,
            action="api.refund.purchase",
            meta={"purchase_id": req.purchase_id, "reason": req.reason},
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/remove-service")
async def remove_service_endpoint(
    req: RemoveServiceRequest,
    cur: CurrentAdmin = Depends(require_level(AdminLevel.SUPER_ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Remove/deprovision a service."""
    if not is_enabled("service_removal"):
        raise HTTPException(status_code=403, detail="Service removal feature disabled")

    try:
        result = await remove_service(
            db,
            service_id=req.service_id,
            admin_id=cur.user.id,
            reason=req.reason,
        )
        await audit(
            db,
            actor_user_id=cur.user.id,
            action="api.service.remove",
            meta={"service_id": req.service_id, "reason": req.reason},
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
