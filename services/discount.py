"""Discount code validation and application logic."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import func, select

from database.models import DiscountCode, DiscountType, Purchase
from database.models.purchase import PurchaseStatus

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession


async def validate_and_apply_discount(
    db: AsyncSession,
    *,
    code: str,
    user_id: int,
    purchase_amount: int,
    is_first_purchase: bool = False,
) -> tuple[DiscountCode | None, int, str]:
    """
    Validate discount code and calculate discount amount.
    Returns: (discount_code, discount_amount, error_message)
    If discount_code is None, error_message explains why.
    """
    code_upper = code.strip().upper()

    res = await db.execute(select(DiscountCode).where(DiscountCode.code == code_upper))
    discount = res.scalar_one_or_none()

    if not discount:
        return None, 0, "Discount code not found."

    if not discount.is_active:
        return None, 0, "This discount code is inactive."

    now = datetime.utcnow()
    if discount.valid_from > now:
        return None, 0, "This discount code is not yet valid."

    if discount.valid_until and discount.valid_until < now:
        return None, 0, "This discount code has expired."

    if discount.max_uses and discount.used_count >= discount.max_uses:
        return None, 0, "This discount code has reached its usage limit."

    # Check per-user usage limit
    res = await db.execute(
        select(func.count(Purchase.id)).where(
            Purchase.user_id == user_id,
            Purchase.discount_code_id == discount.id,
            Purchase.status == PurchaseStatus.COMPLETED,
        )
    )
    user_usage_count = res.scalar() or 0
    if user_usage_count >= discount.max_uses_per_user:
        return None, 0, "You have already used this discount code the maximum allowed times."

    # Check minimum purchase amount
    if purchase_amount < discount.min_purchase_amount:
        min_text = f"{discount.min_purchase_amount:,}"
        return None, 0, f"Minimum purchase amount for this code is {min_text} Toman."

    # Calculate discount
    discount_amount = discount.calculate_discount(purchase_amount)

    return discount, discount_amount, ""


async def apply_gift_code_to_wallet(
    db: AsyncSession,
    *,
    code: str,
    user_id: int,
) -> tuple[bool, str, int]:
    """
    Apply gift code (special discount that adds to wallet instead of applying to purchase).
    Returns: (success, message, amount_added)
    """
    from database.models.wallet import WalletTxType
    from services.wallet import apply_wallet_tx

    code_upper = code.strip().upper()

    res = await db.execute(select(DiscountCode).where(DiscountCode.code == code_upper))
    discount = res.scalar_one_or_none()

    if not discount:
        return False, "Gift code not found.", 0

    # Gift codes should be fixed_amount and not expired
    if not discount.is_active:
        return False, "This gift code is inactive.", 0

    now = datetime.utcnow()
    if discount.valid_from > now:
        return False, "This gift code is not yet valid.", 0

    if discount.valid_until and discount.valid_until < now:
        return False, "This gift code has expired.", 0

    if discount.max_uses and discount.used_count >= discount.max_uses:
        return False, "This gift code has reached its usage limit.", 0

    # Check per-user usage (for gift codes, usually max_uses_per_user = 1)
    res = await db.execute(
        select(func.count(Purchase.id)).where(
            Purchase.user_id == user_id,
            Purchase.discount_code_id == discount.id,
        )
    )
    user_usage_count = res.scalar() or 0
    if user_usage_count >= discount.max_uses_per_user:
        return False, "You have already used this gift code.", 0

    # Gift codes: only fixed amount (avoid ambiguous percentage-to-wallet semantics)
    if discount.discount_type != DiscountType.FIXED_AMOUNT:
        return False, "This gift code is invalid (must be fixed amount).", 0

    amount = int(discount.discount_value)
    if amount <= 0:
        return False, "This gift code is invalid.", 0

    try:
        await apply_wallet_tx(
            db,
            user_id=user_id,
            amount=amount,
            tx_type=WalletTxType.ADJUST,
            ref=f"gift_code_{discount.code}",
            note=f"Gift code: {discount.code}",
        )
        # Mark as used (increment used_count)
        discount.used_count += 1
        await db.commit()

        return True, f"Gift code applied! {amount:,} Toman added to your wallet.", amount
    except Exception as e:
        await db.rollback()
        return False, f"Failed to apply gift code: {str(e)}", 0
