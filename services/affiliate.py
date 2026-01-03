"""Affiliate/referral program logic (binding + commission awarding)."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import settings
from database.models import Purchase, PurchaseStatus, User, WalletTransaction, WalletTxType
from services.wallet import apply_wallet_tx


def normalize_referral_payload(payload: str | None) -> str | None:
    """Normalize /start payload into a referral code (or None)."""
    if not payload:
        return None
    p = payload.strip()
    if not p:
        return None
    if p.lower().startswith("ref_"):
        p = p.split("_", 1)[1]
    code = p.strip().upper()
    # Current generator makes 12 chars, but allow future changes
    if not (6 <= len(code) <= 64):
        return None
    return code


def build_referral_link(*, bot_username: str, referral_code: str) -> str:
    un = bot_username.lstrip("@").strip()
    return f"https://t.me/{un}?start=ref_{referral_code}"


async def try_bind_referral(db: AsyncSession, *, user_id: int, referral_payload: str | None) -> tuple[bool, str | None]:
    """
    Bind referred_by_id once, only if user has no referrer and no completed purchases.
    Returns (bound, message_for_user).
    """
    code = normalize_referral_payload(referral_payload)
    if not code:
        return False, None

    u = await db.get(User, user_id)
    if not u:
        return False, None
    if u.referred_by_id:
        return False, None

    # Prevent abuse: don't allow binding after first successful purchase.
    res = await db.execute(
        select(func.count(Purchase.id)).where(
            Purchase.user_id == u.id,
            Purchase.status == PurchaseStatus.COMPLETED,
        )
    )
    if int(res.scalar() or 0) > 0:
        return False, None

    res = await db.execute(select(User).where(User.referral_code == code))
    ref = res.scalars().first()
    if not ref:
        return False, None
    if ref.id == u.id:
        return False, "❌ نمی‌تونی با لینک خودت زیرمجموعه خودت بشی."

    u.referred_by_id = int(ref.id)
    await db.commit()
    return True, f"✅ با موفقیت با لینک معرفی @{ref.username or ref.id} ثبت شدی."


def _calc_commission(*, final_amount: int) -> int:
    if final_amount < int(settings.affiliate_min_purchase_amount):
        return 0
    pct = max(0, min(100, int(settings.affiliate_commission_percent)))
    fixed = max(0, int(settings.affiliate_fixed_reward))
    return int((final_amount * pct) // 100) + fixed


async def award_referral_commission_for_purchase(db: AsyncSession, *, purchase: Purchase) -> tuple[int, int | None]:
    """
    Award commission to referrer if eligible.
    Returns (amount_awarded, referrer_user_id).
    """
    if not settings.affiliate_enabled:
        return 0, None
    if not purchase or purchase.status != PurchaseStatus.COMPLETED:
        return 0, None

    buyer = await db.get(User, int(purchase.user_id))
    if not buyer or not buyer.referred_by_id:
        return 0, None
    referrer_id = int(buyer.referred_by_id)
    if referrer_id == int(buyer.id):
        return 0, None

    # First purchase only (default true)
    if settings.affiliate_first_purchase_only:
        res = await db.execute(
            select(func.count(Purchase.id)).where(
                Purchase.user_id == buyer.id,
                Purchase.status == PurchaseStatus.COMPLETED,
                Purchase.id != purchase.id,
            )
        )
        if int(res.scalar() or 0) > 0:
            return 0, None

    final_amount = int(purchase.final_amount or 0)
    amt = _calc_commission(final_amount=final_amount)
    if amt <= 0:
        return 0, None

    # Idempotency key: unique per purchase.
    ref = f"aff:purchase:{purchase.id}"
    res = await db.execute(select(WalletTransaction).where(WalletTransaction.ref == ref))
    if res.scalars().first():
        return 0, referrer_id

    await apply_wallet_tx(
        db,
        user_id=referrer_id,
        amount=amt,
        tx_type=WalletTxType.REFERRAL_REWARD,
        ref=ref,
        note=f"Affiliate reward for purchase_id={purchase.id} (buyer_id={buyer.id})",
    )
    return amt, referrer_id



