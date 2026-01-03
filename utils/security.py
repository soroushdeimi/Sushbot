"""Security utilities for authentication and validation."""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import Enum
from functools import wraps
from typing import TYPE_CHECKING, Any, ParamSpec, TypeVar

import jwt
from jwt.exceptions import PyJWTError
from loguru import logger
from passlib.context import CryptContext

from config.settings import settings

if TYPE_CHECKING:
    from telegram import Update

P = ParamSpec("P")
R = TypeVar("R")


class Permission(str, Enum):
    """Available admin permissions."""

    MANAGE_USERS = "manage_users"
    MANAGE_SALES = "manage_sales"
    MANAGE_SUPPORT = "manage_support"
    MANAGE_PAYMENTS = "manage_payments"
    MANAGE_PANELS = "manage_panels"
    VIEW_STATS = "view_stats"
    BROADCAST = "broadcast"
    MANAGE_COUPONS = "manage_coupons"


@dataclass(frozen=True, slots=True)
class AdminCheckResult:
    """Result of admin permission check."""

    is_admin: bool
    level: str | None = None
    permissions: set[str] | None = None
    reason: str | None = None
    source: str | None = None  # "env" or "database"


def check_env_admin(user_id: int) -> AdminCheckResult:
    """
    Check if a Telegram user is an admin from .env configuration.

    This is a fast, synchronous check that doesn't require database access.
    Returns AdminCheckResult with is_admin=True if user_id is in settings.admin_ids or super_admin_telegram_id.
    """
    if settings.is_super_admin(user_id):
        return AdminCheckResult(
            is_admin=True,
            level="super_admin",
            permissions=set(p.value for p in Permission),  # Super admin has all permissions
            source="env",
        )

    if settings.is_env_admin(user_id):
        return AdminCheckResult(
            is_admin=True,
            level="admin",
            permissions=set(),  # .env admins get no specific permissions by default
            source="env",
        )

    return AdminCheckResult(is_admin=False, reason="not_in_env_admins", source="env")


async def check_admin_status(user_id: int, *, check_env_first: bool = True) -> AdminCheckResult:
    """
    Check if a Telegram user is an admin.

    First checks .env configuration (fast), then falls back to database lookup.
    Returns AdminCheckResult with is_admin=True if the user has admin privileges.

    Args:
        user_id: Telegram user ID to check
        check_env_first: If True, check .env admins before database (default: True)
    """
    # Fast path: check .env first
    if check_env_first:
        env_result = check_env_admin(user_id)
        if env_result.is_admin:
            return env_result

    # Slow path: check database
    from database.models import Admin, User, UserRole
    from database.session import get_db

    try:
        async for db in get_db():
            user = await db.get(User, user_id)
            if not user:
                return AdminCheckResult(is_admin=False, reason="user_not_found", source="database")

            if user.role != UserRole.ADMIN:
                return AdminCheckResult(is_admin=False, reason="not_admin", source="database")

            # Check if user has an Admin record for level/permissions
            from sqlalchemy import select

            result = await db.execute(select(Admin).where(Admin.user_id == user_id))
            admin_record = result.scalar_one_or_none()

            if admin_record:
                if not admin_record.is_active:
                    return AdminCheckResult(
                        is_admin=False, reason="admin_inactive", source="database"
                    )

                # Parse permissions JSON if present
                perms = set()
                if admin_record.permissions:
                    import json

                    try:
                        perms = set(json.loads(admin_record.permissions))
                    except json.JSONDecodeError:
                        perms = set()

                return AdminCheckResult(
                    is_admin=True,
                    level=admin_record.level.value if admin_record.level else None,
                    permissions=perms,
                    source="database",
                )

            # User has admin role but no Admin record - treat as basic admin
            return AdminCheckResult(
                is_admin=True, level="admin", permissions=set(), source="database"
            )

    except Exception as e:
        logger.error(f"Error checking admin status for user {user_id}: {e}")
        return AdminCheckResult(is_admin=False, reason="database_error", source="database")


def admin_required(
    *,
    level: str | list[str] | None = None,
    permission: Permission | list[Permission] | None = None,
    silent: bool = True,
    message: str = "⛔ Access denied.",
) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """
    Decorator to require admin privileges for a handler.

    Args:
        level: Required admin level(s). If None, any admin level is accepted.
               Options: "super_admin", "admin", "management", "sales", "support"
        permission: Required permission(s). If None, no specific permission required.
        silent: If True, silently ignore unauthorized users. If False, send denial message.
        message: Custom denial message (only used when silent=False).

    Usage:
        @admin_required()  # Any admin
        async def handler(update, context): ...

        @admin_required(level="super_admin")  # Super admin only
        async def handler(update, context): ...

        @admin_required(permission=Permission.MANAGE_SALES)  # With specific permission
        async def handler(update, context): ...

        @admin_required(level=["admin", "super_admin"], silent=False)  # Multiple levels, with denial message
        async def handler(update, context): ...
    """

    def decorator(func: Callable[P, R]) -> Callable[P, R]:
        @wraps(func)
        async def wrapper(*args: P.args, **kwargs: P.kwargs) -> R | None:
            # Extract update from args (first arg for handlers)
            update: Update | None = None
            for arg in args:
                if hasattr(arg, "effective_user"):
                    update = arg
                    break

            if not update:
                logger.warning(f"admin_required: No Update object found in {func.__name__}")
                return None

            user = update.effective_user
            if not user:
                logger.debug(f"admin_required: No effective_user in {func.__name__}")
                return None

            # Check admin status
            result = await check_admin_status(user.id)

            if not result.is_admin:
                logger.debug(
                    f"Admin check failed for user {user.id} in {func.__name__}: {result.reason}"
                )
                if not silent:
                    await _send_denial_message(update, message)
                return None

            # Check level requirement
            if level:
                required_levels = [level] if isinstance(level, str) else level
                if result.level not in required_levels:
                    logger.debug(
                        f"Level check failed for user {user.id}: has {result.level}, needs {required_levels}"
                    )
                    if not silent:
                        await _send_denial_message(update, message)
                    return None

            # Check permission requirement
            if permission:
                required_perms = [permission] if isinstance(permission, Permission) else permission
                user_perms = result.permissions or set()

                # Super admins bypass permission checks
                if result.level != "super_admin":
                    for perm in required_perms:
                        if perm.value not in user_perms:
                            logger.debug(
                                f"Permission check failed for user {user.id}: missing {perm.value}"
                            )
                            if not silent:
                                await _send_denial_message(update, message)
                            return None

            # All checks passed - execute handler
            return await func(*args, **kwargs)

        return wrapper

    return decorator


async def _send_denial_message(update: Update, message: str) -> None:
    """Send denial message to user (handles both messages and callbacks)."""
    try:
        if update.callback_query:
            await update.callback_query.answer(message, show_alert=True)
        elif update.message:
            await update.message.reply_text(message)
    except Exception as e:
        logger.error(f"Failed to send denial message: {e}")


def super_admin_required(silent: bool = True) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Shortcut decorator for super admin only commands."""
    return admin_required(level="super_admin", silent=silent)


def sales_admin_required(silent: bool = True) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Shortcut decorator for sales admins (sales, management, admin, super_admin)."""
    return admin_required(
        level=["super_admin", "admin", "management", "sales"],
        permission=Permission.MANAGE_SALES,
        silent=silent,
    )


def support_admin_required(silent: bool = True) -> Callable[[Callable[P, R]], Callable[P, R]]:
    """Shortcut decorator for support admins (support, management, admin, super_admin)."""
    return admin_required(
        level=["super_admin", "admin", "management", "support"],
        permission=Permission.MANAGE_SUPPORT,
        silent=silent,
    )


# Password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def _normalize_password_for_bcrypt(password: str) -> str:
    """
    bcrypt only considers the first 72 bytes; for longer passwords we pre-hash to keep UX sane
    and security consistent.
    """
    b = password.encode("utf-8")
    if len(b) <= 72:
        return password
    return hashlib.sha256(b).hexdigest()


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    return pwd_context.hash(_normalize_password_for_bcrypt(password))


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a hash."""
    return pwd_context.verify(_normalize_password_for_bcrypt(plain_password), hashed_password)


def generate_token(data: dict[str, Any], expires_delta: timedelta | None = None) -> str:
    """Generate JWT token."""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(UTC) + expires_delta
    else:
        expire = datetime.now(UTC) + timedelta(hours=24)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.jwt_secret, algorithm="HS256")
    return encoded_jwt


def verify_token(token: str) -> dict[str, Any] | None:
    """Verify and decode JWT token."""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        return payload
    except PyJWTError:
        return None


def generate_referral_code(user_id: int) -> str:
    """Generate a unique referral code for user."""
    data = f"{user_id}{secrets.token_urlsafe(16)}"
    return hashlib.sha256(data.encode()).hexdigest()[:12].upper()


def sanitize_phone_number(phone: str) -> str:
    """Sanitize phone number to standard format."""
    # Remove all non-digit characters
    cleaned = "".join(filter(str.isdigit, phone))
    # Add country code if missing
    if cleaned.startswith("0"):
        cleaned = "98" + cleaned[1:]
    elif not cleaned.startswith("98"):
        cleaned = "98" + cleaned
    return cleaned


def validate_phone_number(phone: str) -> bool:
    """Validate Iranian phone number format."""
    sanitized = sanitize_phone_number(phone)
    # Iranian phone numbers: 98XXXXXXXXXX (12 digits)
    return len(sanitized) == 12 and sanitized.startswith("98")


def generate_verification_code() -> str:
    """Generate 6-digit verification code."""
    return secrets.randbelow(900000) + 100000  # 100000-999999


def hash_sensitive_data(data: str) -> str:
    """Hash sensitive data (like card numbers)."""
    return hashlib.sha256(data.encode()).hexdigest()


def generate_tracking_code() -> str:
    """Generate unique tracking code for payments."""
    timestamp = int(datetime.now(UTC).timestamp())
    random_part = secrets.token_urlsafe(8)[:8]
    return f"{timestamp}{random_part}".upper()
