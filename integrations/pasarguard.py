"""PasarGuard panel integration for automated configuration creation."""

from __future__ import annotations

# Use database-based integration instead of API
from integrations.pasarguard_db import PasarGuardDBClient as PasarGuardClient

# Keep old imports for backward compatibility
from datetime import datetime, timedelta
import uuid
from typing import Any

from loguru import logger

from config.settings import settings


"""
NOTE:
We intentionally removed the old HTTP/API client implementation here.
PasarGuard is integrated via direct Postgres access (`integrations/pasarguard_db.py`)
to keep things stable and fully automated on this server.
"""


async def create_service_config(
    user_email: str,
    protocol: str = "vless",
    port: int = 8443,
    duration_days: int = 30,
    traffic_gb: int = 0,
    panel_id: int = 1,
    inbound_tag: str | None = None,
) -> dict[str, Any]:
    """Create a complete service configuration."""
    client = PasarGuardClient()
    inbound_tag = inbound_tag or "SUSH"

    try:
        # PasarGuard DB user provisioning (creates real proxy_settings with VLESS UUID)
        expire_ts: int | None = None
        if duration_days and duration_days > 0:
            expire_ts = int((datetime.utcnow() + timedelta(days=duration_days)).timestamp())
        data_limit_bytes: int | None = None
        if traffic_gb and traffic_gb > 0:
            data_limit_bytes = int(traffic_gb * (1024**3))

        pg_user = await client.get_or_create_pasarguard_user(
            inbound_tag=inbound_tag,
            username=user_email,
            expire_ts=expire_ts,
            data_limit_bytes=data_limit_bytes,
        )
        proxy = pg_user["proxy_settings"] or {}
        p = (protocol or "vless").lower()
        client_uuid: str | None = None
        if isinstance(proxy, dict):
            if p == "vless":
                client_uuid = (proxy.get("vless") or {}).get("id")
            elif p == "vmess":
                client_uuid = (proxy.get("vmess") or {}).get("id")
        if p in {"vless", "vmess"} and not client_uuid:
            client_uuid = str(uuid.uuid4())

        config_link = await client.generate_config_link(
            inbound_tag=inbound_tag,
            email=user_email,
            client_uuid=client_uuid,
            protocol=protocol,
            proxy_settings=proxy if isinstance(proxy, dict) else None,
        )

        hosts = await client.get_hosts_by_inbound_tag(inbound_tag)
        if not hosts:
            raise ValueError(f"No active host found for inbound tag: {inbound_tag}")
        host = hosts[0]

        inbound = await client.get_inbound_by_tag(inbound_tag)
        inbound_id = inbound["id"] if inbound else None

        return {
            "inbound_id": inbound_id,
            "inbound_tag": inbound_tag,
            "client_email": user_email,
            "client_uuid": client_uuid,
            "config_link": config_link,
            "protocol": protocol,
            "server_address": host.get("address"),
            "port": int(host.get("port") or port),
            "panel_id": panel_id,
        }
    finally:
        await client.close()

