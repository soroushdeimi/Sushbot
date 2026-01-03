"""Reseller pricing and quota models."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .user import User
    from .product import Product


class ResellerPricing(Base, TimestampMixin):
    """Reseller pricing configuration per product."""
    
    __tablename__ = "reseller_pricing"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    reseller_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id: Mapped[int] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=False, index=True)
    discount_percent: Mapped[int] = mapped_column(Integer, nullable=False)  # 0-100
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    
    # Relationships
    reseller: Mapped["User"] = relationship("User", foreign_keys=[reseller_id])
    product: Mapped["Product"] = relationship("Product")

    def __repr__(self) -> str:
        return f"<ResellerPricing(id={self.id}, reseller_id={self.reseller_id}, product_id={self.product_id}, discount_percent={self.discount_percent})>"


class ResellerQuota(Base, TimestampMixin):
    """Reseller quota limits per product."""
    
    __tablename__ = "reseller_quotas"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    reseller_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id", ondelete="CASCADE"), nullable=True, index=True)  # None = global quota
    monthly_limit: Mapped[int | None] = mapped_column(Integer, nullable=True)  # None = unlimited
    current_month_usage: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reset_date: Mapped[datetime] = mapped_column(nullable=False)
    
    # Relationships
    reseller: Mapped["User"] = relationship("User", foreign_keys=[reseller_id])
    product: Mapped["Product | None"] = relationship("Product")

    def __repr__(self) -> str:
        return f"<ResellerQuota(id={self.id}, reseller_id={self.reseller_id}, product_id={self.product_id}, monthly_limit={self.monthly_limit}, current_month_usage={self.current_month_usage})>"

