"""Panel utility functions for capacity checking, protocol validation, and management."""

from __future__ import annotations

from enum import Enum

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Panel, Service, ServiceStatus


class VPNProtocol(str, Enum):
    """Supported VPN protocols with normalized lowercase values.
    
    Panel APIs expect lowercase protocol names in most cases.
    This enum ensures consistent protocol naming across the codebase.
    """
    
    VLESS = "vless"
    VMESS = "vmess"
    TROJAN = "trojan"
    SHADOWSOCKS = "shadowsocks"
    SS = "ss"  # Alias for shadowsocks
    HYSTERIA = "hysteria"
    HYSTERIA2 = "hysteria2"
    WIREGUARD = "wireguard"
    WG = "wg"  # Alias for wireguard
    
    @classmethod
    def normalize(cls, protocol: str) -> str:
        """Normalize protocol name to lowercase and handle aliases.
        
        Args:
            protocol: Raw protocol string (may be mixed case)
        
        Returns:
            Normalized lowercase protocol name
            
        Examples:
            >>> VPNProtocol.normalize("VLESS")
            'vless'
            >>> VPNProtocol.normalize("SS")
            'shadowsocks'
        """
        proto_lower = protocol.lower().strip()
        
        # Handle aliases
        aliases = {
            "ss": "shadowsocks",
            "wg": "wireguard",
        }
        return aliases.get(proto_lower, proto_lower)
    
    @classmethod
    def is_valid(cls, protocol: str) -> bool:
        """Check if a protocol string is a valid/known protocol.
        
        Args:
            protocol: Protocol string to validate
            
        Returns:
            True if protocol is known, False otherwise
        """
        normalized = cls.normalize(protocol)
        return normalized in {p.value for p in cls}


# Protocol-specific parameters and requirements
PROTOCOL_REQUIREMENTS: dict[str, dict] = {
    "vless": {
        "requires_uuid": True,
        "requires_password": False,
        "supports_flow": True,
        "default_flow": "xtls-rprx-vision",
        "alt_id_required": False,
    },
    "vmess": {
        "requires_uuid": True,
        "requires_password": False,
        "supports_flow": False,
        "default_flow": None,
        "alt_id_required": False,  # alterId is deprecated in newer versions
        "default_alter_id": 0,
    },
    "trojan": {
        "requires_uuid": False,
        "requires_password": True,
        "supports_flow": True,  # Some implementations support flow
        "default_flow": None,
        "alt_id_required": False,
    },
    "shadowsocks": {
        "requires_uuid": False,
        "requires_password": True,
        "supports_flow": False,
        "default_flow": None,
        "alt_id_required": False,
        "encryption_methods": [
            "aes-128-gcm", "aes-256-gcm", "chacha20-ietf-poly1305",
            "2022-blake3-aes-128-gcm", "2022-blake3-aes-256-gcm",
            "2022-blake3-chacha20-poly1305",
        ],
    },
    "hysteria": {
        "requires_uuid": False,
        "requires_password": True,
        "supports_flow": False,
        "default_flow": None,
        "alt_id_required": False,
    },
    "hysteria2": {
        "requires_uuid": False,
        "requires_password": True,
        "supports_flow": False,
        "default_flow": None,
        "alt_id_required": False,
    },
    "wireguard": {
        "requires_uuid": False,
        "requires_password": False,
        "requires_private_key": True,
        "supports_flow": False,
        "default_flow": None,
        "alt_id_required": False,
    },
}


# Protocols supported by each panel type
PANEL_SUPPORTED_PROTOCOLS: dict[str, set[str]] = {
    "marzban": {"vless", "vmess", "trojan", "shadowsocks"},
    "pasarguard": {"vless", "vmess", "trojan", "shadowsocks"},
    # Add more panels as needed
    # "x-ui": {"vless", "vmess", "trojan", "shadowsocks"},
    # "3x-ui": {"vless", "vmess", "trojan", "shadowsocks", "hysteria", "hysteria2"},
}


def validate_protocol_compatibility(
    panel_type: str,
    protocol: str,
    strict: bool = True,
) -> tuple[bool, str | None]:
    """
    Validate that a protocol is compatible with the specified panel type.
    
    This function prevents creating users with unsupported protocols before
    calling the panel API, saving time and providing better error messages.
    
    Args:
        panel_type: Panel type (e.g., "marzban", "pasarguard")
        protocol: Protocol to validate (e.g., "vless", "vmess")
        strict: If True, raise error for unknown panel types. If False, allow unknown.
        
    Returns:
        Tuple of (is_valid, error_message)
        - is_valid: True if protocol is compatible
        - error_message: None if valid, error description if not
        
    Examples:
        >>> validate_protocol_compatibility("marzban", "vless")
        (True, None)
        >>> validate_protocol_compatibility("marzban", "wireguard")
        (False, "Protocol 'wireguard' is not supported by panel type 'marzban'. Supported: ...")
    """
    # Normalize inputs
    panel_type_lower = panel_type.lower().strip()
    protocol_normalized = VPNProtocol.normalize(protocol)
    
    # Check if panel type is known
    if panel_type_lower not in PANEL_SUPPORTED_PROTOCOLS:
        if strict:
            return False, f"Unknown panel type: '{panel_type}'"
        # For unknown panels, assume all protocols are supported
        return True, None
    
    supported = PANEL_SUPPORTED_PROTOCOLS[panel_type_lower]
    
    if protocol_normalized not in supported:
        supported_list = ", ".join(sorted(supported))
        return (
            False,
            f"Protocol '{protocol}' is not supported by panel type '{panel_type}'. "
            f"Supported protocols: {supported_list}",
        )
    
    return True, None


def get_protocol_params(protocol: str) -> dict | None:
    """
    Get protocol-specific parameters and requirements.
    
    Args:
        protocol: Protocol name
        
    Returns:
        Dictionary of protocol parameters, or None if protocol is unknown
    """
    normalized = VPNProtocol.normalize(protocol)
    return PROTOCOL_REQUIREMENTS.get(normalized)


def get_panel_supported_protocols(panel_type: str) -> set[str]:
    """
    Get the set of protocols supported by a panel type.
    
    Args:
        panel_type: Panel type name
        
    Returns:
        Set of supported protocol names, or empty set if panel type is unknown
    """
    return PANEL_SUPPORTED_PROTOCOLS.get(panel_type.lower().strip(), set())


async def check_panel_capacity(db: AsyncSession, *, panel_id: int) -> tuple[bool, str | None]:
    """
    Check if panel has capacity for new config.

    Uses database COUNT query for accuracy (avoids sync issues with current_config_count field).

    Args:
        db: Database session
        panel_id: Panel ID to check

    Returns:
        Tuple of (has_capacity, error_message)
        - has_capacity: True if panel can accept new configs, False otherwise
        - error_message: None if has capacity, error message if at capacity
    """
    panel = await db.get(Panel, panel_id)
    if not panel:
        return False, f"Panel {panel_id} not found"

    # If no limit set, panel has unlimited capacity
    if panel.max_configs_per_panel is None:
        return True, None

    # Count active services for this panel
    res = await db.execute(
        select(func.count(Service.id)).where(
            Service.panel_id == panel_id,
            Service.status == ServiceStatus.ACTIVE,
        )
    )
    active_count = int(res.scalar() or 0)

    # Check if at capacity
    if active_count >= panel.max_configs_per_panel:
        return (
            False,
            f"Panel {panel.name} is at capacity ({active_count}/{panel.max_configs_per_panel} configs)",
        )

    return True, None


async def sync_panel_config_count(db: AsyncSession, *, panel_id: int) -> int:
    """
    Sync panel.current_config_count with actual count of active services.

    This is useful for admin display purposes and fixing any sync issues.
    The actual capacity checking uses COUNT queries for accuracy.

    Args:
        db: Database session
        panel_id: Panel ID to sync

    Returns:
        Updated config count
    """
    panel = await db.get(Panel, panel_id)
    if not panel:
        raise ValueError(f"Panel {panel_id} not found")

    # Count active services
    res = await db.execute(
        select(func.count(Service.id)).where(
            Service.panel_id == panel_id,
            Service.status == ServiceStatus.ACTIVE,
        )
    )
    actual_count = int(res.scalar() or 0)

    # Update panel count (for display purposes)
    panel.current_config_count = actual_count
    await db.commit()

    return actual_count
