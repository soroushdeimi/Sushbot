"""Service model for VPN services."""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, SoftDeleteMixin, TimestampMixin

if TYPE_CHECKING:
    from .config import ServiceConfiguration
    from .panel import Panel
    from .purchase import Purchase
    from .user import User


class ServiceType(str, Enum):
    """Service type enumeration."""

    VPN = "vpn"
    TRIAL = "trial"
    RESELLER = "reseller"


class ServiceStatus(str, Enum):
    """Service status enumeration."""

    ACTIVE = "active"
    EXPIRED = "expired"
    SUSPENDED = "suspended"
    CANCELLED = "cancelled"


class Service(Base, TimestampMixin, SoftDeleteMixin):
    """Service model representing VPN service instances."""

    __tablename__ = "services"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id"), nullable=False, index=True
    )

    service_type: Mapped[ServiceType] = mapped_column(
        default=ServiceType.VPN, nullable=False, index=True
    )
    status: Mapped[ServiceStatus] = mapped_column(
        default=ServiceStatus.ACTIVE, nullable=False, index=True
    )

    # Panel and Configuration
    panel_id: Mapped[int] = mapped_column(ForeignKey("panels.id"), nullable=False, index=True)
    config_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )  # PasarGuard config ID
    inbound_id: Mapped[int | None] = mapped_column(
        Integer, nullable=True, index=True
    )  # PasarGuard inbound ID
    client_email: Mapped[str] = mapped_column(String(255), nullable=False, index=True)

    # Service Details
    protocol: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # vless, vmess, trojan, shadowsocks
    server_address: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(nullable=False)

    # Traffic and Duration
    total_traffic_gb: Mapped[int] = mapped_column(default=0, nullable=False)  # 0 means unlimited
    used_traffic_gb: Mapped[float] = mapped_column(default=0.0, nullable=False)
    remaining_traffic_gb: Mapped[float | None] = mapped_column(nullable=True)

    start_date: Mapped[datetime] = mapped_column(nullable=False, index=True)
    expiry_date: Mapped[datetime | None] = mapped_column(nullable=True, index=True)
    is_unlimited: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Configuration Link
    config_link: Mapped[str | None] = mapped_column(Text, nullable=True)
    qr_code: Mapped[str | None] = mapped_column(Text, nullable=True)  # Base64 QR code
    sub_token: Mapped[str | None] = mapped_column(
        String(128), nullable=True, unique=True, index=True
    )

    # Notes
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Notifications (to prevent spam)
    last_expiry_notified_at: Mapped[datetime | None] = mapped_column(nullable=True, index=True)
    last_traffic_notified_at: Mapped[datetime | None] = mapped_column(nullable=True, index=True)

    # Relationships
    user: Mapped[User] = relationship("User", back_populates="services")
    panel: Mapped[Panel] = relationship("Panel", back_populates="services")
    purchases: Mapped[list[Purchase]] = relationship(
        "Purchase", back_populates="service", lazy="selectin"
    )
    configurations: Mapped[list[ServiceConfiguration]] = relationship(
        "ServiceConfiguration",
        back_populates="service",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Service(id={self.id}, user_id={self.user_id}, status={self.status})>"

    @property
    def is_active(self) -> bool:
        """Check if service is active."""
        if self.status != ServiceStatus.ACTIVE:
            return False
        if self.expiry_date and self.expiry_date < datetime.utcnow():
            return False
        return True

    @property
    def is_expired(self) -> bool:
        """Check if service is expired."""
        if self.expiry_date:
            return self.expiry_date < datetime.utcnow()
        return False

    @property
    def days_remaining(self) -> int | None:
        """Get days remaining until expiry."""
        if not self.expiry_date:
            return None
        delta = self.expiry_date - datetime.utcnow()
        return max(0, delta.days) if delta.total_seconds() > 0 else 0

    @property
    def traffic_usage_percent(self) -> float:
        """Get traffic usage percentage."""
        if self.total_traffic_gb == 0 or self.is_unlimited:
            return 0.0
        if self.remaining_traffic_gb is not None:
            used = self.total_traffic_gb - self.remaining_traffic_gb
            return (used / self.total_traffic_gb) * 100
        return (
            (self.used_traffic_gb / self.total_traffic_gb) * 100
            if self.total_traffic_gb > 0
            else 0.0
        )
