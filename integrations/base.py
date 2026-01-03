"""Base interface for VPN panel integrations.

This module defines the abstract base class that all VPN panel services must implement,
ensuring a consistent interface regardless of the underlying panel type (PasarGuard, Marzban, etc.).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field


class UserInfo(BaseModel):
    """Information about a VPN panel user."""

    username: str = Field(..., description="Username/email of the user")
    user_id: int | None = Field(default=None, description="Internal panel user ID")
    status: str = Field(..., description="User status (active, disabled, expired, etc.)")
    expire_ts: int | None = Field(default=None, description="Expiration timestamp (Unix)")
    data_limit_bytes: int | None = Field(
        default=None, description="Data limit in bytes (None = unlimited)"
    )
    used_traffic_bytes: int = Field(default=0, description="Used traffic in bytes")
    proxy_settings: dict[str, Any] | None = Field(
        default=None, description="Protocol-specific proxy settings"
    )


class UserStats(BaseModel):
    """Statistics for a VPN panel user."""

    username: str = Field(..., description="Username/email of the user")
    status: str = Field(..., description="User status")
    used_traffic_bytes: int = Field(default=0, description="Used traffic in bytes")
    data_limit_bytes: int | None = Field(
        default=None, description="Data limit in bytes (None = unlimited)"
    )
    expire_ts: int | None = Field(default=None, description="Expiration timestamp (Unix)")
    proxy_settings: dict[str, Any] | None = Field(
        default=None, description="Protocol-specific proxy settings"
    )


class PanelSystemStats(BaseModel):
    """System statistics from a VPN panel."""

    total_users: int = Field(..., description="Total number of users")
    active_users: int = Field(..., description="Number of active users")
    version: str | None = Field(default=None, description="Panel version")
    memory_total: int | None = Field(default=None, description="Total memory in bytes")
    memory_used: int | None = Field(default=None, description="Used memory in bytes")
    bandwidth_total: int | None = Field(default=None, description="Total bandwidth in bytes")
    bandwidth_incoming: int | None = Field(default=None, description="Incoming bandwidth in bytes")
    bandwidth_outgoing: int | None = Field(default=None, description="Outgoing bandwidth in bytes")


class VPNPanelInterface(ABC):
    """Abstract base class for VPN panel integrations.

    All panel services (PasarGuard, Marzban, etc.) must implement this interface
    to ensure consistent behavior across different panel types.
    """

    @abstractmethod
    async def create_user(
        self,
        *,
        username: str,
        expire_ts: int | None = None,
        data_limit_bytes: int | None = None,
        protocol: str = "vless",
        flow: str = "xtls-rprx-vision",
    ) -> UserInfo:
        """
        Create a new user on the VPN panel.

        Args:
            username: Username/email for the user
            expire_ts: Expiration timestamp (Unix). None = no expiration
            data_limit_bytes: Data limit in bytes. None = unlimited
            protocol: Protocol type (vless, vmess, trojan, shadowsocks)
            flow: Flow type for VLESS (default: xtls-rprx-vision)

        Returns:
            UserInfo object with created user details

        Raises:
            PanelError: If user creation fails
        """
        pass

    @abstractmethod
    async def delete_user(self, *, username: str) -> None:
        """
        Delete a user from the VPN panel.

        Args:
            username: Username/email of the user to delete

        Raises:
            PanelError: If deletion fails
            PanelUserNotFoundError: If user doesn't exist
        """
        pass

    @abstractmethod
    async def get_user_stats(self, *, username: str) -> UserStats:
        """
        Get statistics for a user.

        Args:
            username: Username/email of the user

        Returns:
            UserStats object with user statistics

        Raises:
            PanelError: If retrieval fails
            PanelUserNotFoundError: If user doesn't exist
        """
        pass

    @abstractmethod
    async def renew_user(self, *, username: str, expire_ts: int | None) -> None:
        """
        Renew/extend user expiration.

        Args:
            username: Username/email of the user
            expire_ts: New expiration timestamp (Unix). None = remove expiration

        Raises:
            PanelError: If renewal fails
            PanelUserNotFoundError: If user doesn't exist
        """
        pass

    @abstractmethod
    async def add_traffic(self, *, username: str, add_bytes: int) -> None:
        """
        Add traffic to user's data limit.

        Args:
            username: Username/email of the user
            add_bytes: Bytes to add to data limit

        Raises:
            PanelError: If operation fails
            PanelUserNotFoundError: If user doesn't exist
        """
        pass

    @abstractmethod
    async def reset_traffic(self, *, username: str) -> None:
        """
        Reset user's used traffic to zero.

        Args:
            username: Username/email of the user

        Raises:
            PanelError: If operation fails
            PanelUserNotFoundError: If user doesn't exist
        """
        pass

    @abstractmethod
    async def rotate_credentials(
        self, *, username: str, protocol: str = "vless", flow: str = "xtls-rprx-vision"
    ) -> dict[str, Any]:
        """
        Rotate user's proxy credentials (UUIDs, passwords, etc.).

        Args:
            username: Username/email of the user
            protocol: Protocol type (vless, vmess, trojan, shadowsocks)
            flow: Flow type for VLESS (default: xtls-rprx-vision)

        Returns:
            Dictionary with updated proxy_settings

        Raises:
            PanelError: If operation fails
            PanelUserNotFoundError: If user doesn't exist
        """
        pass

    @abstractmethod
    async def generate_config_link(
        self,
        *,
        username: str,
        protocol: str = "vless",
        server_address: str | None = None,
        port: int | None = None,
    ) -> str:
        """
        Generate configuration link for a user.

        Args:
            username: Username/email of the user
            protocol: Protocol type (vless, vmess, trojan, shadowsocks)
            server_address: Server address (optional, uses panel default if None)
            port: Server port (optional, uses panel default if None)

        Returns:
            Configuration link string (vless://, vmess://, etc.)

        Raises:
            PanelError: If generation fails
            PanelUserNotFoundError: If user doesn't exist
        """
        pass

    @abstractmethod
    async def get_subscription_url(self, *, username: str) -> str:
        """
        Get subscription URL for a user (contains all protocols).

        Modern VPN panels (like Marzban) use subscription links that contain
        multiple protocol configurations (VLESS, VMESS, Trojan, etc.) in a single URL.

        Args:
            username: Username/email of the user

        Returns:
            Subscription URL string (compatible with V2RayNG, Clash, etc.)

        Raises:
            PanelError: If retrieval fails
            PanelUserNotFoundError: If user doesn't exist

        Note:
            For panels that don't support subscription URLs, this should return
            the result of generate_config_link() for the default protocol.
        """
        pass

    @abstractmethod
    async def health_check(self) -> bool:
        """
        Check if the panel is accessible and healthy.

        Returns:
            True if panel is healthy, False otherwise
        """
        pass

    @abstractmethod
    async def get_system_stats(self) -> PanelSystemStats:
        """
        Get system statistics from the panel.

        Returns:
            PanelSystemStats object with panel statistics

        Raises:
            PanelError: If retrieval fails
        """
        pass

    @abstractmethod
    async def close(self) -> None:
        """
        Close connections and cleanup resources.

        Should be called when done with the panel instance.
        """
        pass
