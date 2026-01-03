"""Audit logging helper for API routes and services."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from database.models import AuditLog


async def audit(
    db: AsyncSession,
    *,
    actor_user_id: int,
    action: str,
    entity_type: str | None = None,
    entity_id: str | None = None,
    ip: str | None = None,
    user_agent: str | None = None,
    meta: dict[str, Any] | None = None,
) -> None:
    """
    Create an audit log entry for admin actions.
    
    Args:
        db: Database session
        actor_user_id: ID of the user performing the action
        action: Action name (e.g., "service.transfer", "purchase.refund")
        entity_type: Type of entity affected (e.g., "service", "purchase")
        entity_id: ID of the affected entity
        ip: IP address of the actor (optional, for API requests)
        user_agent: User agent string (optional, for API requests)
        meta: Additional metadata as dictionary (will be JSON-encoded)
    
    Example:
        await audit(
            db,
            actor_user_id=admin_id,
            action="service.transfer",
            entity_type="service",
            entity_id=str(service_id),
            meta={"old_user_id": 123, "new_user_id": 456},
        )
    """
    db.add(
        AuditLog(
            actor_user_id=actor_user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            ip=ip,
            user_agent=user_agent,
            meta=json.dumps(meta or {}, ensure_ascii=False),
        )
    )
    await db.commit()



