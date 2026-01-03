"""Message handlers for the bot."""

from __future__ import annotations

import uuid

from loguru import logger
from telegram import Update
from telegram.ext import Application, ContextTypes, MessageHandler, filters
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from config.features import is_enabled
from database.models import (
    Admin,
    Payment,
    PaymentStatus,
    SupportMessage,
    SupportMessageType,
    SupportSender,
    SupportTicket,
    TicketStatus,
    User,
)
from database.session import get_db
from services.state_machine import clear_state, get_state


async def text_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle text messages."""
    if not update.message or not update.message.text:
        return

    text = update.message.text.strip()
    # Normalize: remove zero-width non-joiner and other invisible characters for consistent matching
    text = text.replace('\u200c', '').replace('\u200d', '').strip()
    user = update.effective_user
    logger.info(f"Incoming text user_id={getattr(user,'id',None)} text={text!r}")

    # Get user state
    if user:
        st = await get_state(user.id)
    else:
        st = None

    # Wallet gift code flow
    if st and st.step == "wallet.entering_gift_code":
        async for db in get_db():
            from database.models import User
            from services.discount import apply_gift_code_to_wallet

            db_user = await db.get(User, user.id)
            if not db_user:
                await update.message.reply_text("Please use /start first.")
                return
            ok, msg, _amt = await apply_gift_code_to_wallet(db, code=text.strip().upper(), user_id=db_user.id)
            await clear_state(user.id)
            await update.message.reply_text(msg)
        return

    # Wallet topup amount flow
    if st and st.step == "wallet.entering_topup_amount":
        async for db in get_db():
            from database.models import User, Purchase
            from database.models.purchase import PurchaseStatus, PurchaseType
            from bot.keyboards import payment_gateway_keyboard
            from utils.i18n import get_user_language, t

            db_user = await db.get(User, user.id)
            if not db_user:
                await update.message.reply_text("Please use /start first.")
                return

            lang = get_user_language(db_user)
            s = "".join(ch for ch in text if ch.isdigit())
            try:
                amount = int(s)
            except Exception:
                await update.message.reply_text(t("wallet_topup_amount_prompt", db_user, lang))
                return
            if amount < 10_000 or amount > 10_000_000:
                await update.message.reply_text(t("wallet_topup_amount_prompt", db_user, lang))
                return

            purchase = Purchase(
                user_id=db_user.id,
                product_id=None,
                service_id=None,
                purchase_type=PurchaseType.WALLET_TOPUP,
                status=PurchaseStatus.PENDING,
                amount=amount,
                discount_amount=0,
                final_amount=amount,
                duration_days=0,
                traffic_gb=0,
                protocol="wallet",
            )
            db.add(purchase)
            await db.commit()
            await db.refresh(purchase)
            await clear_state(user.id)

            txt = (
                f"🧾 {t('order_created', db_user, lang)}\n\n"
                f"Order ID: {purchase.id}\n"
                f"{t('amount', db_user, lang)}: {amount:,} Toman\n\n"
                f"{t('select_payment_method', db_user, lang)}"
            )
            await update.message.reply_text(txt, reply_markup=payment_gateway_keyboard(str(purchase.id), db_user))
        return

    # Discount code input flow
    if st and st.step == "purchase.entering_discount":
        async for db in get_db():
            from database.models import Product, User
            from services.discount import validate_and_apply_discount
            from bot.keyboards import purchase_with_discount_keyboard
            from utils.i18n import get_user_language, t

            db_user = await db.get(User, user.id)
            if not db_user:
                await update.message.reply_text("Please use /start first.")
                return

            product_id = st.payload.get("product_id")
            if not product_id:
                await clear_state(user.id)
                await update.message.reply_text("Invalid state. Please try again.")
                return

            product = await db.get(Product, product_id)
            if not product:
                await clear_state(user.id)
                await update.message.reply_text("Product not found.")
                return

            lang = get_user_language(db_user)
            discount_code = text.strip().upper()

            # Validate discount code
            discount_code_obj, discount_amount, error_msg = await validate_and_apply_discount(
                db,
                code=discount_code,
                user_id=db_user.id,
                purchase_amount=int(product.price),
                is_first_purchase=False,  # Could check here if needed
            )

            if not discount_code_obj:
                await update.message.reply_text(
                    f"{t('discount_error', db_user, lang)}: {error_msg}\n\n"
                    f"{t('enter_code_prompt', db_user, lang)}"
                )
                return

            # Show purchase confirmation with discount
            final_amount = int(product.price) - discount_amount
            if final_amount < 0:
                final_amount = 0

            await clear_state(user.id)
            discount_msg = (
                f"{t('discount_applied', db_user, lang)}\n\n"
                f"📦 {product.name}\n"
                f"{t('price_toman', db_user, lang).format(amount=product.price)}\n"
                f"{t('discount', db_user, lang)}: -{discount_amount:,} Toman\n"
                f"{t('final_amount', db_user, lang)}: {final_amount:,} Toman\n\n"
                f"{t('proceed_to_payment_question', db_user, lang)}"
            )
            await update.message.reply_text(
                discount_msg,
                reply_markup=purchase_with_discount_keyboard(product_id, discount_code, db_user),
            )
        return

    # Admin panel creation flow
    if st and st.step and st.step.startswith("admin.add_panel."):
        async for db in get_db():
            from handlers.commands import _require_admin
            from database.models import Panel, PanelStatus, PanelType
            from services.state_machine import set_step, clear_state
            from utils.encryption import encrypt_panel_credentials

            admin = await _require_admin(db, user.id)
            if not admin:
                await update.message.reply_text("Admin only.")
                await clear_state(user.id)
                return

            step = st.step
            payload = st.payload or {}

            if step == "admin.add_panel.name":
                payload["name"] = text.strip()
                await set_step(user.id, step="admin.add_panel.type", payload=payload)
                await update.message.reply_text(
                    "✅ نام پنل ثبت شد.\n\n"
                    "2️⃣ لطفاً نوع پنل را وارد کنید:\n"
                    "- pasarguard\n"
                    "- marzban"
                )
                return

            elif step == "admin.add_panel.type":
                panel_type = text.strip().lower()
                if panel_type not in ["pasarguard", "marzban"]:
                    await update.message.reply_text("❌ نوع پنل نامعتبر. لطفاً 'pasarguard' یا 'marzban' وارد کنید.")
                    return
                payload["type"] = panel_type
                await set_step(user.id, step="admin.add_panel.api_url", payload=payload)
                await update.message.reply_text(
                    "✅ نوع پنل ثبت شد.\n\n"
                    "3️⃣ لطفاً URL پنل را وارد کنید:\n"
                    "مثال: https://panel.example.com"
                )
                return

            elif step == "admin.add_panel.api_url":
                api_url = text.strip()
                if not api_url.startswith(("http://", "https://")):
                    await update.message.reply_text("❌ URL نامعتبر. باید با http:// یا https:// شروع شود.")
                    return
                payload["api_url"] = api_url
                await set_step(user.id, step="admin.add_panel.credentials", payload=payload)
                await update.message.reply_text(
                    "✅ URL پنل ثبت شد.\n\n"
                    "4️⃣ لطفاً API Key یا Username:Password را وارد کنید:\n"
                    "برای Marzban: username:password\n"
                    "برای PasarGuard: می‌توانید خالی بگذارید (از DB استفاده می‌شود)"
                )
                return

            elif step == "admin.add_panel.credentials":
                credentials = text.strip()
                # Encrypt credentials before storing
                encrypted_credentials = encrypt_panel_credentials(credentials) if credentials else ""
                
                # Parse username:password if applicable
                username = None
                password = None
                if ":" in credentials:
                    parts = credentials.split(":", 1)
                    if len(parts) == 2:
                        username = parts[0].strip()
                        password = encrypt_panel_credentials(parts[1].strip()) if parts[1].strip() else None
                
                payload["api_key"] = encrypted_credentials
                payload["username"] = username
                payload["password"] = password
                
                await set_step(user.id, step="admin.add_panel.node_id", payload=payload)
                await update.message.reply_text(
                    "✅ اعتبارنامه ثبت شد (رمزنگاری شده).\n\n"
                    "5️⃣ لطفاً Node ID را وارد کنید:\n"
                    "برای PasarGuard: شماره Node\n"
                    "برای Marzban: 0 بگذارید"
                )
                return

            elif step == "admin.add_panel.node_id":
                try:
                    node_id = int(text.strip())
                except ValueError:
                    await update.message.reply_text("❌ Node ID باید یک عدد باشد.")
                    return
                payload["node_id"] = node_id
                
                # For PasarGuard, ask for inbound_tag
                if payload.get("type") == "pasarguard":
                    await set_step(user.id, step="admin.add_panel.inbound_tag", payload=payload)
                    await update.message.reply_text(
                        "✅ Node ID ثبت شد.\n\n"
                        "6️⃣ لطفاً Inbound Tag را وارد کنید (اختیاری، پیش‌فرض: SUSH):"
                    )
                    return
                else:
                    # For Marzban, create panel now
                    await _create_panel_from_payload(db, payload, user.id)
                    await clear_state(user.id)
                    await update.message.reply_text("✅ پنل با موفقیت ایجاد شد!")
                    return

            elif step == "admin.add_panel.inbound_tag":
                inbound_tag = text.strip() or "SUSH"
                payload["inbound_tag"] = inbound_tag
                await _create_panel_from_payload(db, payload, user.id)
                await clear_state(user.id)
                await update.message.reply_text("✅ پنل با موفقیت ایجاد شد!")
                return

        return

    # Support ticket flow (state-machine)
    if st and st.step == "support.awaiting_message":
        await clear_state(user.id)
        if not user:
            return

        async for db in get_db():
            db_user = await db.get(User, user.id)
            if not db_user:
                await update.message.reply_text("Please use /start first to register.")
                return

            ticket_no = uuid.uuid4().hex[:10].upper()
            ticket = SupportTicket(
                user_id=db_user.id,
                ticket_number=ticket_no,
                subject="Support Request",
                message=text,
                status=TicketStatus.OPEN,
                priority=3,
            )
            db.add(ticket)
            await db.commit()
            await db.refresh(ticket)

            # Threaded message (first message)
            db.add(
                SupportMessage(
                    ticket_id=ticket.id,
                    sender_id=db_user.id,
                    sender_type=SupportSender.USER,
                    message_type=SupportMessageType.TEXT,
                    text=text,
                )
            )
            await db.commit()

            # Notify admins
            res = await db.execute(select(Admin).where(Admin.is_active.is_(True)))
            admins = list(res.scalars().all())
            notify_text = (
                "🆘 تیکت جدید\n\n"
                f"User: {db_user.id} (@{db_user.username})\n"
                f"Ticket: #{ticket.ticket_number}\n\n"
                f"{text}\n\n"
                f"باز کردن: /topen {ticket.ticket_number}\n"
                f"پاسخ: /treply {ticket.ticket_number} <متن>\n"
                f"بستن: /tclose {ticket.ticket_number}"
            )
            for admin in admins:
                try:
                    await context.bot.send_message(chat_id=admin.user_id, text=notify_text)
                except Exception as e:
                    logger.warning(f"Failed to notify admin {admin.user_id}: {e}")

        await update.message.reply_text(f"✅ تیکت شما ثبت شد.\n\nشماره تیکت: #{ticket_no}\n\nپشتیبانی به زودی پاسخ می‌دهد.")
        return

    # Menu without commands (reply keyboard buttons) - with i18n
    # All reply keyboard buttons just show the menu (simpler UX)
    async for db in get_db():
        db_user = await db.get(User, user.id)
        if not db_user:
            await update.message.reply_text("Please use /start first.")
            return

        from utils.i18n import t
        from bot.keyboards import main_menu_keyboard, main_reply_keyboard
        
        # Check if this is a reply keyboard button (any of the menu buttons)
        # Get all possible button texts
        purchase_text = t("purchase_service", db_user).replace('\u200c', '').replace('\u200d', '').strip()
        services_text = t("my_services", db_user).replace('\u200c', '').replace('\u200d', '').strip()
        wallet_text = t("wallet", db_user).replace('\u200c', '').replace('\u200d', '').strip()
        affiliate_text = t("affiliate", db_user).replace('\u200c', '').replace('\u200d', '').strip()
        trial_text = t("free_trial", db_user).replace('\u200c', '').replace('\u200d', '').strip()
        support_text = t("support", db_user).replace('\u200c', '').replace('\u200d', '').strip()
        menu_text_btn = t("menu", db_user)
        
        # Normalize received text
        text_normalized = text.replace('\u200c', '').replace('\u200d', '').strip()
        
        # Check if it's a reply keyboard button (starts with emoji or matches button text)
        is_reply_keyboard_button = (
            text.startswith("🛒") or text.startswith("📦") or text.startswith("💰") or
            text.startswith("👥") or text.startswith("🎁") or text.startswith("💬") or
            text_normalized == purchase_text or text_normalized == services_text or
            text_normalized == wallet_text or text_normalized == affiliate_text or
            text_normalized == trial_text or text_normalized == support_text or
            text_normalized == menu_text_btn or text.lower() in {"منو", "menu"} or text in {"menu", "/menu"}
        )
        
        if is_reply_keyboard_button:
            # When user presses "Menu" button, show inline keyboard with options
            from bot.keyboards import main_menu_keyboard
            menu_text = t("menu", db_user) + ":\n\n" + t("choose_option", db_user)
            await update.message.reply_text(menu_text, reply_markup=main_menu_keyboard(db_user))
            return

        # Default response - with i18n (only Reply Keyboard, no Inline)
        unknown_msg = t("unknown_command", db_user)
        menu_text = t("menu", db_user) + ":\n\n" + t("choose_option", db_user)
        await update.message.reply_text(unknown_msg, reply_markup=main_reply_keyboard(db_user))
        return


async def photo_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle photo messages."""
    if not update.message or not update.message.photo:
        return
    user = update.effective_user
    if not user:
        return
    logger.info(f"Incoming photo user_id={user.id} caption={update.message.caption!r}")
    st = await get_state(user.id)
    if st.step != "payment.awaiting_receipt":
        await update.message.reply_text("عکس دریافت شد. اگر برای پرداخت نیست، از /menu استفاده کنید.")
        return

    payment_id = int((st.payload or {}).get("payment_id") or 0)
    purchase_id = int((st.payload or {}).get("purchase_id") or 0)
    if not payment_id or not purchase_id:
        await update.message.reply_text("خطا در وضعیت پرداخت. لطفاً دوباره تلاش کنید.")
        await clear_state(user.id)
        return

    file_id = update.message.photo[-1].file_id
    caption = update.message.caption or ""

    async for db in get_db():
        pay = await db.get(Payment, payment_id)
        if not pay:
            await update.message.reply_text("پرداخت پیدا نشد.")
            await clear_state(user.id)
            return
        pay.status = PaymentStatus.PROCESSING
        pay.gateway_response = str({"telegram_receipt_file_id": file_id, "caption": caption})
        await db.commit()

        # Notify admins with inline keyboard
        from bot.admin_keyboards import admin_payment_detail_keyboard
        res = await db.execute(select(Admin).where(Admin.is_active.is_(True)))
        admins = list(res.scalars().all())
        
        # Get payment details for better message
        pay = await db.get(Payment, payment_id)
        purchase = await db.get(Purchase, purchase_id)
        buyer = await db.get(User, purchase.user_id) if purchase else None
        
        amount = int(pay.amount) if pay else 0
        txt = (
            "🧾 رسید پرداخت جدید\n\n"
            f"👤 کاربر: {buyer.username if buyer else 'ناشناس'} (ID: {user.id})\n"
            f"💰 مبلغ: {amount:,} تومان\n"
            f"📦 Purchase ID: {purchase_id}\n"
            f"💳 Payment ID: {payment_id}\n\n"
            "برای تایید یا رد پرداخت، از دکمه‌های زیر استفاده کنید:"
        )
        
        for admin in admins:
            try:
                await context.bot.send_photo(
                    chat_id=admin.user_id,
                    photo=file_id,
                    caption=txt,
                    reply_markup=admin_payment_detail_keyboard(payment_id)
                )
            except Exception as e:
                logger.warning(f"Failed to notify admin {admin.user_id}: {e}")

    await clear_state(user.id)
    await update.message.reply_text("✅ رسید ثبت شد. بعد از تایید ادمین، کانفیگ ارسال می‌شود.")


async def contact_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle shared contact for phone verification."""
    if not update.message or not update.message.contact:
        return
    user = update.effective_user
    if not user:
        return
    c = update.message.contact
    # Only accept the user's own contact to prevent spoofing.
    if c.user_id and int(c.user_id) != int(user.id):
        await update.message.reply_text("Please share your own phone number.")
        return
    phone = (c.phone_number or "").strip()
    async for db in get_db():
        db_user = await db.get(User, user.id)
        if not db_user:
            await update.message.reply_text("Please use /start first.")
            return
        from utils.security import sanitize_phone_number, validate_phone_number
        from utils.i18n import get_user_language, t
        from bot.keyboards import main_menu_keyboard, main_reply_keyboard

        lang = get_user_language(db_user)
        sanitized = sanitize_phone_number(phone)
        if not validate_phone_number(sanitized):
            await update.message.reply_text(t("phone_invalid", db_user, lang))
            return
        db_user.phone_number = sanitized
        db_user.phone_verified = True
        await db.commit()
        await update.message.reply_text(t("phone_verified_ok", db_user, lang), reply_markup=main_reply_keyboard(db_user))
        await update.message.reply_text("⬇️", reply_markup=main_menu_keyboard(db_user))


async def _create_panel_from_payload(db: AsyncSession, payload: dict, admin_id: int) -> None:
    """Helper function to create panel from payload."""
    from database.models import Panel, PanelStatus

    panel = Panel(
        name=payload["name"],
        type=payload["type"],
        api_url=payload["api_url"],
        api_key=payload["api_key"],
        username=payload.get("username"),
        password=payload.get("password"),
        node_id=payload.get("node_id", 0),
        inbound_tag=payload.get("inbound_tag", "SUSH"),
        status=PanelStatus.ACTIVE,
    )
    db.add(panel)
    await db.commit()
    logger.info(f"Admin {admin_id} created panel: {panel.name} (type: {panel.type})")


def register_message_handlers(application: Application) -> None:
    """Register all message handlers."""
    # Register TEXT handler FIRST (before other handlers that might catch it)
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_message_handler), group=0)
    application.add_handler(MessageHandler(filters.CONTACT, contact_message_handler), group=1)
    application.add_handler(MessageHandler(filters.PHOTO, photo_message_handler), group=1)

