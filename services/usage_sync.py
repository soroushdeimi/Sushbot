"""Periodic usage sync from VPN panels into bot DB."""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime

from loguru import logger
from sqlalchemy import select
from telegram.ext import ContextTypes

from config.settings import settings
from database.models import Panel, Service, ServiceStatus
from database.session import AsyncSessionLocal
from integrations.factory import PanelFactory


def _bytes_to_gb(x: int) -> float:
    return x / (1024**3)


async def job_sync_usage(context: ContextTypes.DEFAULT_TYPE) -> None:
    """JobQueue callback: sync a batch of active services."""
    if not settings.usage_sync_enabled:
        return

    async with AsyncSessionLocal() as db:
        res = await db.execute(
            select(Service)
            .where(Service.status == ServiceStatus.ACTIVE)
            .order_by(Service.id.desc())
            .limit(settings.usage_sync_batch_size)
        )
        services = list(res.scalars().all())

        if not services:
            return

        # Group services by panel_id for efficient panel service creation
        services_by_panel: dict[int, list[Service]] = defaultdict(list)
        for svc in services:
            if svc.panel_id:
                services_by_panel[svc.panel_id].append(svc)

        # Sync each panel's services
        for panel_id, panel_services in services_by_panel.items():
            panel = await db.get(Panel, panel_id)
            if not panel:
                logger.warning(
                    f"Panel {panel_id} not found, skipping {len(panel_services)} services"
                )
                continue

            panel_service = None
            try:
                panel_service = await PanelFactory.create_panel(panel)
                if not await panel_service.health_check():
                    logger.warning(f"Panel {panel_id} health check failed, skipping")
                    continue

                for svc in panel_services:
                    try:
                        user_stats = await panel_service.get_user_stats(username=svc.client_email)

                        used_b = user_stats.used_traffic_bytes
                        limit_b = user_stats.data_limit_bytes
                        svc.used_traffic_gb = _bytes_to_gb(used_b)

                        if limit_b is None:
                            svc.is_unlimited = True
                            svc.total_traffic_gb = 0
                            svc.remaining_traffic_gb = None
                        else:
                            limit_bi = int(limit_b)
                            svc.is_unlimited = False
                            svc.total_traffic_gb = limit_bi // (1024**3)
                            svc.remaining_traffic_gb = max(0.0, _bytes_to_gb(limit_bi - used_b))

                        # Update expiry date
                        if user_stats.expire_ts:
                            svc.expiry_date = datetime.fromtimestamp(
                                user_stats.expire_ts, tz=UTC
                            ).replace(tzinfo=None)

                        # Update status
                        status = user_stats.status.lower()
                        if status in {"expired"}:
                            svc.status = ServiceStatus.EXPIRED
                        elif status in {"disabled", "on_hold"}:
                            svc.status = ServiceStatus.SUSPENDED

                    except Exception as e:
                        logger.warning(
                            f"Usage sync failed for service_id={svc.id} user={svc.client_email}: {e}"
                        )
                        continue

            except Exception as e:
                logger.error(f"Failed to sync panel {panel_id}: {e}", exc_info=True)
            finally:
                if panel_service:
                    await panel_service.close()

        await db.commit()
