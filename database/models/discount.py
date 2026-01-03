"""Discount code model."""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, SoftDeleteMixin, TimestampMixin


class DiscountType(str, Enum):
    """Discount type enumeration."""

    PERCENTAGE = "percentage"
    FIXED_AMOUNT = "fixed_amount"


class DiscountCode(Base, TimestampMixin, SoftDeleteMixin):
    """Discount code model."""

    __tablename__ = "discount_codes"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    code: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, index=True)
    discount_type: Mapped[DiscountType] = mapped_column(default=DiscountType.PERCENTAGE, nullable=False)

    # Discount value
    discount_value: Mapped[int] = mapped_column(Numeric(10, 2), nullable=False)  # Percentage or fixed amount

    # Usage limits
    max_uses: Mapped[int | None] = mapped_column(Integer, nullable=True)  # None means unlimited
    used_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_uses_per_user: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Validity
    valid_from: Mapped[datetime] = mapped_column(nullable=False, index=True)
    valid_until: Mapped[datetime | None] = mapped_column(nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Minimum purchase amount
    min_purchase_amount: Mapped[int] = mapped_column(Numeric(15, 0), default=0, nullable=False)

    def __repr__(self) -> str:
        return f"<DiscountCode(id={self.id}, code={self.code}, discount_type={self.discount_type})>"

    @property
    def is_valid(self) -> bool:
        """Check if discount code is valid."""
        if not self.is_active:
            return False
        if self.valid_until and self.valid_until < datetime.utcnow():
            return False
        if self.max_uses and self.used_count >= self.max_uses:
            return False
        return True

    def calculate_discount(self, amount: int) -> int:
        """Calculate discount amount for given purchase amount."""
        if not self.is_valid:
            return 0
        if amount < self.min_purchase_amount:
            return 0

        if self.discount_type == DiscountType.PERCENTAGE:
            return int((amount * self.discount_value) / 100)
        return int(self.discount_value)

