"""Internationalization (i18n) utilities for multi-language support."""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from database.models import User


class Language(str, Enum):
    """Supported languages."""

    PERSIAN = "fa"
    ENGLISH = "en"
    BILINGUAL = "bilingual"  # Show both Persian and English


# Translation dictionary (can be extended to JSON/YAML files later)
TRANSLATIONS: dict[str, dict[str, str]] = {
    "fa": {
        "welcome": "🎉 به ربات فروش VPN خوش آمدید!\n\n"
        "این ربات امکان خرید و مدیریت سرویس‌های VPN را فراهم می‌کند.\n\n"
        "📋 ویژگی‌ها:\n"
        "• خرید سرویس VPN با پشتیبانی از پروتکل‌های مختلف\n"
        "• تست رایگان 5 گیگابایت\n"
        "• مدیریت سرویس‌های فعال\n"
        "• سیستم زیرمجموعه‌گیری و دریافت پاداش\n"
        "• پشتیبانی 24/7\n\n"
        "برای شروع از دکمه‌های زیر استفاده کنید:",
        "menu": "📋 منو",
        "choose_option": "یکی از گزینه‌ها را انتخاب کنید:",
        "purchase_service": "🛒 خرید",
        "my_services": "📦 سرویس‌ها",
        "affiliate": "👥 زیرمجموعه",
        "free_trial": "🎁 تست",
        "support": "💬 پشتیبانی",
        "faq": "❓ سوالات متداول",
        "tutorial": "📚 آموزش",
        "back": "🔙 بازگشت",
        "select_language": "🌍 Please select your preferred language:",
        "select_language_desc": "Welcome! To get started, please choose your language.\n\nChoose from the options below:",
        "persian": "فارسی",
        "english": "English",
        "bilingual": "دو زبانه / Bilingual",
        "language_set": "✅ زبان با موفقیت تنظیم شد! / Language set successfully!",
        "create_ticket": "ایجاد تیکت",
        "my_tickets": "تیکت‌های من",
        "card_to_card": "کارت‌به‌کارت",
        "cancel": "لغو",
        "days": "{days} روز",
        "unlimited_time": "بدون تاریخ",
        "traffic_gb": "{gb}GB",
        "unlimited_traffic": "نامحدود",
        "price_toman": "{amount:,} تومان",
        "service": "سرویس",
        "resend_config": "ارسال مجدد کانفیگ",
        "subscription_link": "لینک سابسکریپشن",
        "renew": "تمدید",
        "add_traffic": "خرید حجم",
        "reset_traffic": "ریست ترافیک",
        "rotate": "ریوک/روتیت",
        "revoke_sub": "ریوک سابسکریپشن",
        "confirm": "تایید",
        "no_products_available": "فعلاً پلنی موجود نیست.",
        "products_list": "🛒 پلن‌های خرید:\n\nیکی را انتخاب کنید:",
        "no_services": "سرویسی ندارید. از بخش خرید سرویس اقدام کنید.",
        "services_list": "📦 سرویس‌های شما:\n\nروی سرویس مورد نظر کلیک کنید:",
        "unknown_command": "متوجه نشدم. لطفاً از منو انتخاب کنید:",
        "purchase": "خرید",
        "enter_discount_code": "کد تخفیف",
        "proceed_to_payment": "ادامه به پرداخت",
        "change_discount_code": "تغییر کد تخفیف",
        "discount_applied": "✅ کد تخفیف اعمال شد",
        "discount_error": "❌ خطا در کد تخفیف",
        "enter_code_prompt": "کد تخفیف خود را وارد کنید:",
        "gift_code": "کد هدیه",
        "enter_gift_code": "وارد کردن کد هدیه",
        "wallet_balance": "موجودی کیف پول",
        "topup_wallet": "افزایش موجودی",
        "wallet": "💰 کیف پول",
        "order_created": "سفارش ساخته شد",
        "amount": "مبلغ",
        "discount": "تخفیف",
        "final_amount": "مبلغ نهایی",
        "select_payment_method": "روش پرداخت را انتخاب کنید:",
        "no_description": "توضیحی موجود نیست",
        "purchase_confirmation": "آیا می‌خواهید این محصول را خریداری کنید؟",
        "proceed_to_payment_question": "آیا می‌خواهید ادامه دهید؟",
        "wallet_topup_amount_prompt": "مبلغ افزایش موجودی را وارد کنید (حداقل ۱۰,۰۰۰ تومان):",
        "config_not_available": "برای این سرویس کانفیگ موجود نیست. با پشتیبانی تماس بگیرید.",
        "config": "کانفیگ",
        "qr_config": "QR کانفیگ سرویس",
        "qr_subscription": "QR سابسکریپشن سرویس",
        "subscription_url_not_configured": "برای لینک سابسکریپشن باید PUBLIC_BASE_URL تنظیم شود.",
        "feature_disabled": "این قابلیت فعلاً غیرفعال است.",
        "share_phone_number": "ارسال شماره موبایل",
        "phone_verification_required": "📱 برای ادامه، لطفاً شماره موبایل خود را ارسال کنید (از دکمه زیر).",
        "phone_invalid": "❌ شماره موبایل معتبر نیست. لطفاً دوباره با دکمه ارسال کنید.",
        "phone_verified_ok": "✅ شماره موبایل شما با موفقیت تایید شد.",
        "channel_membership_required": "📢 برای ادامه باید عضو کانال ما باشید.",
        "join_channel": "📢 عضویت در کانال",
        "i_joined_check": "✅ عضو شدم (بررسی)",
        "channel_membership_ok": "✅ عضویت شما تایید شد. می‌توانید ادامه دهید.",
        "channel_membership_still_missing": "❌ هنوز عضویت شما تایید نشده است. لطفاً عضو کانال شوید و دوباره تلاش کنید.",
        "trial_active_exists": "شما یک تست فعال دارید. لطفاً بعد از اتمام، دوباره درخواست دهید.",
        "trial_already_used": "شما قبلاً از تست استفاده کرده‌اید. لطفاً سرویس خریداری کنید.",
        "trial_created": "✅ تست ساخته شد.\n\nمدت: {days} روز\nحجم: {gb}GB\nService ID: {service_id}",
    },
    "en": {
        "welcome": "🎉 Welcome to VPN Seller Bot!\n\n"
        "This bot allows you to purchase and manage VPN services.\n\n"
        "📋 Features:\n"
        "• Buy VPN services with support for various protocols\n"
        "• Free 5GB trial\n"
        "• Manage active services\n"
        "• Referral system with rewards\n"
        "• 24/7 support\n\n"
        "Use the buttons below to get started:",
        "menu": "📋 Menu",
        "choose_option": "Choose an option:",
        "purchase_service": "🛒 Buy",
        "my_services": "📦 Services",
        "affiliate": "👥 Referral",
        "free_trial": "🎁 Trial",
        "support": "💬 Support",
        "faq": "❓ FAQ",
        "tutorial": "📚 Tutorial",
        "back": "🔙 Back",
        "select_language": "🌍 Please select your language:",
        "select_language_desc": "Welcome! To get started, please choose your language.\n\nChoose from the options below:",
        "persian": "Persian",
        "english": "English",
        "bilingual": "Bilingual",
        "language_set": "✅ Language set successfully!",
        "create_ticket": "Create Ticket",
        "my_tickets": "My Tickets",
        "card_to_card": "Card-to-Card",
        "cancel": "Cancel",
        "days": "{days} days",
        "unlimited_time": "Unlimited",
        "traffic_gb": "{gb}GB",
        "unlimited_traffic": "Unlimited",
        "price_toman": "{amount:,} Toman",
        "service": "Service",
        "resend_config": "Resend Config",
        "subscription_link": "Subscription Link",
        "renew": "Renew",
        "add_traffic": "Add Traffic",
        "reset_traffic": "Reset Traffic",
        "rotate": "Rotate",
        "revoke_sub": "Revoke Subscription",
        "confirm": "Confirm",
        "no_products_available": "No products available at the moment.",
        "products_list": "🛒 Available Plans:\n\nPlease choose one:",
        "no_services": "You don't have any active services. Please purchase a service first.",
        "services_list": "📦 Your Services:\n\nClick on a service to manage it:",
        "unknown_command": "I didn't understand. Please select from the menu:",
        "purchase": "Purchase",
        "enter_discount_code": "Enter Discount Code",
        "proceed_to_payment": "Proceed to Payment",
        "change_discount_code": "Change Discount Code",
        "discount_applied": "✅ Discount applied",
        "discount_error": "❌ Discount code error",
        "enter_code_prompt": "Please enter your discount code:",
        "gift_code": "Gift Code",
        "enter_gift_code": "Enter Gift Code",
        "wallet_balance": "Wallet Balance",
        "topup_wallet": "Top Up Wallet",
        "wallet": "💰 Wallet",
        "order_created": "Order Created",
        "amount": "Amount",
        "discount": "Discount",
        "final_amount": "Final Amount",
        "select_payment_method": "Please select payment method:",
        "no_description": "No description available",
        "purchase_confirmation": "Would you like to purchase this product?",
        "proceed_to_payment_question": "Would you like to proceed?",
        "wallet_topup_amount_prompt": "Enter the amount to add to your wallet (minimum 10,000 Toman):",
        "config_not_available": "Configuration not available for this service. Please contact support.",
        "config": "Config",
        "qr_config": "QR Code for Service Config",
        "qr_subscription": "QR Code for Service Subscription",
        "subscription_url_not_configured": "PUBLIC_BASE_URL must be configured for subscription links.",
        "feature_disabled": "This feature is currently disabled.",
        "share_phone_number": "Share phone number",
        "phone_verification_required": "📱 To continue, please share your phone number using the button below.",
        "phone_invalid": "❌ Invalid phone number. Please try again using the button.",
        "phone_verified_ok": "✅ Your phone number has been verified.",
        "channel_membership_required": "📢 To continue, you must join our channel.",
        "join_channel": "📢 Join channel",
        "i_joined_check": "✅ I joined (check)",
        "channel_membership_ok": "✅ Membership verified. You can continue.",
        "channel_membership_still_missing": "❌ Membership not verified yet. Please join and try again.",
        "trial_active_exists": "You already have an active trial. Please wait until it expires.",
        "trial_already_used": "You have already used your trial. Please purchase a service.",
        "trial_created": "✅ Trial created.\n\nDuration: {days} days\nTraffic: {gb}GB\nService ID: {service_id}",
    },
}


def get_user_language(user: User | None) -> Language:
    """Get user's preferred language, defaulting to Persian."""
    if not user or not user.language_code:
        return Language.PERSIAN
    lang = user.language_code.lower()
    if lang in {"fa", "fa-ir", "persian"}:
        return Language.PERSIAN
    if lang in {"en", "en-us", "en-gb", "english"}:
        return Language.ENGLISH
    if lang == "bilingual":
        return Language.BILINGUAL
    return Language.PERSIAN


def t(key: str, user: User | None = None, lang: Language | None = None) -> str:
    """
    Translate a key based on user's language preference.
    For bilingual users, show both languages.
    """
    if lang is None:
        lang = get_user_language(user)

    if lang == Language.BILINGUAL:
        fa_text = TRANSLATIONS["fa"].get(key, key)
        en_text = TRANSLATIONS["en"].get(key, key)
        # For bilingual, show both
        if fa_text == en_text or key not in TRANSLATIONS["fa"]:
            return fa_text
        return f"{fa_text}\n{en_text}"

    lang_key = lang.value
    if lang_key not in TRANSLATIONS:
        lang_key = "fa"
    return TRANSLATIONS[lang_key].get(key, key)


def get_bilingual_text(persian: str, english: str, user: User | None = None) -> str:
    """Get bilingual text based on user preference."""
    lang = get_user_language(user)
    if lang == Language.BILINGUAL:
        return f"{persian}\n{english}"
    if lang == Language.ENGLISH:
        return english
    return persian

