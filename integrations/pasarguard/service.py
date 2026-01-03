"""PasarGuard panel service implementing VPNPanelInterface."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from loguru import logger

from integrations.base import PanelSystemStats, UserInfo, UserStats, VPNPanelInterface
from integrations.exceptions import PanelError, PanelUserNotFoundError
from integrations.pasarguard.db_client import PasarGuardDBClient
from utils.retry import retry_with_backoff

# Protocol name mappings for PasarGuard compatibility
# PasarGuard DB expects lowercase protocol names
PASARGUARD_PROTOCOL_NAMES: dict[str, str] = {
    "vless": "vless",
    "vmess": "vmess",
    "trojan": "trojan",
    "shadowsocks": "shadowsocks",
    "ss": "shadowsocks",  # Alias
}


def normalize_protocol_for_pasarguard(protocol: str) -> str:
    """Normalize protocol name for PasarGuard.

    PasarGuard expects lowercase protocol names.

    Args:
        protocol: Raw protocol string

    Returns:
        Normalized protocol name for PasarGuard
    """
    proto_lower = protocol.lower().strip()
    return PASARGUARD_PROTOCOL_NAMES.get(proto_lower, proto_lower)


class PasarGuardService(VPNPanelInterface):
    """PasarGuard panel service implementation."""

    def __init__(
        self,
        panel_name: str,
        node_id: int,
        db_url: str | None = None,
        inbound_tag: str = "SUSH",
    ) -> None:
        """
        Initialize PasarGuard service.

        Args:
            panel_name: Name of the panel
            node_id: PasarGuard node ID
            db_url: Database URL (optional, uses settings if None)
            inbound_tag: Inbound tag to use (default: "SUSH")
        """
        self.panel_name = panel_name
        self.node_id = node_id
        self.inbound_tag = inbound_tag
        self._client: PasarGuardDBClient | None = None
        self._db_url = db_url

    @property
    def client(self) -> PasarGuardDBClient:
        """Get or create PasarGuard DB client."""
        if self._client is None:
            self._client = PasarGuardDBClient(db_url=self._db_url, node_id=self.node_id)
        return self._client

    @retry_with_backoff(max_retries=3, initial_delay=0.5)
    async def create_user(
        self,
        *,
        username: str,
        expire_ts: int | None = None,
        data_limit_bytes: int | None = None,
        protocol: str = "vless",
        flow: str = "xtls-rprx-vision",
    ) -> UserInfo:
        """Create a new user on PasarGuard panel.

        Args:
            username: Username for the user
            expire_ts: Expiration timestamp (Unix)
            data_limit_bytes: Data limit in bytes
            protocol: Protocol type (vless, vmess, trojan, shadowsocks)
            flow: Flow type for VLESS (default: xtls-rprx-vision)

        Returns:
            UserInfo with created user details

        Note:
            PasarGuard creates users with a specific protocol based on the
            inbound configuration. The protocol parameter is used to determine
            which inbound to use if multiple are available.
        """
        try:
            # CRITICAL: Normalize protocol to lowercase for consistency
            normalized_protocol = normalize_protocol_for_pasarguard(protocol)

            # Log protocol selection for debugging
            logger.debug(
                f"Creating PasarGuard user: username={username}, "
                f"protocol={normalized_protocol}, flow={flow}"
            )

            # Determine flow based on protocol
            effective_flow = flow
            if normalized_protocol not in {"vless", "trojan"}:
                # VMess and Shadowsocks don't use flow
                effective_flow = ""

            pg_user = await self.client.get_or_create_pasarguard_user(
                inbound_tag=self.inbound_tag,
                username=username,
                expire_ts=expire_ts,
                data_limit_bytes=data_limit_bytes,
                flow=effective_flow,
            )

            # Get user stats to populate all fields
            stats = await self.client.get_user_stats(username=username)

            return UserInfo(
                username=username,
                user_id=pg_user.get("user_id"),
                status=str(stats.get("status", "active")),
                expire_ts=expire_ts,
                data_limit_bytes=data_limit_bytes,
                used_traffic_bytes=int(stats.get("used_traffic", 0)),
                proxy_settings=pg_user.get("proxy_settings"),
            )
        except ValueError as e:
            if "not found" in str(e).lower():
                raise PanelUserNotFoundError(username, panel_name=self.panel_name) from e
            raise PanelError(
                f"Failed to create user: {e}",
                panel_name=self.panel_name,
            ) from e
        except Exception as e:
            raise PanelError(
                f"Failed to create user: {e}",
                panel_name=self.panel_name,
            ) from e

    @retry_with_backoff(max_retries=3, initial_delay=0.5)
    async def delete_user(self, *, username: str) -> None:
        """Delete a user from PasarGuard panel."""
        try:
            # Check if user exists
            await self.client.get_user_stats(username=username)
            # PasarGuard doesn't have a direct delete, so we disable the user
            await self.client.set_user_status(username=username, status="disabled")
            logger.info(f"Disabled PasarGuard user: {username}")
        except ValueError as e:
            if "not found" in str(e).lower():
                raise PanelUserNotFoundError(username, panel_name=self.panel_name) from e
            raise PanelError(
                f"Failed to delete user: {e}",
                panel_name=self.panel_name,
            ) from e
        except Exception as e:
            raise PanelError(
                f"Failed to delete user: {e}",
                panel_name=self.panel_name,
            ) from e

    @retry_with_backoff(max_retries=3, initial_delay=0.5)
    async def get_user_stats(self, *, username: str) -> UserStats:
        """Get statistics for a user."""
        try:
            stats = await self.client.get_user_stats(username=username)

            # Convert expire timestamp if present
            expire_ts: int | None = None
            expire = stats.get("expire")
            if expire:
                if isinstance(expire, datetime):
                    expire_ts = int(expire.timestamp())
                elif isinstance(expire, (int, float)):
                    expire_ts = int(expire)

            return UserStats(
                username=username,
                status=str(stats.get("status", "active")),
                used_traffic_bytes=int(stats.get("used_traffic", 0)),
                data_limit_bytes=stats.get("data_limit"),
                expire_ts=expire_ts,
                proxy_settings=stats.get("proxy_settings"),
            )
        except ValueError as e:
            if "not found" in str(e).lower():
                raise PanelUserNotFoundError(username, panel_name=self.panel_name) from e
            raise PanelError(
                f"Failed to get user stats: {e}",
                panel_name=self.panel_name,
            ) from e
        except Exception as e:
            raise PanelError(
                f"Failed to get user stats: {e}",
                panel_name=self.panel_name,
            ) from e

    @retry_with_backoff(max_retries=3, initial_delay=0.5)
    async def renew_user(self, *, username: str, expire_ts: int | None) -> None:
        """Renew/extend user expiration."""
        try:
            await self.client.update_user_expire(username=username, expire_ts=expire_ts)
        except ValueError as e:
            if "not found" in str(e).lower():
                raise PanelUserNotFoundError(username, panel_name=self.panel_name) from e
            raise PanelError(
                f"Failed to renew user: {e}",
                panel_name=self.panel_name,
            ) from e
        except Exception as e:
            raise PanelError(
                f"Failed to renew user: {e}",
                panel_name=self.panel_name,
            ) from e

    @retry_with_backoff(max_retries=3, initial_delay=0.5)
    async def add_traffic(self, *, username: str, add_bytes: int) -> None:
        """Add traffic to user's data limit."""
        try:
            await self.client.add_user_data_limit(username=username, add_bytes=add_bytes)
        except ValueError as e:
            if "not found" in str(e).lower():
                raise PanelUserNotFoundError(username, panel_name=self.panel_name) from e
            raise PanelError(
                f"Failed to add traffic: {e}",
                panel_name=self.panel_name,
            ) from e
        except Exception as e:
            raise PanelError(
                f"Failed to add traffic: {e}",
                panel_name=self.panel_name,
            ) from e

    @retry_with_backoff(max_retries=3, initial_delay=0.5)
    async def reset_traffic(self, *, username: str) -> None:
        """Reset user's used traffic to zero."""
        try:
            await self.client.reset_user_traffic(username=username)
        except ValueError as e:
            if "not found" in str(e).lower():
                raise PanelUserNotFoundError(username, panel_name=self.panel_name) from e
            raise PanelError(
                f"Failed to reset traffic: {e}",
                panel_name=self.panel_name,
            ) from e
        except Exception as e:
            raise PanelError(
                f"Failed to reset traffic: {e}",
                panel_name=self.panel_name,
            ) from e

    @retry_with_backoff(max_retries=3, initial_delay=0.5)
    async def rotate_credentials(
        self,
        *,
        username: str,
        protocol: str = "vless",
        flow: str = "xtls-rprx-vision",
    ) -> dict[str, Any]:
        """Rotate user's proxy credentials."""
        try:
            result = await self.client.rotate_proxy_credentials(username=username, flow=flow)
            return result
        except ValueError as e:
            if "not found" in str(e).lower():
                raise PanelUserNotFoundError(username, panel_name=self.panel_name) from e
            raise PanelError(
                f"Failed to rotate credentials: {e}",
                panel_name=self.panel_name,
            ) from e
        except Exception as e:
            raise PanelError(
                f"Failed to rotate credentials: {e}",
                panel_name=self.panel_name,
            ) from e

    @retry_with_backoff(max_retries=3, initial_delay=0.5)
    async def generate_config_link(
        self,
        *,
        username: str,
        protocol: str = "vless",
        server_address: str | None = None,
        port: int | None = None,
    ) -> str:
        """Generate configuration link for a user (single protocol)."""
        try:
            # Get user stats to get proxy_settings
            stats = await self.client.get_user_stats(username=username)
            proxy_settings = stats.get("proxy_settings")

            # Extract UUID from proxy_settings based on protocol
            client_uuid: str | None = None
            if isinstance(proxy_settings, dict):
                if protocol.lower() == "vless":
                    client_uuid = (proxy_settings.get("vless") or {}).get("id")
                elif protocol.lower() == "vmess":
                    client_uuid = (proxy_settings.get("vmess") or {}).get("id")

            config_link = await self.client.generate_config_link(
                inbound_tag=self.inbound_tag,
                email=username,
                client_uuid=client_uuid,
                protocol=protocol,
                proxy_settings=proxy_settings if isinstance(proxy_settings, dict) else None,
            )
            return config_link
        except ValueError as e:
            if "not found" in str(e).lower():
                raise PanelUserNotFoundError(username, panel_name=self.panel_name) from e
            raise PanelError(
                f"Failed to generate config link: {e}",
                panel_name=self.panel_name,
            ) from e
        except Exception as e:
            raise PanelError(
                f"Failed to generate config link: {e}",
                panel_name=self.panel_name,
            ) from e

    @retry_with_backoff(max_retries=3, initial_delay=0.5)
    async def get_subscription_url(self, *, username: str) -> str:
        """
        Get subscription URL for a user.

        Note: PasarGuard doesn't natively support subscription URLs.
        This method returns the default protocol config link (VLESS).
        For full subscription support, consider using Marzban or implementing
        a custom subscription generator.
        """
        # PasarGuard doesn't have native subscription URLs
        # Return the default protocol config link
        return await self.generate_config_link(username=username, protocol="vless")

    @retry_with_backoff(max_retries=2, initial_delay=0.3)
    async def health_check(self) -> bool:
        """Check if PasarGuard panel is accessible."""
        try:
            return await self.client.health_check()
        except Exception as e:
            logger.warning(f"PasarGuard health check failed for {self.panel_name}: {e}")
            return False

    async def get_system_stats(self) -> PanelSystemStats:
        """Get system statistics from PasarGuard panel."""
        # PasarGuard DB doesn't expose system stats via DB
        # We can query some basic stats from the users table
        try:
            pool = await self.client._get_pool()
            async with pool.acquire() as conn:
                # Get total users
                total_users = await conn.fetchval("SELECT COUNT(*) FROM users")
                # Get active users
                active_users = await conn.fetchval(
                    "SELECT COUNT(*) FROM users WHERE status = 'active'"
                )

                return PanelSystemStats(
                    total_users=int(total_users or 0),
                    active_users=int(active_users or 0),
                    version=None,  # Not available via DB
                    memory_total=None,  # Not available via DB
                    memory_used=None,  # Not available via DB
                    bandwidth_total=None,  # Not available via DB
                    bandwidth_incoming=None,  # Not available via DB
                    bandwidth_outgoing=None,  # Not available via DB
                )
        except Exception as e:
            raise PanelError(
                f"Failed to get system stats: {e}",
                panel_name=self.panel_name,
            ) from e

    async def close(self) -> None:
        """Close connections and cleanup resources."""
        if self._client:
            await self._client.close()
            self._client = None
