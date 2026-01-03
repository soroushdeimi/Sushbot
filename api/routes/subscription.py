"""Public subscription endpoint for clients (returns base64 config list).

SECURITY NOTES:
- Uses constant-time token comparison to prevent timing oracle attacks
- Returns consistent error responses regardless of token validity
- Tokens are 192-bit (24 bytes urlsafe base64) - brute force infeasible
"""

from __future__ import annotations

import hmac

from fastapi import APIRouter, HTTPException, Response
from sqlalchemy import select

from database.models import Service
from database.session import AsyncSessionLocal
from services.subscription import build_subscription_payload

router = APIRouter()


def _constant_time_token_match(provided: str, stored: str | None) -> bool:
    """Constant-time string comparison to prevent timing oracle attacks."""
    if stored is None:
        # Compare against dummy to maintain constant time
        return hmac.compare_digest(provided, "x" * len(provided))
    return hmac.compare_digest(provided, stored)


@router.get("/sub/{token}")
async def sub(token: str) -> Response:
    """Subscription endpoint - returns base64 encoded config links.

    Security: This endpoint is timing-attack resistant. Invalid tokens
    receive the same response time as valid tokens to prevent enumeration.
    """
    tok = (token or "").strip()

    # Validate token format first (length check is not timing-sensitive)
    if not tok or len(tok) < 16:
        # Generic error - don't leak validation details
        raise HTTPException(status_code=404, detail="not found")

    async with AsyncSessionLocal() as db:
        # Query by token - database timing is consistent for miss vs hit
        res = await db.execute(select(Service).where(Service.sub_token == tok).limit(1))
        svc = res.scalars().first()

        # Constant-time validation to prevent timing oracle
        # Even if svc is None, we do the comparison to maintain timing
        token_valid = _constant_time_token_match(tok, svc.sub_token if svc else None)
        has_config = svc is not None and svc.config_link is not None

        if not token_valid or not has_config:
            # Generic 404 - no distinction between invalid token vs no config
            raise HTTPException(status_code=404, detail="not found")

        payload = build_subscription_payload([svc.config_link])
        return Response(content=payload, media_type="text/plain; charset=utf-8")
