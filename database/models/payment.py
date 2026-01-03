"""Payment model for payment transactions."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .purchase import Purchase


class PaymentGateway(str, Enum):
    """Payment gateway enumeration."""

    CARD_TO_CARD = "card_to_card"
    NOWPAYMENTS = "nowpayments"
    AQAYEPARDAKHT = "aqayepardakht"


class PaymentStatus(str, Enum):
    """Payment status enumeration."""

    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"


class Payment(Base, TimestampMixin):
    """Payment model for payment transactions."""

    __tablename__ = "payments"
    __table_args__ = (
        UniqueConstraint("gateway", "gateway_transaction_id", name="uq_payments_gateway_txid"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    purchase_id: Mapped[int] = mapped_column(ForeignKey("purchases.id"), nullable=False, index=True)

    gateway: Mapped[PaymentGateway] = mapped_column(nullable=False, index=True)
    status: Mapped[PaymentStatus] = mapped_column(
        default=PaymentStatus.PENDING, nullable=False, index=True
    )

    # Amount
    amount: Mapped[int] = mapped_column(Numeric(15, 0), nullable=False)  # Amount in Rials
    currency: Mapped[str] = mapped_column(String(10), default="IRR", nullable=False)

    # Gateway-specific fields
    gateway_transaction_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    gateway_response: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # JSON response from gateway

    # Card-to-card specific
    card_number: Mapped[str | None] = mapped_column(String(20), nullable=True)
    tracking_code: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)

    # Completion
    paid_at: Mapped[datetime | None] = mapped_column(nullable=True)
    verified_at: Mapped[datetime | None] = mapped_column(nullable=True)

    # Notes
    admin_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    purchase: Mapped[Purchase] = relationship("Purchase", back_populates="payments")

    def __repr__(self) -> str:
        return f"<Payment(id={self.id}, gateway={self.gateway}, status={self.status})>"

    @property
    def is_completed(self) -> bool:
        """Check if payment is completed."""
        return self.status == PaymentStatus.COMPLETED

    @property
    def is_pending(self) -> bool:
        """Check if payment is pending."""
        return self.status == PaymentStatus.PENDING
