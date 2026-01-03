"""Trial account model."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .user import User


class TrialAccount(Base, TimestampMixin):
    """Trial account model for trial VPN services."""

    __tablename__ = "trial_accounts"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)

    service_id: Mapped[int | None] = mapped_column(ForeignKey("services.id"), nullable=True, index=True)

    # Trial Details
    duration_days: Mapped[int] = mapped_column(nullable=False, default=1)
    traffic_gb: Mapped[int] = mapped_column(nullable=False, default=1)

    start_date: Mapped[datetime] = mapped_column(nullable=False)
    expiry_date: Mapped[datetime] = mapped_column(nullable=False, index=True)
    is_used: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_expired: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Configuration
    protocol: Mapped[str] = mapped_column(String(50), nullable=False, default="vless")
    config_link: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="trial_accounts")

    def __repr__(self) -> str:
        return f"<TrialAccount(id={self.id}, user_id={self.user_id}, is_used={self.is_used})>"

    @property
    def is_active(self) -> bool:
        """Check if trial is active."""
        if self.is_used or self.is_expired:
            return False
        return self.expiry_date > datetime.utcnow()

    @property
    def days_remaining(self) -> int:
        """Get days remaining."""
        delta = self.expiry_date - datetime.utcnow()
        return max(0, delta.days) if delta.total_seconds() > 0 else 0

