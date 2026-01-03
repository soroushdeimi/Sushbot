"""Cron job interval management (ENV + runtime settings)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import settings
from services.runtime_settings import get_setting


async def get_cron_interval(db: AsyncSession, *, job_name: str, default_seconds: int) -> int:
    """Get cron interval for a job (from runtime settings or ENV default)."""
    key = f"cron_{job_name}_interval_seconds"
    val = await get_setting(db, key)
    if val:
        try:
            return int(val)
        except Exception:
            pass
    return default_seconds


# Job defaults (can be overridden via runtime settings)
JOB_DEFAULTS: dict[str, int] = {
    "usage_sync": settings.usage_sync_interval_seconds,
    "reminders": 600,  # 10 minutes
    "cleanup": 3600,  # 1 hour
    "admin_daily_report": 86400,  # 24 hours
    "payment_reconcile": settings.payment_reconcile_interval_seconds,
}
