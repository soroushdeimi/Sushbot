"""Programmatic Alembic migration runner (for reliable container startup)."""

from __future__ import annotations

import asyncio
from pathlib import Path

from alembic import command
from alembic.config import Config
from loguru import logger

from config.settings import settings


def run_migrations_sync() -> None:
    """Run `alembic upgrade head` using local alembic.ini."""
    if not settings.run_migrations_on_startup:
        return
    ini = Path(__file__).resolve().parent.parent / "alembic.ini"
    if not ini.exists():
        logger.warning("alembic.ini not found; skipping migrations")
        return
    cfg = Config(str(ini))
    logger.info("Running migrations (alembic upgrade head)...")
    command.upgrade(cfg, "head")
    logger.info("Migrations complete")


async def run_migrations() -> None:
    """Async-safe wrapper (runs migrations in a thread to avoid event-loop conflicts)."""
    await asyncio.to_thread(run_migrations_sync)
