"""Public subscription endpoint for clients (returns base64 config list)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Response
from sqlalchemy import select

from database.models import Service
from database.session import AsyncSessionLocal
from services.subscription import build_subscription_payload

router = APIRouter()


@router.get("/sub/{token}")
async def sub(token: str) -> Response:
    tok = (token or "").strip()
    if not tok:
        raise HTTPException(status_code=400, detail="bad token")
    async with AsyncSessionLocal() as db:
        res = await db.execute(select(Service).where(Service.sub_token == tok).limit(1))
        svc = res.scalars().first()
        if not svc or not svc.config_link:
            raise HTTPException(status_code=404, detail="not found")
        payload = build_subscription_payload([svc.config_link])
        return Response(content=payload, media_type="text/plain; charset=utf-8")
