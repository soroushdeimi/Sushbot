"""Marzban panel service implementing VPNPanelInterface."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from loguru import logger

from integrations.base import PanelSystemStats, UserInfo, UserStats, VPNPanelInterface
from integrations.exceptions import PanelError, PanelUserNotFoundError
from integrations.marzban.api_client import MarzbanAPIClient
from utils.retry import retry_with_backoff


class MarzbanService(VPNPanelInterface):
    """Marzban panel service implementation."""

    def __init__(
        self,
        panel_name: str,
        api_url: str,
        username: str | None = None,
        password: str | None = None,
        api_key: str | None = None,
    ) -> None:
        """
        Initialize Marzban service.

        Args:
            panel_name: Name of the panel
            api_url: Base URL of Marzban panel
            username: Admin username (if using username/password)
            password: Admin password (if using username/password)
            api_key: API token (if using token auth)
        """
        self.panel_name = panel_name
        self._client = MarzbanAPIClient(
            api_url=api_url,
            username=username,
            password=password,
            api_key=api_key,
        )

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
        """Create a new user on Marzban panel."""
        try:
            # Marzban supports all protocols by default, but we can specify which ones to enable
            proxies: dict[str, Any] = {}
            if protocol.lower() == "vless":
                proxies["vless"] = {"flow": flow}
            elif protocol.lower() == "vmess":
                proxies["vmess"] = {}
            elif protocol.lower() == "trojan":
                proxies["trojan"] = {}
            elif protocol.lower() in {"shadowsocks", "ss"}:
                proxies["shadowsocks"] = {}

            # If no specific protocol, enable all
            if not proxies:
                proxies = {
                    "vless": {"flow": flow},
                    "vmess": {},
                    "trojan": {},
                    "shadowsocks": {},
                }

            user_data = await self._client.create_user(
                username=username,
                expire_ts=expire_ts,
                data_limit_bytes=data_limit_bytes,
                proxies=proxies,
            )

            return UserInfo(
                username=username,
                user_id=None,  # Marzban doesn't expose internal user ID
                status=str(user_data.get("status", "active")),
                expire_ts=expire_ts,
                data_limit_bytes=data_limit_bytes,
                used_traffic_bytes=int(user_data.get("used_traffic", 0)),
                proxy_settings=user_data.get("proxies"),
            )
        except PanelError:
            raise
        except Exception as e:
            raise PanelError(
                f"Failed to create user: {e}",
                panel_name=self.panel_name,
            ) from e

    @retry_with_backoff(max_retries=3, initial_delay=0.5)
    async def delete_user(self, *, username: str) -> None:
        """Delete a user from Marzban panel."""
        try:
            await self._client.delete_user(username=username)
        except PanelError as e:
            if "not found" in str(e).lower() or "404" in str(e):
                raise PanelUserNotFoundError(username, panel_name=self.panel_name) from e
            raise
        except Exception as e:
            raise PanelError(
                f"Failed to delete user: {e}",
                panel_name=self.panel_name,
            ) from e

    @retry_with_backoff(max_retries=3, initial_delay=0.5)
    async def get_user_stats(self, *, username: str) -> UserStats:
        """Get statistics for a user."""
        try:
            user_data = await self._client.get_user(username=username)

            # Convert expire timestamp
            expire_ts: int | None = None
            expire = user_data.get("expire")
            if expire:
                if isinstance(expire, (int, float)) and expire > 0:
                    expire_ts = int(expire)
                elif isinstance(expire, str):
                    # Try to parse datetime string
                    try:
                        dt = datetime.fromisoformat(expire.replace("Z", "+00:00"))
                        expire_ts = int(dt.timestamp())
                    except (ValueError, AttributeError) as e:
                        # Invalid datetime format, skip expiration
                        logger.debug(f"Could not parse expire datetime '{expire}': {e}")
                        expire_ts = None
                    except Exception as e:
                        logger.warning(f"Unexpected error parsing expire datetime '{expire}': {e}")
                        expire_ts = None

            return UserStats(
                username=username,
                status=str(user_data.get("status", "active")),
                used_traffic_bytes=int(user_data.get("used_traffic", 0)),
                data_limit_bytes=user_data.get("data_limit"),
                expire_ts=expire_ts,
                proxy_settings=user_data.get("proxies"),
            )
        except PanelError as e:
            if "not found" in str(e).lower() or "404" in str(e):
                raise PanelUserNotFoundError(username, panel_name=self.panel_name) from e
            raise
        except Exception as e:
            raise PanelError(
                f"Failed to get user stats: {e}",
                panel_name=self.panel_name,
            ) from e

    @retry_with_backoff(max_retries=3, initial_delay=0.5)
    async def renew_user(self, *, username: str, expire_ts: int | None) -> None:
        """Renew/extend user expiration."""
        try:
            await self._client.update_user(
                username=username,
                expire_ts=expire_ts if expire_ts else 0,
            )
        except PanelError as e:
            if "not found" in str(e).lower() or "404" in str(e):
                raise PanelUserNotFoundError(username, panel_name=self.panel_name) from e
            raise
        except Exception as e:
            raise PanelError(
                f"Failed to renew user: {e}",
                panel_name=self.panel_name,
            ) from e

    @retry_with_backoff(max_retries=3, initial_delay=0.5)
    async def add_traffic(self, *, username: str, add_bytes: int) -> None:
        """Add traffic to user's data limit."""
        try:
            # Get current user data
            user_data = await self._client.get_user(username=username)
            current_limit = user_data.get("data_limit", 0)

            # If unlimited (0), keep unlimited
            if current_limit == 0:
                return

            new_limit = int(current_limit) + int(add_bytes)
            await self._client.update_user(
                username=username,
                data_limit_bytes=new_limit,
            )
        except PanelError as e:
            if "not found" in str(e).lower() or "404" in str(e):
                raise PanelUserNotFoundError(username, panel_name=self.panel_name) from e
            raise
        except Exception as e:
            raise PanelError(
                f"Failed to add traffic: {e}",
                panel_name=self.panel_name,
            ) from e

    @retry_with_backoff(max_retries=3, initial_delay=0.5)
    async def reset_traffic(self, *, username: str) -> None:
        """Reset user's used traffic to zero."""
        try:
            await self._client.reset_user_traffic(username=username)
        except PanelError as e:
            if "not found" in str(e).lower() or "404" in str(e):
                raise PanelUserNotFoundError(username, panel_name=self.panel_name) from e
            raise
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
            # Marzban revokes subscription which rotates all credentials
            await self._client.revoke_subscription(username=username)

            # Get updated user data to return proxy_settings
            user_data = await self._client.get_user(username=username)
            return {"proxy_settings": user_data.get("proxies", {})}
        except PanelError as e:
            if "not found" in str(e).lower() or "404" in str(e):
                raise PanelUserNotFoundError(username, panel_name=self.panel_name) from e
            raise
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
        # For Marzban, we use subscription URL which contains all protocols
        # But if a specific protocol is requested, we can extract it
        subscription_url = await self.get_subscription_url(username=username)

        # If protocol-specific link is needed, return subscription URL
        # (Marzban subscription URLs contain all protocols)
        return subscription_url

    @retry_with_backoff(max_retries=3, initial_delay=0.5)
    async def get_subscription_url(self, *, username: str) -> str:
        """Get subscription URL for a user (contains all protocols)."""
        try:
            user_data = await self._client.get_user(username=username)

            # Marzban provides subscription_url in user data
            subscription_url = user_data.get("subscription_url")
            if subscription_url:
                # If it's a relative URL, make it absolute
                if not subscription_url.startswith(("http://", "https://")):
                    base_url = self._client.api_url
                    subscription_url = f"{base_url}{subscription_url}" if subscription_url.startswith("/") else f"{base_url}/{subscription_url}"

                return subscription_url

            # Fallback: construct link from user data if subscription_url not available
            raise PanelError(
                "Marzban user does not have subscription_url",
                panel_name=self.panel_name,
            )
        except PanelError as e:
            if "not found" in str(e).lower() or "404" in str(e):
                raise PanelUserNotFoundError(username, panel_name=self.panel_name) from e
            raise
        except Exception as e:
            raise PanelError(
                f"Failed to get subscription URL: {e}",
                panel_name=self.panel_name,
            ) from e

    @retry_with_backoff(max_retries=2, initial_delay=0.3)
    async def health_check(self) -> bool:
        """Check if Marzban panel is accessible."""
        return await self._client.health_check()

    @retry_with_backoff(max_retries=2, initial_delay=0.3)
    async def get_system_stats(self) -> PanelSystemStats:
        """Get system statistics from Marzban panel."""
        try:
            stats = await self._client.get_system_stats()

            # Extract user counts
            users = stats.get("users", {})
            total_users = int(users.get("total", 0))
            active_users = int(users.get("active", 0))

            # Extract system info
            version = stats.get("version")
            memory = stats.get("memory", {})
            bandwidth = stats.get("bandwidth", {})

            return PanelSystemStats(
                total_users=total_users,
                active_users=active_users,
                version=version,
                memory_total=memory.get("total"),
                memory_used=memory.get("used"),
                bandwidth_total=bandwidth.get("total"),
                bandwidth_incoming=bandwidth.get("incoming"),
                bandwidth_outgoing=bandwidth.get("outgoing"),
            )
        except Exception as e:
            raise PanelError(
                f"Failed to get system stats: {e}",
                panel_name=self.panel_name,
            ) from e

    async def close(self) -> None:
        """Close connections and cleanup resources."""
        await self._client.close()

