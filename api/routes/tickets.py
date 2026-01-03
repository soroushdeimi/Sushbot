"""Support tickets routes (admin panel)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.audit import audit
from api.deps import CurrentAdmin, get_current_admin
from database.models import SupportMessage, SupportSender, SupportTicket, TicketStatus
from database.session import get_db

router = APIRouter()


class TicketOut(BaseModel):
    id: int
    ticket_number: str
    user_id: int
    status: str
    priority: int


class TicketMessageOut(BaseModel):
    id: int
    sender_type: str
    text: str | None
    created_at: str


class ReplyIn(BaseModel):
    text: str


@router.get("/")
async def list_tickets(cur: CurrentAdmin = Depends(get_current_admin), db: AsyncSession = Depends(get_db), limit: int = 50) -> list[TicketOut]:
    res = await db.execute(select(SupportTicket).order_by(SupportTicket.id.desc()).limit(limit))
    items = list(res.scalars().all())
    await audit(db, actor_user_id=cur.user.id, action="api.tickets.list", meta={"limit": limit})
    return [
        TicketOut(
            id=int(t.id),
            ticket_number=t.ticket_number,
            user_id=int(t.user_id),
            status=str(t.status.value if hasattr(t.status, "value") else t.status),
            priority=int(t.priority),
        )
        for t in items
    ]


@router.get("/{ticket_number}")
async def get_ticket(ticket_number: str, cur: CurrentAdmin = Depends(get_current_admin), db: AsyncSession = Depends(get_db)) -> dict:
    tn = ticket_number.strip().upper()
    res = await db.execute(select(SupportTicket).where(SupportTicket.ticket_number == tn).limit(1))
    t = res.scalars().first()
    if not t:
        raise HTTPException(status_code=404, detail="ticket not found")
    res = await db.execute(
        select(SupportMessage).where(SupportMessage.ticket_id == t.id).order_by(SupportMessage.id.asc()).limit(200)
    )
    msgs = list(res.scalars().all())
    await audit(db, actor_user_id=cur.user.id, action="api.tickets.get", entity_type="ticket", entity_id=tn)
    return {
        "ticket": TicketOut(
            id=int(t.id),
            ticket_number=t.ticket_number,
            user_id=int(t.user_id),
            status=str(t.status.value if hasattr(t.status, "value") else t.status),
            priority=int(t.priority),
        ),
        "messages": [
            TicketMessageOut(
                id=int(m.id),
                sender_type=str(m.sender_type.value if hasattr(m.sender_type, "value") else m.sender_type),
                text=m.text,
                created_at=m.created_at.isoformat(),
            )
            for m in msgs
        ],
    }


@router.post("/{ticket_number}/reply")
async def reply_ticket(ticket_number: str, body: ReplyIn, cur: CurrentAdmin = Depends(get_current_admin), db: AsyncSession = Depends(get_db)) -> dict:
    tn = ticket_number.strip().upper()
    res = await db.execute(select(SupportTicket).where(SupportTicket.ticket_number == tn).limit(1))
    t = res.scalars().first()
    if not t:
        raise HTTPException(status_code=404, detail="ticket not found")
    msg = SupportMessage(ticket_id=t.id, sender_id=cur.user.id, sender_type=SupportSender.ADMIN, text=body.text)
    db.add(msg)
    t.status = TicketStatus.WAITING_USER
    await db.commit()
    await audit(db, actor_user_id=cur.user.id, action="api.tickets.reply", entity_type="ticket", entity_id=tn)
    return {"status": "ok"}


@router.post("/{ticket_number}/close")
async def close_ticket(ticket_number: str, cur: CurrentAdmin = Depends(get_current_admin), db: AsyncSession = Depends(get_db)) -> dict:
    tn = ticket_number.strip().upper()
    res = await db.execute(select(SupportTicket).where(SupportTicket.ticket_number == tn).limit(1))
    t = res.scalars().first()
    if not t:
        raise HTTPException(status_code=404, detail="ticket not found")
    t.status = TicketStatus.CLOSED
    await db.commit()
    await audit(db, actor_user_id=cur.user.id, action="api.tickets.close", entity_type="ticket", entity_id=tn)
    return {"status": "ok"}



