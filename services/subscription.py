"""Subscription link helpers (bot-hosted subscription endpoint)."""

from __future__ import annotations

import base64
import secrets

from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import settings


def build_subscription_payload(links: list[str]) -> str:
    raw = "\n".join([x.strip() for x in links if x and x.strip()]) + "\n"
    return base64.b64encode(raw.encode("utf-8")).decode("ascii")


def subscription_url_from_token(token: str) -> str | None:
    if not settings.public_base_url:
        return None
    base = settings.public_base_url.rstrip("/")
    return f"{base}/api/sub/{token}"


async def ensure_service_sub_token(db: AsyncSession, service) -> str:
    if service.sub_token:
        return str(service.sub_token)
    # 32+ chars urlsafe token
    service.sub_token = secrets.token_urlsafe(24)
    await db.commit()
    return str(service.sub_token)



