"""Wallet operations (atomic balance updates with transaction log)."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import User, WalletTransaction, WalletTxType


async def apply_wallet_tx(
    db: AsyncSession,
    *,
    user_id: int,
    amount: int,
    tx_type: WalletTxType,
    ref: str | None = None,
    note: str | None = None,
) -> WalletTransaction:
    # Lock row for update
    res = await db.execute(select(User).where(User.id == user_id).with_for_update())
    u = res.scalars().first()
    if not u:
        raise ValueError("User not found")
    new_bal = int(u.balance) + int(amount)
    # Prevent negative balance for debits
    if new_bal < 0 and amount < 0:
        raise ValueError(f"Insufficient balance. Current: {u.balance}, Requested: {abs(amount)}")
    u.balance = new_bal
    tx = WalletTransaction(
        user_id=user_id,
        tx_type=tx_type,
        amount=int(amount),
        balance_after=new_bal,
        ref=ref,
        note=note,
    )
    db.add(tx)
    await db.commit()
    await db.refresh(tx)
    return tx
