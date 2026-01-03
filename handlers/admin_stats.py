"""Admin statistics handlers."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import func, select
from telegram import Update
from telegram.ext import ContextTypes

from bot.admin_keyboards import admin_main_keyboard
from database.models import Payment, PaymentStatus, Purchase, PurchaseStatus, Service, ServiceStatus, User
from database.models.purchase import PurchaseType
from database.session import get_db
from loguru import logger


async def admin_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show comprehensive bot statistics."""
    query = update.callback_query
    if not query:
        return
    user = update.effective_user
    if not user:
        return

    async for db in get_db():
        from handlers.commands import _require_admin

        admin = await _require_admin(db, user.id)
        if not admin:
            await query.answer("Admin only.", show_alert=True)
            return

        # Total users
        total_users = await db.scalar(select(func.count(User.id)))

        # Active services
        active_services = await db.scalar(
            select(func.count(Service.id)).where(Service.status == ServiceStatus.ACTIVE)
        )

        # Total revenue (completed purchases)
        total_revenue = await db.scalar(
            select(func.sum(Purchase.final_amount)).where(Purchase.status == PurchaseStatus.COMPLETED)
        ) or 0

        # Today's revenue
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        today_revenue = await db.scalar(
            select(func.sum(Purchase.final_amount)).where(
                Purchase.status == PurchaseStatus.COMPLETED,
                Purchase.created_at >= today_start,
            )
        ) or 0

        # This month's revenue
        month_start = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        month_revenue = await db.scalar(
            select(func.sum(Purchase.final_amount)).where(
                Purchase.status == PurchaseStatus.COMPLETED,
                Purchase.created_at >= month_start,
            )
        ) or 0

        # Pending payments
        pending_payments = await db.scalar(
            select(func.count(Payment.id)).where(Payment.status == PaymentStatus.PENDING)
        )

        # Total wallet balance
        total_wallet = await db.scalar(select(func.sum(User.balance))) or 0

        text = (
            "📊 آمار کلی ربات\n\n"
            f"👥 کل کاربران: {total_users:,}\n"
            f"✅ سرویس‌های فعال: {active_services:,}\n"
            f"💰 کل درآمد: {int(total_revenue):,} تومان\n"
            f"📅 درآمد امروز: {int(today_revenue):,} تومان\n"
            f"📆 درآمد این ماه: {int(month_revenue):,} تومان\n"
            f"⏳ پرداخت‌های در انتظار: {pending_payments:,}\n"
            f"💳 موجودی کل کیف پول‌ها: {int(total_wallet):,} تومان"
        )

        await query.edit_message_text(text, reply_markup=admin_main_keyboard())

