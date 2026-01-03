"""Service management routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.audit import audit
from api.deps import CurrentAdmin, get_current_admin
from database.models import Service
from database.session import get_db

router = APIRouter()


class ServiceOut(BaseModel):
    id: int
    user_id: int
    status: str
    protocol: str
    panel_id: int
    client_email: str
    expiry_date: str | None
    is_unlimited: bool
    remaining_traffic_gb: float | None


@router.get("/")
async def list_services(
    cur: CurrentAdmin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
    offset: int = 0,
) -> list[ServiceOut]:
    """List all services."""
    res = await db.execute(select(Service).order_by(Service.id.desc()).limit(limit).offset(offset))
    services = list(res.scalars().all())
    await audit(db, actor_user_id=cur.user.id, action="api.services.list", meta={"limit": limit, "offset": offset})
    return [
        ServiceOut(
            id=int(s.id),
            user_id=int(s.user_id),
            status=str(s.status.value if hasattr(s.status, "value") else s.status),
            protocol=str(s.protocol),
            panel_id=int(s.panel_id),
            client_email=str(s.client_email),
            expiry_date=s.expiry_date.isoformat() if s.expiry_date else None,
            is_unlimited=bool(s.is_unlimited),
            remaining_traffic_gb=float(s.remaining_traffic_gb) if s.remaining_traffic_gb is not None else None,
        )
        for s in services
    ]

