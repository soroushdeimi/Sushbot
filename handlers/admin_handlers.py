"""
Admin command handlers for the Telegram bot.

This module provides enterprise-level admin functionality:
- User Management: ban, unban, add_balance, user_info
- Live Analytics: daily income, active users, bandwidth stats
- Server Health: panel connectivity checks
- Safe Broadcasting: rate-limited message sending
- Discount System: coupon CRUD operations

All handlers are protected by the @admin_required decorator.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from loguru import logger
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import CommandHandler, ContextTypes

from database.models import UserStatus
from database.session import get_db
from services.admin_panel import (
    BroadcastResult,
    adjust_user_balance,
    broadcast_message,
    check_all_panels_health,
    create_coupon,
    delete_coupon,
    format_analytics_message,
    format_coupons_list,
    format_health_report,
    get_live_analytics,
    get_user_profile,
    list_coupons,
    search_users,
    set_user_status,
)
from utils.security import (
    Permission,
    admin_required,
    check_env_admin,
    super_admin_required,
)

if TYPE_CHECKING:
    from telegram.ext import Application


# =============================================================================
# USER MANAGEMENT COMMANDS
# =============================================================================


@admin_required(silent=False, message="⛔ شما دسترسی ادمین ندارید.")
async def ban_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Ban a user by Telegram ID.

    Usage: /ban_user <user_id> [reason]
    Example: /ban_user 123456789 Spamming
    """
    if not update.message or not context.args:
        await update.message.reply_text(
            "❌ استفاده صحیح:\n`/ban_user <user_id> [reason]`",
            parse_mode="Markdown",
        )
        return

    try:
        target_user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ شناسه کاربر باید عدد باشد.")
        return

    reason = " ".join(context.args[1:]) if len(context.args) > 1 else None
    admin_id = update.effective_user.id

    # Prevent banning admins
    if check_env_admin(target_user_id).is_admin:
        await update.message.reply_text("❌ نمی‌توانید ادمین‌ها را مسدود کنید.")
        return

    async for db in get_db():
        success, message = await set_user_status(
            db,
            user_id=target_user_id,
            status=UserStatus.BANNED,
            admin_id=admin_id,
            reason=reason,
        )

        if success:
            await update.message.reply_text(
                f"✅ کاربر `{target_user_id}` مسدود شد.\n📝 دلیل: {reason or 'ذکر نشده'}",
                parse_mode="Markdown",
            )
            logger.info(f"Admin {admin_id} banned user {target_user_id}. Reason: {reason}")
        else:
            await update.message.reply_text(f"❌ خطا: {message}")


@admin_required(silent=False, message="⛔ شما دسترسی ادمین ندارید.")
async def unban_user_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Unban a user by Telegram ID.

    Usage: /unban_user <user_id>
    Example: /unban_user 123456789
    """
    if not update.message or not context.args:
        await update.message.reply_text(
            "❌ استفاده صحیح:\n`/unban_user <user_id>`",
            parse_mode="Markdown",
        )
        return

    try:
        target_user_id = int(context.args[0])
    except ValueError:
        await update.message.reply_text("❌ شناسه کاربر باید عدد باشد.")
        return

    admin_id = update.effective_user.id

    async for db in get_db():
        success, message = await set_user_status(
            db,
            user_id=target_user_id,
            status=UserStatus.ACTIVE,
            admin_id=admin_id,
            reason="Unbanned by admin",
        )

        if success:
            await update.message.reply_text(
                f"✅ کاربر `{target_user_id}` از حالت مسدود خارج شد.",
                parse_mode="Markdown",
            )
            logger.info(f"Admin {admin_id} unbanned user {target_user_id}")
        else:
            await update.message.reply_text(f"❌ خطا: {message}")


@admin_required(silent=False, message="⛔ شما دسترسی ادمین ندارید.")
async def add_balance_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Add or deduct balance from a user's wallet.

    Usage: /add_balance <user_id> <amount> [reason]
    Example: /add_balance 123456789 50000 Gift
    Example: /add_balance 123456789 -10000 Refund deduction
    """
    if not update.message or len(context.args) < 2:
        await update.message.reply_text(
            "❌ استفاده صحیح:\n"
            "`/add_balance <user_id> <amount> [reason]`\n\n"
            "مثال: `/add_balance 123456789 50000 هدیه`",
            parse_mode="Markdown",
        )
        return

    try:
        target_user_id = int(context.args[0])
        amount = float(context.args[1])
    except ValueError:
        await update.message.reply_text("❌ شناسه کاربر و مبلغ باید عدد باشند.")
        return

    reason = " ".join(context.args[2:]) if len(context.args) > 2 else None
    admin_id = update.effective_user.id

    async for db in get_db():
        success, message = await adjust_user_balance(
            db,
            user_id=target_user_id,
            amount=amount,
            admin_id=admin_id,
            reason=reason,
        )

        action = "افزایش" if amount >= 0 else "کاهش"
        if success:
            await update.message.reply_text(
                f"✅ موجودی کاربر `{target_user_id}` {action} یافت.\n"
                f"💰 مبلغ: {abs(amount):,.0f} تومان\n"
                f"📊 {message}",
                parse_mode="Markdown",
            )
            logger.info(f"Admin {admin_id} adjusted balance for user {target_user_id}: {amount}")
        else:
            await update.message.reply_text(f"❌ خطا: {message}")


@admin_required(silent=False, message="⛔ شما دسترسی ادمین ندارید.")
async def user_info_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Get detailed information about a user.

    Usage: /user_info <user_id_or_username>
    Example: /user_info 123456789
    Example: /user_info @username
    """
    if not update.message or not context.args:
        await update.message.reply_text(
            "❌ استفاده صحیح:\n`/user_info <user_id_or_username>`",
            parse_mode="Markdown",
        )
        return

    query = context.args[0].lstrip("@")

    async for db in get_db():
        # Try to get user by ID or search
        profile = None

        if query.isdigit():
            profile = await get_user_profile(db, int(query))
        else:
            # Search by username
            users = await search_users(db, query, limit=1)
            if users:
                profile = await get_user_profile(db, users[0].id)

        if not profile:
            await update.message.reply_text(f"❌ کاربر '{query}' یافت نشد.")
            return

        # Format user info
        status_emoji = {
            "active": "✅",
            "banned": "🚫",
            "suspended": "⏸️",
        }.get(profile.status, "❓")

        role_emoji = {
            "admin": "👑",
            "reseller": "💼",
            "user": "👤",
        }.get(profile.role, "👤")

        text = (
            f"👤 **اطلاعات کاربر**\n\n"
            f"🆔 شناسه: `{profile.id}`\n"
            f"👤 نام کاربری: @{profile.username or 'ندارد'}\n"
            f"📛 نام: {profile.first_name or ''} {profile.last_name or ''}\n"
            f"{role_emoji} نقش: {profile.role}\n"
            f"{status_emoji} وضعیت: {profile.status}\n"
            f"💰 موجودی: {int(profile.balance):,} تومان\n"
            f"📱 تلفن: {profile.phone or 'ثبت نشده'}\n"
            f"✅ تایید تلفن: {'بله' if profile.phone_verified else 'خیر'}\n"
            f"📅 تاریخ عضویت: {profile.created_at.strftime('%Y-%m-%d')}\n\n"
            f"📊 **آمار**\n"
            f"🔧 تعداد سرویس‌ها: {profile.services_count}\n"
            f"🛒 تعداد خریدها: {profile.purchases_count}\n"
            f"💵 کل خرید: {int(profile.total_spent):,} تومان"
        )

        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "💰 افزایش موجودی", callback_data=f"admin_user_balance_{profile.id}"
                    ),
                    InlineKeyboardButton(
                        "🚫 مسدود کردن", callback_data=f"admin_user_ban_{profile.id}"
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "🔧 سرویس‌ها", callback_data=f"admin_user_services_{profile.id}"
                    ),
                    InlineKeyboardButton(
                        "📜 تاریخچه", callback_data=f"admin_user_purchases_{profile.id}"
                    ),
                ],
            ]
        )

        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)


# =============================================================================
# ANALYTICS COMMANDS
# =============================================================================


@admin_required(silent=False, message="⛔ شما دسترسی ادمین ندارید.")
async def live_stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Show live analytics dashboard.

    Usage: /stats or /live_stats
    """
    if not update.message:
        return

    # Send loading message
    loading_msg = await update.message.reply_text("⏳ در حال بارگذاری آمار...")

    async for db in get_db():
        analytics = await get_live_analytics(db)
        text = format_analytics_message(analytics, lang="fa")

        keyboard = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("🔄 بروزرسانی", callback_data="admin_stats_refresh")],
                [InlineKeyboardButton("📈 آمار تفصیلی", callback_data="admin_stats_detailed")],
            ]
        )

        await loading_msg.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)


# =============================================================================
# SERVER HEALTH COMMANDS
# =============================================================================


@admin_required(silent=False, message="⛔ شما دسترسی ادمین ندارید.")
async def server_health_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Check health status of all configured panels.

    Usage: /health or /server_health
    """
    if not update.message:
        return

    loading_msg = await update.message.reply_text("⏳ در حال بررسی وضعیت سرورها...")

    async for db in get_db():
        health_results = await check_all_panels_health(db)
        text = format_health_report(health_results, lang="fa")

        keyboard = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("🔄 بررسی مجدد", callback_data="admin_health_refresh")],
            ]
        )

        await loading_msg.edit_text(text, parse_mode="Markdown", reply_markup=keyboard)


# =============================================================================
# BROADCASTING COMMANDS
# =============================================================================


@super_admin_required(silent=False)
async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Broadcast a message to all users (super admin only).

    Usage: /broadcast <message>
    Example: /broadcast 🎉 New feature available!

    This command uses safe rate limiting to avoid Telegram flood limits.
    """
    if not update.message or not context.args:
        await update.message.reply_text(
            "❌ استفاده صحیح:\n`/broadcast <message>`\n\n⚠️ این پیام به همه کاربران ارسال می‌شود.",
            parse_mode="Markdown",
        )
        return

    message_text = " ".join(context.args)
    admin_id = update.effective_user.id

    # Confirmation prompt
    keyboard = InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "✅ تایید و ارسال", callback_data=f"broadcast_confirm:{message_text[:50]}"
                ),
                InlineKeyboardButton("❌ لغو", callback_data="broadcast_cancel"),
            ],
        ]
    )

    await update.message.reply_text(
        f"📢 **پیش‌نمایش پیام:**\n\n{message_text}\n\n"
        "آیا می‌خواهید این پیام را به همه کاربران ارسال کنید؟",
        parse_mode="Markdown",
        reply_markup=keyboard,
    )

    # Store message in context for callback
    context.user_data["broadcast_message"] = message_text
    logger.info(f"Admin {admin_id} initiated broadcast: {message_text[:100]}...")


@super_admin_required()
async def execute_broadcast(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    message_text: str,
) -> None:
    """Execute the broadcast after confirmation."""
    if not update.callback_query:
        return

    query = update.callback_query
    await query.answer()

    progress_msg = await query.edit_message_text("📤 در حال ارسال پیام...\n⏳ لطفاً صبر کنید.")

    async for db in get_db():
        result: BroadcastResult = await broadcast_message(
            bot=context.bot,
            db=db,
            message_text=message_text,
            exclude_banned=True,
            delay_between_messages=0.05,  # 50ms = 20 msg/sec
            batch_size=25,
            batch_delay=1.0,
        )

        await progress_msg.edit_text(
            f"✅ **ارسال پیام تکمیل شد**\n\n"
            f"📊 **آمار:**\n"
            f"├ کل کاربران: {result.total_users:,}\n"
            f"├ ارسال موفق: {result.sent_count:,}\n"
            f"├ ناموفق: {result.failed_count:,}\n"
            f"├ رد شده: {result.skipped_count:,}\n"
            f"└ زمان: {result.duration_seconds:.1f} ثانیه",
            parse_mode="Markdown",
        )

        logger.info(
            f"Broadcast completed: {result.sent_count}/{result.total_users} sent, "
            f"{result.failed_count} failed, {result.skipped_count} skipped"
        )


# =============================================================================
# DISCOUNT/COUPON COMMANDS
# =============================================================================


@admin_required(permission=Permission.MANAGE_COUPONS, silent=False)
async def create_coupon_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Create a new discount coupon.

    Usage: /create_coupon <code> <type> <value> [max_uses]
    Types: percentage, fixed

    Examples:
        /create_coupon SALE20 percentage 20 100
        /create_coupon GIFT5000 fixed 5000
    """
    if not update.message or len(context.args) < 3:
        await update.message.reply_text(
            "❌ استفاده صحیح:\n"
            "`/create_coupon <code> <type> <value> [max_uses]`\n\n"
            "**انواع تخفیف:**\n"
            "• `percentage` - درصدی (0-100)\n"
            "• `fixed` - مبلغ ثابت (تومان)\n\n"
            "**مثال:**\n"
            "`/create_coupon SALE20 percentage 20 100`\n"
            "`/create_coupon GIFT5000 fixed 5000`",
            parse_mode="Markdown",
        )
        return

    code = context.args[0].upper()
    discount_type = context.args[1].lower()
    try:
        value = float(context.args[2])
        max_uses = int(context.args[3]) if len(context.args) > 3 else None
    except ValueError:
        await update.message.reply_text("❌ مقادیر عددی نامعتبر هستند.")
        return

    if discount_type not in ("percentage", "fixed"):
        await update.message.reply_text("❌ نوع تخفیف باید `percentage` یا `fixed` باشد.")
        return

    admin_id = update.effective_user.id

    async for db in get_db():
        success, message, coupon = await create_coupon(
            db,
            code=code,
            discount_type=discount_type,
            discount_value=value,
            max_uses=max_uses,
            admin_id=admin_id,
        )

        if success:
            value_str = (
                f"{int(value)}%" if discount_type == "percentage" else f"{int(value):,} تومان"
            )
            max_str = f"{max_uses} بار" if max_uses else "نامحدود"

            await update.message.reply_text(
                f"✅ **کد تخفیف ایجاد شد**\n\n"
                f"🎫 کد: `{code}`\n"
                f"💰 مقدار: {value_str}\n"
                f"🔢 حداکثر استفاده: {max_str}",
                parse_mode="Markdown",
            )
            logger.info(f"Admin {admin_id} created coupon {code}")
        else:
            await update.message.reply_text(f"❌ خطا: {message}")


@admin_required(permission=Permission.MANAGE_COUPONS, silent=False)
async def delete_coupon_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Delete a discount coupon.

    Usage: /delete_coupon <code>
    Example: /delete_coupon SALE20
    """
    if not update.message or not context.args:
        await update.message.reply_text(
            "❌ استفاده صحیح:\n`/delete_coupon <code>`",
            parse_mode="Markdown",
        )
        return

    code = context.args[0].upper()
    admin_id = update.effective_user.id

    async for db in get_db():
        success, message = await delete_coupon(db, code=code, admin_id=admin_id)

        if success:
            await update.message.reply_text(f"✅ کد تخفیف `{code}` حذف شد.", parse_mode="Markdown")
            logger.info(f"Admin {admin_id} deleted coupon {code}")
        else:
            await update.message.reply_text(f"❌ خطا: {message}")


@admin_required(permission=Permission.MANAGE_COUPONS, silent=False)
async def list_coupons_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    List all active discount coupons.

    Usage: /coupons or /list_coupons
    """
    if not update.message:
        return

    async for db in get_db():
        coupons = await list_coupons(db, include_inactive=False, include_expired=False)
        text = format_coupons_list(coupons, lang="fa")

        keyboard = InlineKeyboardMarkup(
            [
                [InlineKeyboardButton("➕ کد جدید", callback_data="admin_coupon_create")],
                [
                    InlineKeyboardButton(
                        "📋 همه کدها (شامل غیرفعال)", callback_data="admin_coupons_all"
                    )
                ],
            ]
        )

        await update.message.reply_text(text, parse_mode="Markdown", reply_markup=keyboard)


# =============================================================================
# SEARCH COMMAND
# =============================================================================


@admin_required(silent=False, message="⛔ شما دسترسی ادمین ندارید.")
async def search_users_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Search for users by ID, username, or phone.

    Usage: /search <query>
    Examples:
        /search 123456789
        /search @username
        /search 09123456789
    """
    if not update.message or not context.args:
        await update.message.reply_text(
            "❌ استفاده صحیح:\n`/search <query>`",
            parse_mode="Markdown",
        )
        return

    query = " ".join(context.args)

    async for db in get_db():
        users = await search_users(db, query, limit=10)

        if not users:
            await update.message.reply_text(f"❌ کاربری با جستجوی '{query}' یافت نشد.")
            return

        text = f"🔍 **نتایج جستجو برای:** `{query}`\n\n"
        keyboard_buttons = []

        for user in users[:10]:
            username = user.username or f"User {user.id}"
            balance = int(user.balance or 0)
            text += f"• `{user.id}` - @{username} ({balance:,} تومان)\n"
            keyboard_buttons.append(
                [
                    InlineKeyboardButton(
                        f"👤 {username}", callback_data=f"admin_user_detail_{user.id}"
                    )
                ]
            )

        await update.message.reply_text(
            text,
            parse_mode="Markdown",
            reply_markup=InlineKeyboardMarkup(keyboard_buttons),
        )


# =============================================================================
# BROADCAST CALLBACK HANDLERS
# =============================================================================


async def broadcast_confirm_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle broadcast confirmation from inline button."""
    query = update.callback_query
    if not query:
        return

    # Get the stored message from context
    message_text = context.user_data.get("broadcast_message")
    if not message_text:
        await query.answer("پیام منقضی شده. لطفاً دوباره امتحان کنید.", show_alert=True)
        return

    await execute_broadcast(update, context, message_text)


async def broadcast_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle broadcast cancellation."""
    query = update.callback_query
    if not query:
        return

    await query.answer("ارسال لغو شد.", show_alert=True)
    await query.edit_message_text("❌ ارسال پیام لغو شد.")

    # Clear stored message
    if "broadcast_message" in context.user_data:
        del context.user_data["broadcast_message"]


# =============================================================================
# HANDLER REGISTRATION
# =============================================================================


def register_admin_handlers(application: Application) -> None:
    """Register all admin command handlers."""
    # User Management
    application.add_handler(CommandHandler("ban_user", ban_user_command))
    application.add_handler(CommandHandler("unban_user", unban_user_command))
    application.add_handler(CommandHandler("add_balance", add_balance_command))
    application.add_handler(CommandHandler("user_info", user_info_command))
    application.add_handler(CommandHandler("search", search_users_command))

    # Analytics
    application.add_handler(CommandHandler("live_stats", live_stats_command))
    application.add_handler(CommandHandler("stats", live_stats_command))  # Alias

    # Server Health
    application.add_handler(CommandHandler("health", server_health_command))
    application.add_handler(CommandHandler("server_health", server_health_command))  # Alias

    # Broadcasting
    application.add_handler(CommandHandler("broadcast", broadcast_command))

    # Coupons
    application.add_handler(CommandHandler("create_coupon", create_coupon_command))
    application.add_handler(CommandHandler("delete_coupon", delete_coupon_command))
    application.add_handler(CommandHandler("coupons", list_coupons_command))
    application.add_handler(CommandHandler("list_coupons", list_coupons_command))  # Alias

    logger.info("Admin command handlers registered")
