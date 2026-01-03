"""Admin callback handlers for improved UX."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from telegram import Update
from telegram.ext import ContextTypes

from bot.admin_keyboards import (
    admin_main_keyboard,
    admin_payment_detail_keyboard,
    admin_payments_list_keyboard,
    admin_services_list_keyboard,
    admin_settings_keyboard,
    admin_users_list_keyboard,
)
from database.models import (
    Payment,
    PaymentGateway,
    PaymentStatus,
    Purchase,
    PurchaseStatus,
    Service,
    ServiceStatus,
    User,
    UserRole,
)
from database.models.purchase import PurchaseType
from database.session import get_db
from services.fulfillment import fulfill_purchase


async def admin_main_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show admin main menu."""
    query = update.callback_query
    if not query:
        return
    user = update.effective_user
    if not user:
        return

    async for db in get_db():
        db_user = await db.get(User, user.id)
        if not db_user or db_user.role != UserRole.ADMIN:
            await query.answer("Admin only.", show_alert=True)
            return

        # Count pending payments
        res = await db.execute(
            select(func.count(Payment.id)).where(Payment.status == PaymentStatus.PENDING)
        )
        pending_count = res.scalar() or 0

        text = (
            "🔐 پنل مدیریت\n\n"
            f"💰 پرداخت‌های در انتظار: {pending_count}\n\n"
            "لطفاً گزینه مورد نظر را انتخاب کنید:"
        )
        await query.edit_message_text(text, reply_markup=admin_main_keyboard())


async def admin_payments_pending_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0) -> None:
    """List pending payments."""
    query = update.callback_query
    if not query:
        return
    user = update.effective_user
    if not user:
        return

    async for db in get_db():
        db_user = await db.get(User, user.id)
        if not db_user or db_user.role != UserRole.ADMIN:
            await query.answer("Admin only.", show_alert=True)
            return

        res = await db.execute(
            select(Payment)
            .where(Payment.status == PaymentStatus.PENDING)
            .order_by(Payment.created_at.desc())
            .limit(50)
        )
        payments = list(res.scalars().all())

        if not payments:
            await query.edit_message_text(
                "✅ هیچ پرداخت در انتظاری وجود ندارد.",
                reply_markup=admin_main_keyboard(),
            )
            return

        # Extract page from callback data if present
        if query.data and query.data.startswith("admin_payments_pending_page_"):
            try:
                page = int(query.data.split("_")[-1])
            except (ValueError, IndexError):
                page = 0

        start = page * 5
        end = start + 5
        payments[start:end]

        text = (
            f"💰 پرداخت‌های در انتظار\n\n"
            f"📊 کل: {len(payments)} مورد\n"
            f"📄 صفحه {page + 1} از {(len(payments) + 4) // 5}\n\n"
            f"برای مشاهده جزئیات یا تایید/رد، روی پرداخت مورد نظر کلیک کنید:"
        )
        await query.edit_message_text(text, reply_markup=admin_payments_list_keyboard(payments, page=page))


async def admin_payment_detail_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, payment_id: int) -> None:
    """Show payment details."""
    query = update.callback_query
    if not query:
        return
    user = update.effective_user
    if not user:
        return

    async for db in get_db():
        db_user = await db.get(User, user.id)
        if not db_user or db_user.role != UserRole.ADMIN:
            await query.answer("Admin only.", show_alert=True)
            return

        pay = await db.get(Payment, payment_id)
        if not pay:
            await query.edit_message_text("پرداخت پیدا نشد.")
            return

        purchase = await db.get(Purchase, pay.purchase_id)
        if not purchase:
            await query.edit_message_text("سفارش پیدا نشد.")
            return

        buyer = await db.get(User, purchase.user_id)
        buyer_name = buyer.username if buyer else f"User {purchase.user_id}"

        gateway_name = {
            PaymentGateway.CARD_TO_CARD: "کارت‌به‌کارت",
            PaymentGateway.NOWPAYMENTS: "NowPayments",
            PaymentGateway.AQAYEPARDAKHT: "Aqayepardakht",
        }.get(pay.gateway, pay.gateway.value)

        purchase_type_name = {
            PurchaseType.NEW: "خرید جدید",
            PurchaseType.RENEW: "تمدید",
            PurchaseType.ADD_TRAFFIC: "افزودن ترافیک",
            PurchaseType.WALLET_TOPUP: "شارژ کیف پول",
        }.get(purchase.purchase_type, purchase.purchase_type.value)

        text = (
            f"💳 جزئیات پرداخت #{pay.id}\n\n"
            f"👤 خریدار: {buyer_name} (ID: {purchase.user_id})\n"
            f"💰 مبلغ: {int(pay.amount):,} تومان\n"
            f"🔧 درگاه: {gateway_name}\n"
            f"📦 نوع: {purchase_type_name}\n"
            f"📅 تاریخ: {pay.created_at.strftime('%Y-%m-%d %H:%M:%S')}\n"
            f"📝 کد پیگیری: {pay.tracking_code or '—'}\n"
        )

        if purchase.product_id:
            from database.models import Product
            product = await db.get(Product, purchase.product_id)
            if product:
                text += f"\n📦 محصول: {product.name}\n"

        if purchase.service_id:
            text += f"\n🔗 سرویس: #{purchase.service_id}\n"

        await query.edit_message_text(text, reply_markup=admin_payment_detail_keyboard(payment_id))


async def admin_payment_approve_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, payment_id: int) -> None:
    """Approve payment via callback."""
    query = update.callback_query
    if not query:
        return

    user = update.effective_user
    if not user:
        return

    async for db in get_db():
        db_user = await db.get(User, user.id)
        if not db_user or db_user.role != UserRole.ADMIN:
            await query.answer("Admin only.", show_alert=True)
            return

        from loguru import logger

        from database.models import Payment, PaymentStatus, Purchase, PurchaseStatus
        from database.models.purchase import PurchaseType

        pay = await db.get(Payment, payment_id)
        if not pay:
            await query.answer("پرداخت پیدا نشد.", show_alert=True)
            return

        purchase = await db.get(Purchase, pay.purchase_id)
        if not purchase:
            await query.answer("سفارش پیدا نشد.", show_alert=True)
            return

        if pay.status == PaymentStatus.COMPLETED and purchase.status == PurchaseStatus.COMPLETED:
            await query.answer("این پرداخت قبلاً تایید شده است.", show_alert=True)
            return

        pay.status = PaymentStatus.COMPLETED
        pay.verified_at = datetime.utcnow()
        purchase.status = PurchaseStatus.COMPLETED
        purchase.completed_at = datetime.utcnow()
        await db.commit()

        svc = await fulfill_purchase(db, purchase=purchase)
        if svc is None and purchase.purchase_type == PurchaseType.WALLET_TOPUP:
            await query.answer("✅ پرداخت تایید شد. کیف پول شارژ شد.", show_alert=True)
            try:
                await context.bot.send_message(
                    chat_id=purchase.user_id,
                    text=f"✅ پرداخت تایید شد.\n\n💰 کیف پول شما به مبلغ {int(purchase.final_amount):,} تومان شارژ شد.",
                )
            except Exception as e:
                logger.warning(f"Failed to notify user {purchase.user_id}: {e}")
        else:
            assert svc is not None
            await query.answer("✅ پرداخت تایید شد. سرویس فعال شد.", show_alert=True)
            try:
                from services.subscription import (
                    ensure_service_sub_token,
                    subscription_url_from_token,
                )
                tok = await ensure_service_sub_token(db, svc)
                sub_url = subscription_url_from_token(tok)
                sub_txt = f"\n\n🔗 Sub:\n{sub_url}" if sub_url else ""
                await context.bot.send_message(chat_id=purchase.user_id, text=f"✅ پرداخت تایید شد.\n\n🔗 {svc.config_link}{sub_txt}")
            except Exception as e:
                logger.warning(f"Failed to notify user {purchase.user_id}: {e}")

        # Affiliate commission (idempotent)
        try:
            from services.affiliate import award_referral_commission_for_purchase

            amt, referrer_id = await award_referral_commission_for_purchase(db, purchase=purchase)
            if amt > 0 and referrer_id:
                await context.bot.send_message(
                    chat_id=referrer_id,
                    text=f"🎁 پورسانت زیرمجموعه‌گیری\n\nمبلغ {amt:,} تومان به کیف پول شما اضافه شد.",
                )
        except Exception as e:
            logger.warning(f"Affiliate commission failed purchase_id={purchase.id}: {e}")

    # Refresh payments list
    await admin_payments_pending_callback(update, context)


async def admin_payment_reject_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, payment_id: int) -> None:
    """Reject payment via callback."""
    query = update.callback_query
    if not query:
        return

    user = update.effective_user
    if not user:
        return

    async for db in get_db():
        db_user = await db.get(User, user.id)
        if not db_user or db_user.role != UserRole.ADMIN:
            await query.answer("Admin only.", show_alert=True)
            return

        from loguru import logger

        from database.models import Payment, PaymentStatus, Purchase, PurchaseStatus

        pay = await db.get(Payment, payment_id)
        if not pay:
            await query.answer("پرداخت پیدا نشد.", show_alert=True)
            return

        purchase = await db.get(Purchase, pay.purchase_id)
        if purchase and purchase.status == PurchaseStatus.PENDING:
            purchase.status = PurchaseStatus.FAILED
            if purchase.product_id:
                from config.features import is_enabled
                if is_enabled("inventory"):
                    from services.inventory import release_product_stock
                    await release_product_stock(db, product_id=int(purchase.product_id), quantity=1)
        pay.status = PaymentStatus.FAILED
        pay.admin_notes = "Rejected by admin"
        pay.verified_at = datetime.utcnow()
        await db.commit()

        await query.answer("❌ پرداخت رد شد.", show_alert=True)
        if purchase:
            try:
                await context.bot.send_message(chat_id=purchase.user_id, text="❌ پرداخت شما رد شد. لطفاً با پشتیبانی تماس بگیرید.")
            except Exception as e:
                logger.warning(f"Failed to notify user {purchase.user_id}: {e}")

    # Refresh payments list
    await admin_payments_pending_callback(update, context)


async def admin_stats_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show admin statistics."""
    query = update.callback_query
    if not query:
        return
    user = update.effective_user
    if not user:
        return

    async for db in get_db():
        db_user = await db.get(User, user.id)
        if not db_user or db_user.role != UserRole.ADMIN:
            await query.answer("Admin only.", show_alert=True)
            return

        # Overall stats
        total_users = (await db.execute(select(func.count(User.id)))).scalar() or 0
        active_services = (
            await db.execute(select(func.count(Service.id)).where(Service.status == ServiceStatus.ACTIVE))
        ).scalar() or 0
        total_revenue = (
            await db.execute(
                select(func.coalesce(func.sum(Purchase.final_amount), 0)).where(
                    Purchase.status == PurchaseStatus.COMPLETED
                )
            )
        ).scalar() or 0
        pending_payments = (
            await db.execute(select(func.count(Payment.id)).where(Payment.status == PaymentStatus.PENDING))
        ).scalar() or 0

        text = (
            "📊 آمار کلی\n\n"
            f"👥 کل کاربران: {total_users}\n"
            f"✅ سرویس‌های فعال: {active_services}\n"
            f"💰 کل درآمد: {int(total_revenue):,} تومان\n"
            f"⏳ پرداخت‌های در انتظار: {pending_payments}\n"
        )

        from bot.admin_keyboards import admin_main_keyboard
        await query.edit_message_text(text, reply_markup=admin_main_keyboard())


async def admin_users_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0) -> None:
    """List users."""
    query = update.callback_query
    if not query:
        return
    user = update.effective_user
    if not user:
        return

    async for db in get_db():
        db_user = await db.get(User, user.id)
        if not db_user or db_user.role != UserRole.ADMIN:
            await query.answer("Admin only.", show_alert=True)
            return

        res = await db.execute(select(User).order_by(User.id.desc()).limit(100))
        users = list(res.scalars().all())

        text = f"👥 لیست کاربران ({len(users)} مورد)\n\n"
        await query.edit_message_text(text, reply_markup=admin_users_list_keyboard(users, page=page))


async def admin_services_callback(update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0) -> None:
    """List services."""
    query = update.callback_query
    if not query:
        return
    user = update.effective_user
    if not user:
        return

    async for db in get_db():
        db_user = await db.get(User, user.id)
        if not db_user or db_user.role != UserRole.ADMIN:
            await query.answer("Admin only.", show_alert=True)
            return

        res = await db.execute(select(Service).order_by(Service.id.desc()).limit(100))
        services = list(res.scalars().all())

        text = f"🔧 لیست سرویس‌ها ({len(services)} مورد)\n\n"
        await query.edit_message_text(text, reply_markup=admin_services_list_keyboard(services, page=page))


async def admin_settings_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show settings menu."""
    query = update.callback_query
    if not query:
        return
    user = update.effective_user
    if not user:
        return

    async for db in get_db():
        db_user = await db.get(User, user.id)
        if not db_user or db_user.role != UserRole.ADMIN:
            await query.answer("Admin only.", show_alert=True)
            return

        text = "⚙️ تنظیمات\n\nلطفاً گزینه مورد نظر را انتخاب کنید:"
        await query.edit_message_text(text, reply_markup=admin_settings_keyboard())

