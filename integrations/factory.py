"""Factory for creating VPN panel service instances."""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from loguru import logger

from integrations.base import VPNPanelInterface
from integrations.exceptions import PanelError, PanelValidationError
from utils.encryption import decrypt_panel_credentials

if TYPE_CHECKING:
    from database.models.panel import Panel


class PanelType(str, Enum):
    """Supported VPN panel types."""

    PASARGUARD = "pasarguard"
    MARZBAN = "marzban"


class PanelFactory:
    """Factory for creating VPN panel service instances."""

    @staticmethod
    async def create_panel(panel: Panel) -> VPNPanelInterface:
        """
        Create a VPN panel service instance based on panel configuration.

        Args:
            panel: Panel database model with configuration

        Returns:
            VPNPanelInterface instance for the specified panel

        Raises:
            PanelValidationError: If panel configuration is invalid
            PanelError: If panel creation fails

        Example:
            ```python
            panel = await db.get(Panel, panel_id)
            service = await PanelFactory.create_panel(panel)
            try:
                user_info = await service.create_user(username="user@example.com")
            finally:
                await service.close()
            ```
        """
        if not panel.name:
            raise PanelValidationError("Panel name is required", panel_name=panel.name)

        # Determine panel type from panel configuration
        # Check if panel has type field, otherwise infer from api_url or other fields
        panel_type_str = getattr(panel, "type", None) or _infer_panel_type(panel)

        try:
            panel_type = PanelType(panel_type_str.lower())
        except ValueError:
            raise PanelValidationError(
                f"Unsupported panel type: {panel_type_str}. Supported types: {', '.join([t.value for t in PanelType])}",
                panel_name=panel.name,
            )

        logger.info(f"Creating {panel_type.value} panel service for '{panel.name}'")

        if panel_type == PanelType.PASARGUARD:
            return await _create_pasarguard_panel(panel)
        elif panel_type == PanelType.MARZBAN:
            return await _create_marzban_panel(panel)
        else:
            raise PanelValidationError(
                f"Panel type {panel_type} not yet implemented",
                panel_name=panel.name,
            )


def _infer_panel_type(panel: Panel) -> str:
    """
    Infer panel type from panel configuration.

    Args:
        panel: Panel database model

    Returns:
        Inferred panel type string
    """
    # Check api_url for hints
    api_url = getattr(panel, "api_url", "") or ""
    api_url_lower = api_url.lower()

    if "marzban" in api_url_lower:
        return PanelType.MARZBAN.value
    elif "pasarguard" in api_url_lower or "pasargad" in api_url_lower:
        return PanelType.PASARGUARD.value

    # Default to pasarguard for backward compatibility
    # In the future, we might require explicit type field
    logger.warning(f"Could not infer panel type for '{panel.name}', defaulting to pasarguard")
    return PanelType.PASARGUARD.value


async def _create_pasarguard_panel(panel: Panel) -> VPNPanelInterface:
    """
    Create a PasarGuard panel service instance.

    Args:
        panel: Panel database model

    Returns:
        PasarGuardService instance

    Raises:
        PanelValidationError: If configuration is invalid
    """
    from integrations.pasarguard.service import PasarGuardService

    # PasarGuard can use either DB connection or HTTP API
    # For now, we'll use DB connection (existing behavior)
    # In the future, we can add support for HTTP API connection

    # Validate required fields
    if not hasattr(panel, "node_id") or panel.node_id is None:
        raise PanelValidationError(
            "PasarGuard panel requires node_id",
            panel_name=panel.name,
        )

    # Get inbound_tag from panel config or use default
    inbound_tag = getattr(panel, "inbound_tag", None) or "SUSH"
    # Try to get from config_template or notes if available
    if not inbound_tag and hasattr(panel, "config_template") and panel.config_template:
        # Could parse from config_template if needed
        pass

    # Create service with DB connection
    # The service will use the database URL from settings and connect to pasarguard database
    service = PasarGuardService(
        panel_name=panel.name,
        node_id=panel.node_id,
        inbound_tag=inbound_tag,
        # Optional: pass database URL if panel has custom DB config
    )

    # Test connection
    if not await service.health_check():
        raise PanelError(
            f"PasarGuard panel '{panel.name}' health check failed",
            panel_name=panel.name,
        )

    return service


async def _create_marzban_panel(panel: Panel) -> VPNPanelInterface:
    """
    Create a Marzban panel service instance.

    Args:
        panel: Panel database model

    Returns:
        MarzbanService instance

    Raises:
        PanelValidationError: If configuration is invalid
    """
    from integrations.marzban.service import MarzbanService

    # Validate required fields
    api_url = getattr(panel, "api_url", None)
    if not api_url:
        raise PanelValidationError(
            "Marzban panel requires api_url",
            panel_name=panel.name,
        )

    # Decrypt credentials if encrypted
    api_key_raw = getattr(panel, "api_key", None)
    api_key: str | None = None
    username: str | None = getattr(panel, "username", None)
    password: str | None = getattr(panel, "password", None)

    # Try to decrypt api_key (might be encrypted)
    if api_key_raw:
        try:
            api_key = decrypt_panel_credentials(api_key_raw)
        except Exception as e:
            # If decryption fails, assume it's plaintext (backward compatibility)
            # This is intentional to support both encrypted and plaintext credentials
            logger.debug(f"Decryption failed for api_key (assuming plaintext): {type(e).__name__}")
            api_key = api_key_raw

    # Decrypt password if set
    if password:
        try:
            password = decrypt_panel_credentials(password)
        except Exception as e:
            # If decryption fails, assume it's plaintext (backward compatibility)
            # This is intentional to support both encrypted and plaintext credentials
            logger.debug(f"Decryption failed for password (assuming plaintext): {type(e).__name__}")
            # Keep original password value

    # For Marzban, api_key might contain username:password or be a token
    # Check if it looks like username:password format
    if api_key and ":" in api_key and not api_key.startswith("Bearer "):
        # Assume format is username:password
        parts = api_key.split(":", 1)
        if len(parts) == 2:
            username = username or parts[0]
            password = password or parts[1]
            api_key = None  # Clear api_key since we're using username/password

    # Marzban uses HTTP API with username/password or token authentication
    # We need either api_key (token) or username/password
    if not api_key and (not username or not password):
        raise PanelValidationError(
            "Marzban panel requires either api_key (token) or username:password in api_key field or in notes JSON",
            panel_name=panel.name,
        )

    # Create service
    service = MarzbanService(
        panel_name=panel.name,
        api_url=api_url,
        api_key=api_key,
        username=username,
        password=password,
    )

    # Test connection
    if not await service.health_check():
        raise PanelError(
            f"Marzban panel '{panel.name}' health check failed",
            panel_name=panel.name,
        )

    return service

