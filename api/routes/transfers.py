"""Service transfer and location change API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from api.audit import audit
from api.deps import AdminLevel, CurrentAdmin, require_level
from config.features import is_enabled
from database.session import get_db
from services.transfer import change_service_location, transfer_service

router = APIRouter()


class TransferServiceRequest(BaseModel):
    service_id: int
    new_user_id: int
    reason: str | None = None


class ChangeLocationRequest(BaseModel):
    service_id: int
    new_inbound_tag: str
    reason: str | None = None


@router.post("/transfer")
async def transfer_service_endpoint(
    req: TransferServiceRequest,
    cur: CurrentAdmin = Depends(require_level(AdminLevel.SUPER_ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Transfer service ownership to another user."""
    if not is_enabled("service_transfer"):
        raise HTTPException(status_code=403, detail="Service transfer feature disabled")

    try:
        result = await transfer_service(
            db,
            service_id=req.service_id,
            new_user_id=req.new_user_id,
            admin_id=cur.user.id,
            reason=req.reason,
        )
        await audit(
            db,
            actor_user_id=cur.user.id,
            action="api.service.transfer",
            meta={"service_id": req.service_id, "new_user_id": req.new_user_id, "reason": req.reason},
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/change-location")
async def change_location_endpoint(
    req: ChangeLocationRequest,
    cur: CurrentAdmin = Depends(require_level(AdminLevel.SUPER_ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Change service location/inbound."""
    if not is_enabled("service_location_change"):
        raise HTTPException(status_code=403, detail="Service location change feature disabled")

    try:
        result = await change_service_location(
            db,
            service_id=req.service_id,
            new_inbound_tag=req.new_inbound_tag,
            admin_id=cur.user.id,
            reason=req.reason,
        )
        await audit(
            db,
            actor_user_id=cur.user.id,
            action="api.service.change_location",
            meta={"service_id": req.service_id, "new_inbound_tag": req.new_inbound_tag, "reason": req.reason},
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

