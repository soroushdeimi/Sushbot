"""Service configuration model."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .service import Service


class ServiceConfiguration(Base, TimestampMixin):
    """Service configuration model for storing configuration details."""

    __tablename__ = "service_configurations"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    service_id: Mapped[int] = mapped_column(ForeignKey("services.id"), nullable=False, index=True)

    # Configuration details
    protocol: Mapped[str] = mapped_column(String(50), nullable=False)
    server_address: Mapped[str] = mapped_column(String(255), nullable=False)
    port: Mapped[int] = mapped_column(nullable=False)
    client_email: Mapped[str] = mapped_column(String(255), nullable=False)

    # Configuration link and QR
    config_link: Mapped[str] = mapped_column(Text, nullable=False)
    config_qr_code: Mapped[str | None] = mapped_column(Text, nullable=True)  # Base64 QR code
    config_subscription_link: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Protocol-specific settings (stored as JSON string)
    protocol_settings: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON string

    # Version (for configuration updates)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Relationships
    service: Mapped["Service"] = relationship("Service", back_populates="configurations")

    def __repr__(self) -> str:
        return f"<ServiceConfiguration(id={self.id}, service_id={self.service_id}, protocol={self.protocol})>"

