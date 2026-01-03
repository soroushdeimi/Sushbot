"""FastAPI dependencies: auth, RBAC, and helpers."""

from __future__ import annotations

from dataclasses import dataclass

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select

from database.models import Admin, AdminLevel, User
from database.session import get_db
from utils.security import verify_token

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/auth/login")


@dataclass(frozen=True)
class CurrentAdmin:
    user: User
    admin: Admin


async def get_current_admin(
    token: str = Depends(oauth2_scheme), db=Depends(get_db)
) -> CurrentAdmin:
    payload = verify_token(token)
    if not payload or "sub" not in payload:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
    try:
        uid = int(payload["sub"])
    except Exception:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    user = await db.get(User, uid)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    res = await db.execute(select(Admin).where(Admin.user_id == uid, Admin.is_active.is_(True)))
    admin = res.scalars().first()
    if not admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    return CurrentAdmin(user=user, admin=admin)


def require_level(*levels: AdminLevel):
    async def _dep(cur: CurrentAdmin = Depends(get_current_admin)) -> CurrentAdmin:
        if cur.admin.level not in levels:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient privileges"
            )
        return cur

    return _dep
