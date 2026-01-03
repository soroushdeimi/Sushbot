"""Persistent bot state machine (Mirza-style, but JSON payload and locking)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import re
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import User, UserState
from database.session import AsyncSessionLocal


@dataclass(frozen=True)
class State:
    user_id: int
    step: str
    payload: dict[str, Any]
    locked_until: datetime | None
    lock_reason: str | None


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)

_STEP_RE = re.compile(r"^[a-z0-9][a-z0-9_.-]{0,127}$")


def _validate_step(step: str) -> str:
    s = (step or "").strip().lower()
    if not _STEP_RE.fullmatch(s):
        raise ValueError("Invalid step name")
    return s


async def _ensure_user(db: AsyncSession, user_id: int) -> None:
    u = await db.get(User, user_id)
    if u:
        return
    # Minimal placeholder user; /start will fill profile fields later.
    db.add(User(id=user_id, telegram_id=user_id, username=None))
    await db.flush()


async def get_state(user_id: int) -> State:
    async with AsyncSessionLocal() as db:
        await _ensure_user(db, user_id)
        st = await db.get(UserState, user_id)
        if not st:
            st = UserState(user_id=user_id, step="none", payload={})
            db.add(st)
            await db.commit()
            await db.refresh(st)
        return State(
            user_id=user_id,
            step=st.step,
            payload=dict(st.payload or {}),
            locked_until=st.locked_until,
            lock_reason=st.lock_reason,
        )


async def set_step(user_id: int, *, step: str, payload: dict[str, Any] | None = None) -> None:
    step = _validate_step(step)
    async with AsyncSessionLocal() as db:
        await _ensure_user(db, user_id)
        st = await db.get(UserState, user_id)
        if not st:
            st = UserState(user_id=user_id, step=step, payload=payload or {})
            db.add(st)
        else:
            st.step = step
            st.payload = payload or {}
        st.locked_until = None
        st.lock_reason = None
        await db.commit()


async def update_payload(user_id: int, patch: dict[str, Any]) -> None:
    async with AsyncSessionLocal() as db:
        await _ensure_user(db, user_id)
        st = await db.get(UserState, user_id)
        if not st:
            st = UserState(user_id=user_id, step="none", payload={})
            db.add(st)
            await db.flush()
        cur = dict(st.payload or {})
        cur.update(patch)
        st.payload = cur
        await db.commit()


async def clear_state(user_id: int) -> None:
    await set_step(user_id, step="none", payload={})


async def release_lock(user_id: int) -> None:
    async with AsyncSessionLocal() as db:
        await _ensure_user(db, user_id)
        st = await db.get(UserState, user_id)
        if not st:
            return
        st.locked_until = None
        st.lock_reason = None
        await db.commit()


async def try_lock(user_id: int, *, seconds: int, reason: str) -> bool:
    """Acquire a short lock; returns False if still locked."""
    now = _utcnow()
    until = now + timedelta(seconds=seconds)
    async with AsyncSessionLocal() as db:
        await _ensure_user(db, user_id)
        st = await db.get(UserState, user_id)
        if not st:
            st = UserState(user_id=user_id, step="none", payload={})
            db.add(st)
            await db.flush()
        if st.locked_until and st.locked_until > now:
            return False
        st.locked_until = until
        st.lock_reason = reason
        await db.commit()
        logger.debug(f"Locked user_state user_id={user_id} reason={reason} until={until.isoformat()}")
        return True


