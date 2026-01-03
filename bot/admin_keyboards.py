"""Admin keyboards for better UX."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from database.models import (
    Panel,
    Payment,
    Service,
    ServiceStatus,
    User,
)
from database.models.purchase import PurchaseType


def admin_main_keyboard() -> InlineKeyboardMarkup:
    """Main admin menu keyboard."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 پرداخت‌های در انتظار", callback_data="admin_payments_pending")],
        [InlineKeyboardButton("📊 آمار کلی", callback_data="admin_stats")],
        [InlineKeyboardButton("👥 مدیریت کاربران", callback_data="admin_users")],
        [InlineKeyboardButton("🔧 مدیریت سرویس‌ها", callback_data="admin_services")],
        [InlineKeyboardButton("📦 مدیریت محصولات", callback_data="admin_products")],
        [InlineKeyboardButton("🖥️ مدیریت پنل‌ها", callback_data="admin_panels")],
        [InlineKeyboardButton("🎫 تیکت‌های پشتیبانی", callback_data="admin_tickets")],
        [InlineKeyboardButton("⚙️ تنظیمات", callback_data="admin_settings")],
    ])


def admin_payments_list_keyboard(payments: list[Payment], page: int = 0, per_page: int = 5) -> InlineKeyboardMarkup:
    """List pending payments with approve/reject buttons."""
    keyboard: list[list[InlineKeyboardButton]] = []

    start = page * per_page
    end = start + per_page
    page_payments = payments[start:end]

    for pay in page_payments:
        purchase = pay.purchase
        amount = int(pay.amount) if pay.amount else 0

        # Get user info if available
        if purchase and purchase.purchase_type == PurchaseType.WALLET_TOPUP:
            text = f"💰 TopUp #{pay.id} - {amount:,} تومان"
        else:
            text = f"💳 Payment #{pay.id} - {amount:,} تومان"

        # Truncate if too long
        if len(text) > 40:
            text = text[:37] + "..."

        keyboard.append([
            InlineKeyboardButton(text, callback_data=f"admin_payment_detail_{pay.id}")
        ])
        keyboard.append([
            InlineKeyboardButton("✅ تایید", callback_data=f"admin_payment_approve_{pay.id}"),
            InlineKeyboardButton("❌ رد", callback_data=f"admin_payment_reject_{pay.id}"),
        ])

    # Pagination
    nav_buttons: list[InlineKeyboardButton] = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ قبلی", callback_data=f"admin_payments_pending_page_{page-1}"))
    if end < len(payments):
        nav_buttons.append(InlineKeyboardButton("بعدی ➡️", callback_data=f"admin_payments_pending_page_{page+1}"))
    if nav_buttons:
        keyboard.append(nav_buttons)

    keyboard.append([InlineKeyboardButton("🔙 بازگشت به منوی ادمین", callback_data="admin_main")])
    return InlineKeyboardMarkup(keyboard)


def admin_payment_detail_keyboard(payment_id: int) -> InlineKeyboardMarkup:
    """Payment detail with action buttons."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("✅ تایید پرداخت", callback_data=f"admin_payment_approve_{payment_id}"),
            InlineKeyboardButton("❌ رد پرداخت", callback_data=f"admin_payment_reject_{payment_id}"),
        ],
        [InlineKeyboardButton("🔙 بازگشت به لیست پرداخت‌ها", callback_data="admin_payments_pending")],
    ])


def admin_users_list_keyboard(users: list[User], page: int = 0, per_page: int = 10) -> InlineKeyboardMarkup:
    """List users with management options."""
    keyboard: list[list[InlineKeyboardButton]] = []

    start = page * per_page
    end = start + per_page
    page_users = users[start:end]

    for u in page_users:
        username = u.username or f"User {u.id}"
        balance = int(u.balance) if u.balance else 0
        text = f"👤 {username} (ID: {u.id}) - Balance: {balance:,}"
        keyboard.append([
            InlineKeyboardButton(text, callback_data=f"admin_user_detail_{u.id}")
        ])

    # Pagination
    nav_buttons: list[InlineKeyboardButton] = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ قبلی", callback_data=f"admin_users_page_{page-1}"))
    if end < len(users):
        nav_buttons.append(InlineKeyboardButton("➡️ بعدی", callback_data=f"admin_users_page_{page+1}"))
    if nav_buttons:
        keyboard.append(nav_buttons)

    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_main")])
    return InlineKeyboardMarkup(keyboard)


def admin_user_detail_keyboard(user_id: int) -> InlineKeyboardMarkup:
    """User detail management keyboard."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💰 تغییر موجودی", callback_data=f"admin_user_balance_{user_id}")],
        [InlineKeyboardButton("📋 سرویس‌های کاربر", callback_data=f"admin_user_services_{user_id}")],
        [InlineKeyboardButton("📊 تاریخچه خرید", callback_data=f"admin_user_purchases_{user_id}")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_users")],
    ])


def admin_services_list_keyboard(services: list[Service], page: int = 0, per_page: int = 10) -> InlineKeyboardMarkup:
    """List services with management options."""
    keyboard: list[list[InlineKeyboardButton]] = []

    start = page * per_page
    end = start + per_page
    page_services = services[start:end]

    for svc in page_services:
        status_icon = "✅" if svc.status == ServiceStatus.ACTIVE else "❌"
        text = f"{status_icon} Service #{svc.id} - {svc.protocol.upper()}"
        keyboard.append([
            InlineKeyboardButton(text, callback_data=f"admin_service_detail_{svc.id}")
        ])

    # Pagination
    nav_buttons: list[InlineKeyboardButton] = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ قبلی", callback_data=f"admin_services_page_{page-1}"))
    if end < len(services):
        nav_buttons.append(InlineKeyboardButton("➡️ بعدی", callback_data=f"admin_services_page_{page+1}"))
    if nav_buttons:
        keyboard.append(nav_buttons)

    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_main")])
    return InlineKeyboardMarkup(keyboard)


def admin_service_detail_keyboard(service_id: int) -> InlineKeyboardMarkup:
    """Service detail management keyboard."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔄 Sync", callback_data=f"admin_service_sync_{service_id}"),
            InlineKeyboardButton("⏰ تمدید", callback_data=f"admin_service_renew_{service_id}"),
        ],
        [
            InlineKeyboardButton("📈 افزودن ترافیک", callback_data=f"admin_service_addgb_{service_id}"),
            InlineKeyboardButton("🔐 Rotate", callback_data=f"admin_service_rotate_{service_id}"),
        ],
        [InlineKeyboardButton("❌ حذف سرویس", callback_data=f"admin_service_remove_{service_id}")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_services")],
    ])


def admin_settings_keyboard() -> InlineKeyboardMarkup:
    """Admin settings keyboard."""
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("💳 تنظیم کارت", callback_data="admin_set_card")],
        [InlineKeyboardButton("🌐 تنظیم NowPayments", callback_data="admin_set_nowpay")],
        [InlineKeyboardButton("💎 تنظیم Aqayepardakht", callback_data="admin_set_aqaye")],
        [InlineKeyboardButton("❓ تنظیم FAQ", callback_data="admin_set_faq")],
        [InlineKeyboardButton("📖 تنظیم Tutorial", callback_data="admin_set_tutorial")],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_main")],
    ])


def admin_panels_list_keyboard(panels: list[Panel], page: int = 0, per_page: int = 10) -> InlineKeyboardMarkup:
    """List panels with management options."""
    keyboard: list[list[InlineKeyboardButton]] = []

    start = page * per_page
    end = start + per_page
    page_panels = panels[start:end]

    for panel in page_panels:
        status_icon = "✅" if panel.status.value == "active" else "❌"
        text = f"{status_icon} {panel.name} ({panel.api_url[:30]}...)"
        if len(text) > 40:
            text = text[:37] + "..."
        keyboard.append([
            InlineKeyboardButton(text, callback_data=f"admin_panel_detail_{panel.id}")
        ])

    # Pagination
    nav_buttons: list[InlineKeyboardButton] = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("⬅️ قبلی", callback_data=f"admin_panels_page_{page-1}"))
    if end < len(panels):
        nav_buttons.append(InlineKeyboardButton("➡️ بعدی", callback_data=f"admin_panels_page_{page+1}"))
    if nav_buttons:
        keyboard.append(nav_buttons)

    keyboard.append([InlineKeyboardButton("➕ افزودن پنل", callback_data="admin_panel_add")])
    keyboard.append([InlineKeyboardButton("🔙 بازگشت", callback_data="admin_main")])
    return InlineKeyboardMarkup(keyboard)


def admin_panel_detail_keyboard(panel_id: int) -> InlineKeyboardMarkup:
    """Panel detail management keyboard."""
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🔌 تست اتصال", callback_data=f"admin_panel_test_{panel_id}"),
            InlineKeyboardButton("📊 آمار پنل", callback_data=f"admin_panel_stats_{panel_id}"),
        ],
        [
            InlineKeyboardButton("✏️ ویرایش", callback_data=f"admin_panel_edit_{panel_id}"),
            InlineKeyboardButton("❌ حذف", callback_data=f"admin_panel_delete_{panel_id}"),
        ],
        [InlineKeyboardButton("🔙 بازگشت", callback_data="admin_panels")],
    ])

