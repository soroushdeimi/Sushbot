"""PasarGuard panel integration using direct database access."""

from __future__ import annotations

import asyncio
import base64
import json
import uuid
from collections.abc import Awaitable, Callable
from typing import Any
from urllib.parse import quote, urlencode, urlparse, urlunparse

import asyncpg
from cryptography.hazmat.primitives.asymmetric import x25519
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from config.settings import settings


class PasarGuardDBClient:
    """Client for interacting with PasarGuard panel via direct database access."""

    def __init__(
        self,
        db_url: str | None = None,
        node_id: int | None = None,
    ) -> None:
        """Initialize PasarGuard database client."""
        # Extract connection info from PasarGuard database URL
        # Format: postgresql://user:pass@host:port/dbname or postgresql+asyncpg://...
        if db_url is None:
            # Parse the database URL to change database name from sushbotseller to pasarguard
            parsed = urlparse(settings.database_url)
            # Remove the +asyncpg driver prefix if present (asyncpg doesn't use it)
            scheme = parsed.scheme.split("+")[0]  # postgresql+asyncpg -> postgresql

            # Change database name from sushbotseller to pasarguard
            path_parts = parsed.path.strip("/").split("/")
            if path_parts and path_parts[0]:
                # Replace database name
                if path_parts[0] == "sushbotseller":
                    path_parts[0] = "pasarguard"
                else:
                    # If database name is different, assume it should be pasarguard
                    path_parts[0] = "pasarguard"

            db_url = urlunparse(parsed._replace(scheme=scheme, path="/" + "/".join(path_parts)))

        self.db_url = db_url
        self.node_id = node_id or settings.pasarguard_node_id
        self._pool: asyncpg.Pool | None = None

    async def _get_pool(self) -> asyncpg.Pool:
        """Get or create database connection pool."""
        if self._pool is None:
            self._pool = await asyncpg.create_pool(
                self.db_url,
                min_size=1,
                max_size=5,
                command_timeout=10,
            )
        return self._pool

    async def _with_retry[T](self, fn: Callable[[], Awaitable[T]], *, retries: int = 3) -> T:
        """Retry transient DB errors with exponential backoff (closes pool between attempts)."""
        delay = 0.3
        last: Exception | None = None
        for _ in range(retries):
            try:
                return await fn()
            except (
                asyncpg.PostgresConnectionError,
                asyncpg.InterfaceError,
                ConnectionError,
                TimeoutError,
            ) as e:
                last = e
                await self.close()
                await asyncio.sleep(delay)
                delay = min(2.0, delay * 2)
        assert last is not None
        raise last

    async def health_check(self) -> bool:
        """Cheap health check against PasarGuard DB."""
        async def _q() -> int:
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                v = await conn.fetchval("SELECT 1")
                return int(v)

        try:
            return await self._with_retry(_q, retries=2) == 1
        except Exception:
            return False

    async def close(self) -> None:
        """Close database connection pool."""
        if self._pool:
            await self._pool.close()
            self._pool = None

    async def get_inbound_by_tag(self, tag: str) -> dict[str, Any] | None:
        """Get inbound by tag."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, tag FROM inbounds WHERE tag = $1",
                tag,
            )
            if row:
                return dict(row)
            return None

    async def get_or_create_inbound(self, tag: str) -> dict[str, Any]:
        """Get or create an inbound by tag."""
        inbound = await self.get_inbound_by_tag(tag)
        if inbound:
            return inbound

        pool = await self._get_pool()
        async with pool.acquire() as conn:
            inbound_id = await conn.fetchval(
                "INSERT INTO inbounds (tag) VALUES ($1) ON CONFLICT (tag) DO UPDATE SET tag = EXCLUDED.tag RETURNING id",
                tag,
            )
            return {"id": inbound_id, "tag": tag}

    async def get_hosts_by_inbound_tag(self, inbound_tag: str) -> list[dict[str, Any]]:
        """Get all hosts for an inbound tag."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            rows = await conn.fetch(
                """
                SELECT id, remark, address, port, inbound_tag, sni, host, security,
                       fingerprint, allowinsecure, is_disabled, path,
                       transport_settings, mux_settings, noise_settings, fragment_settings
                FROM hosts
                WHERE inbound_tag = $1 AND is_disabled = FALSE
                ORDER BY priority ASC
                LIMIT 1
                """,
                inbound_tag,
            )
            return [dict(row) for row in rows]

    async def _get_inbound_reality_settings(self, inbound_tag: str) -> dict[str, Any]:
        """
        Fetch Reality settings from `core_configs.config` for a given inbound tag.

        This is where PasarGuard stores `privateKey`, `shortIds`, `SpiderX`, and `serverNames`.
        """
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT jsonb_path_query_first(
                    config::jsonb,
                    format('$.inbounds[*] ? (@.tag == \"%s\")', $1::text)::jsonpath
                ) AS inbound
                FROM core_configs
                WHERE jsonb_path_exists(
                    config::jsonb,
                    format('$.inbounds[*] ? (@.tag == \"%s\")', $1::text)::jsonpath
                )
                LIMIT 1
                """,
                inbound_tag,
            )
            if not row or not row["inbound"]:
                raise ValueError(f"Reality inbound not found in core_configs for tag={inbound_tag}")
            inbound = row["inbound"]
            if isinstance(inbound, str):
                inbound = json.loads(inbound)
            stream = inbound.get("streamSettings") or {}
            reality = stream.get("realitySettings") or {}
            if (stream.get("security") or "").lower() != "reality":
                raise ValueError(f"Inbound {inbound_tag} is not Reality")
            return reality

    @staticmethod
    def _b64url_decode_nopad(s: str) -> bytes:
        pad = "=" * ((4 - len(s) % 4) % 4)
        return base64.urlsafe_b64decode(s + pad)

    @staticmethod
    def _b64url_encode_nopad(b: bytes) -> str:
        return base64.urlsafe_b64encode(b).decode().rstrip("=")

    async def _get_reality_client_params(self, inbound_tag: str) -> dict[str, str]:
        """Derive client-facing Reality params (pbk/sid/spx) for config links."""
        reality = await self._get_inbound_reality_settings(inbound_tag)

        private_key_b64 = reality.get("privateKey")
        short_ids = reality.get("shortIds") or []
        spider_x = reality.get("SpiderX") or reality.get("spiderX") or "/"
        server_names = reality.get("serverNames") or []

        if not private_key_b64 or not short_ids:
            raise ValueError(f"Reality settings incomplete for inbound {inbound_tag}")

        priv_bytes = self._b64url_decode_nopad(private_key_b64)
        if len(priv_bytes) != 32:
            raise ValueError("Reality privateKey must be 32 bytes")

        priv = x25519.X25519PrivateKey.from_private_bytes(priv_bytes)
        pub = priv.public_key().public_bytes(encoding=Encoding.Raw, format=PublicFormat.Raw)

        return {
            "pbk": self._b64url_encode_nopad(pub),
            "sid": str(short_ids[0]),
            "spx": str(spider_x),
            "sni_default": str(server_names[0]) if server_names else "www.microsoft.com",
        }

    async def _get_group_id_for_inbound(self, inbound_tag: str) -> int:
        """Find the group_id connected to an inbound via `inbounds_groups_association`."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT iga.group_id
                FROM inbounds_groups_association iga
                JOIN inbounds i ON i.id = iga.inbound_id
                WHERE i.tag = $1
                LIMIT 1
                """,
                inbound_tag,
            )
            if not row:
                raise ValueError(f"No group linked to inbound tag: {inbound_tag}")
            return int(row["group_id"])

    async def get_or_create_pasarguard_user(
        self,
        *,
        inbound_tag: str,
        username: str,
        expire_ts: int | None,
        data_limit_bytes: int | None,
        flow: str = "xtls-rprx-vision",
    ) -> dict[str, Any]:
        """
        Create (or fetch) a PasarGuard `users` row with protocol proxy_settings and group membership.

        Returns: {user_id, username, proxy_settings, group_id}
        """
        pool = await self._get_pool()
        group_id = await self._get_group_id_for_inbound(inbound_tag)

        async with pool.acquire() as conn:
            existing = await conn.fetchrow(
                "SELECT id, username, proxy_settings FROM users WHERE username = $1",
                username,
            )
            if existing:
                # Ensure group membership
                await conn.execute(
                    """
                    INSERT INTO users_groups_association (user_id, groups_id)
                    VALUES ($1, $2)
                    ON CONFLICT DO NOTHING
                    """,
                    existing["id"],
                    group_id,
                )
                return {
                    "user_id": int(existing["id"]),
                    "username": existing["username"],
                    "proxy_settings": existing["proxy_settings"],
                    "group_id": group_id,
                }

            vless_id = str(uuid.uuid4())
            vmess_id = str(uuid.uuid4())
            trojan_pw = base64.urlsafe_b64encode(uuid.uuid4().bytes).decode().rstrip("=")
            ss_pw = base64.urlsafe_b64encode(uuid.uuid4().bytes).decode().rstrip("=")
            proxy_settings = {
                "vless": {"id": vless_id, "flow": flow},
                "vmess": {"id": vmess_id},
                "trojan": {"password": trojan_pw},
                "shadowsocks": {"method": "chacha20-ietf-poly1305", "password": ss_pw},
            }

            # Insert user (with conflict handling for unique constraint violations)
            try:
                user_row = await conn.fetchrow(
                    """
                    INSERT INTO users (username, status, used_traffic, data_limit, expire, proxy_settings)
                    VALUES (
                        $1,
                        'active',
                        0,
                        $2,
                        CASE
                            WHEN $3::bigint IS NULL OR $3::bigint <= 0 THEN NULL
                            ELSE to_timestamp($3::bigint)
                        END,
                        $4::jsonb
                    )
                    RETURNING id, username, proxy_settings
                    """,
                    username,
                    data_limit_bytes,
                    expire_ts,
                    json.dumps(proxy_settings),
                )
            except asyncpg.UniqueViolationError:
                # Race condition: user was created between our SELECT and INSERT
                # Fetch the existing user
                existing = await conn.fetchrow(
                    "SELECT id, username, proxy_settings FROM users WHERE username = $1",
                    username,
                )
                if not existing:
                    raise ValueError(f"Username {username} conflict but user not found")
                user_row = existing

            await conn.execute(
                """
                INSERT INTO users_groups_association (user_id, groups_id)
                VALUES ($1, $2)
                ON CONFLICT DO NOTHING
                """,
                user_row["id"],
                group_id,
            )

            return {
                "user_id": int(user_row["id"]),
                "username": user_row["username"],
                "proxy_settings": user_row["proxy_settings"],
                "group_id": group_id,
            }

    async def update_user_expire(self, *, username: str, expire_ts: int | None) -> None:
        """Set user.expire (unix ts). None/0 clears expiry."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            if not expire_ts or expire_ts <= 0:
                await conn.execute("UPDATE users SET expire = NULL WHERE username = $1", username)
            else:
                await conn.execute(
                    "UPDATE users SET expire = to_timestamp($2) WHERE username = $1",
                    username,
                    int(expire_ts),
                )

    async def update_user_data_limit(self, *, username: str, data_limit_bytes: int | None) -> None:
        """Set user.data_limit in bytes. None/0 -> unlimited."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            if not data_limit_bytes or data_limit_bytes <= 0:
                await conn.execute("UPDATE users SET data_limit = NULL WHERE username = $1", username)
            else:
                await conn.execute(
                    "UPDATE users SET data_limit = $2 WHERE username = $1",
                    username,
                    int(data_limit_bytes),
                )

    async def add_user_data_limit(self, *, username: str, add_bytes: int) -> None:
        """Increase data_limit by add_bytes; if unlimited (NULL) keep unlimited."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT data_limit FROM users WHERE username = $1", username)
            if not row:
                raise ValueError("PasarGuard user not found")
            cur = row["data_limit"]
            if cur is None:
                return
            await conn.execute(
                "UPDATE users SET data_limit = $2 WHERE username = $1",
                username,
                int(cur) + int(add_bytes),
            )

    async def reset_user_traffic(self, *, username: str) -> None:
        """Reset used_traffic to 0."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute("UPDATE users SET used_traffic = 0 WHERE username = $1", username)

    async def set_user_status(self, *, username: str, status: str) -> None:
        """Set users.status (enum: active/disabled/limited/expired/on_hold)."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            await conn.execute("UPDATE users SET status = $2::userstatus WHERE username = $1", username, status)

    async def rotate_proxy_credentials(self, *, username: str, flow: str = "xtls-rprx-vision") -> dict[str, Any]:
        """
        Rotate all proxy credentials (vless/vmess/trojan/ss) similar to 'revoke_sub' semantics.
        Returns updated proxy_settings dict.
        """
        pool = await self._get_pool()
        vless_id = str(uuid.uuid4())
        vmess_id = str(uuid.uuid4())
        trojan_pw = base64.urlsafe_b64encode(uuid.uuid4().bytes).decode().rstrip("=")
        ss_pw = base64.urlsafe_b64encode(uuid.uuid4().bytes).decode().rstrip("=")
        proxy_settings = {
            "vless": {"id": vless_id, "flow": flow},
            "vmess": {"id": vmess_id},
            "trojan": {"password": trojan_pw},
            "shadowsocks": {"method": "chacha20-ietf-poly1305", "password": ss_pw},
        }
        async with pool.acquire() as conn:
            await conn.execute(
                "UPDATE users SET proxy_settings = $2::jsonb, sub_revoked_at = now() WHERE username = $1",
                username,
                json.dumps(proxy_settings),
            )
            row = await conn.fetchrow("SELECT proxy_settings FROM users WHERE username = $1", username)
            return {"proxy_settings": row["proxy_settings"]}

    async def get_user_stats(self, *, username: str) -> dict[str, Any]:
        """Fetch PasarGuard user stats for syncing into bot DB."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT id, username, status, used_traffic, data_limit, expire, proxy_settings FROM users WHERE username = $1",
                username,
            )
            if not row:
                raise ValueError("PasarGuard user not found")
            return dict(row)

    async def create_host(
        self,
        inbound_tag: str,
        remark: str,
        address: str,
        port: int,
        sni: str | None = None,
        host: str | None = None,
        security: str = "reality",
        fingerprint: str = "firefox",
    ) -> dict[str, Any]:
        """Create a new host for an inbound."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            host_id = await conn.fetchval(
                """
                INSERT INTO hosts (
                    remark, address, port, inbound_tag, sni, host,
                    security, fingerprint, priority
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, 0)
                RETURNING id
                """,
                remark,
                address,
                port,
                inbound_tag,
                sni,
                host,
                security,
                fingerprint,
            )
            return {
                "id": host_id,
                "remark": remark,
                "address": address,
                "port": port,
                "inbound_tag": inbound_tag,
            }

    async def get_or_create_client(
        self,
        inbound_tag: str,
        email: str,
        client_uuid: str | None = None,
    ) -> dict[str, Any]:
        """Get or create a client for an inbound."""
        # Ensure inbound exists
        inbound = await self.get_or_create_inbound(inbound_tag)

        # Get host
        hosts = await self.get_hosts_by_inbound_tag(inbound_tag)
        if not hosts:
            raise ValueError(f"No active host found for inbound tag: {inbound_tag}")
        host = hosts[0]

        # Create/fetch PasarGuard user
        pg_user = await self.get_or_create_pasarguard_user(
            inbound_tag=inbound_tag,
            username=email,
            expire_ts=None,
            data_limit_bytes=None,
        )
        proxy_settings = pg_user["proxy_settings"] or {}
        vless = (proxy_settings.get("vless") or {}) if isinstance(proxy_settings, dict) else {}
        vless_id = vless.get("id") or str(uuid.uuid4())

        return {
            "inbound_id": inbound["id"],
            "inbound_tag": inbound_tag,
            "host_id": host["id"],
            "email": email,
            "uuid": vless_id,
            "address": host["address"],
            "port": host["port"],
            "sni": host.get("sni"),
            "fingerprint": host.get("fingerprint") or "firefox",
        }

    async def create_inbound(
        self,
        protocol: str = "vless",
        port: int = 8443,
        remark: str | None = None,
        stream_settings: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Create a new inbound (creates tag)."""
        tag = remark or f"{protocol.upper()}-{port}"
        inbound = await self.get_or_create_inbound(tag)
        return {"id": inbound["id"], "tag": inbound["tag"], "protocol": protocol, "port": port}

    async def add_client(
        self,
        inbound_id: int,
        email: str,
        uuid: str | None = None,
        flow: str = "xtls-rprx-vision",
        enable: bool = True,
        protocol: str | None = None,
    ) -> dict[str, Any]:
        """Add a client to an inbound (compatibility method)."""
        # Get inbound tag from id
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT tag FROM inbounds WHERE id = $1", inbound_id)
            if not row:
                raise ValueError(f"Inbound {inbound_id} not found")
            inbound_tag = row["tag"]

        return await self.get_or_create_client(inbound_tag, email, uuid)

    async def get_inbound(self, inbound_id: int) -> dict[str, Any]:
        """Get inbound details (compatibility method)."""
        pool = await self._get_pool()
        async with pool.acquire() as conn:
            row = await conn.fetchrow("SELECT id, tag FROM inbounds WHERE id = $1", inbound_id)
            if not row:
                raise ValueError(f"Inbound {inbound_id} not found")
            return dict(row)

    async def get_client_config(
        self,
        inbound_id: int,
        client_email: str,
    ) -> dict[str, Any]:
        """Get client configuration (compatibility method)."""
        inbound = await self.get_inbound(inbound_id)
        return await self.get_or_create_client(inbound["tag"], client_email)

    async def generate_config_link(
        self,
        inbound_tag: str,
        email: str,
        client_uuid: str | None = None,
        protocol: str = "vless",
        proxy_settings: dict[str, Any] | None = None,
    ) -> str:
        """Generate configuration link for client."""
        hosts = await self.get_hosts_by_inbound_tag(inbound_tag)
        if not hosts:
            raise ValueError(f"No host found for inbound tag: {inbound_tag}")

        host = hosts[0]
        address = host["address"]
        port = host["port"]
        fingerprint = host.get("fingerprint") or "firefox"
        sni = host.get("sni") or host.get("host")

        protocol = (protocol or "vless").lower()

        # Fetch proxy_settings from DB if not provided (PasarGuard stores it per username).
        if proxy_settings is None:
            pool = await self._get_pool()
            async with pool.acquire() as conn:
                row = await conn.fetchrow("SELECT proxy_settings FROM users WHERE username = $1", email)
                if row and row["proxy_settings"]:
                    ps = row["proxy_settings"]
                    if isinstance(ps, str):
                        ps = json.loads(ps)
                    if isinstance(ps, dict):
                        proxy_settings = ps

        proxy_settings = proxy_settings or {}

        if protocol == "vless":
            params = await self._get_reality_client_params(inbound_tag)
            pbk = params["pbk"]
            sid = params["sid"]
            spx = params["spx"]
            sni = sni or params["sni_default"]
            vless_uuid = client_uuid
            if not vless_uuid:
                vless_uuid = (proxy_settings.get("vless") or {}).get("id")
            if not vless_uuid:
                raise ValueError("Missing vless uuid for user")

            # Build query parameters properly (URL-encoded like PasarGuard panel does)
            query_params = {
                "encryption": "none",
                "security": "reality",
                "sni": sni,
                "fp": fingerprint,
                "pbk": pbk,
                "sid": sid,
                "spx": spx,
                "type": "tcp",
                "headerType": "none",
            }
            query_string = urlencode(query_params)

            # URL-encode the email fragment (like PasarGuard panel does)
            encoded_email = quote(email)

            config = f"vless://{vless_uuid}@{address}:{port}?{query_string}#{encoded_email}"
            return config

        if protocol == "vmess":
            vmess_id = (proxy_settings.get("vmess") or {}).get("id") or client_uuid
            if not vmess_id:
                raise ValueError("Missing vmess id for user")
            obj = {
                "v": "2",
                "ps": email,
                "add": address,
                "port": str(port),
                "id": vmess_id,
                "aid": "0",
                "scy": "auto",
                "net": "tcp",
                "type": "none",
                "host": "",
                "path": "",
                "tls": host.get("security") or "tls",
                "sni": sni or "",
                "fp": fingerprint,
            }
            b = base64.b64encode(json.dumps(obj, ensure_ascii=False).encode("utf-8")).decode("ascii")
            return f"vmess://{b}"

        if protocol == "trojan":
            pw = (proxy_settings.get("trojan") or {}).get("password")
            if not pw:
                raise ValueError("Missing trojan password for user")
            sec = host.get("security") or "tls"
            query_params = {"security": sec}
            if sni:
                query_params["sni"] = sni
            qs = urlencode(query_params)
            encoded_email = quote(email)
            return f"trojan://{pw}@{address}:{port}?{qs}#{encoded_email}"

        if protocol in {"shadowsocks", "ss"}:
            ss = proxy_settings.get("shadowsocks") or {}
            method = ss.get("method") or "chacha20-ietf-poly1305"
            pw = ss.get("password")
            if not pw:
                raise ValueError("Missing shadowsocks password for user")
            userinfo = base64.urlsafe_b64encode(f"{method}:{pw}".encode()).decode().rstrip("=")
            encoded_email = quote(email)
            return f"ss://{userinfo}@{address}:{port}#{encoded_email}"

        raise ValueError(f"Unsupported protocol: {protocol}")


# Alias for backward compatibility
PasarGuardClient = PasarGuardDBClient

