"""User management routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.audit import audit
from api.deps import CurrentAdmin, get_current_admin
from database.models import User
from database.session import get_db

router = APIRouter()


class UserOut(BaseModel):
    id: int
    telegram_id: int
    username: str | None
    role: str
    status: str
    balance: int


@router.get("/")
async def list_users(
    cur: CurrentAdmin = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
    limit: int = 50,
    offset: int = 0,
) -> list[UserOut]:
    """List all users."""
    res = await db.execute(select(User).order_by(User.id.desc()).limit(limit).offset(offset))
    users = list(res.scalars().all())
    await audit(
        db,
        actor_user_id=cur.user.id,
        action="api.users.list",
        meta={"limit": limit, "offset": offset},
    )
    return [
        UserOut(
            id=int(u.id),
            telegram_id=int(u.telegram_id),
            username=u.username,
            role=str(u.role.value if hasattr(u.role, "value") else u.role),
            status=str(u.status.value if hasattr(u.status, "value") else u.status),
            balance=int(u.balance),
        )
        for u in users
    ]
