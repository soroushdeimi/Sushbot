"""User model for Telegram users."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, SoftDeleteMixin, TimestampMixin

if TYPE_CHECKING:
    from .user_state import UserState
    from .purchase import Purchase
    from .trial import TrialAccount
    from .support import SupportTicket


class UserRole(str, Enum):
    """User role enumeration."""

    USER = "user"
    RESELLER = "reseller"
    ADMIN = "admin"


class UserStatus(str, Enum):
    """User status enumeration."""

    ACTIVE = "active"
    BANNED = "banned"
    SUSPENDED = "suspended"


class User(Base, TimestampMixin, SoftDeleteMixin):
    """User model representing Telegram users."""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=False)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, nullable=False, index=True)
    username: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    first_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone_number: Mapped[str | None] = mapped_column(String(20), nullable=True, unique=True, index=True)
    phone_verified: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    phone_verified_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # Optional password (for admin web panel login)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)

    role: Mapped[UserRole] = mapped_column(default=UserRole.USER, nullable=False, index=True)
    status: Mapped[UserStatus] = mapped_column(default=UserStatus.ACTIVE, nullable=False, index=True)

    language_code: Mapped[str | None] = mapped_column(String(10), nullable=True, default="fa")
    channel_member: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    balance: Mapped[int] = mapped_column(default=0, nullable=False)  # Balance in Rials (Toman)
    total_spent: Mapped[int] = mapped_column(default=0, nullable=False)  # Total spent in Rials

    referral_code: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True, index=True)
    referred_by_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True, index=True)

    last_activity: Mapped[datetime | None] = mapped_column(nullable=True)

    # Relationships
    services: Mapped[list["Service"]] = relationship("Service", back_populates="user", lazy="selectin")
    purchases: Mapped[list["Purchase"]] = relationship("Purchase", back_populates="user", lazy="selectin")
    trial_accounts: Mapped[list["TrialAccount"]] = relationship("TrialAccount", back_populates="user", lazy="selectin")
    support_tickets: Mapped[list["SupportTicket"]] = relationship("SupportTicket", back_populates="user", lazy="selectin")
    state: Mapped["UserState | None"] = relationship(
        "UserState",
        back_populates="user",
        uselist=False,
        lazy="selectin",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<User(id={self.id}, telegram_id={self.telegram_id}, username={self.username})>"

    @property
    def full_name(self) -> str:
        """Get user's full name."""
        parts = [self.first_name, self.last_name]
        return " ".join(filter(None, parts)) or (self.username or f"User {self.telegram_id}")

    @property
    def is_admin(self) -> bool:
        """Check if user is an admin."""
        return self.role == UserRole.ADMIN

    @property
    def is_reseller(self) -> bool:
        """Check if user is a reseller."""
        return self.role == UserRole.RESELLER

    @property
    def is_verified(self) -> bool:
        """Check if user phone is verified."""
        return self.phone_verified

