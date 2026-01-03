"""Fulfillment for paid purchases: provision new service or apply to existing service."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from loguru import logger

from database.models import Panel, Purchase, Service
from database.models.purchase import PurchaseType
from database.models.wallet import WalletTransaction, WalletTxType
from integrations.exceptions import PanelError, PanelConnectionError, PanelUserNotFoundError
from integrations.factory import PanelFactory
from services.provisioning import provision_purchase
from services.wallet import apply_wallet_tx


async def fulfill_purchase(db: AsyncSession, *, purchase: Purchase) -> Service | None:
    """
    Fulfill a completed purchase based on purchase type.
    
    This function handles different types of purchases:
    - NEW: Provisions a new VPN service
    - RENEWAL: Extends expiration date on existing service
    - ADDITIONAL_VOLUME: Increases data limit on existing service
    - WALLET_TOPUP: Credits user wallet (returns None)

    Args:
        db: Database session for database operations
        purchase: Purchase object to fulfill. Must have purchase_type and status COMPLETED.

    Returns:
        Service object if purchase type creates/modifies a service, None for wallet top-ups.

    Raises:
        ValueError: If purchase/service/panel is invalid or missing.
        PanelError: If panel operations fail.
        PanelConnectionError: If cannot connect to panel.

    Note:
        For WALLET_TOPUP purchases, this function is idempotent and will not create
        duplicate wallet transactions for the same purchase_id.
    """
    if purchase.purchase_type == PurchaseType.WALLET_TOPUP:
        # Idempotent wallet credit (keyed by purchase id)
        ref = f"topup_purchase_{purchase.id}"
        res = await db.execute(select(WalletTransaction).where(WalletTransaction.user_id == purchase.user_id, WalletTransaction.ref == ref))
        existing = res.scalars().first()
        if existing:
            return None

        amt = int(purchase.final_amount)
        if amt <= 0:
            return None
        await apply_wallet_tx(
            db,
            user_id=purchase.user_id,
            amount=amt,
            tx_type=WalletTxType.TOPUP,
            ref=ref,
            note=f"Wallet top-up from purchase_id={purchase.id}",
        )
        logger.info(f"Wallet topup credited user_id={purchase.user_id} amount={amt} purchase_id={purchase.id}")
        return None

    if purchase.purchase_type == PurchaseType.NEW or not purchase.service_id:
        return await provision_purchase(db, purchase=purchase)

    svc = await db.get(Service, purchase.service_id)
    if not svc:
        # Fallback: provision new service if target missing
        return await provision_purchase(db, purchase=purchase)

    # Get panel and create service using factory
    panel = await db.get(Panel, svc.panel_id)
    if not panel:
        raise ValueError(f"Panel {svc.panel_id} not found for service")

    panel_service = None
    try:
        panel_service = await PanelFactory.create_panel(panel)
        
        if purchase.purchase_type == PurchaseType.RENEWAL:
            now = datetime.utcnow()
            base = svc.expiry_date if svc.expiry_date and svc.expiry_date > now else now
            new_exp = base + timedelta(days=int(purchase.duration_days))
            try:
                await panel_service.renew_user(username=svc.client_email, expire_ts=int(new_exp.timestamp()))
                svc.expiry_date = new_exp
                await db.commit()
                logger.info(f"Renewed service_id={svc.id} to {new_exp.isoformat()} by purchase_id={purchase.id}")
            except PanelConnectionError as e:
                await db.rollback()
                logger.error(f"Cannot connect to panel {panel.name} to renew service_id={svc.id} for purchase_id={purchase.id}: {e}")
                raise ValueError(f"Cannot connect to panel {panel.name}. Please check panel configuration.") from e
            except (PanelError, PanelUserNotFoundError) as e:
                await db.rollback()
                logger.error(f"Panel error renewing service_id={svc.id} (user={svc.client_email}) for purchase_id={purchase.id}: {e}")
                raise ValueError(f"Failed to renew service on panel {panel.name}: {e}") from e
            except Exception as e:
                await db.rollback()
                logger.error(f"Unexpected error renewing service_id={svc.id} for purchase_id={purchase.id}: {e}", exc_info=True)
                raise
            return svc

        if purchase.purchase_type == PurchaseType.ADDITIONAL_VOLUME:
            add_gb = int(purchase.traffic_gb)
            if add_gb > 0 and not svc.is_unlimited:
                try:
                    await panel_service.add_traffic(username=svc.client_email, add_bytes=add_gb * (1024**3))
                    svc.total_traffic_gb = int(svc.total_traffic_gb or 0) + add_gb
                    if svc.remaining_traffic_gb is not None:
                        svc.remaining_traffic_gb = float(svc.remaining_traffic_gb) + float(add_gb)
                    await db.commit()
                    logger.info(f"Added traffic to service_id={svc.id} +{add_gb}GB purchase_id={purchase.id}")
                except PanelConnectionError as e:
                    await db.rollback()
                    logger.error(f"Cannot connect to panel {panel.name} to add traffic to service_id={svc.id} for purchase_id={purchase.id}: {e}")
                    raise ValueError(f"Cannot connect to panel {panel.name}. Please check panel configuration.") from e
                except (PanelError, PanelUserNotFoundError) as e:
                    await db.rollback()
                    logger.error(f"Panel error adding traffic to service_id={svc.id} (user={svc.client_email}) for purchase_id={purchase.id}: {e}")
                    raise ValueError(f"Failed to add traffic on panel {panel.name}: {e}") from e
                except Exception as e:
                    await db.rollback()
                    logger.error(f"Unexpected error adding traffic to service_id={svc.id} for purchase_id={purchase.id}: {e}", exc_info=True)
                    raise
            return svc

        return svc
    except Exception as e:
        logger.error(f"Unexpected error during fulfillment for purchase {purchase.id}: {e}", exc_info=True)
        raise
    finally:
        if panel_service:
            try:
                await panel_service.close()
            except Exception as e:
                logger.warning(f"Error closing panel service for panel {panel.name}: {e}")



