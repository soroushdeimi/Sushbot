"""Panel management routes (admin)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.audit import audit
from api.deps import AdminLevel, CurrentAdmin, require_level
from database.models import Panel, PanelStatus
from database.session import get_db
from services.panel_utils import sync_panel_config_count

router = APIRouter()


class PanelOut(BaseModel):
    id: int
    name: str
    api_url: str
    node_id: int
    status: str
    is_test_panel: bool
    max_configs_per_panel: int | None
    current_config_count: int
    location: str | None
    country_code: str | None
    default_protocol: str
    default_port: int


class PanelCreate(BaseModel):
    name: str
    api_url: str = ""
    api_key: str = ""
    node_id: int = 1
    status: PanelStatus = PanelStatus.ACTIVE
    is_test_panel: bool = False
    max_configs_per_panel: int | None = Field(default=None, ge=0)
    location: str | None = None
    country_code: str | None = None
    default_protocol: str = "vless"
    default_port: int = 8443
    notes: str | None = None


class PanelUpdate(BaseModel):
    name: str | None = None
    api_url: str | None = None
    api_key: str | None = None
    node_id: int | None = None
    status: PanelStatus | None = None
    is_test_panel: bool | None = None
    max_configs_per_panel: int | None = Field(default=None, ge=0)
    location: str | None = None
    country_code: str | None = None
    default_protocol: str | None = None
    default_port: int | None = None
    notes: str | None = None


@router.get("/")
async def list_panels(
    cur: CurrentAdmin = Depends(require_level(AdminLevel.SUPER_ADMIN, AdminLevel.MANAGEMENT)),
    db: AsyncSession = Depends(get_db),
    limit: int = 100,
    offset: int = 0,
) -> list[PanelOut]:
    res = await db.execute(select(Panel).order_by(Panel.id.desc()).limit(limit).offset(offset))
    items = list(res.scalars().all())
    await audit(
        db,
        actor_user_id=cur.user.id,
        action="api.panels.list",
        meta={"limit": limit, "offset": offset},
    )
    return [
        PanelOut(
            id=int(p.id),
            name=p.name,
            api_url=p.api_url,
            node_id=int(p.node_id),
            status=str(p.status.value if hasattr(p.status, "value") else p.status),
            is_test_panel=bool(p.is_test_panel),
            max_configs_per_panel=int(p.max_configs_per_panel)
            if p.max_configs_per_panel is not None
            else None,
            current_config_count=int(p.current_config_count),
            location=p.location,
            country_code=p.country_code,
            default_protocol=p.default_protocol,
            default_port=int(p.default_port),
        )
        for p in items
    ]


@router.post("/")
async def create_panel(
    body: PanelCreate,
    cur: CurrentAdmin = Depends(require_level(AdminLevel.SUPER_ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> PanelOut:
    p = Panel(**body.model_dump())
    db.add(p)
    await db.commit()
    await db.refresh(p)
    await audit(db, actor_user_id=cur.user.id, action="api.panels.create", meta={"id": int(p.id)})
    return PanelOut(
        id=int(p.id),
        name=p.name,
        api_url=p.api_url,
        node_id=int(p.node_id),
        status=str(p.status.value if hasattr(p.status, "value") else p.status),
        is_test_panel=bool(p.is_test_panel),
        max_configs_per_panel=int(p.max_configs_per_panel)
        if p.max_configs_per_panel is not None
        else None,
        current_config_count=int(p.current_config_count),
        location=p.location,
        country_code=p.country_code,
        default_protocol=p.default_protocol,
        default_port=int(p.default_port),
    )


@router.patch("/{panel_id}")
async def update_panel(
    panel_id: int,
    body: PanelUpdate,
    cur: CurrentAdmin = Depends(require_level(AdminLevel.SUPER_ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> PanelOut:
    p = await db.get(Panel, panel_id)
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
        action="api.panels.update",
        meta={"id": int(p.id), "fields": list(data.keys())},
    )
    return PanelOut(
        id=int(p.id),
        name=p.name,
        api_url=p.api_url,
        node_id=int(p.node_id),
        status=str(p.status.value if hasattr(p.status, "value") else p.status),
        is_test_panel=bool(p.is_test_panel),
        max_configs_per_panel=int(p.max_configs_per_panel)
        if p.max_configs_per_panel is not None
        else None,
        current_config_count=int(p.current_config_count),
        location=p.location,
        country_code=p.country_code,
        default_protocol=p.default_protocol,
        default_port=int(p.default_port),
    )


@router.post("/{panel_id}/sync-config-count")
async def sync_config_count(
    panel_id: int,
    cur: CurrentAdmin = Depends(require_level(AdminLevel.SUPER_ADMIN)),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """Sync panel config count with actual count of active services."""
    try:
        count = await sync_panel_config_count(db, panel_id=panel_id)
        await audit(
            db,
            actor_user_id=cur.user.id,
            action="api.panels.sync_config_count",
            meta={"panel_id": panel_id, "count": count},
        )
        return {"panel_id": panel_id, "config_count": count, "status": "synced"}
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
