"""Admin user management handlers."""

from __future__ import annotations

from sqlalchemy import func, select
from telegram import Update
from telegram.ext import ContextTypes

from bot.admin_keyboards import (
    admin_main_keyboard,
    admin_user_detail_keyboard,
    admin_users_list_keyboard,
)
from database.models import Service, User
from database.session import get_db


async def admin_users_list_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0
) -> None:
    """List all users with pagination."""
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

        res = await db.execute(select(User).order_by(User.id.desc()).limit(100))
        users = list(res.scalars().all())

        if not users:
            await query.edit_message_text(
                "📭 هیچ کاربری ثبت نشده است.",
                reply_markup=admin_main_keyboard(),
            )
            return

        text = f"👥 مدیریت کاربران\n\nتعداد کل: {len(users)}\n\n"
        await query.edit_message_text(
            text, reply_markup=admin_users_list_keyboard(users, page=page)
        )


async def admin_user_detail_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int
) -> None:
    """Show user details and management options."""
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

        db_user = await db.get(User, user_id)
        if not db_user:
            await query.edit_message_text("❌ کاربر پیدا نشد.", reply_markup=admin_main_keyboard())
            return

        # Get user services count
        services_count = (
            await db.scalar(select(func.count(Service.id)).where(Service.user_id == user_id)) or 0
        )

        # Get user purchases count
        from database.models import Purchase

        purchases_count = (
            await db.scalar(select(func.count(Purchase.id)).where(Purchase.user_id == user_id)) or 0
        )

        text = (
            f"👤 کاربر: {db_user.username or f'User {user_id}'}\n\n"
            f"🆔 ID: {user_id}\n"
            f"💰 موجودی: {int(db_user.balance) if db_user.balance else 0:,} تومان\n"
            f"🔧 سرویس‌ها: {services_count}\n"
            f"📦 خریدها: {purchases_count}\n"
            f"📅 تاریخ ثبت: {db_user.created_at.strftime('%Y-%m-%d %H:%M') if db_user.created_at else 'N/A'}"
        )

        await query.edit_message_text(text, reply_markup=admin_user_detail_keyboard(user_id))


async def admin_user_balance_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int
) -> None:
    """Start process to edit user balance."""
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

        db_user = await db.get(User, user_id)
        if not db_user:
            await query.edit_message_text("❌ کاربر پیدا نشد.")
            return

        text = (
            f"💰 تغییر موجودی کاربر\n\n"
            f"کاربر: {db_user.username or f'User {user_id}'}\n"
            f"موجودی فعلی: {int(db_user.balance) if db_user.balance else 0:,} تومان\n\n"
            f"لطفاً مبلغ جدید را ارسال کنید (مثبت برای افزایش، منفی برای کاهش):\n"
            f"برای لغو /cancel را ارسال کنید."
        )

        await set_step(user.id, step="admin.edit_user_balance", payload={"user_id": user_id})
        await query.edit_message_text(text)


async def admin_user_services_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int
) -> None:
    """Show user's services."""
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

        db_user = await db.get(User, user_id)
        if not db_user:
            await query.edit_message_text("❌ کاربر پیدا نشد.")
            return

        res = await db.execute(
            select(Service).where(Service.user_id == user_id).order_by(Service.id.desc())
        )
        services = list(res.scalars().all())

        if not services:
            text = f"📭 کاربر {db_user.username or f'User {user_id}'} هیچ سرویسی ندارد."
        else:
            text = f"🔧 سرویس‌های کاربر: {db_user.username or f'User {user_id}'}\n\n"
            for svc in services[:10]:  # Show first 10
                text += f"#{svc.id} - {svc.protocol.upper()} - {svc.status.value}\n"

        await query.edit_message_text(text, reply_markup=admin_user_detail_keyboard(user_id))


async def admin_user_purchases_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int
) -> None:
    """Show user's purchase history."""
    query = update.callback_query
    if not query:
        return
    user = update.effective_user
    if not user:
        return

    async for db in get_db():
        from handlers.commands import _require_admin
        from database.models import Purchase

        admin = await _require_admin(db, user.id)
        if not admin:
            await query.answer("Admin only.", show_alert=True)
            return

        db_user = await db.get(User, user_id)
        if not db_user:
            await query.edit_message_text("❌ کاربر پیدا نشد.")
            return

        res = await db.execute(
            select(Purchase).where(Purchase.user_id == user_id).order_by(Purchase.id.desc())
        )
        purchases = list(res.scalars().all())

        if not purchases:
            text = f"📭 کاربر {db_user.username or f'User {user_id}'} هیچ خریدی نداشته."
        else:
            text = f"📜 تاریخچه خرید کاربر: {db_user.username or f'User {user_id}'}\n\n"
            for p in purchases[:10]:  # Show first 10
                text += f"#{p.id} - {int(p.final_amount):,}T - {p.status.value}\n"

        await query.edit_message_text(text, reply_markup=admin_user_detail_keyboard(user_id))


async def admin_user_ban_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int
) -> None:
    """Toggle user ban status."""
    query = update.callback_query
    if not query:
        return
    user = update.effective_user
    if not user:
        return

    async for db in get_db():
        from handlers.commands import _require_admin
        from database.models import UserStatus

        admin = await _require_admin(db, user.id)
        if not admin:
            await query.answer("Admin only.", show_alert=True)
            return

        db_user = await db.get(User, user_id)
        if not db_user:
            await query.edit_message_text("❌ کاربر پیدا نشد.")
            return

        # Toggle ban status
        if db_user.status == UserStatus.BANNED:
            db_user.status = UserStatus.ACTIVE
            status_text = "فعال"
        else:
            db_user.status = UserStatus.BANNED
            status_text = "مسدود"

        await db.commit()

        await query.answer(f"کاربر {status_text} شد.", show_alert=True)
        await admin_user_detail_callback(update, context, user_id)
