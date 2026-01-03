"""Support ticket model."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin
from .support_message import SupportMessage


class TicketStatus(str, Enum):
    """Ticket status enumeration."""

    OPEN = "open"
    IN_PROGRESS = "in_progress"
    WAITING_USER = "waiting_user"
    RESOLVED = "resolved"
    CLOSED = "closed"


class SupportTicket(Base, TimestampMixin):
    """Support ticket model."""

    __tablename__ = "support_tickets"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)

    # Relationship
    user: Mapped["User"] = relationship("User", back_populates="support_tickets")
    messages: Mapped[list["SupportMessage"]] = relationship(
        "SupportMessage",
        back_populates="ticket",
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    ticket_number: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    # Legacy first message (kept for backward compatibility; new messages in support_messages)
    message: Mapped[str] = mapped_column(Text, nullable=False)

    status: Mapped[TicketStatus] = mapped_column(default=TicketStatus.OPEN, nullable=False, index=True)
    priority: Mapped[int] = mapped_column(Integer, default=3, nullable=False)  # 1=High, 2=Medium, 3=Low

    # Admin assignment
    assigned_to_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)

    # Resolution
    resolved_at: Mapped[datetime | None] = mapped_column(nullable=True)
    resolved_by_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    resolution_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # User notification
    user_notified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_admin_response_at: Mapped[datetime | None] = mapped_column(nullable=True)

    def __repr__(self) -> str:
        return f"<SupportTicket(id={self.id}, ticket_number={self.ticket_number}, status={self.status})>"

    @property
    def is_open(self) -> bool:
        """Check if ticket is open."""
        return self.status in [TicketStatus.OPEN, TicketStatus.IN_PROGRESS, TicketStatus.WAITING_USER]

    @property
    def is_resolved(self) -> bool:
        """Check if ticket is resolved."""
        return self.status in [TicketStatus.RESOLVED, TicketStatus.CLOSED]

