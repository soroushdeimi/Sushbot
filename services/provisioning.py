"""Provisioning logic for turning a paid Purchase into an active Service."""

from __future__ import annotations

from datetime import datetime, timedelta

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import settings
from database.models import Panel, Product, Purchase, PurchaseStatus, Service, ServiceStatus, User
from database.models.service import ServiceType
from integrations.exceptions import PanelConnectionError, PanelError, PanelUserNotFoundError
from integrations.factory import PanelFactory
from services.panel_utils import (
    VPNProtocol,
    check_panel_capacity,
    get_protocol_params,
    validate_protocol_compatibility,
)
from services.subscription import ensure_service_sub_token
from utils.panel_username import make_panel_username


def normalize_protocol(protocol: str) -> str:
    """Normalize protocol string to lowercase and handle aliases.

    Panel APIs expect lowercase protocol names. This function ensures
    consistent protocol naming regardless of user input.

    Args:
        protocol: Raw protocol string (may be mixed case)

    Returns:
        Normalized lowercase protocol name

    Examples:
        >>> normalize_protocol("VLESS")
        'vless'
        >>> normalize_protocol("SS")
        'shadowsocks'
    """
    return VPNProtocol.normalize(protocol)


async def provision_purchase(db: AsyncSession, *, purchase: Purchase) -> Service:
    """
    Idempotently provision a service for a paid purchase.

    This function creates a VPN service on the configured panel for a completed purchase.
    It handles user creation on the panel, generates configuration links, and creates
    the service record in the database. The operation is idempotent - if a service
    already exists for this purchase, it returns the existing service.

    Assumes Purchase.status is COMPLETED (or being completed within same transaction).

    Args:
        db: Database session for database operations
        purchase: Purchase object to provision. Must have product_id and user_id.

    Returns:
        Service object that was created or already exists for this purchase.

    Raises:
        ValueError: If purchase/product/panel is invalid or missing required fields.
        PanelError: If panel operations fail (user creation, config generation).
        PanelConnectionError: If cannot connect to panel (network issues, panel down).

    Note:
        This function performs the following operations:
        1. Checks if service already exists (idempotency)
        2. Validates purchase and product
        3. Generates unique panel username
        4. Creates user on VPN panel
        5. Generates configuration link
        6. Creates service record in database
        7. Updates purchase with service_id
        8. Consumes inventory if applicable
    """
    if purchase.service_id:
        svc = await db.get(Service, purchase.service_id)
        if svc:
            return svc

    if not purchase.product_id:
        raise ValueError("Purchase has no product_id")

    product = await db.get(Product, purchase.product_id)
    if not product:
        raise ValueError(f"Product {purchase.product_id} not found for purchase")

    u = await db.get(User, purchase.user_id)
    tg_un = u.username if u else None
    username = make_panel_username(
        telegram_username=tg_un, user_id=purchase.user_id, suffix=str(product.id)
    )

    # Get panel and create service using factory
    panel = await db.get(Panel, product.panel_id)
    if not panel:
        raise ValueError(f"Panel {product.panel_id} not found for product {product.id}")

    # Check panel capacity before provisioning
    has_capacity, error_msg = await check_panel_capacity(db, panel_id=panel.id)
    if not has_capacity:
        raise ValueError(error_msg or f"Panel {panel.name} is at capacity")

    # Use the protocol from purchase (user's selection) not product (template)
    # This allows users to choose their preferred protocol for multi-protocol products
    raw_protocol = purchase.protocol or product.get_default_protocol()

    # CRITICAL: Normalize protocol to lowercase for panel API compatibility
    # Panel APIs (Marzban, X-UI, etc.) expect lowercase protocol names
    selected_protocol = normalize_protocol(raw_protocol)

    # Validate protocol is supported by this panel type before making API call
    panel_type = getattr(panel, "type", None) or "pasarguard"  # Default for legacy panels
    is_valid, validation_error = validate_protocol_compatibility(
        panel_type=panel_type,
        protocol=selected_protocol,
        strict=False,  # Don't fail for unknown panel types
    )
    if not is_valid:
        logger.warning(
            f"Protocol compatibility warning for purchase {purchase.id}: {validation_error}"
        )
        # Don't fail here - the panel might support it even if we don't know about it
        # Just log the warning for monitoring

    # Get protocol-specific parameters for proper config generation
    protocol_params = get_protocol_params(selected_protocol)
    default_flow = protocol_params.get("default_flow") if protocol_params else "xtls-rprx-vision"

    panel_service = None
    try:
        panel_service = await PanelFactory.create_panel(panel)

        # Calculate expiration timestamp
        expire_ts: int | None = None
        if product.duration_days and product.duration_days > 0:
            expire_ts = int((datetime.utcnow() + timedelta(days=product.duration_days)).timestamp())

        # Calculate data limit in bytes
        data_limit_bytes: int | None = None
        if product.traffic_gb and product.traffic_gb > 0:
            data_limit_bytes = int(product.traffic_gb * (1024**3))

        # Create user on panel
        try:
            await panel_service.create_user(
                username=username,
                expire_ts=expire_ts,
                data_limit_bytes=data_limit_bytes,
                protocol=selected_protocol,
                flow=default_flow or "xtls-rprx-vision",  # Pass flow for VLESS/Trojan
            )
        except PanelConnectionError as e:
            logger.error(
                f"Failed to connect to panel {panel.name} (id={panel.id}) for purchase {purchase.id}: {e}"
            )
            raise ValueError(
                f"Cannot connect to panel {panel.name}. Please check panel configuration."
            ) from e
        except PanelError as e:
            logger.error(
                f"Panel error creating user {username} on panel {panel.name} for purchase {purchase.id}: {e}"
            )
            raise ValueError(f"Failed to create user on panel {panel.name}: {e}") from e

        # Generate config link
        try:
            config_link = await panel_service.generate_config_link(
                username=username,
                protocol=selected_protocol,
            )
        except (PanelError, PanelUserNotFoundError) as e:
            logger.error(
                f"Failed to generate config link for user {username} on panel {panel.name}: {e}"
            )
            # Continue without config_link - service can still be created
            config_link = None

        # Get server address and port from panel or use defaults
        server_address = getattr(panel, "location", None) or "unknown"
        port = product.port if hasattr(product, "port") else panel.default_port

        cfg = {
            "inbound_id": None,  # Not used for all panels
            "inbound_tag": getattr(panel, "inbound_tag", "SUSH"),
            "client_email": username,
            "client_uuid": None,  # Extracted from proxy_settings if needed
            "config_link": config_link,
            "protocol": selected_protocol,  # Use user's selected protocol
            "server_address": server_address,
            "port": port,
            "panel_id": product.panel_id,
        }
    except Exception as e:
        logger.error(
            f"Unexpected error during provisioning for purchase {purchase.id}: {e}", exc_info=True
        )
        raise
    finally:
        if panel_service:
            try:
                await panel_service.close()
            except Exception as e:
                logger.warning(f"Error closing panel service for panel {panel.name}: {e}")

    now = datetime.utcnow()
    expiry = None
    if product.duration_days and product.duration_days > 0:
        expiry = now + timedelta(days=product.duration_days)

    svc = Service(
        user_id=purchase.user_id,
        service_type=ServiceType.VPN,
        status=ServiceStatus.ACTIVE,
        panel_id=product.panel_id,
        inbound_id=cfg.get("inbound_id"),
        client_email=username,
        protocol=selected_protocol,  # Use user's selected protocol from purchase
        server_address=cfg.get("server_address") or "unknown",
        port=int(cfg.get("port") or settings.pasarguard_default_port),
        total_traffic_gb=product.traffic_gb,
        used_traffic_gb=0.0,
        remaining_traffic_gb=None if product.traffic_gb == 0 else float(product.traffic_gb),
        start_date=now,
        expiry_date=expiry,
        is_unlimited=product.traffic_gb == 0,
        config_link=cfg.get("config_link"),
        notes=f"Provisioned from purchase_id={purchase.id}",
    )
    db.add(svc)

    # Inventory: consume reserved unit on successful provisioning (before commit).
    if product.stock_quantity is not None:
        from config.features import is_enabled

        if is_enabled("inventory"):
            from services.inventory import consume_stock

            await consume_stock(db, product_id=product.id, qty=1)

    # Update purchase
    purchase.service_id = svc.id
    purchase.status = PurchaseStatus.COMPLETED
    purchase.completed_at = now

    # Single commit for all operations (atomic transaction)
    await db.commit()
    await db.refresh(svc)

    try:
        await ensure_service_sub_token(db, svc)
    except Exception:
        # best-effort, non-critical
        pass

    logger.info(f"Provisioned service_id={svc.id} for purchase_id={purchase.id}")
    return svc
