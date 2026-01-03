"""Callback query handlers for inline buttons."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from loguru import logger
from sqlalchemy import select
from telegram import Update
from telegram.error import NetworkError, TelegramError
from telegram.ext import ContextTypes

if TYPE_CHECKING:
    from telegram.ext import Application

from config.features import is_enabled
from database.models import Payment, PaymentGateway, PaymentStatus, Purchase, PurchaseStatus, User
from database.session import get_db
from integrations.exceptions import PanelConnectionError, PanelError
from integrations.payments import AqayepardakhtGateway, CardToCardGateway, NowPaymentsGateway
from services.state_machine import release_lock, set_step, try_lock


async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle callback queries."""
    query = update.callback_query
    if not query:
        return

    from loguru import logger

    logger.info(
        f"Incoming callback user_id={getattr(update.effective_user, 'id', None)} data={query.data!r}"
    )

    await query.answer()

    data = query.data
    if not data:
        return

    # Feature-gated routing (safety: reject disabled features early)
    if data in {"purchase", "product", "confirm_purchase"} and not is_enabled("purchase"):
        await query.edit_message_text("This feature is disabled.")
        return
    if data == "my_services" and not is_enabled("services"):
        await query.edit_message_text("This feature is disabled.")
        return
    if data == "trial" and not is_enabled("trial"):
        await query.edit_message_text("This feature is disabled.")
        return
    if data == "support" and not is_enabled("support"):
        await query.edit_message_text("This feature is disabled.")
        return
    if data.startswith("payment_") and not is_enabled("purchase"):
        await query.edit_message_text("This feature is disabled.")
        return
    if data.startswith("payment_card_") and not is_enabled("pay_card_to_card"):
        await query.edit_message_text("This feature is disabled.")
        return
    if data.startswith(("payment_nowpayments_", "payment_nowpay_")) and not is_enabled(
        "pay_nowpayments"
    ):
        await query.edit_message_text("This feature is disabled.")
        return
    if data.startswith(("payment_aqayepardakht_", "payment_aqaye_")) and not is_enabled(
        "pay_aqayepardakht"
    ):
        await query.edit_message_text("This feature is disabled.")
        return
    if data == "wallet" or data.startswith("wallet_") or data == "gift_code":
        if not is_enabled("wallet"):
            await query.edit_message_text("This feature is disabled.")
            return
    if data == "affiliate" and not is_enabled("affiliate"):
        await query.edit_message_text("This feature is disabled.")
        return
    if data in {"faq", "tutorial"} and not is_enabled("content_cms"):
        # We still allow basic placeholder content if CMS is off.
        pass

    # Settings callbacks (cfg_* prefix)
    if data.startswith("cfg_"):
        from handlers.admin_settings import settings_callback_router

        await settings_callback_router(update, context)
        return

    # Admin callbacks (check first)
    if data.startswith("admin_"):
        await admin_router(update, context, data)
        return

    # Route to appropriate handler
    if data.startswith("lang_"):
        await language_selection_callback(update, context, data)
    elif data == "menu":
        await menu_callback(update, context)
    elif data == "purchase":
        await purchase_callback(update, context)
    elif data == "my_services":
        await my_services_callback(update, context)
    elif data == "trial":
        await trial_callback(update, context)
    elif data == "support":
        await support_callback(update, context)
    elif data.startswith("product_"):
        product_id = int(data.split("_")[1])
        await product_callback(update, context, product_id)
    elif data.startswith("select_protocol_"):
        # select_protocol_{product_id}_{protocol}[_{discount_code}]
        # Check if protocol selection feature is enabled
        if not is_enabled("protocol_selection"):
            await query.edit_message_text("This feature is disabled.")
            return
        await select_protocol_callback(update, context, data)
    elif data.startswith("payment_"):
        await payment_callback(update, context, data)
    elif data.startswith("discount_enter_"):
        # discount_enter_{product_id} OR discount_enter_{product_id}_proto_{protocol}
        await discount_enter_callback_handler(update, context, data)
    elif data.startswith("confirm_purchase_"):
        # Formats:
        # - confirm_purchase_{product_id}
        # - confirm_purchase_{product_id}_{discount_code}
        # - confirm_purchase_{product_id}_proto_{protocol}
        # - confirm_purchase_{product_id}_proto_{protocol}_{discount_code}
        await confirm_purchase_callback_handler(update, context, data)
    elif data.startswith("purchase_pay_"):
        # purchase_pay_{product_id}_{discount_code}
        await purchase_pay_callback(update, context, data)
    elif data.startswith("cancel_order_"):
        order_id = int(data.split("_")[-1])
        await cancel_order_callback(update, context, order_id)
    elif data.startswith(("svc_", "service_")):
        await service_router(update, context, data)
    elif data == "faq":
        await faq_callback(update, context)
    elif data == "tutorial":
        await tutorial_callback(update, context)
    elif data == "affiliate":
        await affiliate_callback(update, context)
    elif data == "wallet":
        await wallet_menu_callback(update, context)
    elif data == "wallet_balance":
        await wallet_balance_callback(update, context)
    elif data == "wallet_topup":
        await wallet_topup_callback(update, context)
    elif data == "gift_code":
        await gift_code_callback(update, context)
    elif data == "create_ticket":
        await create_ticket_callback(update, context)
    elif data == "my_tickets":
        await my_tickets_callback(update, context)
    elif data == "check_channel_member":
        await check_channel_member_callback(update, context)
    else:
        await query.edit_message_text("Unknown action.")


async def check_channel_member_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Re-check channel membership after user clicks 'I joined'."""
    query = update.callback_query
    if not query:
        return
    user = update.effective_user
    if not user:
        return
    async for db in get_db():
        db_user = await db.get(User, user.id)
        if not db_user:
            await query.edit_message_text("Please use /start first.")
            return
        from services.access_control import ensure_channel_member

        r = await ensure_channel_member(update, context, db_user=db_user, purpose="purchase")
        if r.ok:
            db_user.channel_member = True
            await db.commit()
            from bot.keyboards import main_reply_keyboard
            from utils.i18n import t

            await query.edit_message_text(t("channel_membership_ok", db_user))
            await query.message.reply_text(
                t("menu", db_user) + ":\n\n" + t("choose_option", db_user),
                reply_markup=main_reply_keyboard(db_user),
            )
        else:
            # ensure_channel_member already prompted
            try:
                await query.edit_message_text(t("channel_membership_still_missing", db_user))
            except (TelegramError, NetworkError) as e:
                logger.warning(f"Telegram error editing channel membership message: {e}")
            except Exception as e:
                logger.error(
                    f"Unexpected error editing channel membership message: {e}", exc_info=True
                )


async def wallet_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    user = update.effective_user
    if not user:
        return
    async for db in get_db():
        from bot.keyboards import wallet_menu_keyboard
        from database.models import User
        from utils.i18n import get_user_language, t

        db_user = await db.get(User, user.id)
        if not db_user:
            await query.edit_message_text("Please use /start first.")
            return
        lang = get_user_language(db_user)
        txt = f"{t('wallet', db_user, lang)}\n\n{t('choose_option', db_user, lang)}"
        await query.edit_message_text(txt, reply_markup=wallet_menu_keyboard(db_user))


async def wallet_balance_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    user = update.effective_user
    if not user:
        return
    async for db in get_db():
        from bot.keyboards import wallet_menu_keyboard
        from database.models import User
        from utils.i18n import get_user_language, t

        db_user = await db.get(User, user.id)
        if not db_user:
            await query.edit_message_text("Please use /start first.")
            return
        lang = get_user_language(db_user)
        await query.edit_message_text(
            f"💰 {t('wallet_balance', db_user, lang)}: {int(db_user.balance):,} Toman",
            reply_markup=wallet_menu_keyboard(db_user),
        )


async def language_selection_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE, data: str
) -> None:
    """Handle language selection callback: lang_fa, lang_en, lang_bilingual."""
    query = update.callback_query
    if not query:
        return
    user = update.effective_user
    if not user:
        return

    lang_map = {"lang_fa": "fa", "lang_en": "en", "lang_bilingual": "bilingual"}
    selected_lang = lang_map.get(data, "fa")

    async for db in get_db():
        from database.models import User

        db_user = await db.get(User, user.id)
        if not db_user:
            await query.edit_message_text("Please use /start first.")
            return

        db_user.language_code = selected_lang
        await db.commit()

        from bot.keyboards import main_reply_keyboard
        from utils.i18n import Language, t

        user_lang = Language(selected_lang)
        welcome_text = t("welcome", db_user, user_lang)
        lang_set_msg = t("language_set", db_user, user_lang)
        t("menu", db_user, user_lang) + ":\n\n" + t("choose_option", db_user, user_lang)

        await query.edit_message_text(lang_set_msg)
        # Only show Reply Keyboard (not Inline) to avoid duplication
        await query.message.reply_text(welcome_text, reply_markup=main_reply_keyboard(db_user))


async def menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle menu callback with i18n."""
    from bot.keyboards import main_reply_keyboard
    from utils.i18n import t

    query = update.callback_query
    user = update.effective_user
    if not user or not query or not query.message:
        return

    async for db in get_db():
        from database.models import User

        db_user = await db.get(User, user.id)
        if not db_user:
            await query.edit_message_text("Please use /start first.")
            return

        menu_text = t("menu", db_user) + "\n\n" + t("choose_option", db_user)
        # Only show Reply Keyboard (not Inline) to avoid duplication
        await query.message.reply_text(menu_text, reply_markup=main_reply_keyboard(db_user))


async def purchase_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle purchase callback."""
    query = update.callback_query
    if not query:
        return
    user = update.effective_user
    if not user:
        return

    # Get available products
    async for db in get_db():
        from database.models import Panel, Product, ProductStatus
        from services.access_control import ensure_access
        from utils.i18n import t

        db_user = await db.get(User, user.id)
        if not db_user:
            await query.edit_message_text("Please use /start first.")
            return

        guard = await ensure_access(update, context, db_user=db_user, purpose="purchase")
        if not guard.ok:
            await db.commit()
            return

        res = await db.execute(
            select(Product)
            .where(Product.status == ProductStatus.ACTIVE)
            .order_by(Product.sort_order.asc(), Product.id.asc())
        )
        products_all = list(res.scalars().all())
        products: list[Product] = []
        for p in products_all:
            panel = await db.get(Panel, p.panel_id)
            if panel and panel.is_available:
                from config.features import is_enabled

                if is_enabled("inventory") and not p.is_in_stock:
                    continue
                products.append(p)

        if not products:
            await query.edit_message_text(t("no_products_available", db_user))
            return

        from bot.keyboards import products_keyboard

        products_text = t("products_list", db_user)
        await query.edit_message_text(
            products_text, reply_markup=products_keyboard(products, db_user)
        )


async def my_services_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle my services callback."""
    query = update.callback_query
    if not query:
        return

    user = update.effective_user
    if not user:
        return

    async for db in get_db():
        db_user = await db.get(User, user.id)
        if not db_user:
            await query.edit_message_text("Please use /start first.")
            return

        from database.models import Service, ServiceStatus

        res = await db.execute(
            select(Service).where(
                Service.user_id == db_user.id, Service.status == ServiceStatus.ACTIVE
            )
        )
        services = list(res.scalars().all())

        if not services:
            await query.edit_message_text("You don't have any active services.")
            return

        from bot.keyboards import services_list_keyboard

        await query.edit_message_text(
            "📦 سرویس‌های شما:\n\nروی سرویس مورد نظر بزنید:",
            reply_markup=services_list_keyboard(services),
        )


async def service_router(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str) -> None:
    """svc_* routes."""
    parts = data.split("_")
    if len(parts) < 2:
        return
    if parts[1].isdigit():
        await service_detail_callback(update, context, int(parts[1]))
        return
    # svc_<action>_<service_id>...
    action = parts[1]
    # Backward-compat aliases (older keyboards)
    if action == "config":
        action = "send"
    if action == "sub" and len(parts) >= 3 and parts[2].isdigit():
        await service_send_sub(update, context, int(parts[2]))
        return
    if action == "send" and len(parts) >= 3 and parts[2].isdigit():
        await service_send_config(update, context, int(parts[2]))
        return
    if (
        action in {"renew", "add", "reset", "rotate", "revoke"}
        and len(parts) >= 3
        and parts[2].isdigit()
    ):
        sid = int(parts[2])
        if action in {"renew", "add"}:
            await service_select_product_callback(update, context, sid, action)
            return
        if action in {"reset", "rotate", "revoke"}:
            await service_confirm_callback(update, context, sid, action)
            return
    if (
        action in {"reset", "rotate", "revoke"}
        and len(parts) >= 4
        and parts[2] in {"yes", "no"}
        and parts[3].isdigit()
    ):
        sid = int(parts[3])
        if parts[2] == "yes":
            await service_execute_action(update, context, sid, action)
        else:
            await service_detail_callback(update, context, sid)
        return
    if action == "apply" and len(parts) >= 5 and parts[2] in {"renew", "add"}:
        act = parts[2]
        sid = int(parts[3])
        pid = int(parts[4])
        await service_apply_product_callback(update, context, sid, pid, act)
        return


async def service_detail_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE, service_id: int
) -> None:
    query = update.callback_query
    if not query:
        return
    user = update.effective_user
    if not user:
        return
    async for db in get_db():
        from database.models import Service

        svc = await db.get(Service, service_id)
        if not svc or svc.user_id != user.id:
            await query.edit_message_text("سرویس پیدا نشد.")
            return
        from bot.keyboards import service_manage_keyboard

        days = svc.days_remaining if svc.days_remaining is not None else "Unlimited"
        await query.edit_message_text(
            f"🔹 Service #{svc.id}\n"
            f"Protocol: {svc.protocol.upper()}\n"
            f"Days remaining: {days}\n"
            f"Traffic: {'Unlimited' if svc.is_unlimited else f'{svc.remaining_traffic_gb:.2f}GB'}\n\n"
            "چه کاری انجام بدیم؟",
            reply_markup=service_manage_keyboard(svc.id),
        )


async def service_send_config(
    update: Update, context: ContextTypes.DEFAULT_TYPE, service_id: int
) -> None:
    query = update.callback_query
    if not query:
        return
    user = update.effective_user
    if not user:
        return
    async for db in get_db():
        from database.models import Service, User
        from utils.i18n import get_user_language, t

        svc = await db.get(Service, service_id)
        if not svc or svc.user_id != user.id:
            await query.edit_message_text("سرویس پیدا نشد.")
            return
        db_user = await db.get(User, user.id)
        if not db_user:
            await query.edit_message_text("Please use /start first.")
            return
        lang = get_user_language(db_user)
        if not svc.config_link:
            await query.edit_message_text(t("config_not_available", db_user, lang))
            return
        from loguru import logger

        from services.subscription import ensure_service_sub_token, subscription_url_from_token
        from utils.qr import send_qr_code

        tok = await ensure_service_sub_token(db, svc)
        sub_url = subscription_url_from_token(tok)
        sub_txt = f"\n\n🔗 {t('subscription_link', db_user, lang)}:\n{sub_url}" if sub_url else ""
        config_text = f"🔗 {t('service', db_user, lang)} #{svc.id} {t('config', db_user, lang)}:\n\n{svc.config_link}{sub_txt}"
        await query.edit_message_text(config_text)
        # Send QR code for config
        try:
            await send_qr_code(
                query.message, svc.config_link, caption=f"{t('qr_config', db_user, lang)} #{svc.id}"
            )
        except Exception as e:
            logger.warning(f"Failed to send QR code: {e}")


async def service_send_sub(
    update: Update, context: ContextTypes.DEFAULT_TYPE, service_id: int
) -> None:
    query = update.callback_query
    if not query:
        return
    user = update.effective_user
    if not user:
        return
    async for db in get_db():
        from database.models import Service
        from services.subscription import ensure_service_sub_token, subscription_url_from_token

        svc = await db.get(Service, service_id)
        if not svc or svc.user_id != user.id:
            await query.edit_message_text("سرویس پیدا نشد.")
            return
        from database.models import User
        from utils.i18n import get_user_language, t
        from utils.qr import send_qr_code

        db_user = await db.get(User, user.id)
        lang = get_user_language(db_user)
        tok = await ensure_service_sub_token(db, svc)
        url = subscription_url_from_token(tok)
        if not url:
            await query.edit_message_text(t("subscription_url_not_configured", db_user, lang))
            return
        await query.edit_message_text(
            f"🔗 {t('subscription_link', db_user, lang)} {t('service', db_user, lang)} #{svc.id}:\n\n{url}"
        )
        # Send QR code for subscription
        try:
            await send_qr_code(
                query.message, url, caption=f"{t('qr_subscription', db_user, lang)} #{svc.id}"
            )
        except Exception as e:
            logger.warning(f"Failed to send QR code: {e}")


async def service_confirm_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE, service_id: int, action: str
) -> None:
    query = update.callback_query
    if not query:
        return
    from bot.keyboards import confirm_action_keyboard

    txt = "آیا مطمئن هستید؟"
    if action == "reset":
        txt = "ریست ترافیک انجام شود؟"
    if action == "rotate":
        txt = "ریوک/روتیت انجام شود؟ (کانفیگ جدید می‌گیرید)"
    if action == "revoke":
        txt = "ریوک سابسکریپشن انجام شود؟ (لینک قبلی از کار می‌افتد)"
    await query.edit_message_text(
        txt,
        reply_markup=confirm_action_keyboard(
            action,
            service_id,
            prefix="svc",
            confirm_token="yes",
            cancel_token="no",
        ),
    )


async def service_execute_action(
    update: Update, context: ContextTypes.DEFAULT_TYPE, service_id: int, action: str
) -> None:
    query = update.callback_query
    if not query:
        return
    user = update.effective_user
    if not user:
        return
    if not await try_lock(user.id, seconds=30, reason=f"svc.{action}.{service_id}"):
        await query.edit_message_text("⏳ درخواست قبلی هنوز در حال پردازش است.")
        return
    try:
        async for db in get_db():
            from database.models import Service

            svc = await db.get(Service, service_id)
            if not svc or svc.user_id != user.id:
                await query.edit_message_text("سرویس پیدا نشد.")
                return
            if action == "revoke":
                import secrets

                from database.models import User
                from services.subscription import subscription_url_from_token
                from utils.i18n import get_user_language, t
                from utils.qr import send_qr_code

                db_user = await db.get(User, user.id)
                if not db_user:
                    await query.edit_message_text("Please use /start first.")
                    return
                svc.sub_token = secrets.token_urlsafe(24)
                await db.commit()
                url = subscription_url_from_token(str(svc.sub_token))
                lang = get_user_language(db_user)
                if not url:
                    await query.edit_message_text(
                        t("subscription_url_not_configured", db_user, lang)
                    )
                    return
                await query.edit_message_text(
                    f"✅ {t('revoke_sub', db_user, lang)}\n\n🔗 {t('subscription_link', db_user, lang)}:\n{url}"
                )
                try:
                    await send_qr_code(
                        query.message,
                        url,
                        caption=f"{t('qr_subscription', db_user, lang)} #{svc.id}",
                    )
                except (TelegramError, NetworkError) as e:
                    logger.warning(f"Telegram error sending QR code: {e}")
                except Exception as e:
                    logger.error(f"Unexpected error sending QR code: {e}", exc_info=True)
                return
            from database.models import Panel
            from integrations.factory import PanelFactory

            panel = await db.get(Panel, svc.panel_id)
            if not panel:
                await query.edit_message_text("❌ پنل پیدا نشد.")
                return

            panel_service = await PanelFactory.create_panel(panel)
            try:
                if action == "reset":
                    await panel_service.reset_traffic(username=svc.client_email)
                    svc.used_traffic_gb = 0.0
                    if not svc.is_unlimited and svc.total_traffic_gb > 0:
                        svc.remaining_traffic_gb = float(svc.total_traffic_gb)
                    await db.commit()
                    await query.edit_message_text("✅ ریست ترافیک انجام شد.")
                    return
                if action == "rotate":
                    try:
                        # Get current traffic usage before rotate
                        user_stats = await panel_service.get_user_stats(username=svc.client_email)
                        used_bytes = user_stats.used_traffic_bytes
                        data_limit_bytes = user_stats.data_limit_bytes

                        # Rotate credentials (this creates new UUID)
                        await panel_service.rotate_credentials(
                            username=svc.client_email, protocol=svc.protocol
                        )

                        # Generate new config link
                        new_link = await panel_service.generate_config_link(
                            username=svc.client_email,
                            protocol=svc.protocol,
                        )

                        # Update data_limit: subtract used traffic from limit
                        if data_limit_bytes is not None and used_bytes > 0:
                            new_limit = max(0, int(data_limit_bytes) - used_bytes)
                            # For panels that support it, update the limit
                            # Note: Some panels may not support this operation
                            try:
                                # Try to update limit (may not be supported by all panels)
                                await panel_service.add_traffic(
                                    username=svc.client_email, add_bytes=-used_bytes
                                )
                            except (PanelError, PanelConnectionError) as e:
                                logger.warning(
                                    f"Panel error updating traffic limit (operation may not be supported): {e}"
                                )
                                # If not supported, just reset traffic
                            except Exception as e:
                                logger.error(
                                    f"Unexpected error updating traffic limit: {e}", exc_info=True
                                )
                                # If not supported, just reset traffic
                            # Reset used_traffic to 0 after subtracting from limit
                            await panel_service.reset_traffic(username=svc.client_email)
                            # Update service record
                            svc.used_traffic_gb = 0.0
                            svc.total_traffic_gb = new_limit / (1024**3)
                            svc.remaining_traffic_gb = new_limit / (1024**3)
                        else:
                            # Unlimited or no limit - just reset used_traffic
                            await panel_service.reset_traffic(username=svc.client_email)
                            svc.used_traffic_gb = 0.0

                        svc.config_link = new_link
                        await db.commit()
                        await query.edit_message_text(f"✅ روتیت انجام شد.\n\n🔗 {new_link}")
                    except Exception as e:
                        await db.rollback()
                        logger.error(f"Failed to rotate service {service_id}: {e}", exc_info=True)
                        await query.edit_message_text("❌ خطا در روتیت. لطفاً دوباره تلاش کنید.")
                    return
            finally:
                await panel_service.close()
    finally:
        await release_lock(user.id)


async def service_select_product_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE, service_id: int, action: str
) -> None:
    query = update.callback_query
    if not query:
        return
    user = update.effective_user
    if not user:
        return
    async for db in get_db():
        from database.models import Product, ProductStatus, Service

        svc = await db.get(Service, service_id)
        if not svc or svc.user_id != user.id:
            await query.edit_message_text("سرویس پیدا نشد.")
            return
        q = select(Product).where(
            Product.status == ProductStatus.ACTIVE, Product.protocol == svc.protocol
        )
        if action == "renew":
            q = q.where(Product.duration_days > 0)
        if action == "add":
            q = q.where(Product.traffic_gb > 0)
        res = await db.execute(q)
        products = list(res.scalars().all())
        if not products:
            await query.edit_message_text("محصولی برای این عملیات پیدا نشد.")
            return
        from bot.keyboards import service_products_keyboard

        title = "🧾 انتخاب پکیج تمدید" if action == "renew" else "📈 انتخاب پکیج حجم"
        await query.edit_message_text(
            title, reply_markup=service_products_keyboard(action, service_id, products)
        )


async def service_apply_product_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    service_id: int,
    product_id: int,
    action: str,
) -> None:
    query = update.callback_query
    if not query:
        return
    user = update.effective_user
    if not user:
        return
    async for db in get_db():
        from bot.keyboards import payment_gateway_keyboard
        from config.settings import settings
        from database.models import Product, Service
        from database.models.purchase import PurchaseType

        svc = await db.get(Service, service_id)
        if not svc or svc.user_id != user.id:
            await query.edit_message_text("سرویس پیدا نشد.")
            return
        product = await db.get(Product, product_id)
        if not product:
            await query.edit_message_text("Product not found.")
            return

        if not settings.subscription_version:
            await query.edit_message_text("این قابلیت فعال نیست.")
            return

        ptype = PurchaseType.RENEWAL if action == "renew" else PurchaseType.ADDITIONAL_VOLUME
        purchase = Purchase(
            user_id=user.id,
            product_id=product.id,
            service_id=svc.id,
            purchase_type=ptype,
            status=PurchaseStatus.PENDING,
            amount=int(product.price),
            discount_amount=0,
            final_amount=int(product.price),
            duration_days=product.duration_days,
            traffic_gb=product.traffic_gb,
            protocol=product.protocol,
        )
        db.add(purchase)
        await db.commit()
        await db.refresh(purchase)
        await set_step(
            user.id, step="purchase.awaiting_payment", payload={"purchase_id": purchase.id}
        )
        await query.edit_message_text(
            f"🧾 سفارش ساخته شد.\n\nOrder ID: {purchase.id}\nAmount: {int(purchase.final_amount):,} Toman\n\nروش پرداخت را انتخاب کنید:",
            reply_markup=payment_gateway_keyboard(str(purchase.id)),
        )


async def trial_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle trial callback."""
    query = update.callback_query
    user = update.effective_user
    if not query or not user:
        return
    if not await try_lock(user.id, seconds=30, reason="trial.create"):
        await query.edit_message_text(
            "⏳ درخواست قبلی هنوز در حال پردازش است. چند ثانیه دیگر دوباره تلاش کنید."
        )
        return
    try:
        async for db in get_db():
            db_user = await db.get(User, user.id)
            if not db_user:
                await query.edit_message_text("Please use /start first.")
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
                trial, svc = await create_trial_for_user(db, user=db_user)
            except TrialError as e:
                if str(e) == "active_trial_exists":
                    await query.edit_message_text(t("trial_active_exists", db_user, lang))
                    return
                if str(e) == "trial_already_used":
                    await query.edit_message_text(t("trial_already_used", db_user, lang))
                    return
                raise
            await query.edit_message_text(
                t("trial_created", db_user, lang).format(
                    days=trial.duration_days, gb=trial.traffic_gb, service_id=svc.id
                )
            )
            await query.message.reply_text(f"🔗 {t('config', db_user, lang)}:\n{trial.config_link}")
    finally:
        await release_lock(user.id)


async def support_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle support callback."""
    from bot.keyboards import support_keyboard

    support_text = "💬 Support\n\nHow can we help you?"
    query = update.callback_query
    if query and query.message:
        await query.edit_message_text(support_text, reply_markup=support_keyboard())


async def product_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    product_id: int,
) -> None:
    """Handle product selection callback.

    If the product supports multiple protocols AND the protocol_selection
    feature is enabled, shows a protocol selection keyboard first.
    Otherwise, proceeds directly to purchase confirmation.
    """
    query = update.callback_query
    if not query:
        return

    async for db in get_db():
        from database.models import Product

        product = await db.get(Product, product_id)
        if not product:
            await query.edit_message_text("Product not found.")
            return

        from bot.keyboards import product_detail_keyboard, protocol_selection_keyboard
        from utils.i18n import get_user_language, t

        db_user = await db.get(User, query.from_user.id)
        lang = get_user_language(db_user)

        traffic_text = (
            f"{product.traffic_gb} GB"
            if product.traffic_gb > 0
            else t("unlimited_traffic", db_user, lang)
        )

        # Check if product supports multiple protocols
        allowed_protocols = product.get_allowed_protocols()

        # Build protocol display text
        if product.supports_multiple_protocols:
            protocols_display = " / ".join([p.upper() for p in allowed_protocols])
        else:
            protocols_display = (
                allowed_protocols[0].upper() if allowed_protocols else product.protocol.upper()
            )

        product_text_i18n = (
            f"📦 {product.name}\n\n"
            f"💵 {t('price_toman', db_user, lang).format(amount=product.price)}\n"
            f"⏱ {t('days', db_user, lang).format(days=product.duration_days)}\n"
            f"📊 {traffic_text}\n"
            f"🔌 {protocols_display}\n\n"
            f"{product.description or t('no_description', db_user, lang)}\n\n"
        )

        # Check if protocol selection feature is enabled
        protocol_selection_enabled = is_enabled("protocol_selection")

        # If product supports multiple protocols AND feature is enabled, show protocol selection
        if product.supports_multiple_protocols and protocol_selection_enabled:
            product_text_i18n += t("select_protocol", db_user, lang)
            await query.edit_message_text(
                product_text_i18n,
                reply_markup=protocol_selection_keyboard(
                    product_id=product_id,
                    protocols=allowed_protocols,
                    user=db_user,
                ),
            )
        else:
            # Single protocol OR feature disabled - show standard purchase confirmation
            product_text_i18n += t("purchase_confirmation", db_user, lang)
            await query.edit_message_text(
                product_text_i18n, reply_markup=product_detail_keyboard(product_id, db_user)
            )


async def select_protocol_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    data: str,
) -> None:
    """Handle protocol selection for multi-protocol products.

    Callback data format: select_protocol_{product_id}_{protocol}[_{discount_code}]

    Stores the selected protocol in FSM state and proceeds to purchase confirmation.
    """
    query = update.callback_query
    if not query:
        return
    user = update.effective_user
    if not user:
        return

    # Parse callback data: select_protocol_{product_id}_{protocol}[_{discount_code}]
    parts = data.removeprefix("select_protocol_").split("_", 2)
    if len(parts) < 2:
        await query.edit_message_text("Invalid protocol selection.")
        return

    product_id = int(parts[0])
    selected_protocol = parts[1].lower()
    discount_code = parts[2] if len(parts) > 2 else None

    async for db in get_db():
        from database.models import Product

        product = await db.get(Product, product_id)
        if not product:
            await query.edit_message_text("Product not found.")
            return

        # Validate that the selected protocol is allowed for this product
        allowed_protocols = product.get_allowed_protocols()
        if selected_protocol not in allowed_protocols:
            await query.edit_message_text(
                f"Protocol '{selected_protocol}' is not available for this product."
            )
            return

        db_user = await db.get(User, user.id)
        if not db_user:
            await query.edit_message_text("Please use /start first.")
            return

        from utils.i18n import get_user_language, t

        lang = get_user_language(db_user)

        # Store the selected protocol in FSM state for later use during purchase creation
        await set_step(
            user.id,
            step="purchase.protocol_selected",
            payload={
                "product_id": product_id,
                "selected_protocol": selected_protocol,
                "discount_code": discount_code,
            },
        )

        # Show purchase confirmation with the selected protocol
        from bot.keyboards import product_detail_keyboard_with_protocol

        traffic_text = (
            f"{product.traffic_gb} GB"
            if product.traffic_gb > 0
            else t("unlimited_traffic", db_user, lang)
        )

        confirmation_text = (
            f"📦 {product.name}\n\n"
            f"💵 {t('price_toman', db_user, lang).format(amount=product.price)}\n"
            f"⏱ {t('days', db_user, lang).format(days=product.duration_days)}\n"
            f"📊 {traffic_text}\n"
            f"🔌 {selected_protocol.upper()} ✓\n\n"
            f"{product.description or t('no_description', db_user, lang)}\n\n"
            f"{t('purchase_confirmation', db_user, lang)}"
        )

        await query.edit_message_text(
            confirmation_text,
            reply_markup=product_detail_keyboard_with_protocol(
                product_id=product_id,
                protocol=selected_protocol,
                discount_code=discount_code,
                user=db_user,
            ),
        )


async def discount_enter_callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    data: str,
) -> None:
    """Route discount_enter callbacks to the appropriate handler.

    Formats:
    - discount_enter_{product_id}
    - discount_enter_{product_id}_proto_{protocol}
    """
    # Parse callback data
    rest = data.removeprefix("discount_enter_")

    protocol = None
    if "_proto_" in rest:
        parts = rest.split("_proto_", 1)
        product_id = int(parts[0])
        protocol = parts[1].lower() if len(parts) > 1 else None
    else:
        product_id = int(rest)

    await discount_enter_callback(update, context, product_id, protocol)


async def discount_enter_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    product_id: int,
    selected_protocol: str | None = None,
) -> None:
    """Prompt user to enter discount code."""
    query = update.callback_query
    if not query:
        return
    user = update.effective_user
    if not user:
        return

    async for db in get_db():
        from database.models import User
        from utils.i18n import get_user_language, t

        db_user = await db.get(User, user.id)
        if not db_user:
            await query.edit_message_text("Please use /start first.")
            return

        lang = get_user_language(db_user)
        # Store product_id and optional protocol in state
        payload = {"product_id": product_id}
        if selected_protocol:
            payload["selected_protocol"] = selected_protocol
        await set_step(
            user.id,
            step="purchase.entering_discount",
            payload=payload,
        )
        await query.edit_message_text(
            t("enter_code_prompt", db_user, lang),
        )
        await query.answer()


async def confirm_purchase_callback_handler(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    data: str,
) -> None:
    """Route confirm_purchase callbacks to the appropriate handler.

    Formats:
    - confirm_purchase_{product_id}
    - confirm_purchase_{product_id}_{discount_code}
    - confirm_purchase_{product_id}_proto_{protocol}
    - confirm_purchase_{product_id}_proto_{protocol}_{discount_code}
    """
    rest = data.removeprefix("confirm_purchase_")

    protocol = None
    discount_code = None

    if "_proto_" in rest:
        # Format with protocol
        parts = rest.split("_proto_", 1)
        product_id = int(parts[0])
        proto_and_maybe_discount = parts[1] if len(parts) > 1 else ""

        # Check if there's a discount code after the protocol
        if "_" in proto_and_maybe_discount:
            proto_parts = proto_and_maybe_discount.split("_", 1)
            protocol = proto_parts[0].lower()
            discount_code = proto_parts[1].strip() or None
        else:
            protocol = proto_and_maybe_discount.lower()
    else:
        # Legacy format without protocol
        if "_" in rest:
            pid_s, disc = rest.split("_", 1)
            product_id = int(pid_s)
            discount_code = disc.strip() or None
        else:
            product_id = int(rest)

    await confirm_purchase_callback(update, context, product_id, discount_code, protocol)


async def confirm_purchase_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    product_id: int,
    discount_code: str | None = None,
    selected_protocol: str | None = None,
) -> None:
    """Provision service immediately for the selected product.

    Args:
        update: Telegram update
        context: Bot context
        product_id: Product to purchase
        discount_code: Optional discount code
        selected_protocol: User's selected protocol for multi-protocol products.
                          If None, uses the product's default protocol.
    """
    query = update.callback_query
    if not query:
        return
    user = update.effective_user
    if not user:
        return

    if not await try_lock(user.id, seconds=30, reason=f"purchase.confirm.{product_id}"):
        await query.edit_message_text(
            "⏳ درخواست قبلی هنوز در حال پردازش است. چند ثانیه دیگر دوباره تلاش کنید."
        )
        return
    try:
        async for db in get_db():
            db_user = await db.get(User, user.id)
            if not db_user:
                await query.edit_message_text("Please use /start first.")
                return
            from services.access_control import ensure_access

            guard = await ensure_access(update, context, db_user=db_user, purpose="purchase")
            if not guard.ok:
                await db.commit()
                return

            from bot.keyboards import payment_gateway_keyboard
            from config.settings import settings
            from database.models import Product

            product = await db.get(Product, product_id)
            if not product:
                await query.edit_message_text("Product not found.")
                return

            # Phase 4 (subscription_version): order -> payment -> approve -> provision
            if settings.subscription_version:
                from sqlalchemy import func, select

                from database.models.purchase import Purchase as PurchaseModel
                from database.models.purchase import PurchaseStatus as PurchaseStatusEnum
                from services.discount import validate_and_apply_discount

                # Is first successful purchase?
                res = await db.execute(
                    select(func.count(PurchaseModel.id)).where(
                        PurchaseModel.user_id == db_user.id,
                        PurchaseModel.status == PurchaseStatusEnum.COMPLETED,
                    )
                )
                is_first_purchase = int(res.scalar() or 0) == 0

                discount_code_obj = None
                discount_amount = 0
                if discount_code:
                    (
                        discount_code_obj,
                        discount_amount,
                        error_msg,
                    ) = await validate_and_apply_discount(
                        db,
                        code=discount_code,
                        user_id=db_user.id,
                        purchase_amount=int(product.price),
                        is_first_purchase=is_first_purchase,
                    )
                    if not discount_code_obj:
                        from utils.i18n import get_user_language, t

                        lang = get_user_language(db_user)
                        await set_step(
                            user.id,
                            step="purchase.entering_discount",
                            payload={"product_id": product_id},
                        )
                        await query.edit_message_text(
                            f"{t('discount_error', db_user, lang)}: {error_msg}\n\n{t('enter_code_prompt', db_user, lang)}"
                        )
                        return

                final_amount = int(product.price) - int(discount_amount)
                if final_amount < 0:
                    final_amount = 0

                # Inventory reservation (prevents oversell)
                from config.features import is_enabled

                if is_enabled("inventory") and product.stock_quantity is not None:
                    from services.inventory import InventoryError, reserve_stock

                    try:
                        await reserve_stock(db, product_id=product.id, qty=1)
                    except InventoryError:
                        from utils.i18n import get_user_language, t

                        lang = get_user_language(db_user)
                        await query.edit_message_text(t("no_products_available", db_user, lang))
                        return

                # Determine the protocol to use for this purchase
                # Priority: selected_protocol (user choice) > product.get_default_protocol()
                if selected_protocol:
                    # Validate that the selected protocol is allowed
                    allowed_protocols = product.get_allowed_protocols()
                    if selected_protocol.lower() not in allowed_protocols:
                        purchase_protocol = product.get_default_protocol()
                    else:
                        purchase_protocol = selected_protocol.lower()
                else:
                    purchase_protocol = product.get_default_protocol()

                purchase = Purchase(
                    user_id=db_user.id,
                    product_id=product.id,
                    service_id=None,
                    status=PurchaseStatus.PENDING,
                    amount=int(product.price),
                    discount_amount=int(discount_amount),
                    discount_code_id=discount_code_obj.id if discount_code_obj else None,
                    final_amount=int(final_amount),
                    duration_days=product.duration_days,
                    traffic_gb=product.traffic_gb,
                    protocol=purchase_protocol,  # Use user's selected protocol
                )
                db.add(purchase)
                await db.commit()
                await db.refresh(purchase)

                await set_step(
                    user.id,
                    step="purchase.awaiting_payment",
                    payload={"purchase_id": purchase.id, "product_id": product.id},
                )

                await query.edit_message_text(
                    f"🧾 سفارش ساخته شد.\n\n"
                    f"Order ID: {purchase.id}\n"
                    f"Amount: {int(product.price):,} Toman\n"
                    + (
                        f"Discount: -{int(discount_amount):,} Toman\n"
                        if int(discount_amount) > 0
                        else ""
                    )
                    + f"Final: {int(final_amount):,} Toman\n\n"
                    "روش پرداخت را انتخاب کنید:",
                    reply_markup=payment_gateway_keyboard(str(purchase.id)),
                )
                return

            # Legacy mode: provision immediately
            from database.models import Service, ServiceStatus
            from database.models.service import ServiceType
            from integrations.pasarguard import create_service_config
            from utils.panel_username import make_panel_username

            # Determine the protocol to use for legacy mode
            if selected_protocol:
                allowed_protocols = product.get_allowed_protocols()
                if selected_protocol.lower() in allowed_protocols:
                    legacy_protocol = selected_protocol.lower()
                else:
                    legacy_protocol = product.get_default_protocol()
            else:
                legacy_protocol = product.get_default_protocol()

            # Use same username format as new mode for consistency
            username = make_panel_username(
                telegram_username=db_user.username, user_id=db_user.id, suffix=str(product.id)
            )
            await query.edit_message_text("⏳ Provisioning your service... please wait.")
            cfg = await create_service_config(
                user_email=username,
                protocol=legacy_protocol,  # Use user's selected protocol
                port=settings.pasarguard_default_port,
                duration_days=product.duration_days,
                traffic_gb=product.traffic_gb,
                panel_id=product.panel_id,
            )
            now = datetime.utcnow()
            expiry = None
            if product.duration_days and product.duration_days > 0:
                expiry = now + timedelta(days=product.duration_days)
            service = Service(
                user_id=db_user.id,
                service_type=ServiceType.VPN,
                status=ServiceStatus.ACTIVE,
                panel_id=product.panel_id,
                inbound_id=cfg.get("inbound_id"),
                client_email=username,
                protocol=legacy_protocol,  # Use user's selected protocol
                server_address=cfg.get("server_address") or "unknown",
                port=int(cfg.get("port") or settings.pasarguard_default_port),
                total_traffic_gb=product.traffic_gb,
                used_traffic_gb=0.0,
                remaining_traffic_gb=None if product.traffic_gb == 0 else float(product.traffic_gb),
                start_date=now,
                expiry_date=expiry,
                is_unlimited=product.traffic_gb == 0,
                config_link=cfg.get("config_link"),
            )
            db.add(service)
            await db.commit()
            await db.refresh(service)
            purchase = Purchase(
                user_id=db_user.id,
                product_id=product.id,
                service_id=service.id,
                status=PurchaseStatus.COMPLETED,
                amount=int(product.price),
                discount_amount=0,
                final_amount=int(product.price),
                duration_days=product.duration_days,
                traffic_gb=product.traffic_gb,
                protocol=product.protocol,
                completed_at=now,
            )
            db.add(purchase)
            await db.commit()
            await query.edit_message_text(
                f"✅ Service created!\n\n"
                f"Service ID: {service.id}\n"
                f"Protocol: {service.protocol.upper()}\n\n"
                f"🔗 Config link:\n{service.config_link}\n\n"
                "Use /services anytime to view your services."
            )
    finally:
        await release_lock(user.id)


async def purchase_pay_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE, data: str
) -> None:
    """Handle purchase_pay_{product_id}_{discount_code} callback.

    This is a legacy callback that redirects to confirm_purchase.
    """
    query = update.callback_query
    if not query:
        return

    # Parse: purchase_pay_{product_id}_{discount_code_optional}
    rest = data.removeprefix("purchase_pay_")
    parts = rest.split("_", 1)

    if len(parts) >= 1 and parts[0].isdigit():
        product_id = int(parts[0])
        discount_code = parts[1].strip() if len(parts) > 1 and parts[1] else None
        await confirm_purchase_callback(update, context, product_id, discount_code)
    else:
        await query.edit_message_text("Invalid purchase data.")


async def faq_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.message:
        return
    user = update.effective_user
    if not user:
        return
    async for db in get_db():
        db_user = await db.get(User, user.id)
        if not db_user:
            await query.edit_message_text("Please use /start first.")
            return
        from services.runtime_settings import get_setting
        from utils.i18n import Language, get_user_language

        lang = get_user_language(db_user)
        fa = await get_setting(db, "faq_fa") or "❓ سوالات متداول\n\n(توسط ادمین قابل تنظیم است)"
        en = await get_setting(db, "faq_en") or "❓ FAQ\n\n(Admin can customize this content)"
        if lang == Language.BILINGUAL:
            body = f"{fa}\n\n---\n\n{en}"
        elif lang == Language.ENGLISH:
            body = en
        else:
            body = fa
        await query.edit_message_text(body)


async def tutorial_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query or not query.message:
        return
    user = update.effective_user
    if not user:
        return
    async for db in get_db():
        db_user = await db.get(User, user.id)
        if not db_user:
            await query.edit_message_text("Please use /start first.")
            return
        from services.runtime_settings import get_setting
        from utils.i18n import Language, get_user_language

        lang = get_user_language(db_user)
        fa = await get_setting(db, "tutorial_fa") or "📚 آموزش\n\n(توسط ادمین قابل تنظیم است)"
        en = (
            await get_setting(db, "tutorial_en")
            or "📚 Tutorial\n\n(Admin can customize this content)"
        )
        if lang == Language.BILINGUAL:
            body = f"{fa}\n\n---\n\n{en}"
        elif lang == Language.ENGLISH:
            body = en
        else:
            body = fa
        await query.edit_message_text(body)


async def affiliate_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    user = update.effective_user
    if not user:
        return
    async for db in get_db():
        db_user = await db.get(User, user.id)
        if not db_user:
            await query.edit_message_text("Please use /start first.")
            return
        if not db_user.referral_code:
            from utils.security import generate_referral_code

            db_user.referral_code = generate_referral_code(db_user.id)
            await db.commit()
        from sqlalchemy import func, select

        from config.settings import settings
        from database.models import WalletTransaction, WalletTxType
        from services.affiliate import build_referral_link

        res = await db.execute(select(func.count(User.id)).where(User.referred_by_id == db_user.id))
        cnt = int(res.scalar() or 0)
        res = await db.execute(
            select(func.coalesce(func.sum(WalletTransaction.amount), 0)).where(
                WalletTransaction.user_id == db_user.id,
                WalletTransaction.tx_type == WalletTxType.REFERRAL_REWARD.value,
            )
        )
        earned = int(res.scalar() or 0)
        link = build_referral_link(
            bot_username=settings.bot_username, referral_code=str(db_user.referral_code)
        )
        txt = (
            "👥 زیرمجموعه‌گیری\n\n"
            f"🔗 لینک دعوت شما:\n{link}\n\n"
            f"👤 تعداد زیرمجموعه‌ها: {cnt}\n"
            f"💰 درآمد شما: {earned:,} تومان\n\n"
            "لینک بالا را برای دوستانتان ارسال کنید. بعد از اولین خرید موفق، پورسانت به کیف پول شما اضافه می‌شود."
        )
        await query.edit_message_text(txt)


async def create_ticket_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    # Persist support step in DB (survives restarts)
    if update.effective_user:
        await set_step(update.effective_user.id, step="support.awaiting_message", payload={})
    await query.edit_message_text("📝 Please send your support message as a normal text message.")


async def my_tickets_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if not query:
        return
    user = update.effective_user
    if not user:
        return
    async for db in get_db():
        from database.models import SupportTicket

        res = await db.execute(select(User).where(User.id == user.id))
        db_user = res.scalars().first()
        if not db_user:
            await query.edit_message_text("Please use /start first.")
            return
        res = await db.execute(
            select(SupportTicket)
            .where(SupportTicket.user_id == db_user.id)
            .order_by(SupportTicket.id.desc())
            .limit(10)
        )
        tickets = list(res.scalars().all())
        if not tickets:
            await query.edit_message_text("You have no tickets.")
            return
        txt = "📋 Your tickets:\n\n" + "\n".join(
            [f"#{t.ticket_number} - {t.status}" for t in tickets]
        )
        await query.edit_message_text(txt)


async def payment_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    data: str,
) -> None:
    """Handle payment gateway callback: payment_<gateway>_<purchase_id>."""
    query = update.callback_query
    if not query:
        return
    user = update.effective_user
    if not user:
        return

    parts = (data or "").split("_", 2)
    if len(parts) != 3:
        await query.edit_message_text("Invalid payment action.")
        return
    _, gw, purchase_id_s = parts
    # Backward-compat aliases from older keyboards
    if gw == "nowpay":
        gw = "nowpayments"
    if gw == "aqaye":
        gw = "aqayepardakht"
    try:
        purchase_id = int(purchase_id_s)
    except ValueError:
        await query.edit_message_text("Invalid order id.")
        return

    async for db in get_db():
        purchase = await db.get(Purchase, purchase_id)
        if not purchase or purchase.user_id != user.id:
            await query.edit_message_text("Order not found.")
            return
        if purchase.status != PurchaseStatus.PENDING:
            await query.edit_message_text("این سفارش دیگر قابل پرداخت نیست.")
            return

        from config.settings import settings
        from services.runtime_settings import get_setting

        if gw == "card":
            card_no = await get_setting(db, "card_to_card_number") or settings.card_to_card_number
            card_owner = await get_setting(db, "card_to_card_owner") or settings.card_to_card_owner
            if not card_no or card_no.strip().upper() in {"SET_ME", "CHANGEME"}:
                await query.edit_message_text(
                    "کارت‌به‌کارت تنظیم نشده. لطفاً با ادمین تماس بگیرید یا درگاه دیگری انتخاب کنید."
                )
                return
            c2c = CardToCardGateway()
            d = await c2c.create_payment(
                amount=int(purchase.final_amount), order_id=str(purchase.id), callback_url=None
            )
            pay = Payment(
                purchase_id=purchase.id,
                gateway=PaymentGateway.CARD_TO_CARD,
                status=PaymentStatus.PENDING,
                amount=int(purchase.final_amount),
                currency="IRR",
                tracking_code=d.get("tracking_code"),
                gateway_response=str(d),
                card_number=card_no,
            )
            db.add(pay)
            await db.commit()
            await db.refresh(pay)

            await set_step(
                user.id,
                step="payment.awaiting_receipt",
                payload={"purchase_id": purchase.id, "payment_id": pay.id},
            )
            card_line = card_no or "—"
            owner_line = card_owner or ""
            owner_txt = f"\n👤 {owner_line}" if owner_line else ""
            await query.edit_message_text(
                "💳 پرداخت کارت‌به‌کارت\n\n"
                f"Order ID: {purchase.id}\n"
                f"Amount: {int(purchase.final_amount):,} Toman\n"
                f"Tracking Code: {pay.tracking_code}\n\n"
                f"کارت مقصد:\n{card_line}{owner_txt}\n\n"
                "بعد از واریز، لطفاً رسید را به صورت عکس ارسال کنید (می‌توانید در کپشن کد پیگیری را هم بنویسید)."
            )
            return

        if gw == "nowpayments":
            np_key = await get_setting(db, "nowpayments_api_key") or settings.nowpayments_api_key
            if not np_key or not settings.public_base_url:
                await query.edit_message_text(
                    "NowPayments تنظیم نشده. لطفاً Card-to-Card را انتخاب کنید."
                )
                return
            np = NowPaymentsGateway(api_key=np_key)
            cb = f"{settings.public_base_url.rstrip('/')}/api/payments/webhook/nowpayments"
            res = await np.create_payment(
                amount=float(int(purchase.final_amount)),
                order_id=str(purchase.id),
                callback_url=cb,
                currency="USD",
                description=f"Order {purchase.id}",
            )
            pay = Payment(
                purchase_id=purchase.id,
                gateway=PaymentGateway.NOWPAYMENTS,
                status=PaymentStatus.PROCESSING,
                amount=int(purchase.final_amount),
                currency="IRR",
                gateway_transaction_id=str(res.get("payment_id") or res.get("id") or ""),
                gateway_response=str(res),
            )
            db.add(pay)
            await db.commit()
            await db.refresh(pay)
            url = res.get("invoice_url") or res.get("pay_address") or res.get("payment_url") or ""
            await query.edit_message_text(f"🌐 NowPayments\n\nOrder ID: {purchase.id}\n\n{url}")
            return

        if gw == "aqayepardakht":
            pin = await get_setting(db, "aqayepardakht_pin") or settings.aqayepardakht_api_key
            if not pin or not settings.public_base_url:
                await query.edit_message_text(
                    "Aqayepardakht تنظیم نشده. لطفاً Card-to-Card را انتخاب کنید."
                )
                return
            ag = AqayepardakhtGateway(pin=pin)
            cb = f"{settings.public_base_url.rstrip('/')}/api/payments/webhook/aqayepardakht"
            res = await ag.create_payment(
                amount=int(purchase.final_amount),
                order_id=str(purchase.id),
                callback_url=cb,
                description=f"Order {purchase.id}",
            )
            pay = Payment(
                purchase_id=purchase.id,
                gateway=PaymentGateway.AQAYEPARDAKHT,
                status=PaymentStatus.PROCESSING,
                amount=int(purchase.final_amount),
                currency="IRR",
                gateway_transaction_id=str(
                    res.get("transid") or res.get("transaction_id") or res.get("id") or ""
                ),
                gateway_response=str(res),
            )
            db.add(pay)
            await db.commit()
            await db.refresh(pay)
            url = res.get("payment_url") or res.get("url") or ""
            await query.edit_message_text(f"💎 Aqayepardakht\n\nOrder ID: {purchase.id}\n\n{url}")
            return

        await query.edit_message_text("Unsupported gateway.")


async def gift_code_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle gift code entry."""
    query = update.callback_query
    if not query:
        return
    user = update.effective_user
    if not user:
        return

    async for db in get_db():
        from database.models import User
        from services.state_machine import set_step
        from utils.i18n import get_user_language, t

        db_user = await db.get(User, user.id)
        if not db_user:
            await query.edit_message_text("Please use /start first.")
            return

        lang = get_user_language(db_user)
        await set_step(user.id, step="wallet.entering_gift_code", payload={})
        await query.edit_message_text(t("enter_code_prompt", db_user, lang))
        await query.answer()


async def wallet_topup_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle wallet top-up initiation."""
    query = update.callback_query
    if not query:
        return
    user = update.effective_user
    if not user:
        return

    async for db in get_db():
        from database.models import User
        from utils.i18n import get_user_language, t

        db_user = await db.get(User, user.id)
        if not db_user:
            await query.edit_message_text("Please use /start first.")
            return

        lang = get_user_language(db_user)
        await set_step(user.id, step="wallet.entering_topup_amount", payload={})
        await query.edit_message_text(
            t("wallet_topup_amount_prompt", db_user, lang)
            + "\n\n"
            + t("wallet_balance", db_user, lang)
            + f": {int(db_user.balance):,} Toman"
        )
        await query.answer()


async def cancel_order_callback(
    update: Update, context: ContextTypes.DEFAULT_TYPE, order_id: int
) -> None:
    query = update.callback_query
    if not query:
        return
    user = update.effective_user
    if not user:
        return
    async for db in get_db():
        purchase = await db.get(Purchase, order_id)
        if not purchase or purchase.user_id != user.id:
            await query.edit_message_text("Order not found.")
            return
        if purchase.status != PurchaseStatus.PENDING:
            await query.edit_message_text("این سفارش قابل کنسل نیست.")
            return
        purchase.status = PurchaseStatus.CANCELLED
        if purchase.product_id:
            from config.features import is_enabled

            if is_enabled("inventory"):
                from services.inventory import release_stock

                await release_stock(db, product_id=int(purchase.product_id), qty=1)
        await db.commit()
        await query.edit_message_text("❌ سفارش کنسل شد.")


async def admin_router(update: Update, context: ContextTypes.DEFAULT_TYPE, data: str) -> None:
    """Route admin callbacks - SECURITY: All admin routes check UserRole.ADMIN."""
    from handlers.admin_callbacks import (
        admin_main_callback,
        admin_payment_approve_callback,
        admin_payment_detail_callback,
        admin_payment_reject_callback,
        admin_payments_pending_callback,
        admin_services_callback,
        admin_settings_callback,
        admin_stats_callback,
        admin_users_callback,
    )

    # Main menu
    if data == "admin_main":
        await admin_main_callback(update, context)
    # Payments
    elif data == "admin_payments_pending":
        await admin_payments_pending_callback(update, context)
    elif data.startswith("admin_payments_pending_page_"):
        page = int(data.split("_")[-1])
        await admin_payments_pending_callback(update, context, page=page)
    elif data.startswith("admin_payment_detail_"):
        payment_id = int(data.split("_")[-1])
        await admin_payment_detail_callback(update, context, payment_id)
    elif data.startswith("admin_payment_approve_"):
        payment_id = int(data.split("_")[-1])
        await admin_payment_approve_callback(update, context, payment_id)
    elif data.startswith("admin_payment_reject_"):
        payment_id = int(data.split("_")[-1])
        await admin_payment_reject_callback(update, context, payment_id)
    # Panels
    elif data == "admin_panels":
        from handlers.admin_panels import admin_panels_list_callback

        await admin_panels_list_callback(update, context, page=0)
    elif data.startswith("admin_panels_page_"):
        page = int(data.split("_")[-1])
        from handlers.admin_panels import admin_panels_list_callback

        await admin_panels_list_callback(update, context, page=page)
    elif data.startswith("admin_panel_detail_"):
        panel_id = int(data.split("_")[-1])
        from handlers.admin_panels import admin_panel_detail_callback

        await admin_panel_detail_callback(update, context, panel_id)
    elif data.startswith("admin_panel_test_"):
        panel_id = int(data.split("_")[-1])
        from handlers.admin_panels import admin_panel_test_connection_callback

        await admin_panel_test_connection_callback(update, context, panel_id)
    elif data.startswith("admin_panel_stats_"):
        panel_id = int(data.split("_")[-1])
        from handlers.admin_panels import admin_panel_stats_callback

        await admin_panel_stats_callback(update, context, panel_id)
    elif data == "admin_panel_add":
        from handlers.admin_panels import admin_panel_add_callback

        await admin_panel_add_callback(update, context)
    elif data.startswith("admin_panel_delete_"):
        panel_id = int(data.split("_")[-1])
        from handlers.admin_panels import admin_panel_delete_callback

        await admin_panel_delete_callback(update, context, panel_id)
    # Stats
    elif data == "admin_stats":
        from handlers.admin_stats import admin_stats_callback

        await admin_stats_callback(update, context)
    # Users
    elif data == "admin_users":
        await admin_users_callback(update, context)
    elif data.startswith("admin_users_page_"):
        page = int(data.split("_")[-1])
        await admin_users_callback(update, context, page=page)
    elif data.startswith("admin_user_detail_"):
        user_id = int(data.split("_")[-1])
        from handlers.admin_callbacks_complete import (
            admin_user_detail_callback as admin_user_detail,
        )

        await admin_user_detail(update, context, user_id)
    # Services
    elif data == "admin_services":
        await admin_services_callback(update, context)
    elif data.startswith("admin_services_page_"):
        page = int(data.split("_")[-1])
        await admin_services_callback(update, context, page=page)
    elif data.startswith("admin_service_detail_"):
        service_id = int(data.split("_")[-1])
        from handlers.admin_callbacks_complete import (
            admin_service_detail_callback as admin_service_detail,
        )

        await admin_service_detail(update, context, service_id)
    elif data.startswith("admin_service_sync_"):
        service_id = int(data.split("_")[-1])
        from handlers.admin_callbacks_complete import (
            admin_service_sync_callback as admin_service_sync,
        )

        await admin_service_sync(update, context, service_id)
    elif data.startswith("admin_service_renew_"):
        service_id = int(data.split("_")[-1])
        from handlers.admin_callbacks_complete import (
            admin_service_renew_callback as admin_service_renew,
        )

        await admin_service_renew(update, context, service_id)
    elif data.startswith("admin_service_addgb_"):
        service_id = int(data.split("_")[-1])
        from handlers.admin_callbacks_complete import (
            admin_service_addgb_callback as admin_service_addgb,
        )

        await admin_service_addgb(update, context, service_id)
    elif data.startswith("admin_service_rotate_"):
        service_id = int(data.split("_")[-1])
        from handlers.admin_callbacks_complete import (
            admin_service_rotate_callback as admin_service_rotate,
        )

        await admin_service_rotate(update, context, service_id)
    elif data.startswith("admin_service_remove_"):
        service_id = int(data.split("_")[-1])
        from handlers.admin_callbacks_complete import (
            admin_service_remove_callback as admin_service_remove,
        )

        await admin_service_remove(update, context, service_id)
    # Products
    elif data == "admin_products":
        from handlers.admin_callbacks_complete import admin_products_callback as admin_products

        await admin_products(update, context)
    # Tickets
    elif data == "admin_tickets":
        from handlers.admin_callbacks_complete import admin_tickets_callback as admin_tickets

        await admin_tickets(update, context)
    # Panels
    elif data == "admin_panels":
        from handlers.admin_panels import admin_panels_list_callback

        await admin_panels_list_callback(update, context, page=0)
    elif data.startswith("admin_panels_page_"):
        page = int(data.split("_")[-1])
        from handlers.admin_panels import admin_panels_list_callback

        await admin_panels_list_callback(update, context, page=page)
    elif data.startswith("admin_panel_detail_"):
        panel_id = int(data.split("_")[-1])
        from handlers.admin_panels import admin_panel_detail_callback

        await admin_panel_detail_callback(update, context, panel_id)
    elif data.startswith("admin_panel_test_"):
        panel_id = int(data.split("_")[-1])
        from handlers.admin_panels import admin_panel_test_connection_callback

        await admin_panel_test_connection_callback(update, context, panel_id)
    elif data.startswith("admin_panel_stats_"):
        panel_id = int(data.split("_")[-1])
        from handlers.admin_panels import admin_panel_stats_callback

        await admin_panel_stats_callback(update, context, panel_id)
    elif data == "admin_panel_add":
        from handlers.admin_panels import admin_panel_add_callback

        await admin_panel_add_callback(update, context)
    elif data.startswith("admin_panel_delete_"):
        panel_id = int(data.split("_")[-1])
        from handlers.admin_panels import admin_panel_delete_callback

        await admin_panel_delete_callback(update, context, panel_id)
    # Stats
    elif data == "admin_stats":
        from handlers.admin_stats import admin_stats_callback

        await admin_stats_callback(update, context)
    # Settings
    elif data == "admin_settings":
        await admin_settings_callback(update, context)
    elif data == "admin_set_card":
        from handlers.admin_callbacks_complete import admin_set_card_callback as admin_set_card

        await admin_set_card(update, context)
    elif data == "admin_set_nowpay":
        from handlers.admin_callbacks_complete import admin_set_nowpay_callback as admin_set_nowpay

        await admin_set_nowpay(update, context)
    elif data == "admin_set_aqaye":
        from handlers.admin_callbacks_complete import admin_set_aqaye_callback as admin_set_aqaye

        await admin_set_aqaye(update, context)
    elif data == "admin_set_faq":
        from handlers.admin_callbacks_complete import admin_set_faq_callback as admin_set_faq

        await admin_set_faq(update, context)
    elif data == "admin_set_tutorial":
        from handlers.admin_callbacks_complete import (
            admin_set_tutorial_callback as admin_set_tutorial,
        )

        await admin_set_tutorial(update, context)
    # User management actions
    elif data.startswith("admin_user_balance_"):
        user_id = int(data.split("_")[-1])
        from handlers.admin_users import admin_user_balance_callback

        await admin_user_balance_callback(update, context, user_id)
    elif data.startswith("admin_user_services_"):
        user_id = int(data.split("_")[-1])
        from handlers.admin_users import admin_user_services_callback

        await admin_user_services_callback(update, context, user_id)
    elif data.startswith("admin_user_purchases_"):
        user_id = int(data.split("_")[-1])
        from handlers.admin_users import admin_user_purchases_callback

        await admin_user_purchases_callback(update, context, user_id)
    elif data.startswith("admin_user_ban_"):
        user_id = int(data.split("_")[-1])
        from handlers.admin_users import admin_user_ban_callback

        await admin_user_ban_callback(update, context, user_id)
    # Stats actions
    elif data == "admin_stats_refresh":
        from handlers.admin_stats import admin_stats_callback

        await admin_stats_callback(update, context)
    elif data == "admin_stats_detailed":
        from handlers.admin_stats import admin_stats_detailed_callback

        await admin_stats_detailed_callback(update, context)
    elif data == "admin_health_refresh":
        from handlers.admin_stats import admin_health_callback

        await admin_health_callback(update, context)
    # Broadcast actions
    elif data.startswith("broadcast_confirm:"):
        from handlers.admin_handlers import broadcast_confirm_callback

        await broadcast_confirm_callback(update, context)
    elif data == "broadcast_cancel":
        from handlers.admin_handlers import broadcast_cancel_callback

        await broadcast_cancel_callback(update, context)
    # Coupon actions
    elif data == "admin_coupon_create":
        from handlers.admin_coupons import admin_coupon_create_callback

        await admin_coupon_create_callback(update, context)
    elif data == "admin_coupons_all":
        from handlers.admin_coupons import admin_coupons_all_callback

        await admin_coupons_all_callback(update, context)
    # Panel edit
    elif data.startswith("admin_panel_edit_"):
        panel_id = int(data.split("_")[-1])
        from handlers.admin_panels import admin_panel_edit_callback

        await admin_panel_edit_callback(update, context, panel_id)
    else:
        await update.callback_query.answer("Unknown admin action.", show_alert=True)


def register_callback_handlers(application: Application) -> None:
    """Register all callback handlers."""
    from telegram.ext import CallbackQueryHandler

    application.add_handler(CallbackQueryHandler(callback_handler))
