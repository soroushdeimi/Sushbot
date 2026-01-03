"""Service transfer and location change operations."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from api.audit import audit
from config.features import is_enabled
from database.models import Panel, Service, ServiceStatus, User
from integrations.base import UserStats
from integrations.exceptions import PanelError, PanelConnectionError, PanelUserNotFoundError
from integrations.factory import PanelFactory, PanelType
from integrations.pasarguard.service import PasarGuardService
from integrations.marzban.service import MarzbanService


async def transfer_service(
    db: AsyncSession,
    *,
    service_id: int,
    new_user_id: int,
    admin_id: int,
    reason: str | None = None,
) -> dict[str, Any]:
    """Transfer service ownership from current user to new user."""
    if not is_enabled("service_transfer"):
        raise ValueError("Service transfer feature disabled")

    service = await db.get(Service, service_id)
    if not service:
        raise ValueError("Service not found")

    if service.status != ServiceStatus.ACTIVE:
        raise ValueError(f"Service {service_id} is not active (status: {service.status})")

    new_user = await db.get(User, new_user_id)
    if not new_user:
        raise ValueError("New user not found")

    old_user_id = service.user_id
    if old_user_id == new_user_id:
        raise ValueError("Cannot transfer service to the same user")

    # Update service ownership
    service.user_id = new_user_id
    service.notes = (
        (service.notes or "")
        + f"\n[Transferred from user_id={old_user_id} to user_id={new_user_id} at {datetime.utcnow().isoformat()} by admin_id={admin_id}. Reason: {reason or 'N/A'}]"
    )
    await db.commit()

    # Audit log entry
    await audit(
        db,
        actor_user_id=admin_id,
        action="service.transfer",
        entity_type="service",
        entity_id=str(service_id),
        meta={
            "old_user_id": old_user_id,
            "new_user_id": new_user_id,
            "reason": reason,
        },
    )

    logger.info(f"Transferred service_id={service_id} from user_id={old_user_id} to user_id={new_user_id} admin_id={admin_id}")
    return {
        "status": "transferred",
        "service_id": service_id,
        "old_user_id": old_user_id,
        "new_user_id": new_user_id,
    }


async def _migrate_pasarguard_location(
    panel_service: PasarGuardService,
    service: Service,
    new_inbound_tag: str,
    user_stats: UserStats,
) -> None:
    """
    Migrate PasarGuard user to new inbound.
    
    Strategy:
    1. Create user in new inbound with same credentials (expire_ts, data_limit_bytes, protocol)
    2. User will be automatically added to the new inbound's group
    3. Note: PasarGuard allows users in multiple groups, so old access remains
    """
    # Create a new PasarGuardService instance with the new inbound_tag
    # We need to create user in the new inbound
    from integrations.pasarguard.service import PasarGuardService
    
    # Create temporary service instance for new inbound
    new_panel_service = PasarGuardService(
        panel_name=panel_service.panel_name,
        node_id=panel_service.node_id,
        inbound_tag=new_inbound_tag,
    )
    
    try:
        # Create user in new inbound (preserves credentials and settings)
        await new_panel_service.create_user(
            username=service.client_email,
            expire_ts=user_stats.expire_ts,
            data_limit_bytes=user_stats.data_limit_bytes,
            protocol=service.protocol,
        )
        logger.info(f"Created user {service.client_email} in new inbound {new_inbound_tag}")
    finally:
        await new_panel_service.close()


async def _migrate_marzban_location(
    panel_service: MarzbanService,
    service: Service,
    new_inbound_tag: str,
    user_stats: UserStats,
) -> None:
    """
    Migrate Marzban user to new inbound.
    
    Strategy:
    1. Delete user from old location
    2. Create user in new location with preserved stats
    """
    try:
        # Delete user from old location
        await panel_service.delete_user(username=service.client_email)
        logger.info(f"Deleted user {service.client_email} from old location")
    except PanelUserNotFoundError:
        # User might not exist in old location, continue anyway
        logger.warning(f"User {service.client_email} not found in old location, continuing migration")
    
    # Create user in new location
    await panel_service.create_user(
        username=service.client_email,
        expire_ts=user_stats.expire_ts,
        data_limit_bytes=user_stats.data_limit_bytes,
        protocol=service.protocol,
    )
    logger.info(f"Created user {service.client_email} in new location with inbound_tag {new_inbound_tag}")


async def change_service_location(
    db: AsyncSession,
    *,
    service_id: int,
    new_inbound_tag: str,
    admin_id: int,
    reason: str | None = None,
) -> dict[str, Any]:
    """Change service location by migrating to a different inbound in PasarGuard."""
    if not is_enabled("service_location_change"):
        raise ValueError("Service location change feature disabled")

    service = await db.get(Service, service_id)
    if not service:
        raise ValueError("Service not found")

    if service.status != ServiceStatus.ACTIVE:
        raise ValueError(f"Service {service_id} is not active (status: {service.status})")

    panel = await db.get(Panel, service.panel_id)
    if not panel:
        raise ValueError("Panel not found for service")

    panel_service = None
    try:
        panel_service = await PanelFactory.create_panel(panel)
        
        # Get current user data from panel
        try:
            user_stats = await panel_service.get_user_stats(username=service.client_email)
            expire_ts = user_stats.expire_ts
            data_limit_bytes = user_stats.data_limit_bytes
        except PanelConnectionError as e:
            logger.error(f"Cannot connect to panel {panel.name} to get user stats for service_id={service_id}: {e}")
            raise ValueError(f"Cannot connect to panel {panel.name}. Please check panel configuration.") from e
        except (PanelError, PanelUserNotFoundError) as e:
            logger.error(f"Panel error getting user stats for service_id={service_id} (user={service.client_email}): {e}")
            raise ValueError(f"Failed to get user information from panel {panel.name}: {e}") from e

        # Migrate user to new location (panel-specific)
        try:
            panel_type_str = panel.type or "pasarguard"
            try:
                panel_type = PanelType(panel_type_str.lower())
            except ValueError:
                raise ValueError(f"Unsupported panel type: {panel_type_str}")

            if panel_type == PanelType.PASARGUARD:
                await _migrate_pasarguard_location(panel_service, service, new_inbound_tag, user_stats)
            elif panel_type == PanelType.MARZBAN:
                await _migrate_marzban_location(panel_service, service, new_inbound_tag, user_stats)
            else:
                raise ValueError(f"Location change not supported for panel type: {panel_type}")
        except PanelError as e:
            logger.error(f"Failed to migrate service_id={service_id} to new location: {e}")
            raise ValueError(f"Failed to migrate service to new location: {e}") from e

        # Update service record
        # Note: Service model doesn't have inbound_tag field, so we track it in notes
        service.notes = (
            (service.notes or "")
            + f"\n[Location changed to inbound_tag={new_inbound_tag} at {datetime.utcnow().isoformat()} by admin_id={admin_id}. Reason: {reason or 'N/A'}]"
        )
        await db.commit()

        # Audit log entry
        await audit(
            db,
            actor_user_id=admin_id,
            action="service.location_change",
            entity_type="service",
            entity_id=str(service_id),
            meta={
                "new_inbound_tag": new_inbound_tag,
                "reason": reason,
            },
        )

        logger.info(f"Changed location for service_id={service_id} to inbound_tag={new_inbound_tag} admin_id={admin_id}")
        return {
            "status": "location_changed",
            "service_id": service_id,
            "new_inbound_tag": new_inbound_tag,
        }
    except Exception as e:
        logger.error(f"Unexpected error changing service location for service_id={service_id}: {e}", exc_info=True)
        raise
    finally:
        if panel_service:
            try:
                await panel_service.close()
            except Exception as e:
                logger.warning(f"Error closing panel service for panel {panel.name}: {e}")

