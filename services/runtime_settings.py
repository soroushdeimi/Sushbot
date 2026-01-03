"""Runtime settings stored in DB (admin-managed)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import AppSetting


async def get_setting(db: AsyncSession, key: str) -> str | None:
    res = await db.execute(select(AppSetting).where(AppSetting.key == key))
    s = res.scalars().first()
    return s.value if s else None


async def set_setting(db: AsyncSession, *, key: str, value: str) -> None:
    res = await db.execute(select(AppSetting).where(AppSetting.key == key))
    s = res.scalars().first()
    if s:
        s.value = value
    else:
        db.add(AppSetting(key=key, value=value))
    await db.commit()
