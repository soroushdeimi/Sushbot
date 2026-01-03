"""Marzban panel HTTP API client."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

import httpx
from loguru import logger

from integrations.exceptions import PanelAuthenticationError, PanelConnectionError, PanelError
from utils.retry import retry_with_backoff


class MarzbanAPIClient:
    """HTTP client for Marzban panel API."""

    def __init__(
        self,
        api_url: str,
        username: str | None = None,
        password: str | None = None,
        api_key: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        """
        Initialize Marzban API client.

        Args:
            api_url: Base URL of Marzban panel (e.g., https://panel.example.com)
            username: Admin username (if using username/password auth)
            password: Admin password (if using username/password auth)
            api_key: API token (if using token auth, takes precedence)
            timeout: Request timeout in seconds
        """
        self.api_url = api_url.rstrip("/")
        self.username = username
        self.password = password
        self.api_key = api_key
        self.timeout = timeout
        self._token: str | None = None
        self._token_expires_at: datetime | None = None
        self._client: httpx.AsyncClient | None = None

    @property
    async def client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=self.timeout, follow_redirects=True)
        return self._client

    async def _get_token(self) -> str:
        """
        Get authentication token, refreshing if necessary.

        Returns:
            Bearer token string

        Raises:
            PanelAuthenticationError: If authentication fails
        """
        # Check if we have a valid cached token
        if self._token and self._token_expires_at:
            if datetime.utcnow() < self._token_expires_at - timedelta(
                minutes=5
            ):  # Refresh 5 min before expiry
                return self._token

        # If api_key is provided, use it directly
        if self.api_key:
            self._token = self.api_key
            self._token_expires_at = datetime.utcnow() + timedelta(
                hours=24
            )  # Assume long-lived token
            return self._token

        # Otherwise, authenticate with username/password
        if not self.username or not self.password:
            raise PanelAuthenticationError(
                "Marzban authentication requires either api_key or username/password",
            )

        try:
            client = await self.client
            response = await client.post(
                f"{self.api_url}/api/admin/token",
                data={
                    "username": self.username,
                    "password": self.password,
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
            response.raise_for_status()
            data = response.json()

            if "access_token" not in data:
                raise PanelAuthenticationError(
                    f"Token response missing access_token: {data}",
                )

            self._token = data["access_token"]
            # Marzban tokens typically expire in 1 hour, but we'll refresh after 50 minutes
            self._token_expires_at = datetime.utcnow() + timedelta(minutes=50)

            return self._token
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 401:
                raise PanelAuthenticationError(
                    "Invalid Marzban username or password",
                ) from e
            raise PanelConnectionError(
                f"Failed to authenticate with Marzban: {e}",
            ) from e
        except httpx.RequestError as e:
            raise PanelConnectionError(
                f"Failed to connect to Marzban: {e}",
            ) from e

    async def _request(
        self,
        method: str,
        endpoint: str,
        *,
        json_data: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Make authenticated HTTP request to Marzban API.

        Args:
            method: HTTP method (GET, POST, PUT, DELETE)
            endpoint: API endpoint (e.g., "/api/user")
            json_data: JSON body data
            params: Query parameters

        Returns:
            JSON response as dictionary

        Raises:
            PanelError: If request fails
        """
        token = await self._get_token()
        url = f"{self.api_url}{endpoint}"

        try:
            client = await self.client
            response = await client.request(
                method=method,
                url=url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Accept": "application/json",
                    "Content-Type": "application/json",
                },
                json=json_data,
                params=params,
            )
            response.raise_for_status()

            # Handle empty responses
            if response.status_code == 204 or not response.text:
                return {}

            return response.json()
        except httpx.HTTPStatusError as e:
            error_detail = ""
            try:
                error_data = e.response.json()
                error_detail = error_data.get("detail", str(error_data))
            except Exception:
                error_detail = e.response.text or str(e)

            if e.response.status_code == 401:
                # Token expired, clear it and try to refresh
                self._token = None
                self._token_expires_at = None

                # If we have username/password, try to re-authenticate
                if self.username and self.password:
                    try:
                        # Re-authenticate and retry the request once
                        await self._get_token()
                        # Retry the original request
                        client = await self.client
                        response = await client.request(
                            method=method,
                            url=url,
                            headers={
                                "Authorization": f"Bearer {await self._get_token()}",
                                "Accept": "application/json",
                                "Content-Type": "application/json",
                            },
                            json=json_data,
                            params=params,
                        )
                        response.raise_for_status()
                        if response.status_code == 204 or not response.text:
                            return {}
                        return response.json()
                    except Exception:
                        # If retry fails, raise authentication error
                        pass

                raise PanelAuthenticationError(
                    f"Marzban authentication failed: {error_detail}",
                ) from e
            elif e.response.status_code == 404:
                raise PanelError(
                    f"Marzban resource not found: {error_detail}",
                ) from e
            else:
                raise PanelError(
                    f"Marzban API error ({e.response.status_code}): {error_detail}",
                ) from e
        except httpx.RequestError as e:
            raise PanelConnectionError(
                f"Failed to connect to Marzban API: {e}",
            ) from e

    @retry_with_backoff(max_retries=3, initial_delay=0.5)
    async def create_user(
        self,
        *,
        username: str,
        expire_ts: int | None = None,
        data_limit_bytes: int | None = None,
        proxies: dict[str, Any] | None = None,
        inbounds: list[str] | None = None,
    ) -> dict[str, Any]:
        """
        Create a new user.

        Args:
            username: Username for the user
            expire_ts: Expiration timestamp (Unix). 0 or None = no expiration
            data_limit_bytes: Data limit in bytes. 0 or None = unlimited
            proxies: Proxy settings (protocols configuration)
            inbounds: List of inbound tags

        Returns:
            User data dictionary
        """
        data: dict[str, Any] = {
            "username": username,
        }

        if expire_ts is not None and expire_ts > 0:
            data["expire"] = expire_ts
        else:
            data["expire"] = 0

        if data_limit_bytes is not None and data_limit_bytes > 0:
            data["data_limit"] = data_limit_bytes
        else:
            data["data_limit"] = 0

        if proxies:
            data["proxies"] = proxies
        else:
            # Default proxies for all protocols
            data["proxies"] = {
                "vless": {},
                "vmess": {},
                "trojan": {},
                "shadowsocks": {},
            }

        if inbounds:
            data["inbounds"] = inbounds

        return await self._request("POST", "/api/user", json_data=data)

    @retry_with_backoff(max_retries=3, initial_delay=0.5)
    async def get_user(self, *, username: str) -> dict[str, Any]:
        """
        Get user information.

        Args:
            username: Username to retrieve

        Returns:
            User data dictionary
        """
        return await self._request("GET", f"/api/user/{username}")

    @retry_with_backoff(max_retries=3, initial_delay=0.5)
    async def update_user(
        self,
        *,
        username: str,
        expire_ts: int | None = None,
        data_limit_bytes: int | None = None,
        proxies: dict[str, Any] | None = None,
        status: str | None = None,
    ) -> dict[str, Any]:
        """
        Update user information.

        Args:
            username: Username to update
            expire_ts: New expiration timestamp
            data_limit_bytes: New data limit in bytes
            proxies: New proxy settings
            status: New status (active, disabled, on_hold, limited, expired)

        Returns:
            Updated user data dictionary
        """
        data: dict[str, Any] = {}

        if expire_ts is not None:
            data["expire"] = expire_ts if expire_ts > 0 else 0

        if data_limit_bytes is not None:
            data["data_limit"] = data_limit_bytes if data_limit_bytes > 0 else 0

        if proxies:
            data["proxies"] = proxies

        if status:
            data["status"] = status

        return await self._request("PUT", f"/api/user/{username}", json_data=data)

    @retry_with_backoff(max_retries=3, initial_delay=0.5)
    async def delete_user(self, *, username: str) -> None:
        """
        Delete a user.

        Args:
            username: Username to delete
        """
        await self._request("DELETE", f"/api/user/{username}")

    @retry_with_backoff(max_retries=3, initial_delay=0.5)
    async def reset_user_traffic(self, *, username: str) -> dict[str, Any]:
        """
        Reset user's used traffic.

        Args:
            username: Username to reset

        Returns:
            Response dictionary
        """
        return await self._request("POST", f"/api/user/{username}/reset")

    @retry_with_backoff(max_retries=3, initial_delay=0.5)
    async def revoke_subscription(self, *, username: str) -> dict[str, Any]:
        """
        Revoke user's subscription (rotate credentials).

        Args:
            username: Username to revoke subscription for

        Returns:
            Response dictionary
        """
        return await self._request("POST", f"/api/user/{username}/revoke_sub")

    @retry_with_backoff(max_retries=2, initial_delay=0.3)
    async def get_system_stats(self) -> dict[str, Any]:
        """
        Get system statistics.

        Returns:
            System statistics dictionary
        """
        return await self._request("GET", "/api/system")

    @retry_with_backoff(max_retries=2, initial_delay=0.3)
    async def health_check(self) -> bool:
        """
        Check if Marzban panel is accessible.

        Returns:
            True if panel is healthy
        """
        try:
            await self.get_system_stats()
            return True
        except Exception as e:
            logger.warning(f"Marzban health check failed: {e}")
            return False

    async def close(self) -> None:
        """Close HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None
