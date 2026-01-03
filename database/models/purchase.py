"""Purchase model for service purchases."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .payment import Payment
    from .product import Product
    from .service import Service
    from .user import User


class PurchaseStatus(str, Enum):
    """Purchase status enumeration."""

    PENDING = "pending"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"
    FAILED = "failed"


class PurchaseType(str, Enum):
    """Purchase type enumeration."""

    NEW = "new"
    RENEWAL = "renewal"
    ADDITIONAL_VOLUME = "additional_volume"
    WALLET_TOPUP = "wallet_topup"


class Purchase(Base, TimestampMixin):
    """Purchase model for service purchases."""

    __tablename__ = "purchases"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    product_id: Mapped[int | None] = mapped_column(ForeignKey("products.id"), nullable=True, index=True)
    service_id: Mapped[int | None] = mapped_column(ForeignKey("services.id"), nullable=True, index=True)

    purchase_type: Mapped[PurchaseType] = mapped_column(default=PurchaseType.NEW, nullable=False)
    status: Mapped[PurchaseStatus] = mapped_column(default=PurchaseStatus.PENDING, nullable=False, index=True)

    # Pricing
    amount: Mapped[int] = mapped_column(Numeric(15, 0), nullable=False)  # Amount in Rials
    discount_amount: Mapped[int] = mapped_column(Numeric(15, 0), default=0, nullable=False)
    final_amount: Mapped[int] = mapped_column(Numeric(15, 0), nullable=False)
    discount_code_id: Mapped[int | None] = mapped_column(ForeignKey("discount_codes.id"), nullable=True)
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Service Details
    duration_days: Mapped[int] = mapped_column(nullable=False)
    traffic_gb: Mapped[int] = mapped_column(nullable=False)
    protocol: Mapped[str] = mapped_column(String(50), nullable=False)

    # Completion
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # Relationships
    user: Mapped[User] = relationship("User", back_populates="purchases")
    product: Mapped[Product | None] = relationship("Product", back_populates="purchases")
    service: Mapped[Service | None] = relationship("Service", back_populates="purchases")
    payments: Mapped[list[Payment]] = relationship("Payment", back_populates="purchase", lazy="selectin")

    def __repr__(self) -> str:
        return f"<Purchase(id={self.id}, user_id={self.user_id}, status={self.status})>"

    @property
    def is_completed(self) -> bool:
        """Check if purchase is completed."""
        return self.status == PurchaseStatus.COMPLETED

    @property
    def is_pending(self) -> bool:
        """Check if purchase is pending."""
        return self.status == PurchaseStatus.PENDING

