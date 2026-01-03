"""Refund and service removal operations."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.audit import audit
from config.features import is_enabled
from database.models import Panel, Purchase, PurchaseStatus, Service, ServiceStatus
from database.models.wallet import WalletTransaction, WalletTxType
from integrations.exceptions import PanelConnectionError, PanelError, PanelUserNotFoundError
from integrations.factory import PanelFactory
from services.wallet import apply_wallet_tx


async def refund_purchase(
    db: AsyncSession,
    *,
    purchase_id: int,
    admin_id: int,
    reason: str | None = None,
) -> dict[str, Any]:
    """Refund a completed purchase: reverse fulfillment, credit wallet, audit log."""
    if not is_enabled("refunds"):
        raise ValueError("Refunds feature disabled")

    purchase = await db.get(Purchase, purchase_id)
    if not purchase:
        raise ValueError("Purchase not found")

    if purchase.status != PurchaseStatus.COMPLETED:
        raise ValueError(f"Purchase {purchase_id} is not completed (status: {purchase.status})")

    # Check if already refunded (idempotent)
    res = await db.execute(
        select(WalletTransaction).where(
            WalletTransaction.user_id == purchase.user_id,
            WalletTransaction.tx_type == WalletTxType.REFUND,
            WalletTransaction.ref == f"refund_purchase_{purchase_id}",
        )
    )
    existing_refund = res.scalars().first()
    if existing_refund:
        return {"status": "already_refunded", "refund_tx_id": existing_refund.id}

    # Reverse service fulfillment if applicable
    if purchase.service_id:
        svc = await db.get(Service, purchase.service_id)
        if svc and svc.status == ServiceStatus.ACTIVE:
            # Optionally remove service from panel (if feature enabled)
            if is_enabled("service_removal"):
                panel = await db.get(Panel, svc.panel_id)
                if panel:
                    panel_service = None
                    try:
                        panel_service = await PanelFactory.create_panel(panel)
                        try:
                            await panel_service.delete_user(username=svc.client_email)
                        except PanelUserNotFoundError:
                            # User already deleted on panel, continue
                            logger.warning(
                                f"User {svc.client_email} not found on panel {panel.name} during refund, already deleted"
                            )
                        except (PanelConnectionError, PanelError) as e:
                            logger.warning(
                                f"Panel error deleting user {svc.client_email} from panel {panel.name} during refund: {e}"
                            )
                            # Continue with refund even if panel operation fails
                        except Exception as e:
                            logger.warning(
                                f"Unexpected error deleting panel user during refund: {e}",
                                exc_info=True,
                            )
                    except Exception as e:
                        logger.warning(f"Failed to create panel service for refund: {e}")
                    finally:
                        if panel_service:
                            try:
                                await panel_service.close()
                            except Exception as e:
                                logger.warning(f"Error closing panel service during refund: {e}")

            svc.status = ServiceStatus.CANCELLED
            svc.notes = (svc.notes or "") + f"\n[Refunded at {datetime.utcnow().isoformat()}]"

    # Credit user wallet
    refund_amount = int(purchase.final_amount)
    tx = await apply_wallet_tx(
        db,
        user_id=purchase.user_id,
        amount=refund_amount,
        tx_type=WalletTxType.REFUND,
        ref=f"refund_purchase_{purchase_id}",
        note=f"Refund for purchase_id={purchase_id} by admin_id={admin_id}. Reason: {reason or 'N/A'}",
    )

    # Mark purchase as refunded
    purchase.status = PurchaseStatus.REFUNDED
    await db.commit()

    # Audit log entry
    await audit(
        db,
        actor_user_id=admin_id,
        action="purchase.refund",
        entity_type="purchase",
        entity_id=str(purchase_id),
        meta={
            "refund_amount": refund_amount,
            "refund_tx_id": tx.id,
            "reason": reason,
            "service_id": purchase.service_id,
        },
    )

    logger.info(f"Refunded purchase_id={purchase_id} amount={refund_amount} admin_id={admin_id}")
    return {
        "status": "refunded",
        "purchase_id": purchase_id,
        "refund_amount": refund_amount,
        "refund_tx_id": tx.id,
    }


async def remove_service(
    db: AsyncSession,
    *,
    service_id: int,
    admin_id: int,
    reason: str | None = None,
) -> dict[str, Any]:
    """Remove/deprovision a service from PasarGuard and mark as cancelled."""
    if not is_enabled("service_removal"):
        raise ValueError("Service removal feature disabled")

    service = await db.get(Service, service_id)
    if not service:
        raise ValueError("Service not found")

    if service.status == ServiceStatus.CANCELLED:
        return {"status": "already_removed", "service_id": service_id}

    # Remove from panel
    panel = await db.get(Panel, service.panel_id)
    if panel:
        panel_service = None
        try:
            panel_service = await PanelFactory.create_panel(panel)
            try:
                await panel_service.delete_user(username=service.client_email)
            except PanelUserNotFoundError:
                # User already deleted on panel, continue
                logger.warning(
                    f"User {service.client_email} not found on panel {panel.name}, already deleted"
                )
            except PanelConnectionError as e:
                logger.error(
                    f"Cannot connect to panel {panel.name} to remove user for service_id={service_id}: {e}"
                )
                # Continue with service cancellation even if panel is unreachable
            except PanelError as e:
                logger.error(
                    f"Panel error removing user {service.client_email} from panel {panel.name} for service_id={service_id}: {e}"
                )
                # Continue with service cancellation
            except Exception as e:
                logger.error(
                    f"Unexpected error removing panel user for service_id={service_id}: {e}",
                    exc_info=True,
                )
                # Continue with service cancellation
        except Exception as e:
            logger.error(
                f"Failed to create panel service for panel {panel.name} to remove service_id={service_id}: {e}"
            )
            # Continue with service cancellation
        finally:
            if panel_service:
                try:
                    await panel_service.close()
                except Exception as e:
                    logger.warning(f"Error closing panel service for panel {panel.name}: {e}")

    # Mark service as cancelled
    service.status = ServiceStatus.CANCELLED
    service.notes = (
        (service.notes or "")
        + f"\n[Removed at {datetime.utcnow().isoformat()} by admin_id={admin_id}. Reason: {reason or 'N/A'}]"
    )
    await db.commit()

    # Audit log entry
    await audit(
        db,
        actor_user_id=admin_id,
        action="service.remove",
        entity_type="service",
        entity_id=str(service_id),
        meta={
            "user_id": service.user_id,
            "panel_id": service.panel_id,
            "reason": reason,
        },
    )

    logger.info(f"Removed service_id={service_id} admin_id={admin_id}")
    return {"status": "removed", "service_id": service_id}
