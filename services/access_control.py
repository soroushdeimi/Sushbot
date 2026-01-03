"""Access control helpers (phone verification, channel membership, feature gates)."""

from __future__ import annotations

from dataclasses import dataclass

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from config.features import is_enabled
from config.settings import settings
from database.models import User
from utils.i18n import get_user_language, t


@dataclass(frozen=True, slots=True)
class GuardResult:
    ok: bool
    reason: str | None = None


def _channel_url() -> str | None:
    if settings.required_channel_username:
        u = settings.required_channel_username.strip().lstrip("@")
        if u:
            return f"https://t.me/{u}"
    return None


async def ensure_phone_verified(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    db_user: User,
    purpose: str,
) -> GuardResult:
    """Ensure user has verified phone via Telegram contact share."""
    if purpose == "purchase" and not is_enabled("require_phone_for_purchase"):
        return GuardResult(True)
    if purpose == "trial" and not is_enabled("require_phone_for_trial"):
        return GuardResult(True)
    if not is_enabled("phone_verification"):
        return GuardResult(True)
    if db_user.phone_verified:
        return GuardResult(True)

    from bot.keyboards import phone_request_keyboard

    lang = get_user_language(db_user)
    msg = t("phone_verification_required", db_user, lang)
    # Use reply keyboard with request_contact
    if update.callback_query and update.callback_query.message:
        await update.callback_query.message.reply_text(
            msg, reply_markup=phone_request_keyboard(db_user)
        )
    elif update.message:
        await update.message.reply_text(msg, reply_markup=phone_request_keyboard(db_user))
    else:
        # Fallback: best-effort.
        uid = update.effective_user.id if update.effective_user else None
        if uid:
            await context.bot.send_message(
                chat_id=uid, text=msg, reply_markup=phone_request_keyboard(db_user)
            )
    return GuardResult(False, "phone_required")


async def ensure_channel_member(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    db_user: User,
    purpose: str,
) -> GuardResult:
    """Ensure user is member of required channel (if configured)."""
    if purpose == "purchase" and not is_enabled("require_channel_for_purchase"):
        return GuardResult(True)
    if purpose == "trial" and not is_enabled("require_channel_for_trial"):
        return GuardResult(True)
    if not is_enabled("channel_membership"):
        return GuardResult(True)
    if not (settings.required_channel_id or settings.required_channel_username):
        # No channel configured -> allow (misconfig safe)
        return GuardResult(True)

    user_id = db_user.id
    channel = settings.required_channel_id or (
        f"@{settings.required_channel_username.lstrip('@')}"
        if settings.required_channel_username
        else None
    )
    if not channel:
        return GuardResult(True)

    try:
        member = await context.bot.get_chat_member(chat_id=channel, user_id=user_id)
        status = (member.status or "").lower()
        ok = status in {"member", "administrator", "creator"}
    except Exception:
        ok = False

    if ok:
        db_user.channel_member = True
        return GuardResult(True)

    lang = get_user_language(db_user)
    url = _channel_url()
    join_btns: list[list[InlineKeyboardButton]] = []
    if url:
        join_btns.append([InlineKeyboardButton(t("join_channel", db_user, lang), url=url)])
    join_btns.append(
        [
            InlineKeyboardButton(
                t("i_joined_check", db_user, lang), callback_data="check_channel_member"
            )
        ]
    )
    kb = InlineKeyboardMarkup(join_btns)

    msg = t("channel_membership_required", db_user, lang)
    if update.callback_query and update.callback_query.message:
        await update.callback_query.message.reply_text(msg, reply_markup=kb)
    elif update.message:
        await update.message.reply_text(msg, reply_markup=kb)
    else:
        if update.effective_user:
            await context.bot.send_message(
                chat_id=update.effective_user.id, text=msg, reply_markup=kb
            )
    return GuardResult(False, "channel_required")


async def ensure_access(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    *,
    db_user: User,
    purpose: str,
) -> GuardResult:
    """Combined access checks for a purpose: 'purchase' | 'trial'."""
    r = await ensure_channel_member(update, context, db_user=db_user, purpose=purpose)
    if not r.ok:
        return r
    r = await ensure_phone_verified(update, context, db_user=db_user, purpose=purpose)
    return r
