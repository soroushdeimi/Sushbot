"""Trial account creation logic (shared by /trial and UI buttons)."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from loguru import logger

from config.settings import settings
from database.models import Panel, PanelStatus, Service, ServiceStatus, TrialAccount, User
from database.models.service import ServiceType
from integrations.exceptions import PanelError, PanelConnectionError
from integrations.pasarguard import create_service_config
from services.panel_utils import check_panel_capacity
from services.subscription import ensure_service_sub_token
from utils.panel_username import make_panel_username


class TrialError(RuntimeError):
    pass


async def create_trial_for_user(db: AsyncSession, *, user: User) -> tuple[TrialAccount, Service]:
    now = datetime.utcnow()

    res = await db.execute(
        select(TrialAccount).where(
            TrialAccount.user_id == user.id,
            TrialAccount.is_used.is_(False),
            TrialAccount.expiry_date > now,
        )
    )
    active_trial = res.scalars().first()
    if active_trial:
        raise TrialError("active_trial_exists")

    res = await db.execute(select(TrialAccount).where(TrialAccount.user_id == user.id, TrialAccount.is_used.is_(True)))
    used_trial = res.scalars().first()
    if used_trial:
        raise TrialError("trial_already_used")

    expiry_date = now + timedelta(days=settings.trial_duration_days)
    trial = TrialAccount(
        user_id=user.id,
        duration_days=settings.trial_duration_days,
        traffic_gb=settings.trial_traffic_gb,
        start_date=now,
        expiry_date=expiry_date,
        protocol=settings.pasarguard_default_protocol,
    )
    db.add(trial)
    await db.commit()

    # Select panel for trial: prefer test panel if available, otherwise use default
    trial_panel_id = 1  # Default fallback
    res = await db.execute(
        select(Panel.id)
        .where(
            Panel.is_test_panel.is_(True),
            Panel.status == PanelStatus.ACTIVE,
        )
        .order_by(Panel.id.asc())
        .limit(1)
    )
    test_panel = res.scalar_one_or_none()
    if test_panel:
        # Check if test panel has capacity
        has_capacity, error_msg = await check_panel_capacity(db, panel_id=test_panel)
        if has_capacity:
            trial_panel_id = test_panel
        else:
            logger.warning(f"Test panel {test_panel} is at capacity, falling back to default panel")
    else:
        logger.debug("No test panel found, using default panel for trial")

    username = make_panel_username(telegram_username=user.username, user_id=user.id, suffix="trial")
    cfg = await create_service_config(
        user_email=username,
        protocol=settings.pasarguard_default_protocol,
        port=settings.pasarguard_default_port,
        duration_days=settings.trial_duration_days,
        traffic_gb=settings.trial_traffic_gb,
        panel_id=trial_panel_id,
    )

    # Check panel capacity before creating service (double-check)
    panel_id = cfg.get("panel_id") or trial_panel_id
    has_capacity, error_msg = await check_panel_capacity(db, panel_id=panel_id)
    if not has_capacity:
        raise TrialError(f"Panel is at capacity: {error_msg}")

    svc_expiry = now + timedelta(days=settings.trial_duration_days)
    service = Service(
        user_id=user.id,
        service_type=ServiceType.TRIAL,
        status=ServiceStatus.ACTIVE,
        panel_id=cfg.get("panel_id") or 1,
        inbound_id=cfg.get("inbound_id"),
        client_email=username,
        protocol=cfg.get("protocol") or settings.pasarguard_default_protocol,
        server_address=cfg.get("server_address") or "unknown",
        port=int(cfg.get("port") or settings.pasarguard_default_port),
        total_traffic_gb=settings.trial_traffic_gb,
        used_traffic_gb=0.0,
        remaining_traffic_gb=float(settings.trial_traffic_gb),
        start_date=now,
        expiry_date=svc_expiry,
        is_unlimited=False,
        config_link=cfg["config_link"],
    )
    db.add(service)
    await db.commit()
    await db.refresh(service)

    try:
        await ensure_service_sub_token(db, service)
    except (PanelError, PanelConnectionError) as e:
        logger.warning(f"Panel error creating trial service subscription token: {e}")
        # Don't fail trial creation if subscription token fails
    except Exception as e:
        logger.error(f"Unexpected error creating trial service subscription token: {e}", exc_info=True)
        # Still don't fail - subscription token is optional

    trial.service_id = service.id
    trial.config_link = cfg["config_link"]
    trial.is_used = True
    db.add(trial)
    await db.commit()
    await db.refresh(trial)
    return trial, service


