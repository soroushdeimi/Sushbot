"""Command handlers for the bot."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from database.models import (
    Admin,
    AdminLevel,
    Payment,
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
from integrations.factory import PanelFactory
from services.fulfillment import fulfill_purchase
from services.state_machine import release_lock, try_lock
from services.wallet import apply_wallet_tx
from utils.security import generate_referral_code, hash_password
from utils.admin_check import get_admin

if TYPE_CHECKING:
    from telegram.ext import Application


async def _require_support_admin(db: AsyncSession, telegram_user_id: int) -> Admin | None:
    a = await get_admin(db, telegram_user_id)
    if not a or not a.can_manage_support:
        return None
    return a


async def _require_admin(db: AsyncSession, telegram_user_id: int) -> Admin | None:
    """Unified admin check used across admin handlers.

    Accepts both:
    - .env admin IDs (super admins + static admins)
    - DB-promoted admins (users.role==ADMIN + active admins row)
    """
    return await get_admin(db, telegram_user_id)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command."""
    user = update.effective_user
    if not user:
        return

    async for db in get_db():
        # Get or create user
        db_user = await db.get(User, user.id)
        if not db_user:
            db_user = User(
                id=user.id,
                telegram_id=user.id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name,
                language_code=user.language_code,
                referral_code=generate_referral_code(user.id),
            )
            db.add(db_user)
            await db.commit()
            logger.info(f"New user registered: {user.id}")
        else:
            # Upsert profile fields (supports placeholder users created by state machine)
            changed = False
            if db_user.username != user.username:
                db_user.username = user.username
                changed = True
            if db_user.first_name != user.first_name:
                db_user.first_name = user.first_name
                changed = True
            if db_user.last_name != user.last_name:
                db_user.last_name = user.last_name
                changed = True
            # Don't overwrite user's selected language with Telegram's language_code
            # Only update if user hasn't selected a language yet
            if not db_user.language_code or db_user.language_code not in {"fa", "en", "bilingual"}:
                # Keep Telegram's language_code as fallback, but will prompt for selection below
                pass
            if not db_user.referral_code:
                db_user.referral_code = generate_referral_code(user.id)
                changed = True
            if changed:
                await db.commit()

        # Optional affiliate binding via /start payload
        try:
            payload = context.args[0] if getattr(context, "args", None) else None
        except (IndexError, AttributeError, TypeError):
            # Expected errors when args is None or empty
            payload = None
        except Exception as e:
            logger.warning(f"Unexpected error getting start payload: {e}")
            payload = None
        try:
            from services.affiliate import try_bind_referral

            bound, msg = await try_bind_referral(db, user_id=user.id, referral_payload=payload)
            if bound and msg and update.message:
                await update.message.reply_text(msg)
        except Exception as e:
            logger.warning(f"Referral bind failed user_id={user.id}: {e}")

        # Auto-promote first real user to admin if SUPER_ADMIN_TELEGRAM_ID is not set (0)
        from config.settings import settings

        if settings.super_admin_telegram_id == 0:
            res = await db.execute(select(Admin))
            any_admin = res.scalars().first()
            if not any_admin:
                db_user.role = UserRole.ADMIN
                admin = Admin(user_id=db_user.id, level=AdminLevel.SUPER_ADMIN, is_active=True)
                db.add(admin)
                await db.commit()
                logger.info(f"Auto-promoted first user to SUPER_ADMIN: {db_user.id}")

        from bot.keyboards import (
            language_selection_keyboard,
            main_reply_keyboard,
        )
        from utils.i18n import Language, get_user_language, t

        # Check if user needs to select language (new user or language not set)
        user_lang = get_user_language(db_user)
        if not db_user.language_code or db_user.language_code not in {"fa", "en", "bilingual"}:
            # Show language selection for new users (always in English first)
            lang_desc = t("select_language_desc", None, Language.ENGLISH)
            t("select_language", None, Language.ENGLISH)
            await update.message.reply_text(lang_desc, reply_markup=language_selection_keyboard())
            return

        # User has selected language, show welcome in their language
        welcome_text = t("welcome", db_user, user_lang)
        # Only show Reply Keyboard (not Inline) to avoid duplication
        await update.message.reply_text(welcome_text, reply_markup=main_reply_keyboard(db_user))


async def menu_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /menu command with i18n."""
    from bot.keyboards import main_reply_keyboard
    from utils.i18n import t

    user = update.effective_user
    if not user:
        return

    async for db in get_db():
        db_user = await db.get(User, user.id)
        if not db_user:
            await update.message.reply_text("Please use /start first.")
            return

        menu_text = t("menu", db_user) + "\n\n" + t("choose_option", db_user)
        # Only show Reply Keyboard (not Inline) to avoid duplication
        await update.message.reply_text(menu_text, reply_markup=main_reply_keyboard(db_user))


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /help command."""
    help_text = (
        "🆘 Help\n\n"
        "Available commands:\n"
        "/start - Start the bot\n"
        "/menu - Show main menu\n"
        "/services - View your services\n"
        "/trial - Get trial account\n"
        "/support - Contact support\n"
        "/help - Show this help message\n\n"
        "For more information, visit our channel."
    )
    await update.message.reply_text(help_text)


async def services_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /services command."""
    user = update.effective_user
    if not user:
        return

    async for db in get_db():
        db_user = await db.get(User, user.id)
        if not db_user:
            await update.message.reply_text("Please use /start first to register.")
            return

        # Get user services
        res = await db.execute(
            select(Service).where(
                Service.user_id == db_user.id, Service.status == ServiceStatus.ACTIVE
            )
        )
        services = list(res.scalars().all())

        if not services:
            await update.message.reply_text(
                "You don't have any active services.\n\n"
                "Use /trial to get a free trial or /menu to purchase a service."
            )
            return

        # Show services
        services_text = "📦 Your Active Services:\n\n"
        for service in services:
            days = service.days_remaining or "Unlimited"
            traffic = (
                f"{service.used_traffic_gb:.2f}GB / {service.total_traffic_gb}GB"
                if service.total_traffic_gb > 0
                else "Unlimited"
            )
            services_text += (
                f"🔹 Service #{service.id}\n"
                f"   Protocol: {service.protocol.upper()}\n"
                f"   Days remaining: {days}\n"
                f"   Traffic: {traffic}\n\n"
            )

        await update.message.reply_text(services_text)


async def trial_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /trial command."""
    user = update.effective_user
    if not user:
        return

    if not await try_lock(user.id, seconds=30, reason="trial.create"):
        await update.message.reply_text(
            "⏳ درخواست قبلی هنوز در حال پردازش است. چند ثانیه دیگر دوباره تلاش کنید."
        )
        return

    try:
        async for db in get_db():
            db_user = await db.get(User, user.id)
            if not db_user:
                await update.message.reply_text("Please use /start first to register.")
                return

            from services.access_control import ensure_access

            guard = await ensure_access(update, context, db_user=db_user, purpose="trial")
            if not guard.ok:
                await db.commit()
                return

            from services.trial_service import TrialError, create_trial_for_user
            from utils.i18n import get_user_language, t

            lang = get_user_language(db_user)
            try:
                trial, service = await create_trial_for_user(db, user=db_user)
            except TrialError as e:
                if str(e) == "active_trial_exists":
                    await update.message.reply_text(t("trial_active_exists", db_user, lang))
                    return
                if str(e) == "trial_already_used":
                    await update.message.reply_text(t("trial_already_used", db_user, lang))
                    return
                raise

            await update.message.reply_text(
                t("trial_created", db_user, lang).format(
                    days=trial.duration_days, gb=trial.traffic_gb, service_id=service.id
                )
            )
            await update.message.reply_text(
                f"🔗 {t('config', db_user, lang)}:\n{trial.config_link}"
            )
    finally:
        await release_lock(user.id)


async def support_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /support command."""
    from bot.keyboards import support_keyboard

    support_text = "💬 Support\n\nHow can we help you?\n\nChoose an option:"
    await update.message.reply_text(support_text, reply_markup=support_keyboard())


async def tickets_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: list recent open tickets."""
    user = update.effective_user
    if not user or not update.message:
        return
    async for db in get_db():
        a = await _require_support_admin(db, user.id)
        if not a:
            await update.message.reply_text("Admin only.")
            return
        from database.models import SupportTicket, TicketStatus

        res = await db.execute(
            select(SupportTicket)
            .where(
                SupportTicket.status.in_(
                    [TicketStatus.OPEN, TicketStatus.IN_PROGRESS, TicketStatus.WAITING_USER]
                )
            )
            .order_by(SupportTicket.id.desc())
            .limit(15)
        )
        tickets = list(res.scalars().all())
        if not tickets:
            await update.message.reply_text("No open tickets.")
            return
        lines = ["📩 Open tickets:"]
        for t in tickets:
            lines.append(f"#{t.ticket_number} | {t.status} | user={t.user_id} | prio={t.priority}")
        lines.append("\nUse /topen <ticket_number>")
        await update.message.reply_text("\n".join(lines))


async def topen_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: open ticket thread: /topen <ticket_number>."""
    user = update.effective_user
    if not user or not update.message:
        return
    if not context.args:
        await update.message.reply_text("Usage: /topen <ticket_number>")
        return
    tn = context.args[0].strip().upper()
    async for db in get_db():
        a = await _require_support_admin(db, user.id)
        if not a:
            await update.message.reply_text("Admin only.")
            return
        from database.models import SupportMessage, SupportSender, SupportTicket

        res = await db.execute(
            select(SupportTicket).where(SupportTicket.ticket_number == tn).limit(1)
        )
        t = res.scalars().first()
        if not t:
            await update.message.reply_text("Ticket not found.")
            return
        res = await db.execute(
            select(SupportMessage)
            .where(SupportMessage.ticket_id == t.id)
            .order_by(SupportMessage.id.asc())
            .limit(20)
        )
        msgs = list(res.scalars().all())
        out = [f"🎫 Ticket #{t.ticket_number} | {t.status} | user={t.user_id}"]
        for m in msgs[-12:]:
            who = "👤" if m.sender_type == SupportSender.USER else "🛠"
            txt = (m.text or "").strip()
            if len(txt) > 350:
                txt = txt[:350] + "…"
            out.append(f"{who} {txt}")
        out.append(f"\nReply: /treply {t.ticket_number} <text>\nClose: /tclose {t.ticket_number}")
        await update.message.reply_text("\n\n".join(out))


async def treply_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: reply to ticket: /treply <ticket_number> <text...>."""
    user = update.effective_user
    if not user or not update.message:
        return
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /treply <ticket_number> <text...>")
        return
    tn = context.args[0].strip().upper()
    body = " ".join(context.args[1:]).strip()
    async for db in get_db():
        a = await _require_support_admin(db, user.id)
        if not a:
            await update.message.reply_text("Admin only.")
            return
        from database.models import (
            SupportMessage,
            SupportMessageType,
            SupportSender,
            SupportTicket,
            TicketStatus,
        )

        res = await db.execute(
            select(SupportTicket).where(SupportTicket.ticket_number == tn).limit(1)
        )
        t = res.scalars().first()
        if not t:
            await update.message.reply_text("Ticket not found.")
            return
        db.add(
            SupportMessage(
                ticket_id=t.id,
                sender_id=user.id,
                sender_type=SupportSender.ADMIN,
                message_type=SupportMessageType.TEXT,
                text=body,
            )
        )
        t.status = TicketStatus.WAITING_USER
        t.last_admin_response_at = datetime.utcnow()
        await db.commit()
        await update.message.reply_text("✅ Reply sent.")
        try:
            await context.bot.send_message(
                chat_id=t.user_id, text=f"🛠 پاسخ پشتیبانی (#{t.ticket_number}):\n\n{body}"
            )
        except Exception as e:
            logger.warning(f"Failed to notify ticket user {t.user_id}: {e}")


async def tclose_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: close ticket: /tclose <ticket_number>."""
    user = update.effective_user
    if not user or not update.message:
        return
    if not context.args:
        await update.message.reply_text("Usage: /tclose <ticket_number>")
        return
    tn = context.args[0].strip().upper()
    async for db in get_db():
        a = await _require_support_admin(db, user.id)
        if not a:
            await update.message.reply_text("Admin only.")
            return
        from database.models import SupportTicket, TicketStatus

        res = await db.execute(
            select(SupportTicket).where(SupportTicket.ticket_number == tn).limit(1)
        )
        t = res.scalars().first()
        if not t:
            await update.message.reply_text("Ticket not found.")
            return
        t.status = TicketStatus.CLOSED
        t.resolved_at = datetime.utcnow()
        t.resolved_by_id = user.id
        await db.commit()
        await update.message.reply_text("✅ Ticket closed.")
        try:
            await context.bot.send_message(
                chat_id=t.user_id, text=f"✅ تیکت شما بسته شد. (#{t.ticket_number})"
            )
        except Exception as e:
            logger.warning(f"Failed to notify ticket user {t.user_id}: {e}")


async def setpass_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: set password for web panel login: /setpass <password>."""
    user = update.effective_user
    if not user or not update.message:
        return
    if not context.args:
        await update.message.reply_text("Usage: /setpass <password>")
        return
    pw = " ".join(context.args).strip()
    if len(pw) < 8:
        await update.message.reply_text("Password too short (min 8).")
        return
    async for db in get_db():
        a = await _require_support_admin(db, user.id)
        if not a:
            await update.message.reply_text("Admin only.")
            return
        u = await db.get(User, user.id)
        if not u:
            await update.message.reply_text("User not found.")
            return
        u.password_hash = hash_password(pw)
        await db.commit()
        await update.message.reply_text("✅ Password set for web panel login.")


async def addbal_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: add/subtract user balance: /addbal <user_id> <amount> [note]."""
    user = update.effective_user
    if not user or not update.message:
        return
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /addbal <user_id> <amount> [note]")
        return
    target_id = int(context.args[0])
    amount = int(context.args[1])
    note = " ".join(context.args[2:]).strip() if len(context.args) > 2 else None
    async for db in get_db():
        a = await _require_support_admin(db, user.id)
        if not a or not a.can_manage_sales:
            await update.message.reply_text("Admin only.")
            return
        from database.models import WalletTxType

        tx = await apply_wallet_tx(
            db,
            user_id=target_id,
            amount=amount,
            tx_type=WalletTxType.ADJUST,
            ref=f"admin:{user.id}",
            note=note,
        )
        await update.message.reply_text(f"✅ Balance updated. New balance={tx.balance_after}")


async def admin_sync_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: sync a service traffic/limits from panel: /sync <service_id>."""
    user = update.effective_user
    if not user or not update.message:
        return
    if not context.args:
        await update.message.reply_text("Usage: /sync <service_id>")
        return
    service_id = int(context.args[0])
    async for db in get_db():
        from database.models import Panel

        db_user = await db.get(User, user.id)
        if not db_user or not await _require_admin(db, user.id):
            await update.message.reply_text("Admin only.")
            return
        svc = await db.get(Service, service_id)
        if not svc:
            await update.message.reply_text("Service not found.")
            return

        panel = await db.get(Panel, svc.panel_id)
        if not panel:
            await update.message.reply_text("Panel not found.")
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
            await update.message.reply_text(
                f"✅ Synced service #{svc.id}\nUsed: {svc.used_traffic_gb:.2f}GB\nRemaining: {svc.remaining_traffic_gb}"
            )
        finally:
            await panel_service.close()


async def admin_renew_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: renew by days: /renew <service_id> <days>."""
    user = update.effective_user
    if not user or not update.message:
        return
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /renew <service_id> <days>")
        return
    service_id = int(context.args[0])
    add_days = int(context.args[1])
    async for db in get_db():
        from database.models import Panel

        db_user = await db.get(User, user.id)
        if not db_user or not await _require_admin(db, user.id):
            await update.message.reply_text("Admin only.")
            return
        svc = await db.get(Service, service_id)
        if not svc:
            await update.message.reply_text("Service not found.")
            return

        panel = await db.get(Panel, svc.panel_id)
        if not panel:
            await update.message.reply_text("Panel not found.")
            return

        new_exp = (svc.expiry_date or datetime.utcnow()) + timedelta(days=add_days)
        panel_service = await PanelFactory.create_panel(panel)
        try:
            await panel_service.renew_user(
                username=svc.client_email, expire_ts=int(new_exp.timestamp())
            )
        finally:
            await panel_service.close()
        svc.expiry_date = new_exp
        await db.commit()
        await update.message.reply_text(f"✅ Renewed service #{svc.id} to {new_exp.isoformat()}")


async def admin_addgb_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: add traffic: /addgb <service_id> <gb>."""
    user = update.effective_user
    if not user or not update.message:
        return
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /addgb <service_id> <gb>")
        return
    service_id = int(context.args[0])
    gb = int(context.args[1])
    async for db in get_db():
        from database.models import Panel

        db_user = await db.get(User, user.id)
        if not db_user or not await _require_admin(db, user.id):
            await update.message.reply_text("Admin only.")
            return
        svc = await db.get(Service, service_id)
        if not svc:
            await update.message.reply_text("Service not found.")
            return

        panel = await db.get(Panel, svc.panel_id)
        if not panel:
            await update.message.reply_text("Panel not found.")
            return

        panel_service = await PanelFactory.create_panel(panel)
        try:
            await panel_service.add_traffic(username=svc.client_email, add_bytes=gb * (1024**3))
        finally:
            await panel_service.close()
        await update.message.reply_text(
            f"✅ Added {gb}GB to service #{svc.id}. Run /sync {svc.id} to refresh stats."
        )


async def admin_rotate_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: rotate credentials + send new link: /rotate <service_id>."""
    user = update.effective_user
    if not user or not update.message:
        return
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /rotate <service_id>")
        return
    service_id = int(context.args[0])
    async for db in get_db():
        from database.models import Panel

        db_user = await db.get(User, user.id)
        if not db_user or not await _require_admin(db, user.id):
            await update.message.reply_text("Admin only.")
            return
        svc = await db.get(Service, service_id)
        if not svc:
            await update.message.reply_text("Service not found.")
            return

        panel = await db.get(Panel, svc.panel_id)
        if not panel:
            await update.message.reply_text("Panel not found.")
            return

        panel_service = await PanelFactory.create_panel(panel)
        try:
            await panel_service.rotate_credentials(username=svc.client_email, protocol=svc.protocol)
            # Rebuild config link with new credentials
            new_link = await panel_service.generate_config_link(
                username=svc.client_email, protocol=svc.protocol
            )
        finally:
            await panel_service.close()
        svc.config_link = new_link
        await db.commit()
        await update.message.reply_text(f"✅ Rotated service #{svc.id}\n\n🔗 {new_link}")


async def admin_payapprove_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: approve a pending payment and provision service: /payapprove <payment_id>."""
    user = update.effective_user
    if not user or not update.message:
        return
    if not context.args:
        await update.message.reply_text("Usage: /payapprove <payment_id>")
        return
    payment_id = int(context.args[0])
    async for db in get_db():
        db_user = await db.get(User, user.id)
        if not db_user or not await _require_admin(db, user.id):
            await update.message.reply_text("Admin only.")
            return
        pay = await db.get(Payment, payment_id)
        if not pay:
            await update.message.reply_text("Payment not found.")
            return
        purchase = await db.get(Purchase, pay.purchase_id)
        if not purchase:
            await update.message.reply_text("Purchase not found.")
            return

        if pay.status == PaymentStatus.COMPLETED and purchase.status == PurchaseStatus.COMPLETED:
            if purchase.purchase_type == PurchaseType.WALLET_TOPUP:
                await update.message.reply_text("Already completed (wallet top-up).")
                return
            if purchase.service_id:
                svc = await db.get(Service, purchase.service_id)
                if svc and svc.config_link:
                    await update.message.reply_text(
                        f"Already completed. Service #{svc.id}\n{svc.config_link}"
                    )
                else:
                    await update.message.reply_text("Already completed.")
                return

        pay.status = PaymentStatus.COMPLETED
        pay.verified_at = datetime.utcnow()
        purchase.status = PurchaseStatus.COMPLETED
        purchase.completed_at = datetime.utcnow()
        await db.commit()

        svc = await fulfill_purchase(db, purchase=purchase)
        if svc is None and purchase.purchase_type == PurchaseType.WALLET_TOPUP:
            await update.message.reply_text(f"✅ Approved payment #{pay.id}. Wallet credited.")
            try:
                await context.bot.send_message(
                    chat_id=purchase.user_id,
                    text=f"✅ پرداخت تایید شد.\n\n💰 کیف پول شما به مبلغ {int(purchase.final_amount):,} تومان شارژ شد.",
                )
            except Exception as e:
                logger.warning(f"Failed to notify user {purchase.user_id}: {e}")
        else:
            assert svc is not None
            await update.message.reply_text(
                f"✅ Approved payment #{pay.id}. Fulfilled service #{svc.id}."
            )
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


async def admin_payreject_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: reject a payment: /payreject <payment_id>."""
    user = update.effective_user
    if not user or not update.message:
        return
    if not context.args:
        await update.message.reply_text("Usage: /payreject <payment_id>")
        return
    payment_id = int(context.args[0])
    async for db in get_db():
        db_user = await db.get(User, user.id)
        if not db_user or not await _require_admin(db, user.id):
            await update.message.reply_text("Admin only.")
            return
        pay = await db.get(Payment, payment_id)
        if not pay:
            await update.message.reply_text("Payment not found.")
            return
        purchase = await db.get(Purchase, pay.purchase_id)
        if purchase and purchase.status == PurchaseStatus.PENDING:
            purchase.status = PurchaseStatus.FAILED
            if purchase.product_id:
                from config.features import is_enabled

                if is_enabled("inventory"):
                    from services.inventory import release_stock

                    await release_stock(db, product_id=int(purchase.product_id), qty=1)
        pay.status = PaymentStatus.FAILED
        pay.admin_notes = "Rejected by admin"
        pay.verified_at = datetime.utcnow()
        await db.commit()
        await update.message.reply_text(f"❌ Rejected payment #{pay.id}.")
        if purchase:
            try:
                await context.bot.send_message(
                    chat_id=purchase.user_id,
                    text="❌ پرداخت شما رد شد. لطفاً با پشتیبانی تماس بگیرید.",
                )
            except Exception as e:
                logger.warning(f"Failed to notify user {purchase.user_id}: {e}")


async def admin_setcard_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: set card-to-card destination: /setcard <card_number> [owner]."""
    user = update.effective_user
    if not user or not update.message:
        return
    if not context.args:
        await update.message.reply_text("Usage: /setcard <card_number> [owner]")
        return
    card = context.args[0].strip()
    owner = " ".join(context.args[1:]).strip()
    async for db in get_db():
        db_user = await db.get(User, user.id)
        if not db_user or not await _require_admin(db, user.id):
            await update.message.reply_text("Admin only.")
            return
        from services.runtime_settings import set_setting

        await set_setting(db, key="card_to_card_number", value=card)
        if owner:
            await set_setting(db, key="card_to_card_owner", value=owner)
        await update.message.reply_text("✅ Card-to-card settings saved.")


async def admin_setnowpay_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: set NowPayments: /setnowpay <api_key> <ipn_secret>."""
    user = update.effective_user
    if not user or not update.message:
        return
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /setnowpay <api_key> <ipn_secret>")
        return
    api_key = context.args[0].strip()
    ipn = context.args[1].strip()
    async for db in get_db():
        db_user = await db.get(User, user.id)
        if not db_user or not await _require_admin(db, user.id):
            await update.message.reply_text("Admin only.")
            return
        from services.runtime_settings import set_setting

        await set_setting(db, key="nowpayments_api_key", value=api_key)
        await set_setting(db, key="nowpayments_ipn_secret", value=ipn)
        await update.message.reply_text("✅ NowPayments settings saved.")


async def admin_setaqaye_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: set Aqayepardakht pin: /setaqaye <pin>."""
    user = update.effective_user
    if not user or not update.message:
        return
    if len(context.args) < 1:
        await update.message.reply_text("Usage: /setaqaye <pin>")
        return
    pin = context.args[0].strip()
    async for db in get_db():
        db_user = await db.get(User, user.id)
        if not db_user or not await _require_admin(db, user.id):
            await update.message.reply_text("Admin only.")
            return
        from services.runtime_settings import set_setting

        await set_setting(db, key="aqayepardakht_pin", value=pin)
        await update.message.reply_text("✅ Aqayepardakht settings saved.")


async def admin_setfaq_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: set FAQ content. Usage: /setfaq <fa|en> <text...>"""
    user = update.effective_user
    if not user or not update.message:
        return
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /setfaq <fa|en> <text...>")
        return
    lang = context.args[0].strip().lower()
    text = " ".join(context.args[1:]).strip()
    if lang not in {"fa", "en"}:
        await update.message.reply_text("Language must be fa or en.")
        return
    async for db in get_db():
        db_user = await db.get(User, user.id)
        if not db_user or not await _require_admin(db, user.id):
            await update.message.reply_text("Admin only.")
            return
        from services.runtime_settings import set_setting

        await set_setting(db, key=f"faq_{lang}", value=text)
        await update.message.reply_text("✅ FAQ updated.")


async def admin_settutorial_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: set Tutorial content. Usage: /settutorial <fa|en> <text...>"""
    user = update.effective_user
    if not user or not update.message:
        return
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /settutorial <fa|en> <text...>")
        return
    lang = context.args[0].strip().lower()
    text = " ".join(context.args[1:]).strip()
    if lang not in {"fa", "en"}:
        await update.message.reply_text("Language must be fa or en.")
        return
    async for db in get_db():
        db_user = await db.get(User, user.id)
        if not db_user or not await _require_admin(db, user.id):
            await update.message.reply_text("Admin only.")
            return
        from services.runtime_settings import set_setting

        await set_setting(db, key=f"tutorial_{lang}", value=text)
        await update.message.reply_text("✅ Tutorial updated.")


async def admin_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: get comprehensive stats. Usage: /stats [overall|purchases|trials|revenue]"""
    user = update.effective_user
    if not user or not update.message:
        return
    async for db in get_db():
        db_user = await db.get(User, user.id)
        if not db_user or not await _require_admin(db, user.id):
            await update.message.reply_text("Admin only.")
            return

        from config.features import is_enabled
        from services.reports import (
            get_overall_stats,
            get_purchase_report,
            get_revenue_breakdown,
            get_trial_report,
        )

        if not is_enabled("reporting"):
            await update.message.reply_text("Reporting feature disabled.")
            return

        report_type = (context.args[0].lower() if context.args else "overall").strip()

        if report_type == "overall":
            stats = await get_overall_stats(db)
            txt = (
                f"📊 Overall Stats\n\n"
                f"👤 Total users: {stats['total_users']}\n"
                f"📦 Active services: {stats['active_services']}\n"
                f"💰 Total revenue: {stats['total_revenue']:,} Toman\n"
                f"🧾 Total purchases: {stats['total_purchases']}\n"
                f"🎁 Total trials: {stats['total_trials']}\n"
                f"💳 Pending payments: {stats['pending_payments']}"
            )
            await update.message.reply_text(txt)
        elif report_type == "purchases":
            report = await get_purchase_report(db)
            txt = (
                f"📊 Purchase Report\n\n"
                f"Total: {report['total_count']}\n"
                f"Revenue: {report['total_revenue']:,} Toman\n\n"
                f"By Product:\n"
            )
            for pid, data in list(report["by_product"].items())[:5]:
                txt += (
                    f"  {data['product_name']}: {data['count']} sales, {data['revenue']:,} Toman\n"
                )
            await update.message.reply_text(txt)
        elif report_type == "trials":
            report = await get_trial_report(db)
            txt = (
                f"📊 Trial Report\n\n"
                f"Total: {report['total']}\n"
                f"Active: {report['active']}\n"
                f"Expired: {report['expired']}"
            )
            await update.message.reply_text(txt)
        elif report_type == "revenue":
            report = await get_revenue_breakdown(db, days=30)
            txt = "📊 Revenue Breakdown (last 30 days)\n\n"
            for day in report["daily_breakdown"][:7]:
                txt += f"{day['date']}: {day['count']} sales, {day['revenue']:,} Toman\n"
            await update.message.reply_text(txt)
        else:
            await update.message.reply_text("Usage: /stats [overall|purchases|trials|revenue]")


async def admin_refund_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: refund a purchase. Usage: /refund <purchase_id> [reason]"""
    user = update.effective_user
    if not user or not update.message:
        return
    if not context.args:
        await update.message.reply_text("Usage: /refund <purchase_id> [reason]")
        return
    purchase_id = int(context.args[0])
    reason = " ".join(context.args[1:]).strip() if len(context.args) > 1 else None
    async for db in get_db():
        db_user = await db.get(User, user.id)
        if not db_user or not await _require_admin(db, user.id):
            await update.message.reply_text("Admin only.")
            return

        from config.features import is_enabled
        from services.refund import refund_purchase

        if not is_enabled("refunds"):
            await update.message.reply_text("Refunds feature disabled.")
            return

        try:
            result = await refund_purchase(
                db, purchase_id=purchase_id, admin_id=user.id, reason=reason
            )
            await update.message.reply_text(
                f"✅ Refunded purchase #{purchase_id}. Amount: {result.get('refund_amount', 0):,} Toman"
            )
        except ValueError as e:
            await update.message.reply_text(f"❌ Error: {e}")


async def admin_remove_service_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: remove a service. Usage: /removesvc <service_id> [reason]"""
    user = update.effective_user
    if not user or not update.message:
        return
    if not context.args:
        await update.message.reply_text("Usage: /removesvc <service_id> [reason]")
        return
    service_id = int(context.args[0])
    reason = " ".join(context.args[1:]).strip() if len(context.args) > 1 else None
    async for db in get_db():
        db_user = await db.get(User, user.id)
        if not db_user or not await _require_admin(db, user.id):
            await update.message.reply_text("Admin only.")
            return

        from config.features import is_enabled
        from services.refund import remove_service

        if not is_enabled("service_removal"):
            await update.message.reply_text("Service removal feature disabled.")
            return

        try:
            await remove_service(db, service_id=service_id, admin_id=user.id, reason=reason)
            await update.message.reply_text(f"✅ Removed service #{service_id}")
        except ValueError as e:
            await update.message.reply_text(f"❌ Error: {e}")


async def admin_panel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admin: open admin panel: /admin."""
    user = update.effective_user
    if not user or not update.message:
        return
    async for db in get_db():
        db_user = await db.get(User, user.id)
        if not db_user or not await _require_admin(db, user.id):
            await update.message.reply_text("Admin only.")
            return

        from sqlalchemy import func

        from bot.admin_keyboards import admin_main_keyboard
        from database.models import Payment, PaymentStatus

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
        await update.message.reply_text(text, reply_markup=admin_main_keyboard())


async def admin_transfer_service_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    """Admin: transfer service to another user. Usage: /transfersvc <service_id> <new_user_id> [reason]"""
    user = update.effective_user
    if not user or not update.message:
        return
    if len(context.args) < 2:
        await update.message.reply_text("Usage: /transfersvc <service_id> <new_user_id> [reason]")
        return
    service_id = int(context.args[0])
    new_user_id = int(context.args[1])
    reason = " ".join(context.args[2:]).strip() if len(context.args) > 2 else None
    async for db in get_db():
        db_user = await db.get(User, user.id)
        if not db_user or not await _require_admin(db, user.id):
            await update.message.reply_text("Admin only.")
            return

        from config.features import is_enabled
        from services.transfer import transfer_service

        if not is_enabled("service_transfer"):
            await update.message.reply_text("Service transfer feature disabled.")
            return

        try:
            await transfer_service(
                db, service_id=service_id, new_user_id=new_user_id, admin_id=user.id, reason=reason
            )
            await update.message.reply_text(
                f"✅ Transferred service #{service_id} to user {new_user_id}"
            )
        except ValueError as e:
            await update.message.reply_text(f"❌ Error: {e}")


def register_command_handlers(application: Application) -> None:
    """Register all command handlers."""
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("menu", menu_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("services", services_command))
    application.add_handler(CommandHandler("trial", trial_command))
    application.add_handler(CommandHandler("support", support_command))
    application.add_handler(CommandHandler("tickets", tickets_command))
    application.add_handler(CommandHandler("topen", topen_command))
    application.add_handler(CommandHandler("treply", treply_command))
    application.add_handler(CommandHandler("tclose", tclose_command))
    application.add_handler(CommandHandler("setpass", setpass_command))
    application.add_handler(CommandHandler("addbal", addbal_command))
    application.add_handler(CommandHandler("sync", admin_sync_command))
    application.add_handler(CommandHandler("renew", admin_renew_command))
    application.add_handler(CommandHandler("addgb", admin_addgb_command))
    application.add_handler(CommandHandler("rotate", admin_rotate_command))
    application.add_handler(CommandHandler("payapprove", admin_payapprove_command))
    application.add_handler(CommandHandler("payreject", admin_payreject_command))
    application.add_handler(CommandHandler("admin", admin_panel_command))
    application.add_handler(CommandHandler("setcard", admin_setcard_command))
    application.add_handler(CommandHandler("setnowpay", admin_setnowpay_command))
    application.add_handler(CommandHandler("setaqaye", admin_setaqaye_command))
    application.add_handler(CommandHandler("setfaq", admin_setfaq_command))
    application.add_handler(CommandHandler("settutorial", admin_settutorial_command))
    application.add_handler(CommandHandler("stats", admin_stats_command))
    application.add_handler(CommandHandler("refund", admin_refund_command))
    application.add_handler(CommandHandler("removesvc", admin_remove_service_command))
    application.add_handler(CommandHandler("transfersvc", admin_transfer_service_command))
