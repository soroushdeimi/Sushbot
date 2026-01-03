"""Admin coupon management handlers."""

from __future__ import annotations

from sqlalchemy import select
from telegram import Update
from telegram.ext import ContextTypes

from bot.admin_keyboards import admin_main_keyboard
from database.session import get_db


async def admin_coupon_create_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Start coupon creation process."""
    query = update.callback_query
    if not query:
        return
    user = update.effective_user
    if not user:
        return

    async for db in get_db():
        from handlers.commands import _require_admin
        from services.state_machine import set_step

        admin = await _require_admin(db, user.id)
        if not admin:
            await query.answer("Admin only.", show_alert=True)
            return

        text = (
            "🎫 ساخت کد تخفیف جدید\n\n"
            "لطفاً کد تخفیف را وارد کنید (بدون فاصله):\n\n"
            "برای لغو /cancel را ارسال کنید."
        )

        await set_step(user.id, step="admin.create_coupon_code", payload={})
        await query.edit_message_text(text)


async def admin_coupons_all_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Show all coupons including inactive ones."""
    query = update.callback_query
    if not query:
        return
    user = update.effective_user
    if not user:
        return

    async for db in get_db():
        from database.models import Coupon
        from handlers.commands import _require_admin

        admin = await _require_admin(db, user.id)
        if not admin:
            await query.answer("Admin only.", show_alert=True)
            return

        result = await db.execute(select(Coupon).order_by(Coupon.id.desc()))
        coupons = list(result.scalars().all())

        if not coupons:
            text = "📭 هیچ کد تخفیفی ثبت نشده."
        else:
            text = "🎫 لیست همه کدهای تخفیف:\n\n"
            for c in coupons[:20]:  # Show first 20
                status = "✅" if c.is_active else "❌"
                text += (
                    f"{status} {c.code}\n"
                    f"   تخفیف: {int(c.discount_amount):,}T | "
                    f"استفاده: {c.used_count}/{c.max_uses or '∞'}\n\n"
                )

        await query.edit_message_text(text, reply_markup=admin_main_keyboard())
