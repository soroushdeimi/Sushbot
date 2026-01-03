"""Product category model."""

from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, SoftDeleteMixin, TimestampMixin

if TYPE_CHECKING:
    from .product import Product


class ProductCategory(Base, TimestampMixin, SoftDeleteMixin):
    """Product category model for organizing products."""
    
    __tablename__ = "product_categories"
    
    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    slug: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("product_categories.id", ondelete="SET NULL"), nullable=True, index=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False, index=True)
    
    # Self-referencing relationship for hierarchy
    parent: Mapped["ProductCategory | None"] = relationship("ProductCategory", remote_side=[id], back_populates="children")
    children: Mapped[list["ProductCategory"]] = relationship("ProductCategory", back_populates="parent")
    
    # Products in this category
    products: Mapped[list["Product"]] = relationship("Product", back_populates="category")

    def __repr__(self) -> str:
        return f"<ProductCategory(id={self.id}, name={self.name}, slug={self.slug})>"

