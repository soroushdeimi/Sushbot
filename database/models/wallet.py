"""Wallet transactions for user balance."""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin

if TYPE_CHECKING:
    from .user import User


class WalletTxType(str, Enum):
    TOPUP = "topup"
    PURCHASE = "purchase"
    REFUND = "refund"
    ADJUST = "adjust"
    REFERRAL_REWARD = "referral_reward"


class WalletTransaction(Base, TimestampMixin):
    __tablename__ = "wallet_transactions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), index=True)

    tx_type: Mapped[WalletTxType] = mapped_column(default=WalletTxType.ADJUST, nullable=False, index=True)
    amount: Mapped[int] = mapped_column(Integer, nullable=False)  # IRR (positive/negative)
    balance_after: Mapped[int] = mapped_column(Integer, nullable=False)

    ref: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    user: Mapped["User"] = relationship("User", lazy="selectin")



