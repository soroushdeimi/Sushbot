"""Admin model for bot administrators."""

from __future__ import annotations

from enum import Enum

from sqlalchemy import BigInteger, Boolean, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class AdminLevel(str, Enum):
    """Admin level enumeration."""

    SUPER_ADMIN = "super_admin"
    ADMIN = "admin"
    MANAGEMENT = "management"
    SALES = "sales"
    SUPPORT = "support"


class Admin(Base, TimestampMixin):
    """Admin model for bot administrators."""

    __tablename__ = "admins"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), unique=True, nullable=False, index=True
    )

    level: Mapped[AdminLevel] = mapped_column(
        default=AdminLevel.SUPPORT, nullable=False, index=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Permissions (stored as JSON in database, but using string for simplicity)
    permissions: Mapped[str | None] = mapped_column(String(500), nullable=True)  # JSON string

    # Notes
    notes: Mapped[str | None] = mapped_column(String(500), nullable=True)

    def __repr__(self) -> str:
        return f"<Admin(id={self.id}, user_id={self.user_id}, level={self.level})>"

    @property
    def is_super_admin(self) -> bool:
        """Check if admin is super admin."""
        return self.level == AdminLevel.SUPER_ADMIN

    @property
    def can_manage_users(self) -> bool:
        """Check if admin can manage users."""
        return self.level in [AdminLevel.SUPER_ADMIN, AdminLevel.ADMIN, AdminLevel.MANAGEMENT]

    @property
    def can_manage_sales(self) -> bool:
        """Check if admin can manage sales."""
        return self.level in [
            AdminLevel.SUPER_ADMIN,
            AdminLevel.ADMIN,
            AdminLevel.MANAGEMENT,
            AdminLevel.SALES,
        ]

    @property
    def can_manage_support(self) -> bool:
        """Check if admin can manage support."""
        return self.level in [
            AdminLevel.SUPER_ADMIN,
            AdminLevel.ADMIN,
            AdminLevel.MANAGEMENT,
            AdminLevel.SUPPORT,
        ]
