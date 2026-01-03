"""Keyboard layouts for Telegram bot."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup

from config.features import is_enabled
from database.models import User
from utils.i18n import get_user_language, t


def main_menu_keyboard(user: User | None = None) -> InlineKeyboardMarkup:
    """Main menu inline keyboard with i18n."""
    lang = get_user_language(user)
    keyboard: list[list[InlineKeyboardButton]] = []

    if is_enabled("purchase"):
        keyboard.append(
            [InlineKeyboardButton(t("purchase_service", user, lang), callback_data="purchase")]
        )
    if is_enabled("services"):
        keyboard.append(
            [InlineKeyboardButton(t("my_services", user, lang), callback_data="my_services")]
        )

    row: list[InlineKeyboardButton] = []
    if is_enabled("wallet"):
        row.append(InlineKeyboardButton(t("wallet", user, lang), callback_data="wallet"))
    if is_enabled("affiliate"):
        row.append(InlineKeyboardButton(t("affiliate", user, lang), callback_data="affiliate"))
    if row:
        keyboard.append(row)

    if is_enabled("trial"):
        keyboard.append([InlineKeyboardButton(t("free_trial", user, lang), callback_data="trial")])
    if is_enabled("support"):
        keyboard.append([InlineKeyboardButton(t("support", user, lang), callback_data="support")])
    return InlineKeyboardMarkup(keyboard)


def main_reply_keyboard(user: User | None = None) -> ReplyKeyboardMarkup:
    """Persistent keyboard - only shows Menu button to avoid duplication."""
    lang = get_user_language(user)
    kb: list[list[KeyboardButton]] = []

    # Only add a single "Menu" button to the reply keyboard
    menu_button_text = t("menu", user, lang)
    kb.append([KeyboardButton(menu_button_text)])

    return ReplyKeyboardMarkup(
        kb,
        resize_keyboard=True,
        is_persistent=True,
        input_field_placeholder=t("choose_option", user, lang),
    )


def wallet_menu_keyboard(user: User | None = None) -> InlineKeyboardMarkup:
    """Wallet menu keyboard."""
    lang = get_user_language(user)
    keyboard = [
        [
            InlineKeyboardButton(
                "💰 " + t("wallet_balance", user, lang), callback_data="wallet_balance"
            )
        ],
        [InlineKeyboardButton("➕ " + t("topup_wallet", user, lang), callback_data="wallet_topup")],
        [InlineKeyboardButton("🎁 " + t("gift_code", user, lang), callback_data="gift_code")],
        [InlineKeyboardButton(t("back", user, lang), callback_data="menu")],
    ]
    return InlineKeyboardMarkup(keyboard)


def support_keyboard(user: User | None = None) -> InlineKeyboardMarkup:
    """Create support keyboard with i18n."""
    lang = get_user_language(user)
    keyboard = [
        [
            InlineKeyboardButton(
                "📝 " + t("create_ticket", user, lang), callback_data="create_ticket"
            )
        ],
        [InlineKeyboardButton("📋 " + t("my_tickets", user, lang), callback_data="my_tickets")],
        [InlineKeyboardButton(t("back", user, lang), callback_data="menu")],
    ]
    return InlineKeyboardMarkup(keyboard)


def product_detail_keyboard(product_id: int, user: User | None = None) -> InlineKeyboardMarkup:
    """Product detail keyboard with discount code option."""
    lang = get_user_language(user)
    keyboard = [
        [
            InlineKeyboardButton(
                "✅ " + t("purchase", user, lang), callback_data=f"confirm_purchase_{product_id}"
            )
        ],
        [
            InlineKeyboardButton(
                "🎁 " + t("enter_discount_code", user, lang),
                callback_data=f"discount_enter_{product_id}",
            )
        ],
        [InlineKeyboardButton(t("back", user, lang), callback_data="purchase")],
    ]
    return InlineKeyboardMarkup(keyboard)


def product_detail_keyboard_with_protocol(
    product_id: int,
    protocol: str,
    discount_code: str | None = None,
    user: User | None = None,
) -> InlineKeyboardMarkup:
    """Product detail keyboard with pre-selected protocol.

    This is shown after the user selects a protocol from a multi-protocol product.
    The confirm_purchase callback will include the protocol in its payload.

    Args:
        product_id: The product ID
        protocol: The user-selected protocol (e.g., "vless")
        discount_code: Optional discount code
        user: Database user for i18n

    Returns:
        InlineKeyboardMarkup for purchase confirmation
    """
    lang = get_user_language(user)

    # Build confirm callback data with protocol
    # Format: confirm_purchase_{product_id}_proto_{protocol}[_{discount_code}]
    confirm_data = f"confirm_purchase_{product_id}_proto_{protocol}"
    if discount_code:
        confirm_data += f"_{discount_code}"

    discount_enter_data = f"discount_enter_{product_id}_proto_{protocol}"

    keyboard = [
        [InlineKeyboardButton("✅ " + t("purchase", user, lang), callback_data=confirm_data)],
        [
            InlineKeyboardButton(
                "🎁 " + t("enter_discount_code", user, lang),
                callback_data=discount_enter_data,
            )
        ],
        [InlineKeyboardButton(t("back", user, lang), callback_data=f"product_{product_id}")],
    ]
    return InlineKeyboardMarkup(keyboard)


def purchase_with_discount_keyboard(
    product_id: int, discount_code: str | None = None, user: User | None = None
) -> InlineKeyboardMarkup:
    """Purchase confirmation keyboard with applied discount."""
    lang = get_user_language(user)
    keyboard = [
        [
            InlineKeyboardButton(
                "✅ " + t("proceed_to_payment", user, lang),
                callback_data=f"purchase_pay_{product_id}_{discount_code or ''}",
            )
        ],
        [InlineKeyboardButton(t("back", user, lang), callback_data=f"product_{product_id}")],
    ]
    return InlineKeyboardMarkup(keyboard)


def payment_gateway_keyboard(purchase_id: str, user: User | None = None) -> InlineKeyboardMarkup:
    """Payment gateway selection keyboard."""
    lang = get_user_language(user)
    keyboard: list[list[InlineKeyboardButton]] = []

    from config.settings import settings

    if settings.card_to_card_enabled:
        keyboard.append(
            [
                InlineKeyboardButton(
                    "💳 " + t("card_to_card", user, lang),
                    callback_data=f"payment_card_{purchase_id}",
                )
            ]
        )
    if settings.nowpayments_enabled:
        keyboard.append(
            [
                InlineKeyboardButton(
                    "🌐 " + t("nowpayments", user, lang),
                    callback_data=f"payment_nowpay_{purchase_id}",
                )
            ]
        )
    if settings.aqayepardakht_enabled:
        keyboard.append(
            [
                InlineKeyboardButton(
                    "🏦 " + t("aqayepardakht", user, lang),
                    callback_data=f"payment_aqaye_{purchase_id}",
                )
            ]
        )

    keyboard.append(
        [InlineKeyboardButton(t("cancel", user, lang), callback_data=f"cancel_order_{purchase_id}")]
    )
    return InlineKeyboardMarkup(keyboard)


def products_keyboard(products: list, user: User | None = None) -> InlineKeyboardMarkup:
    """Products list keyboard."""
    lang = get_user_language(user)
    keyboard: list[list[InlineKeyboardButton]] = []
    for product in products:
        name = product.name or f"Product {product.id}"
        price_text = f"{int(product.price):,} Toman" if product.price > 0 else t("free", user, lang)
        button_text = f"{name} | {product.duration_days} days | {price_text}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"product_{product.id}")])
    keyboard.append([InlineKeyboardButton(t("back", user, lang), callback_data="menu")])
    return InlineKeyboardMarkup(keyboard)


def services_list_keyboard(services: list, user: User | None = None) -> InlineKeyboardMarkup:
    """Services list keyboard."""
    lang = get_user_language(user)
    keyboard: list[list[InlineKeyboardButton]] = []
    for svc in services:
        name = svc.name or f"Service {svc.id}"
        status_emoji = "✅" if svc.is_active else "❌"
        button_text = f"{status_emoji} {name}"
        keyboard.append([InlineKeyboardButton(button_text, callback_data=f"service_{svc.id}")])
    keyboard.append([InlineKeyboardButton(t("back", user, lang), callback_data="menu")])
    return InlineKeyboardMarkup(keyboard)


def service_manage_keyboard(service_id: int, user: User | None = None) -> InlineKeyboardMarkup:
    """Service management keyboard."""
    lang = get_user_language(user)
    keyboard = [
        [
            InlineKeyboardButton(
                "📋 " + t("get_config", user, lang), callback_data=f"service_config_{service_id}"
            )
        ],
        [
            InlineKeyboardButton(
                "🔗 " + t("get_subscription", user, lang), callback_data=f"service_sub_{service_id}"
            )
        ],
        [
            InlineKeyboardButton(
                "🔄 " + t("rotate", user, lang), callback_data=f"service_rotate_{service_id}"
            )
        ],
        [InlineKeyboardButton(t("back", user, lang), callback_data="my_services")],
    ]
    return InlineKeyboardMarkup(keyboard)


def confirm_action_keyboard(
    action: str, item_id: int, user: User | None = None
) -> InlineKeyboardMarkup:
    """Confirmation keyboard for actions."""
    lang = get_user_language(user)
    keyboard = [
        [
            InlineKeyboardButton(
                "✅ " + t("confirm", user, lang), callback_data=f"{action}_confirm_{item_id}"
            ),
            InlineKeyboardButton(
                "❌ " + t("cancel", user, lang), callback_data=f"{action}_cancel_{item_id}"
            ),
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def service_products_keyboard(
    service_id: int, products: list, user: User | None = None
) -> InlineKeyboardMarkup:
    """Products keyboard for service upgrade/renewal."""
    lang = get_user_language(user)
    keyboard: list[list[InlineKeyboardButton]] = []
    for product in products:
        name = product.name or f"Product {product.id}"
        price_text = f"{int(product.price):,} Toman" if product.price > 0 else t("free", user, lang)
        button_text = f"{name} | {price_text}"
        keyboard.append(
            [
                InlineKeyboardButton(
                    button_text, callback_data=f"service_product_{service_id}_{product.id}"
                )
            ]
        )
    keyboard.append(
        [InlineKeyboardButton(t("back", user, lang), callback_data=f"service_{service_id}")]
    )
    return InlineKeyboardMarkup(keyboard)


# Protocol emoji mapping for better UX
PROTOCOL_EMOJIS: dict[str, str] = {
    "vless": "⚡",
    "vmess": "🔷",
    "trojan": "🐴",
    "shadowsocks": "🌑",
    "ss": "🌑",
    "hysteria": "🌊",
    "hysteria2": "🌊",
    "reality": "🔐",
    "wireguard": "🔒",
    "wg": "🔒",
}


def get_protocol_display_name(protocol: str) -> str:
    """Get display name for a protocol with emoji.

    Args:
        protocol: Protocol identifier (e.g., "vless", "vmess")

    Returns:
        Display name with emoji (e.g., "⚡ VLESS")
    """
    protocol_lower = protocol.lower().strip()
    emoji = PROTOCOL_EMOJIS.get(protocol_lower, "🔌")
    return f"{emoji} {protocol.upper()}"


def protocol_selection_keyboard(
    product_id: int,
    protocols: list[str],
    user: User | None = None,
    discount_code: str | None = None,
) -> InlineKeyboardMarkup:
    """Protocol selection keyboard for multi-protocol products.

    This keyboard is shown when a product supports multiple VPN protocols,
    allowing the user to choose their preferred protocol before purchase.

    Args:
        product_id: The product ID
        protocols: List of allowed protocols (e.g., ["vless", "vmess", "trojan"])
        user: Database user for i18n
        discount_code: Optional discount code to carry through

    Returns:
        InlineKeyboardMarkup with protocol buttons
    """
    lang = get_user_language(user)
    keyboard: list[list[InlineKeyboardButton]] = []

    for protocol in protocols:
        display_name = get_protocol_display_name(protocol)
        # Callback format: select_protocol_{product_id}_{protocol}[_{discount_code}]
        callback_data = f"select_protocol_{product_id}_{protocol.lower()}"
        if discount_code:
            callback_data += f"_{discount_code}"
        keyboard.append([InlineKeyboardButton(display_name, callback_data=callback_data)])

    # Back button
    keyboard.append(
        [InlineKeyboardButton(t("back", user, lang), callback_data=f"product_{product_id}")]
    )

    return InlineKeyboardMarkup(keyboard)
