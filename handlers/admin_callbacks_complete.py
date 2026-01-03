"""Complete admin callback handlers with all features."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select
from telegram import Update
from telegram.ext import ContextTypes

from bot.admin_keyboards import (
    admin_main_keyboard,
    admin_payment_detail_keyboard,
    admin_payments_list_keyboard,
    admin_service_detail_keyboard,
    admin_services_list_keyboard,
    admin_settings_keyboard,
    admin_user_detail_keyboard,
    admin_users_list_keyboard,
)
from database.models import (
    Panel,
    Payment,
    PaymentGateway,
    PaymentStatus,
    Product,
    ProductStatus,
    Purchase,
    PurchaseStatus,
    Service,
    ServiceStatus,
    SupportTicket,
    TicketStatus,
    User,
    UserRole,
)
from database.models.purchase import PurchaseType
from database.session import get_db
from handlers.commands import (
    admin_addgb_command,
    admin_renew_command,
    admin_rotate_command,
)
from integrations.factory import PanelFactory
from services.fulfillment import fulfill_purchase
from services.refund import remove_service
from utils.admin_check import is_admin


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
        if not db_user or not await is_admin(db, user.id):
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


async def admin_payments_pending_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0
) -> None:
    """List pending payments."""
    query = update.callback_query
    if not query:
        return
    user = update.effective_user
    if not user:
        return

    async for db in get_db():
        db_user = await db.get(User, user.id)
        if not db_user or not await is_admin(db, user.id):
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

        text = f"💰 پرداخت‌های در انتظار ({len(payments)} مورد)\n\n"
        await query.edit_message_text(
            text, reply_markup=admin_payments_list_keyboard(payments, page=page)
        )


async def admin_payment_detail_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE, payment_id: int
) -> None:
    """Show payment details."""
    query = update.callback_query
    if not query:
        return
    user = update.effective_user
    if not user:
        return

    async for db in get_db():
        db_user = await db.get(User, user.id)
        if not db_user or not await is_admin(db, user.id):
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
            product = await db.get(Product, purchase.product_id)
            if product:
                text += f"\n📦 محصول: {product.name}\n"

        if purchase.service_id:
            text += f"\n🔗 سرویس: #{purchase.service_id}\n"

        await query.edit_message_text(text, reply_markup=admin_payment_detail_keyboard(payment_id))


async def admin_payment_approve_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE, payment_id: int
) -> None:
    """Approve payment via callback."""
    query = update.callback_query
    if not query:
        return

    user = update.effective_user
    if not user:
        return

    async for db in get_db():
        db_user = await db.get(User, user.id)
        if not db_user or not await is_admin(db, user.id):
            await query.answer("Admin only.", show_alert=True)
            return

        from loguru import logger

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
                await context.bot.send_message(
                    chat_id=purchase.user_id,
                    text=f"✅ پرداخت تایید شد.\n\n🔗 {svc.config_link}{sub_txt}",
                )
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
    await admin_payments_pending_callback(update, context, page=0)


async def admin_payment_reject_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE, payment_id: int
) -> None:
    """Reject payment via callback."""
    query = update.callback_query
    if not query:
        return

    user = update.effective_user
    if not user:
        return

    async for db in get_db():
        db_user = await db.get(User, user.id)
        if not db_user or not await is_admin(db, user.id):
            await query.answer("Admin only.", show_alert=True)
            return

        from loguru import logger

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
                await context.bot.send_message(
                    chat_id=purchase.user_id,
                    text="❌ پرداخت شما رد شد. لطفاً با پشتیبانی تماس بگیرید.",
                )
            except Exception as e:
                logger.warning(f"Failed to notify user {purchase.user_id}: {e}")

    # Refresh payments list
    await admin_payments_pending_callback(update, context, page=0)


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
        if not db_user or not await is_admin(db, user.id):
            await query.answer("Admin only.", show_alert=True)
            return

        # Overall stats
        total_users = (await db.execute(select(func.count(User.id)))).scalar() or 0
        active_services = (
            await db.execute(
                select(func.count(Service.id)).where(Service.status == ServiceStatus.ACTIVE)
            )
        ).scalar() or 0
        total_revenue = (
            await db.execute(
                select(func.coalesce(func.sum(Purchase.final_amount), 0)).where(
                    Purchase.status == PurchaseStatus.COMPLETED
                )
            )
        ).scalar() or 0
        pending_payments = (
            await db.execute(
                select(func.count(Payment.id)).where(Payment.status == PaymentStatus.PENDING)
            )
        ).scalar() or 0

        text = (
            "📊 آمار کلی\n\n"
            f"👥 کل کاربران: {total_users}\n"
            f"✅ سرویس‌های فعال: {active_services}\n"
            f"💰 کل درآمد: {int(total_revenue):,} تومان\n"
            f"⏳ پرداخت‌های در انتظار: {pending_payments}\n"
        )

        await query.edit_message_text(text, reply_markup=admin_main_keyboard())


async def admin_users_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0
) -> None:
    """List users."""
    query = update.callback_query
    if not query:
        return
    user = update.effective_user
    if not user:
        return

    async for db in get_db():
        db_user = await db.get(User, user.id)
        if not db_user or not await is_admin(db, user.id):
            await query.answer("Admin only.", show_alert=True)
            return

        res = await db.execute(select(User).order_by(User.id.desc()).limit(100))
        users = list(res.scalars().all())

        text = f"👥 لیست کاربران ({len(users)} مورد)\n\n"
        await query.edit_message_text(
            text, reply_markup=admin_users_list_keyboard(users, page=page)
        )


async def admin_user_detail_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE, user_id: int
) -> None:
    """Show user details."""
    query = update.callback_query
    if not query:
        return
    user = update.effective_user
    if not user:
        return

    async for db in get_db():
        db_user = await db.get(User, user.id)
        if not db_user or not await is_admin(db, user.id):
            await query.answer("Admin only.", show_alert=True)
            return

        target_user = await db.get(User, user_id)
        if not target_user:
            await query.edit_message_text("کاربر پیدا نشد.")
            return

        # Get user services
        res = await db.execute(
            select(Service).where(
                Service.user_id == user_id, Service.status == ServiceStatus.ACTIVE
            )
        )
        services = list(res.scalars().all())

        # Get user purchases
        res = await db.execute(
            select(Purchase)
            .where(Purchase.user_id == user_id)
            .order_by(Purchase.created_at.desc())
            .limit(10)
        )
        purchases = list(res.scalars().all())

        text = (
            f"👤 جزئیات کاربر #{user_id}\n\n"
            f"Username: {target_user.username or '—'}\n"
            f"💰 موجودی: {int(target_user.balance):,} تومان\n"
            f"📦 سرویس‌های فعال: {len(services)}\n"
            f"🧾 تعداد خریدها: {len(purchases)}\n"
        )

        await query.edit_message_text(text, reply_markup=admin_user_detail_keyboard(user_id))


async def admin_services_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE, page: int = 0
) -> None:
    """List services."""
    query = update.callback_query
    if not query:
        return
    user = update.effective_user
    if not user:
        return

    async for db in get_db():
        db_user = await db.get(User, user.id)
        if not db_user or not await is_admin(db, user.id):
            await query.answer("Admin only.", show_alert=True)
            return

        res = await db.execute(select(Service).order_by(Service.id.desc()).limit(100))
        services = list(res.scalars().all())

        text = f"🔧 لیست سرویس‌ها ({len(services)} مورد)\n\n"
        await query.edit_message_text(
            text, reply_markup=admin_services_list_keyboard(services, page=page)
        )


async def admin_service_detail_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE, service_id: int
) -> None:
    """Show service details."""
    query = update.callback_query
    if not query:
        return
    user = update.effective_user
    if not user:
        return

    async for db in get_db():
        db_user = await db.get(User, user.id)
        if not db_user or not await is_admin(db, user.id):
            await query.answer("Admin only.", show_alert=True)
            return

        svc = await db.get(Service, service_id)
        if not svc:
            await query.edit_message_text("سرویس پیدا نشد.")
            return

        owner = await db.get(User, svc.user_id)
        owner_name = owner.username if owner else f"User {svc.user_id}"

        days = svc.days_remaining if svc.days_remaining is not None else "Unlimited"
        traffic = (
            "Unlimited"
            if svc.is_unlimited
            else f"{svc.remaining_traffic_gb:.2f}GB / {svc.total_traffic_gb:.2f}GB"
        )

        text = (
            f"🔧 جزئیات سرویس #{svc.id}\n\n"
            f"👤 مالک: {owner_name} (ID: {svc.user_id})\n"
            f"🔹 Protocol: {svc.protocol.upper()}\n"
            f"⏰ روزهای باقی‌مانده: {days}\n"
            f"📊 ترافیک: {traffic}\n"
            f"📈 مصرف شده: {svc.used_traffic_gb:.2f}GB\n"
            f"📅 تاریخ انقضا: {svc.expiry_date.strftime('%Y-%m-%d %H:%M:%S') if svc.expiry_date else '—'}\n"
        )

        await query.edit_message_text(text, reply_markup=admin_service_detail_keyboard(service_id))


async def admin_service_sync_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE, service_id: int
) -> None:
    """Sync service from PasarGuard."""
    query = update.callback_query
    if not query:
        return
    user = update.effective_user
    if not user:
        return

    async for db in get_db():
        db_user = await db.get(User, user.id)
        if not db_user or not await is_admin(db, user.id):
            await query.answer("Admin only.", show_alert=True)
            return

        svc = await db.get(Service, service_id)
        if not svc:
            await query.answer("سرویس پیدا نشد.", show_alert=True)
            return

        panel = await db.get(Panel, svc.panel_id)
        if not panel:
            await query.answer("Panel not found.", show_alert=True)
            return

        panel_service = await PanelFactory.create_panel(panel)
        try:
            user_stats = await panel_service.get_user_stats(username=svc.client_email)
            used = user_stats.used_traffic_bytes
            limit = user_stats.data_limit_bytes
            svc.used_traffic_gb = used / (1024**3)
            if limit is None:
                svc.total_traffic_gb = 0
                svc.is_unlimited = True
                svc.remaining_traffic_gb = None
            else:
                svc.total_traffic_gb = int(limit) // (1024**3)
                svc.is_unlimited = False
                remaining = max(0.0, (int(limit) - used) / (1024**3))
                svc.remaining_traffic_gb = remaining
            await db.commit()
            await query.answer(
                f"✅ Sync انجام شد. مصرف: {svc.used_traffic_gb:.2f}GB", show_alert=True
            )
        except Exception as e:
            await query.answer(f"❌ خطا: {str(e)}", show_alert=True)
        finally:
            await panel_service.close()

        await admin_service_detail_callback(update, context, service_id)


async def admin_service_renew_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE, service_id: int
) -> None:
    """Renew service."""
    query = update.callback_query
    if not query:
        return
    user = update.effective_user
    if not user:
        return

    async for db in get_db():
        db_user = await db.get(User, user.id)
        if not db_user or not await is_admin(db, user.id):
            await query.answer("Admin only.", show_alert=True)
            return

        # Use existing command handler

        class MockArgs:
            def __init__(self):
                self.args = [str(service_id), "30"]  # Default 30 days

        context.args = MockArgs()
        await admin_renew_command(update, context)

        await admin_service_detail_callback(update, context, service_id)


async def admin_service_addgb_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE, service_id: int
) -> None:
    """Add traffic to service."""
    query = update.callback_query
    if not query:
        return
    user = update.effective_user
    if not user:
        return

    async for db in get_db():
        db_user = await db.get(User, user.id)
        if not db_user or not await is_admin(db, user.id):
            await query.answer("Admin only.", show_alert=True)
            return

        # Use existing command handler

        class MockArgs:
            def __init__(self):
                self.args = [str(service_id), "10"]  # Default 10GB

        context.args = MockArgs()
        await admin_addgb_command(update, context)

        await admin_service_detail_callback(update, context, service_id)


async def admin_service_rotate_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE, service_id: int
) -> None:
    """Rotate service credentials."""
    query = update.callback_query
    if not query:
        return
    user = update.effective_user
    if not user:
        return

    async for db in get_db():
        db_user = await db.get(User, user.id)
        if not db_user or not await is_admin(db, user.id):
            await query.answer("Admin only.", show_alert=True)
            return

        # Use existing command handler

        class MockArgs:
            def __init__(self):
                self.args = [str(service_id)]

        context.args = MockArgs()
        await admin_rotate_command(update, context)

        await admin_service_detail_callback(update, context, service_id)


async def admin_service_remove_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE, service_id: int
) -> None:
    """Remove service."""
    query = update.callback_query
    if not query:
        return
    user = update.effective_user
    if not user:
        return

    async for db in get_db():
        db_user = await db.get(User, user.id)
        if not db_user or not await is_admin(db, user.id):
            await query.answer("Admin only.", show_alert=True)
            return

        svc = await db.get(Service, service_id)
        if not svc:
            await query.answer("سرویس پیدا نشد.", show_alert=True)
            return

        try:
            await remove_service(
                db, service=svc, admin_id=user.id, reason="Removed via admin panel"
            )
            await query.answer("✅ سرویس حذف شد.", show_alert=True)
        except Exception as e:
            await query.answer(f"❌ خطا: {str(e)}", show_alert=True)

        await admin_services_callback(update, context, page=0)


async def admin_products_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List products."""
    query = update.callback_query
    if not query:
        return
    user = update.effective_user
    if not user:
        return

    async for db in get_db():
        db_user = await db.get(User, user.id)
        if not db_user or not await is_admin(db, user.id):
            await query.answer("Admin only.", show_alert=True)
            return

        res = await db.execute(
            select(Product)
            .where(Product.status == ProductStatus.ACTIVE)
            .order_by(Product.sort_order.asc())
        )
        products = list(res.scalars().all())

        text = f"📦 لیست محصولات ({len(products)} مورد)\n\n"
        for p in products[:10]:
            text += f"• {p.name}: {int(p.price):,} تومان\n"

        await query.edit_message_text(text, reply_markup=admin_main_keyboard())


async def admin_tickets_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """List support tickets."""
    query = update.callback_query
    if not query:
        return
    user = update.effective_user
    if not user:
        return

    async for db in get_db():
        db_user = await db.get(User, user.id)
        if not db_user or not await is_admin(db, user.id):
            await query.answer("Admin only.", show_alert=True)
            return

        res = await db.execute(
            select(SupportTicket)
            .where(SupportTicket.status != TicketStatus.CLOSED)
            .order_by(SupportTicket.created_at.desc())
            .limit(20)
        )
        tickets = list(res.scalars().all())

        text = f"🎫 تیکت‌های پشتیبانی ({len(tickets)} مورد)\n\n"
        for t in tickets[:10]:
            status_icon = "🟢" if t.status == TicketStatus.OPEN else "🟡"
            text += f"{status_icon} #{t.ticket_number} - {t.status.value}\n"

        await query.edit_message_text(text, reply_markup=admin_main_keyboard())


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
        if not db_user or not await is_admin(db, user.id):
            await query.answer("Admin only.", show_alert=True)
            return

        text = "⚙️ تنظیمات\n\nلطفاً گزینه مورد نظر را انتخاب کنید:"
        await query.edit_message_text(text, reply_markup=admin_settings_keyboard())


async def admin_set_card_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Prompt for card settings."""
    query = update.callback_query
    if not query:
        return
    user = update.effective_user
    if not user:
        return

    async for db in get_db():
        db_user = await db.get(User, user.id)
        if not db_user or not await is_admin(db, user.id):
            await query.answer("Admin only.", show_alert=True)
            return

        await query.edit_message_text(
            "برای تنظیم کارت از دستور استفاده کنید:\n/setcard <شماره_کارت> [نام_صاحب]"
        )
        await query.answer()


async def admin_set_nowpay_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Prompt for NowPayments settings."""
    query = update.callback_query
    if not query:
        return
    user = update.effective_user
    if not user:
        return

    async for db in get_db():
        db_user = await db.get(User, user.id)
        if not db_user or not await is_admin(db, user.id):
            await query.answer("Admin only.", show_alert=True)
            return

        await query.edit_message_text(
            "برای تنظیم NowPayments از دستور استفاده کنید:\n/setnowpay <api_key> <ipn_secret>"
        )
        await query.answer()


async def admin_set_aqaye_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Prompt for Aqayepardakht settings."""
    query = update.callback_query
    if not query:
        return
    user = update.effective_user
    if not user:
        return

    async for db in get_db():
        db_user = await db.get(User, user.id)
        if not db_user or not await is_admin(db, user.id):
            await query.answer("Admin only.", show_alert=True)
            return

        await query.edit_message_text(
            "برای تنظیم Aqayepardakht از دستور استفاده کنید:\n/setaqaye <pin>"
        )
        await query.answer()


async def admin_set_faq_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Prompt for FAQ settings."""
    query = update.callback_query
    if not query:
        return
    user = update.effective_user
    if not user:
        return

    async for db in get_db():
        db_user = await db.get(User, user.id)
        if not db_user or not await is_admin(db, user.id):
            await query.answer("Admin only.", show_alert=True)
            return

        await query.edit_message_text(
            "برای تنظیم FAQ از دستور استفاده کنید:\n/setfaq <fa|en> <متن>"
        )
        await query.answer()


async def admin_set_tutorial_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Prompt for Tutorial settings."""
    query = update.callback_query
    if not query:
        return
    user = update.effective_user
    if not user:
        return

    async for db in get_db():
        db_user = await db.get(User, user.id)
        if not db_user or not await is_admin(db, user.id):
            await query.answer("Admin only.", show_alert=True)
            return

        await query.edit_message_text(
            "برای تنظیم Tutorial از دستور استفاده کنید:\n/settutorial <fa|en> <متن>"
        )
        await query.answer()
