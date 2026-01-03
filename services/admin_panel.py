"""
Admin panel service with advanced features.

Provides:
- Live Analytics (daily/monthly income, active users, bandwidth usage)
- User Management (search, view profile, balance operations, ban/unban)
- Server Health (panel connectivity, node status)
- Broadcasting (safe async messaging with rate limiting)
- Coupon System (create/delete discount codes)
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from loguru import logger
from sqlalchemy import and_, func, or_, select

from database.models import (
    DiscountCode,
    Panel,
    PanelStatus,
    Payment,
    PaymentStatus,
    Purchase,
    PurchaseStatus,
    Service,
    ServiceStatus,
    User,
    UserRole,
    UserStatus,
)

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession
    from telegram import Bot


# =============================================================================
# DATA CLASSES
# =============================================================================


@dataclass(frozen=True, slots=True)
class AnalyticsSnapshot:
    """Point-in-time analytics data."""

    total_users: int
    active_users_today: int
    active_users_month: int
    new_users_today: int
    new_users_month: int

    total_revenue: float
    revenue_today: float
    revenue_week: float
    revenue_month: float

    active_services: int
    expired_services: int
    pending_payments: int

    total_wallet_balance: float
    total_bandwidth_gb: float

    timestamp: datetime


@dataclass(frozen=True, slots=True)
class UserProfile:
    """User profile details for admin view."""

    id: int
    username: str | None
    first_name: str | None
    last_name: str | None
    role: str
    status: str
    balance: float
    phone: str | None
    phone_verified: bool
    created_at: datetime
    services_count: int
    purchases_count: int
    total_spent: float


@dataclass(frozen=True, slots=True)
class PanelHealth:
    """Panel health check result."""

    panel_id: int
    panel_name: str
    api_url: str
    is_online: bool
    response_time_ms: float | None
    users_count: int | None
    online_users: int | None
    error: str | None


@dataclass(frozen=True, slots=True)
class BroadcastResult:
    """Result of broadcast operation."""

    total_users: int
    sent_count: int
    failed_count: int
    skipped_count: int
    duration_seconds: float


@dataclass(frozen=True, slots=True)
class CouponInfo:
    """Discount coupon information."""

    id: int
    code: str
    discount_type: str
    discount_value: float
    max_uses: int | None
    current_uses: int
    valid_from: datetime | None
    valid_until: datetime | None
    is_active: bool
    created_at: datetime


# =============================================================================
# ANALYTICS SERVICE
# =============================================================================


async def get_live_analytics(db: AsyncSession) -> AnalyticsSnapshot:
    """
    Get comprehensive live analytics for the admin dashboard.

    Returns real-time statistics about users, revenue, services, and bandwidth.
    """
    now = datetime.now(UTC)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = today_start - timedelta(days=now.weekday())
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)

    # User statistics
    total_users = await db.scalar(select(func.count(User.id))) or 0

    active_users_today = (
        await db.scalar(select(func.count(User.id)).where(User.updated_at >= today_start)) or 0
    )

    active_users_month = (
        await db.scalar(select(func.count(User.id)).where(User.updated_at >= month_start)) or 0
    )

    new_users_today = (
        await db.scalar(select(func.count(User.id)).where(User.created_at >= today_start)) or 0
    )

    new_users_month = (
        await db.scalar(select(func.count(User.id)).where(User.created_at >= month_start)) or 0
    )

    # Revenue statistics
    total_revenue = (
        await db.scalar(
            select(func.sum(Purchase.final_amount)).where(
                Purchase.status == PurchaseStatus.COMPLETED
            )
        )
        or 0.0
    )

    revenue_today = (
        await db.scalar(
            select(func.sum(Purchase.final_amount)).where(
                and_(
                    Purchase.status == PurchaseStatus.COMPLETED,
                    Purchase.created_at >= today_start,
                )
            )
        )
        or 0.0
    )

    revenue_week = (
        await db.scalar(
            select(func.sum(Purchase.final_amount)).where(
                and_(
                    Purchase.status == PurchaseStatus.COMPLETED,
                    Purchase.created_at >= week_start,
                )
            )
        )
        or 0.0
    )

    revenue_month = (
        await db.scalar(
            select(func.sum(Purchase.final_amount)).where(
                and_(
                    Purchase.status == PurchaseStatus.COMPLETED,
                    Purchase.created_at >= month_start,
                )
            )
        )
        or 0.0
    )

    # Service statistics
    active_services = (
        await db.scalar(
            select(func.count(Service.id)).where(Service.status == ServiceStatus.ACTIVE)
        )
        or 0
    )

    expired_services = (
        await db.scalar(
            select(func.count(Service.id)).where(Service.status == ServiceStatus.EXPIRED)
        )
        or 0
    )

    # Pending payments
    pending_payments = (
        await db.scalar(
            select(func.count(Payment.id)).where(Payment.status == PaymentStatus.PENDING)
        )
        or 0
    )

    # Wallet balance
    total_wallet_balance = await db.scalar(select(func.sum(User.balance))) or 0.0

    # Bandwidth usage (from services - already in GB)
    total_bandwidth_gb = (
        await db.scalar(
            select(func.sum(Service.used_traffic_gb)).where(Service.used_traffic_gb.isnot(None))
        )
        or 0.0
    )

    return AnalyticsSnapshot(
        total_users=total_users,
        active_users_today=active_users_today,
        active_users_month=active_users_month,
        new_users_today=new_users_today,
        new_users_month=new_users_month,
        total_revenue=float(total_revenue),
        revenue_today=float(revenue_today),
        revenue_week=float(revenue_week),
        revenue_month=float(revenue_month),
        active_services=active_services,
        expired_services=expired_services,
        pending_payments=pending_payments,
        total_wallet_balance=float(total_wallet_balance),
        total_bandwidth_gb=float(total_bandwidth_gb),
        timestamp=now,
    )


def format_analytics_message(analytics: AnalyticsSnapshot, lang: str = "fa") -> str:
    """Format analytics data as a Telegram message."""
    if lang == "fa":
        return (
            "📊 **آمار زنده**\n"
            f"🕐 آخرین بروزرسانی: {analytics.timestamp.strftime('%H:%M:%S')}\n\n"
            "👥 **کاربران**\n"
            f"├ کل: {analytics.total_users:,}\n"
            f"├ فعال امروز: {analytics.active_users_today:,}\n"
            f"├ فعال این ماه: {analytics.active_users_month:,}\n"
            f"├ جدید امروز: {analytics.new_users_today:,}\n"
            f"└ جدید این ماه: {analytics.new_users_month:,}\n\n"
            "💰 **درآمد**\n"
            f"├ کل: {int(analytics.total_revenue):,} تومان\n"
            f"├ امروز: {int(analytics.revenue_today):,} تومان\n"
            f"├ این هفته: {int(analytics.revenue_week):,} تومان\n"
            f"└ این ماه: {int(analytics.revenue_month):,} تومان\n\n"
            "🔧 **سرویس‌ها**\n"
            f"├ فعال: {analytics.active_services:,}\n"
            f"└ منقضی شده: {analytics.expired_services:,}\n\n"
            "📦 **سایر**\n"
            f"├ پرداخت‌های معلق: {analytics.pending_payments:,}\n"
            f"├ موجودی کیف پول‌ها: {int(analytics.total_wallet_balance):,} تومان\n"
            f"└ مصرف ترافیک: {analytics.total_bandwidth_gb:.2f} GB"
        )
    else:
        return (
            "📊 **Live Analytics**\n"
            f"🕐 Updated: {analytics.timestamp.strftime('%H:%M:%S')}\n\n"
            "👥 **Users**\n"
            f"├ Total: {analytics.total_users:,}\n"
            f"├ Active Today: {analytics.active_users_today:,}\n"
            f"├ Active This Month: {analytics.active_users_month:,}\n"
            f"├ New Today: {analytics.new_users_today:,}\n"
            f"└ New This Month: {analytics.new_users_month:,}\n\n"
            "💰 **Revenue**\n"
            f"├ Total: {int(analytics.total_revenue):,} Toman\n"
            f"├ Today: {int(analytics.revenue_today):,} Toman\n"
            f"├ This Week: {int(analytics.revenue_week):,} Toman\n"
            f"└ This Month: {int(analytics.revenue_month):,} Toman\n\n"
            "🔧 **Services**\n"
            f"├ Active: {analytics.active_services:,}\n"
            f"└ Expired: {analytics.expired_services:,}\n\n"
            "📦 **Other**\n"
            f"├ Pending Payments: {analytics.pending_payments:,}\n"
            f"├ Total Wallet Balance: {int(analytics.total_wallet_balance):,} Toman\n"
            f"└ Bandwidth Used: {analytics.total_bandwidth_gb:.2f} GB"
        )


# =============================================================================
# USER MANAGEMENT
# =============================================================================


async def search_users(
    db: AsyncSession,
    query: str,
    limit: int = 20,
) -> list[User]:
    """
    Search users by ID, username, or phone.

    Args:
        db: Database session
        query: Search term (user ID, username fragment, or phone)
        limit: Maximum results to return

    Returns:
        List of matching users
    """
    # Check if query is a numeric ID
    search_conditions = []

    if query.isdigit():
        search_conditions.append(User.id == int(query))

    # Search by username (case-insensitive)
    search_conditions.append(User.username.ilike(f"%{query}%"))

    # Search by phone number
    search_conditions.append(User.phone_number.ilike(f"%{query}%"))

    # Search by first/last name
    search_conditions.append(User.first_name.ilike(f"%{query}%"))
    search_conditions.append(User.last_name.ilike(f"%{query}%"))

    result = await db.execute(
        select(User).where(or_(*search_conditions)).order_by(User.created_at.desc()).limit(limit)
    )
    return list(result.scalars().all())


async def get_user_profile(db: AsyncSession, user_id: int) -> UserProfile | None:
    """
    Get detailed user profile for admin view.

    Args:
        db: Database session
        user_id: Telegram user ID

    Returns:
        UserProfile if found, None otherwise
    """
    user = await db.get(User, user_id)
    if not user:
        return None

    # Count services
    services_count = (
        await db.scalar(select(func.count(Service.id)).where(Service.user_id == user_id)) or 0
    )

    # Count purchases
    purchases_count = (
        await db.scalar(select(func.count(Purchase.id)).where(Purchase.user_id == user_id)) or 0
    )

    # Total spent
    total_spent = (
        await db.scalar(
            select(func.sum(Purchase.final_amount)).where(
                and_(
                    Purchase.user_id == user_id,
                    Purchase.status == PurchaseStatus.COMPLETED,
                )
            )
        )
        or 0.0
    )

    return UserProfile(
        id=user.id,
        username=user.username,
        first_name=user.first_name,
        last_name=user.last_name,
        role=user.role.value if user.role else "user",
        status=user.status.value if user.status else "active",
        balance=float(user.balance or 0),
        phone=user.phone,
        phone_verified=user.phone_verified or False,
        created_at=user.created_at,
        services_count=services_count,
        purchases_count=purchases_count,
        total_spent=float(total_spent),
    )


async def adjust_user_balance(
    db: AsyncSession,
    user_id: int,
    amount: float,
    admin_id: int,
    reason: str | None = None,
) -> tuple[bool, str]:
    """
    Add or deduct balance from user's wallet.

    Args:
        db: Database session
        user_id: Target user's Telegram ID
        amount: Amount to add (positive) or deduct (negative)
        admin_id: Admin performing the action
        reason: Optional reason for audit

    Returns:
        Tuple of (success, message)
    """
    user = await db.get(User, user_id)
    if not user:
        return False, "User not found"

    old_balance = float(user.balance or 0)
    new_balance = old_balance + amount

    if new_balance < 0:
        return False, f"Insufficient balance. Current: {old_balance:,.0f}"

    user.balance = new_balance
    await db.commit()

    action = "added" if amount >= 0 else "deducted"
    logger.info(
        f"Admin {admin_id} {action} {abs(amount):,.0f} to user {user_id}. "
        f"Old: {old_balance:,.0f}, New: {new_balance:,.0f}. Reason: {reason}"
    )

    return True, f"Balance updated. Old: {old_balance:,.0f}, New: {new_balance:,.0f}"


async def set_user_status(
    db: AsyncSession,
    user_id: int,
    status: UserStatus,
    admin_id: int,
    reason: str | None = None,
) -> tuple[bool, str]:
    """
    Ban/unban/suspend a user.

    Args:
        db: Database session
        user_id: Target user's Telegram ID
        status: New status (ACTIVE, BANNED, SUSPENDED)
        admin_id: Admin performing the action
        reason: Optional reason for audit

    Returns:
        Tuple of (success, message)
    """
    user = await db.get(User, user_id)
    if not user:
        return False, "User not found"

    if user.role == UserRole.ADMIN:
        return False, "Cannot change status of admin users"

    old_status = user.status
    user.status = status
    await db.commit()

    logger.info(
        f"Admin {admin_id} changed user {user_id} status from {old_status} to {status}. "
        f"Reason: {reason}"
    )

    return True, f"User status changed from {old_status.value} to {status.value}"


# =============================================================================
# SERVER HEALTH
# =============================================================================


async def check_panel_health(db: AsyncSession, panel_id: int) -> PanelHealth:
    """
    Check connectivity and health of a specific panel.

    Args:
        db: Database session
        panel_id: Panel ID to check

    Returns:
        PanelHealth with connection status and stats
    """
    import httpx

    panel = await db.get(Panel, panel_id)
    if not panel:
        return PanelHealth(
            panel_id=panel_id,
            panel_name="Unknown",
            api_url="",
            is_online=False,
            response_time_ms=None,
            users_count=None,
            online_users=None,
            error="Panel not found",
        )

    start_time = asyncio.get_event_loop().time()

    try:
        # nosec B501 - Admin panels often use self-signed certificates
        async with httpx.AsyncClient(timeout=10.0, verify=False) as client:  # nosec B501
            # Try to get token and check API
            if panel.panel_type == "marzban":
                response = await client.post(
                    f"{panel.api_url.rstrip('/')}/api/admin/token",
                    data={"username": panel.username, "password": panel.password},
                )
                response.raise_for_status()

                token_data = response.json()
                access_token = token_data.get("access_token")

                # Get system stats
                stats_response = await client.get(
                    f"{panel.api_url.rstrip('/')}/api/system",
                    headers={"Authorization": f"Bearer {access_token}"},
                )
                stats = stats_response.json()

                response_time_ms = (asyncio.get_event_loop().time() - start_time) * 1000

                return PanelHealth(
                    panel_id=panel_id,
                    panel_name=panel.name,
                    api_url=panel.api_url,
                    is_online=True,
                    response_time_ms=response_time_ms,
                    users_count=stats.get("users_count"),
                    online_users=stats.get("online_users"),
                    error=None,
                )

            elif panel.panel_type == "pasarguard":
                # PasarGuard uses direct DB - check via internal service
                response_time_ms = (asyncio.get_event_loop().time() - start_time) * 1000
                return PanelHealth(
                    panel_id=panel_id,
                    panel_name=panel.name,
                    api_url=panel.api_url,
                    is_online=True,  # Direct DB access
                    response_time_ms=response_time_ms,
                    users_count=None,
                    online_users=None,
                    error=None,
                )

            else:
                # Generic health check
                response = await client.get(panel.api_url, timeout=5.0)
                response_time_ms = (asyncio.get_event_loop().time() - start_time) * 1000
                return PanelHealth(
                    panel_id=panel_id,
                    panel_name=panel.name,
                    api_url=panel.api_url,
                    is_online=response.status_code < 500,
                    response_time_ms=response_time_ms,
                    users_count=None,
                    online_users=None,
                    error=None if response.status_code < 500 else f"HTTP {response.status_code}",
                )

    except Exception as e:
        response_time_ms = (asyncio.get_event_loop().time() - start_time) * 1000
        return PanelHealth(
            panel_id=panel_id,
            panel_name=panel.name,
            api_url=panel.api_url,
            is_online=False,
            response_time_ms=response_time_ms,
            users_count=None,
            online_users=None,
            error=str(e)[:100],
        )


async def check_all_panels_health(db: AsyncSession) -> list[PanelHealth]:
    """
    Check health of all active panels.

    Returns:
        List of PanelHealth for all panels
    """
    result = await db.execute(select(Panel).where(Panel.status == PanelStatus.ACTIVE))
    panels = result.scalars().all()

    # Check all panels concurrently
    health_checks = [check_panel_health(db, panel.id) for panel in panels]
    return await asyncio.gather(*health_checks)


def format_health_report(health_results: list[PanelHealth], lang: str = "fa") -> str:
    """Format panel health results as Telegram message."""
    if not health_results:
        return "❌ No panels configured" if lang != "fa" else "❌ پنلی تنظیم نشده"

    lines = ["🖥️ **Server Health Report**\n"] if lang != "fa" else ["🖥️ **وضعیت سرورها**\n"]

    for h in health_results:
        status = "🟢" if h.is_online else "🔴"
        line = f"{status} **{h.panel_name}**\n"

        if h.is_online:
            line += f"   ├ Response: {h.response_time_ms:.0f}ms\n"
            if h.users_count is not None:
                line += f"   ├ Users: {h.users_count}\n"
            if h.online_users is not None:
                line += f"   └ Online: {h.online_users}\n"
        else:
            line += f"   └ Error: {h.error or 'Connection failed'}\n"

        lines.append(line)

    return "".join(lines)


# =============================================================================
# BROADCASTING
# =============================================================================


async def broadcast_message(
    bot: Bot,
    db: AsyncSession,
    message_text: str,
    *,
    exclude_banned: bool = True,
    only_active: bool = False,
    parse_mode: str = "HTML",
    delay_between_messages: float = 0.05,  # 50ms between messages (20/sec)
    batch_size: int = 25,
    batch_delay: float = 1.0,  # 1 second between batches
) -> BroadcastResult:
    """
    Safely broadcast a message to all users with rate limiting.

    Args:
        bot: Telegram Bot instance
        db: Database session
        message_text: Message to send
        exclude_banned: Skip banned users
        only_active: Only send to users with active services
        parse_mode: Telegram parse mode
        delay_between_messages: Delay between individual messages
        batch_size: Messages per batch
        batch_delay: Delay between batches

    Returns:
        BroadcastResult with statistics
    """
    import time

    start_time = time.time()

    # Build query
    query = select(User.id)
    if exclude_banned:
        query = query.where(User.status != UserStatus.BANNED)

    if only_active:
        # Only users with at least one active service
        active_user_ids = (
            select(Service.user_id).where(Service.status == ServiceStatus.ACTIVE).distinct()
        )
        query = query.where(User.id.in_(active_user_ids))

    result = await db.execute(query)
    user_ids = [row[0] for row in result.fetchall()]

    total_users = len(user_ids)
    sent_count = 0
    failed_count = 0
    skipped_count = 0

    for i, user_id in enumerate(user_ids):
        try:
            await bot.send_message(
                chat_id=user_id,
                text=message_text,
                parse_mode=parse_mode,
            )
            sent_count += 1
        except Exception as e:
            error_str = str(e).lower()
            if "blocked" in error_str or "deactivated" in error_str:
                skipped_count += 1
            else:
                failed_count += 1
                logger.warning(f"Broadcast failed for user {user_id}: {e}")

        # Rate limiting
        await asyncio.sleep(delay_between_messages)

        # Batch delay
        if (i + 1) % batch_size == 0:
            await asyncio.sleep(batch_delay)

    duration = time.time() - start_time

    logger.info(
        f"Broadcast complete: {sent_count}/{total_users} sent, "
        f"{failed_count} failed, {skipped_count} skipped in {duration:.1f}s"
    )

    return BroadcastResult(
        total_users=total_users,
        sent_count=sent_count,
        failed_count=failed_count,
        skipped_count=skipped_count,
        duration_seconds=duration,
    )


# =============================================================================
# COUPON SYSTEM
# =============================================================================


async def create_coupon(
    db: AsyncSession,
    code: str,
    discount_type: str,  # "percentage" or "fixed"
    discount_value: float,
    *,
    max_uses: int | None = None,
    valid_from: datetime | None = None,
    valid_until: datetime | None = None,
    admin_id: int | None = None,
) -> tuple[bool, str, DiscountCode | None]:
    """
    Create a new discount coupon.

    Args:
        db: Database session
        code: Unique coupon code
        discount_type: "percentage" (0-100) or "fixed" (amount)
        discount_value: Discount value
        max_uses: Maximum number of uses (None for unlimited)
        valid_from: Start validity date
        valid_until: End validity date
        admin_id: Admin creating the coupon

    Returns:
        Tuple of (success, message, coupon or None)
    """
    # Validate code uniqueness
    existing = await db.scalar(select(DiscountCode).where(DiscountCode.code == code.upper()))
    if existing:
        return False, f"Coupon code '{code}' already exists", None

    # Validate discount value
    if discount_type == "percentage" and (discount_value < 0 or discount_value > 100):
        return False, "Percentage must be between 0 and 100", None

    if discount_type == "fixed" and discount_value < 0:
        return False, "Fixed discount cannot be negative", None

    coupon = DiscountCode(
        code=code.upper(),
        discount_type=discount_type,
        discount_value=discount_value,
        max_uses=max_uses,
        used_count=0,
        valid_from=valid_from,
        valid_until=valid_until,
        is_active=True,
    )

    db.add(coupon)
    await db.commit()
    await db.refresh(coupon)

    logger.info(f"Admin {admin_id} created coupon {code}: {discount_type} {discount_value}")

    return True, f"Coupon '{code}' created successfully", coupon


async def delete_coupon(
    db: AsyncSession,
    code: str,
    admin_id: int | None = None,
) -> tuple[bool, str]:
    """
    Delete a coupon by code.

    Args:
        db: Database session
        code: Coupon code to delete
        admin_id: Admin deleting the coupon

    Returns:
        Tuple of (success, message)
    """
    coupon = await db.scalar(select(DiscountCode).where(DiscountCode.code == code.upper()))
    if not coupon:
        return False, f"Coupon '{code}' not found"

    await db.delete(coupon)
    await db.commit()

    logger.info(f"Admin {admin_id} deleted coupon {code}")
    return True, f"Coupon '{code}' deleted"


async def toggle_coupon(
    db: AsyncSession,
    code: str,
    admin_id: int | None = None,
) -> tuple[bool, str]:
    """
    Toggle coupon active status.

    Args:
        db: Database session
        code: Coupon code to toggle
        admin_id: Admin performing the action

    Returns:
        Tuple of (success, message)
    """
    coupon = await db.scalar(select(DiscountCode).where(DiscountCode.code == code.upper()))
    if not coupon:
        return False, f"Coupon '{code}' not found"

    coupon.is_active = not coupon.is_active
    await db.commit()

    status = "activated" if coupon.is_active else "deactivated"
    logger.info(f"Admin {admin_id} {status} coupon {code}")
    return True, f"Coupon '{code}' {status}"


async def list_coupons(
    db: AsyncSession,
    include_inactive: bool = False,
    include_expired: bool = False,
) -> list[CouponInfo]:
    """
    List all coupons with usage statistics.

    Args:
        db: Database session
        include_inactive: Include inactive coupons
        include_expired: Include expired coupons

    Returns:
        List of CouponInfo
    """
    query = select(DiscountCode)

    if not include_inactive:
        query = query.where(DiscountCode.is_active)

    if not include_expired:
        now = datetime.now(UTC)
        query = query.where(
            or_(
                DiscountCode.valid_until.is_(None),
                DiscountCode.valid_until > now,
            )
        )

    result = await db.execute(query.order_by(DiscountCode.created_at.desc()))
    coupons = result.scalars().all()

    return [
        CouponInfo(
            id=c.id,
            code=c.code,
            discount_type=c.discount_type,
            discount_value=float(c.discount_value),
            max_uses=c.max_uses,
            current_uses=c.used_count or 0,
            valid_from=c.valid_from,
            valid_until=c.valid_until,
            is_active=c.is_active,
            created_at=c.created_at,
        )
        for c in coupons
    ]


def format_coupons_list(coupons: list[CouponInfo], lang: str = "fa") -> str:
    """Format coupon list as Telegram message."""
    if not coupons:
        return "❌ No coupons found" if lang != "fa" else "❌ کدی یافت نشد"

    lines = ["🎫 **Discount Coupons**\n"] if lang != "fa" else ["🎫 **کدهای تخفیف**\n"]

    for c in coupons:
        status = "✅" if c.is_active else "❌"
        discount = (
            f"{int(c.discount_value)}%"
            if c.discount_type == "percentage"
            else f"{int(c.discount_value):,}"
        )

        line = f"{status} `{c.code}` - {discount}\n"

        if c.max_uses:
            line += f"   └ Uses: {c.current_uses}/{c.max_uses}\n"
        else:
            line += f"   └ Uses: {c.current_uses} (unlimited)\n"

        if c.valid_until:
            line += f"   └ Expires: {c.valid_until.strftime('%Y-%m-%d')}\n"

        lines.append(line)

    return "".join(lines)
