"""User state model for multi-step bot flows (Mirza-style, but JSON-based)."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .user import User


class UserState(Base, TimestampMixin):
    """Persistent per-user state for multi-step flows."""

    __tablename__ = "user_states"

    user_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
        autoincrement=False,
    )

    step: Mapped[str] = mapped_column(String(128), nullable=False, index=True, default="none")
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    # Lightweight lock to prevent races (e.g., double-click / multiple updates)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lock_reason: Mapped[str | None] = mapped_column(String(255), nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
        index=True,
    )

    user: Mapped["User"] = relationship("User", back_populates="state")




