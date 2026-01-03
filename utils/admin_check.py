"""Unified admin authorization helpers for bot handlers.

This module is imported by multiple handlers (e.g. admin settings) and acts as the
single source of truth for admin checks.

Admin sources:
- .env (settings.all_admin_ids): super admins / static admins
- DB: users.role == ADMIN plus an active row in admins table

Note: We intentionally treat .env admins as active admins even if no DB Admin row exists.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from telegram import Update
from telegram.ext import ContextTypes

from config.settings import settings
from database.models import Admin, AdminLevel, User, UserRole
from database.session import get_db


async def get_admin(db: AsyncSession, telegram_user_id: int) -> Admin | None:
    """Return an Admin object if the user is allowed admin access.

    This unifies both environment-based admins and DB-promoted admins.
    """
    # Env-based admins always pass
    if settings.is_super_admin(telegram_user_id):
        return Admin(user_id=telegram_user_id, level=AdminLevel.SUPER_ADMIN, is_active=True)
    if settings.is_env_admin(telegram_user_id):
        return Admin(user_id=telegram_user_id, level=AdminLevel.ADMIN, is_active=True)

    # DB-based admins must have role + active admin row
    u = await db.get(User, telegram_user_id)
    if not u or u.role != UserRole.ADMIN:
        return None

    res = await db.execute(
        select(Admin).where(Admin.user_id == telegram_user_id, Admin.is_active.is_(True))
    )
    return res.scalars().first()


async def is_admin(db: AsyncSession, telegram_user_id: int) -> bool:
    """True if user is an admin by env or DB."""
    return (await get_admin(db, telegram_user_id)) is not None


def require_admin[F: Callable[..., Awaitable[Any]]](func: F) -> F:
    """Decorator for PTB handlers requiring admin access."""

    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE, *args: Any, **kwargs: Any):
        tg_user = update.effective_user
        user_id = getattr(tg_user, "id", None)
        if not user_id:
            return

        async for db in get_db():
            admin = await get_admin(db, int(user_id))
            if not admin:
                # Prefer replying in-place depending on update type
                if update.callback_query:
                    try:
                        await update.callback_query.answer("⛔️ دسترسی ندارید.", show_alert=True)
                    except Exception:
                        pass
                    try:
                        await update.callback_query.edit_message_text("⛔️ دسترسی ندارید.")
                    except Exception:
                        pass
                elif update.message:
                    await update.message.reply_text("⛔️ دسترسی ندارید.")
                return

        return await func(update, context, *args, **kwargs)

    return wrapper  # type: ignore[return-value]
