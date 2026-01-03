"""Panel model for PasarGuard panel integration."""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, SoftDeleteMixin, TimestampMixin

if TYPE_CHECKING:
    from .product import Product
    from .service import Service


class PanelStatus(str, Enum):
    """Panel status enumeration."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    MAINTENANCE = "maintenance"
    ERROR = "error"


class Panel(Base, TimestampMixin, SoftDeleteMixin):
    """Panel model for PasarGuard panel integration."""

    __tablename__ = "panels"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)

    name: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    api_url: Mapped[str] = mapped_column(String(500), nullable=False)

    # Encrypted credentials (api_key can be token or username:password)
    # For PasarGuard: not used (direct DB access)
    # For Marzban: can be token or username:password (encrypted)
    api_key: Mapped[str] = mapped_column(Text, nullable=False)  # Encrypted credentials

    # For PasarGuard: node_id is required
    # For Marzban: not used
    node_id: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Panel type (pasarguard, marzban, etc.)
    type: Mapped[str | None] = mapped_column(String(50), nullable=True, default=None)

    # Additional fields for Marzban
    username: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )  # Optional, can be in api_key
    password: Mapped[str | None] = mapped_column(Text, nullable=True)  # Optional, encrypted if set

    status: Mapped[PanelStatus] = mapped_column(
        default=PanelStatus.ACTIVE, nullable=False, index=True
    )

    # Settings
    is_test_panel: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    max_configs_per_panel: Mapped[int | None] = mapped_column(Integer, nullable=True)
    current_config_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Location
    location: Mapped[str | None] = mapped_column(String(100), nullable=True)
    country_code: Mapped[str | None] = mapped_column(String(10), nullable=True)

    # Configuration
    default_protocol: Mapped[str] = mapped_column(String(50), default="vless", nullable=False)
    default_port: Mapped[int] = mapped_column(Integer, default=8443, nullable=False)
    inbound_tag: Mapped[str | None] = mapped_column(
        String(100), nullable=True, default="SUSH"
    )  # For PasarGuard
    config_template: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Notes
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    services: Mapped[list[Service]] = relationship(
        "Service", back_populates="panel", lazy="selectin"
    )
    products: Mapped[list[Product]] = relationship(
        "Product", foreign_keys="[Product.panel_id]", back_populates="panel", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<Panel(id={self.id}, name={self.name}, status={self.status})>"

    @property
    def is_available(self) -> bool:
        """Check if panel is available for new configs."""
        if self.status != PanelStatus.ACTIVE:
            return False
        if self.max_configs_per_panel:
            return self.current_config_count < self.max_configs_per_panel
        return True
