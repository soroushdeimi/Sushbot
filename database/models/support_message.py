"""Support ticket message (threaded conversation)."""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .support import SupportTicket


class SupportSender(str, Enum):
    USER = "user"
    ADMIN = "admin"
    SYSTEM = "system"


class SupportMessageType(str, Enum):
    TEXT = "text"
    PHOTO = "photo"
    FILE = "file"
    VOICE = "voice"


class SupportMessage(Base, TimestampMixin):
    __tablename__ = "support_messages"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ticket_id: Mapped[int] = mapped_column(
        ForeignKey("support_tickets.id", ondelete="CASCADE"), index=True
    )

    sender_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)
    sender_type: Mapped[SupportSender] = mapped_column(
        default=SupportSender.USER, nullable=False, index=True
    )

    message_type: Mapped[SupportMessageType] = mapped_column(
        default=SupportMessageType.TEXT, nullable=False, index=True
    )
    text: Mapped[str | None] = mapped_column(Text, nullable=True)
    telegram_file_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    caption: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Optional metadata for future (mime, size, etc.)
    meta: Mapped[str | None] = mapped_column(Text, nullable=True)

    ticket: Mapped[SupportTicket] = relationship(
        "SupportTicket", back_populates="messages", lazy="selectin"
    )
