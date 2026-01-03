"""Product model for VPN service products."""

from __future__ import annotations

import json
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, SoftDeleteMixin, TimestampMixin

if TYPE_CHECKING:
    from .panel import Panel
    from .product_category import ProductCategory
    from .purchase import Purchase


class ProductStatus(str, Enum):
    """Product status enumeration."""

    ACTIVE = "active"
    INACTIVE = "inactive"
    OUT_OF_STOCK = "out_of_stock"


class Product(Base, TimestampMixin, SoftDeleteMixin):
    """Product model for VPN service products."""

    __tablename__ = "products"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    panel_id: Mapped[int] = mapped_column(ForeignKey("panels.id"), nullable=False, index=True)
    test_panel_id: Mapped[int | None] = mapped_column(
        ForeignKey("panels.id", ondelete="SET NULL"), nullable=True, index=True
    )

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ProductStatus] = mapped_column(
        default=ProductStatus.ACTIVE, nullable=False, index=True
    )

    # Pricing
    price: Mapped[int] = mapped_column(Numeric(15, 0), nullable=False)  # Price in Rials
    currency: Mapped[str] = mapped_column(String(10), default="IRR", nullable=False)

    # Service Configuration
    duration_days: Mapped[int] = mapped_column(nullable=False)
    traffic_gb: Mapped[int] = mapped_column(nullable=False, default=0)  # 0 means unlimited
    protocol: Mapped[str] = mapped_column(String(50), nullable=False, default="vless")
    # JSON array of allowed protocols for multi-protocol products.
    # Example: '["vless", "vmess", "trojan"]'
    # If NULL, falls back to single protocol from 'protocol' field (backward compatible).
    allowed_protocols: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Inventory
    stock_quantity: Mapped[int | None] = mapped_column(
        Integer, nullable=True
    )  # None means unlimited
    sold_quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reserved_quantity: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    min_stock: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    max_stock: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Settings
    auto_send_config: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_featured: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Category
    category_id: Mapped[int | None] = mapped_column(
        ForeignKey("product_categories.id", ondelete="SET NULL"), nullable=True, index=True
    )

    # Relationships
    panel: Mapped[Panel] = relationship("Panel", foreign_keys=[panel_id], back_populates="products")
    test_panel: Mapped[Panel | None] = relationship("Panel", foreign_keys=[test_panel_id])
    category: Mapped[ProductCategory | None] = relationship(
        "ProductCategory", back_populates="products"
    )
    purchases: Mapped[list[Purchase]] = relationship(
        "Purchase", back_populates="product", lazy="selectin"
    )

    def __repr__(self) -> str:
        return f"<Product(id={self.id}, name={self.name}, price={self.price})>"

    @property
    def available_stock(self) -> int | None:
        """Get available stock."""
        if self.stock_quantity is None:
            return None
        return max(0, self.stock_quantity - int(self.sold_quantity) - int(self.reserved_quantity))

    @property
    def is_in_stock(self) -> bool:
        """Check if product is in stock."""
        if self.stock_quantity is None:
            return True
        return self.available_stock is not None and self.available_stock > 0

    @property
    def is_unlimited_traffic(self) -> bool:
        """Check if product has unlimited traffic."""
        return self.traffic_gb == 0

    def get_allowed_protocols(self) -> list[str]:
        """Get list of allowed protocols for this product.

        Returns parsed allowed_protocols JSON array if set,
        otherwise returns a single-item list with the default protocol.
        This ensures backward compatibility with legacy products.

        Returns:
            List of protocol strings (e.g., ["vless", "vmess", "trojan"])
        """
        if self.allowed_protocols:
            try:
                protocols = json.loads(self.allowed_protocols)
                if isinstance(protocols, list) and len(protocols) > 0:
                    return [str(p).lower().strip() for p in protocols if p]
            except (json.JSONDecodeError, TypeError):
                pass
        # Fallback to single protocol (backward compatibility)
        return [self.protocol.lower().strip()] if self.protocol else ["vless"]

    def set_allowed_protocols(self, protocols: list[str]) -> None:
        """Set allowed protocols for this product.

        Args:
            protocols: List of protocol strings (e.g., ["vless", "vmess"])
        """
        if protocols and len(protocols) > 0:
            # Normalize to lowercase
            normalized = [str(p).lower().strip() for p in protocols if p]
            self.allowed_protocols = json.dumps(normalized)
        else:
            self.allowed_protocols = None

    @property
    def supports_multiple_protocols(self) -> bool:
        """Check if product supports multiple protocol choices.

        Returns:
            True if user should be prompted to select protocol,
            False if product only supports one protocol.
        """
        return len(self.get_allowed_protocols()) > 1

    def get_default_protocol(self) -> str:
        """Get the default protocol for this product.

        Returns the first allowed protocol, or falls back to
        the legacy 'protocol' field.

        Returns:
            Protocol string (e.g., "vless")
        """
        protocols = self.get_allowed_protocols()
        return protocols[0] if protocols else self.protocol or "vless"
