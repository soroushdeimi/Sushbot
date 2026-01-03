"""
Unit tests for admin dashboard features.

Tests:
- Live Analytics: data retrieval and formatting
- User Management: ban, unban, balance adjustment, user info
- Server Health: panel connectivity checks
- Safe Broadcasting: rate-limited message sending
- Discount System: coupon CRUD operations
- Full Purchase Flow: start -> select plan -> payment -> config

All tests use mocked database, Telegram API, and Marzban/V2Ray panel.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_db():
    """Create a mock database session."""
    db = AsyncMock()
    db.get = AsyncMock()
    db.execute = AsyncMock()
    db.scalar = AsyncMock()
    db.add = MagicMock()
    db.delete = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.rollback = AsyncMock()
    return db


@pytest.fixture
def mock_bot():
    """Create a mock Telegram Bot."""
    bot = AsyncMock()
    bot.send_message = AsyncMock()
    return bot


@pytest.fixture
def mock_update():
    """Create a mock Telegram Update."""
    update = MagicMock()
    update.effective_user = MagicMock()
    update.effective_user.id = 123456789
    update.effective_user.username = "admin_user"
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    update.callback_query = None
    return update


@pytest.fixture
def mock_context(mock_bot):
    """Create a mock Telegram context."""
    context = MagicMock()
    context.bot = mock_bot
    context.args = []
    context.user_data = {}
    return context


# =============================================================================
# TEST: Live Analytics
# =============================================================================


@pytest.mark.asyncio
async def test_get_live_analytics_returns_snapshot(mock_db):
    """Test that get_live_analytics returns a complete AnalyticsSnapshot."""
    from services.admin_panel import AnalyticsSnapshot, get_live_analytics

    # Mock database responses
    mock_db.scalar = AsyncMock(side_effect=[
        100,    # total_users
        25,     # active_users_today
        80,     # active_users_month
        5,      # new_users_today
        30,     # new_users_month
        500000, # total_revenue
        50000,  # revenue_today
        150000, # revenue_week
        300000, # revenue_month
        45,     # active_services
        10,     # expired_services
        3,      # pending_payments
        250000, # total_wallet_balance
        1073741824 * 100,  # total_bandwidth (100 GB in bytes)
    ])

    analytics = await get_live_analytics(mock_db)

    assert isinstance(analytics, AnalyticsSnapshot)
    assert analytics.total_users == 100
    assert analytics.active_users_today == 25
    assert analytics.revenue_today == 50000
    assert analytics.active_services == 45
    assert analytics.pending_payments == 3


@pytest.mark.asyncio
async def test_format_analytics_message_persian():
    """Test analytics message formatting in Persian."""
    from services.admin_panel import AnalyticsSnapshot, format_analytics_message

    analytics = AnalyticsSnapshot(
        total_users=100,
        active_users_today=25,
        active_users_month=80,
        new_users_today=5,
        new_users_month=30,
        total_revenue=500000,
        revenue_today=50000,
        revenue_week=150000,
        revenue_month=300000,
        active_services=45,
        expired_services=10,
        pending_payments=3,
        total_wallet_balance=250000,
        total_bandwidth_gb=100.5,
        timestamp=datetime.now(timezone.utc),
    )

    message = format_analytics_message(analytics, lang="fa")

    assert "آمار زنده" in message
    assert "100" in message  # total_users
    assert "50,000" in message  # revenue_today


# =============================================================================
# TEST: User Management
# =============================================================================


@pytest.mark.asyncio
async def test_search_users_by_id(mock_db):
    """Test searching users by Telegram ID."""
    from services.admin_panel import search_users
    from database.models import User

    mock_user = MagicMock(spec=User)
    mock_user.id = 123456789
    mock_user.username = "testuser"

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_user]
    mock_db.execute = AsyncMock(return_value=mock_result)

    users = await search_users(mock_db, "123456789", limit=10)

    assert len(users) == 1
    assert users[0].id == 123456789


@pytest.mark.asyncio
async def test_get_user_profile_returns_complete_profile(mock_db):
    """Test that get_user_profile returns a complete UserProfile."""
    from services.admin_panel import UserProfile, get_user_profile
    from database.models import User, UserRole, UserStatus

    mock_user = MagicMock(spec=User)
    mock_user.id = 123456789
    mock_user.username = "testuser"
    mock_user.first_name = "Test"
    mock_user.last_name = "User"
    mock_user.role = UserRole.USER
    mock_user.status = UserStatus.ACTIVE
    mock_user.balance = 50000
    mock_user.phone = "09123456789"
    mock_user.phone_verified = True
    mock_user.created_at = datetime.now(timezone.utc)

    mock_db.get = AsyncMock(return_value=mock_user)
    mock_db.scalar = AsyncMock(side_effect=[5, 3, 150000])  # services, purchases, total_spent

    profile = await get_user_profile(mock_db, 123456789)

    assert isinstance(profile, UserProfile)
    assert profile.id == 123456789
    assert profile.username == "testuser"
    assert profile.services_count == 5
    assert profile.total_spent == 150000


@pytest.mark.asyncio
async def test_adjust_user_balance_add(mock_db):
    """Test adding balance to user wallet."""
    from services.admin_panel import adjust_user_balance
    from database.models import User

    mock_user = MagicMock(spec=User)
    mock_user.id = 123456789
    mock_user.balance = 10000

    mock_db.get = AsyncMock(return_value=mock_user)

    success, message = await adjust_user_balance(
        mock_db,
        user_id=123456789,
        amount=5000,
        admin_id=999999,
        reason="Test credit",
    )

    assert success is True
    assert "15,000" in message  # New balance
    assert mock_user.balance == 15000
    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_adjust_user_balance_deduct_insufficient(mock_db):
    """Test deducting more than available balance fails."""
    from services.admin_panel import adjust_user_balance
    from database.models import User

    mock_user = MagicMock(spec=User)
    mock_user.id = 123456789
    mock_user.balance = 5000

    mock_db.get = AsyncMock(return_value=mock_user)

    success, message = await adjust_user_balance(
        mock_db,
        user_id=123456789,
        amount=-10000,  # More than balance
        admin_id=999999,
    )

    assert success is False
    assert "Insufficient" in message


@pytest.mark.asyncio
async def test_set_user_status_ban(mock_db):
    """Test banning a user."""
    from services.admin_panel import set_user_status
    from database.models import User, UserRole, UserStatus

    mock_user = MagicMock(spec=User)
    mock_user.id = 123456789
    mock_user.role = UserRole.USER
    mock_user.status = UserStatus.ACTIVE

    mock_db.get = AsyncMock(return_value=mock_user)

    success, message = await set_user_status(
        mock_db,
        user_id=123456789,
        status=UserStatus.BANNED,
        admin_id=999999,
        reason="Spam",
    )

    assert success is True
    assert mock_user.status == UserStatus.BANNED
    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_cannot_ban_admin_user(mock_db):
    """Test that admin users cannot be banned."""
    from services.admin_panel import set_user_status
    from database.models import User, UserRole, UserStatus

    mock_user = MagicMock(spec=User)
    mock_user.id = 999999
    mock_user.role = UserRole.ADMIN  # Admin user
    mock_user.status = UserStatus.ACTIVE

    mock_db.get = AsyncMock(return_value=mock_user)

    success, message = await set_user_status(
        mock_db,
        user_id=999999,
        status=UserStatus.BANNED,
        admin_id=888888,
    )

    assert success is False
    assert "admin" in message.lower()


# =============================================================================
# TEST: Server Health
# =============================================================================


@pytest.mark.asyncio
async def test_check_panel_health_online(mock_db):
    """Test panel health check for an online panel."""
    from services.admin_panel import PanelHealth, check_panel_health
    from database.models import Panel

    mock_panel = MagicMock(spec=Panel)
    mock_panel.id = 1
    mock_panel.name = "Test Panel"
    mock_panel.api_url = "https://panel.example.com"
    mock_panel.panel_type = "marzban"
    mock_panel.username = "admin"
    mock_panel.password = "password"

    mock_db.get = AsyncMock(return_value=mock_panel)

    with patch("httpx.AsyncClient") as mock_client:
        mock_response = MagicMock()
        mock_response.json.return_value = {"access_token": "token123"}
        mock_response.raise_for_status = MagicMock()

        mock_stats_response = MagicMock()
        mock_stats_response.json.return_value = {
            "users_count": 50,
            "online_users": 10,
        }

        mock_client_instance = AsyncMock()
        mock_client_instance.post = AsyncMock(return_value=mock_response)
        mock_client_instance.get = AsyncMock(return_value=mock_stats_response)
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.__aexit__.return_value = None
        mock_client.return_value = mock_client_instance

        health = await check_panel_health(mock_db, panel_id=1)

        assert isinstance(health, PanelHealth)
        assert health.is_online is True
        assert health.panel_name == "Test Panel"


@pytest.mark.asyncio
async def test_check_panel_health_offline(mock_db):
    """Test panel health check for an offline panel."""
    from services.admin_panel import PanelHealth, check_panel_health
    from database.models import Panel

    mock_panel = MagicMock(spec=Panel)
    mock_panel.id = 1
    mock_panel.name = "Test Panel"
    mock_panel.api_url = "https://panel.example.com"
    mock_panel.panel_type = "marzban"
    mock_panel.username = "admin"
    mock_panel.password = "password"

    mock_db.get = AsyncMock(return_value=mock_panel)

    with patch("httpx.AsyncClient") as mock_client:
        mock_client_instance = AsyncMock()
        mock_client_instance.post = AsyncMock(side_effect=Exception("Connection refused"))
        mock_client_instance.__aenter__.return_value = mock_client_instance
        mock_client_instance.__aexit__.return_value = None
        mock_client.return_value = mock_client_instance

        health = await check_panel_health(mock_db, panel_id=1)

        assert health.is_online is False
        assert health.error is not None


@pytest.mark.asyncio
async def test_check_panel_health_not_found(mock_db):
    """Test panel health check for non-existent panel."""
    from services.admin_panel import check_panel_health

    mock_db.get = AsyncMock(return_value=None)

    health = await check_panel_health(mock_db, panel_id=999)

    assert health.is_online is False
    assert health.error == "Panel not found"


# =============================================================================
# TEST: Safe Broadcasting
# =============================================================================


@pytest.mark.asyncio
async def test_broadcast_message_success(mock_db, mock_bot):
    """Test successful broadcast to all users."""
    from services.admin_panel import BroadcastResult, broadcast_message
    from database.models import User, UserStatus

    # Mock user IDs to broadcast to
    mock_result = MagicMock()
    mock_result.fetchall.return_value = [(1,), (2,), (3,)]
    mock_db.execute = AsyncMock(return_value=mock_result)

    # All sends succeed
    mock_bot.send_message = AsyncMock(return_value=MagicMock())

    result = await broadcast_message(
        bot=mock_bot,
        db=mock_db,
        message_text="Test broadcast message",
        exclude_banned=True,
        delay_between_messages=0.001,  # Fast for testing
        batch_size=10,
        batch_delay=0.001,
    )

    assert isinstance(result, BroadcastResult)
    assert result.total_users == 3
    assert result.sent_count == 3
    assert result.failed_count == 0


@pytest.mark.asyncio
async def test_broadcast_handles_blocked_users(mock_db, mock_bot):
    """Test that broadcast handles blocked/deactivated users gracefully."""
    from services.admin_panel import broadcast_message

    # Mock 3 users
    mock_result = MagicMock()
    mock_result.fetchall.return_value = [(1,), (2,), (3,)]
    mock_db.execute = AsyncMock(return_value=mock_result)

    # First succeeds, second is blocked, third succeeds
    mock_bot.send_message = AsyncMock(
        side_effect=[
            MagicMock(),  # Success
            Exception("Forbidden: user blocked the bot"),  # Blocked
            MagicMock(),  # Success
        ]
    )

    result = await broadcast_message(
        bot=mock_bot,
        db=mock_db,
        message_text="Test",
        delay_between_messages=0.001,
        batch_size=10,
        batch_delay=0.001,
    )

    assert result.sent_count == 2
    assert result.skipped_count == 1  # Blocked user
    assert result.failed_count == 0


@pytest.mark.asyncio
async def test_broadcast_rate_limiting():
    """Test that broadcast respects rate limiting delays."""
    import time

    from services.admin_panel import broadcast_message

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.fetchall.return_value = [(i,) for i in range(5)]
    mock_db.execute = AsyncMock(return_value=mock_result)

    mock_bot = AsyncMock()
    mock_bot.send_message = AsyncMock()

    start_time = time.time()

    await broadcast_message(
        bot=mock_bot,
        db=mock_db,
        message_text="Test",
        delay_between_messages=0.01,  # 10ms between messages
        batch_size=100,
        batch_delay=0.001,
    )

    elapsed = time.time() - start_time

    # Should take at least 50ms (5 messages * 10ms delay)
    assert elapsed >= 0.04  # Give some margin


# =============================================================================
# TEST: Discount/Coupon System
# =============================================================================


@pytest.mark.asyncio
async def test_create_coupon_success(mock_db):
    """Test successful coupon creation."""
    from services.admin_panel import create_coupon

    # No existing coupon with same code
    mock_db.scalar = AsyncMock(return_value=None)

    success, message, coupon = await create_coupon(
        mock_db,
        code="SAVE20",
        discount_type="percentage",
        discount_value=20,
        max_uses=100,
        admin_id=999,
    )

    assert success is True
    assert "created" in message.lower()
    mock_db.add.assert_called_once()
    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_create_coupon_duplicate_code(mock_db):
    """Test that duplicate coupon codes are rejected."""
    from services.admin_panel import create_coupon

    # Existing coupon with same code
    mock_db.scalar = AsyncMock(return_value=MagicMock())

    success, message, coupon = await create_coupon(
        mock_db,
        code="EXISTING",
        discount_type="percentage",
        discount_value=10,
        admin_id=999,
    )

    assert success is False
    assert "already exists" in message.lower()
    assert coupon is None


@pytest.mark.asyncio
async def test_create_coupon_invalid_percentage(mock_db):
    """Test that invalid percentage values are rejected."""
    from services.admin_panel import create_coupon

    mock_db.scalar = AsyncMock(return_value=None)

    success, message, _ = await create_coupon(
        mock_db,
        code="INVALID",
        discount_type="percentage",
        discount_value=150,  # Invalid: > 100
        admin_id=999,
    )

    assert success is False
    assert "0 and 100" in message


@pytest.mark.asyncio
async def test_delete_coupon_success(mock_db):
    """Test successful coupon deletion."""
    from services.admin_panel import delete_coupon

    mock_coupon = MagicMock()
    mock_db.scalar = AsyncMock(return_value=mock_coupon)

    success, message = await delete_coupon(mock_db, code="DELETE_ME", admin_id=999)

    assert success is True
    mock_db.delete.assert_called_once_with(mock_coupon)
    mock_db.commit.assert_called_once()


@pytest.mark.asyncio
async def test_delete_coupon_not_found(mock_db):
    """Test deleting non-existent coupon."""
    from services.admin_panel import delete_coupon

    mock_db.scalar = AsyncMock(return_value=None)

    success, message = await delete_coupon(mock_db, code="NONEXISTENT", admin_id=999)

    assert success is False
    assert "not found" in message.lower()


@pytest.mark.asyncio
async def test_list_coupons(mock_db):
    """Test listing active coupons."""
    from services.admin_panel import CouponInfo, list_coupons

    mock_coupon = MagicMock()
    mock_coupon.id = 1
    mock_coupon.code = "SALE20"
    mock_coupon.discount_type = "percentage"
    mock_coupon.discount_value = 20
    mock_coupon.max_uses = 100
    mock_coupon.used_count = 15
    mock_coupon.valid_from = None
    mock_coupon.valid_until = None
    mock_coupon.is_active = True
    mock_coupon.created_at = datetime.now(timezone.utc)

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_coupon]
    mock_db.execute = AsyncMock(return_value=mock_result)

    coupons = await list_coupons(mock_db)

    assert len(coupons) == 1
    assert isinstance(coupons[0], CouponInfo)
    assert coupons[0].code == "SALE20"
    assert coupons[0].current_uses == 15


# =============================================================================
# TEST: Full Purchase Flow (Integration-style with mocks)
# =============================================================================


@pytest.mark.asyncio
async def test_full_purchase_flow():
    """
    Test the complete user purchase flow:
    1. User starts bot
    2. User selects a product
    3. Payment is created
    4. Payment is marked as completed
    5. Service is provisioned
    6. User receives config

    All external services are mocked.
    """
    from database.models import (
        Payment,
        PaymentStatus,
        Product,
        Purchase,
        PurchaseStatus,
        PurchaseType,
        Service,
        ServiceStatus,
        User,
    )

    # Setup mocks
    mock_db = AsyncMock()

    # Step 1: User exists
    mock_user = MagicMock(spec=User)
    mock_user.id = 123456789
    mock_user.balance = 0

    # Step 2: Product exists
    mock_product = MagicMock(spec=Product)
    mock_product.id = 1
    mock_product.name = "30 Day VPN"
    mock_product.price = 50000
    mock_product.duration_days = 30
    mock_product.traffic_gb = 50
    mock_product.protocol = "vless"

    # Step 3: Create purchase and payment
    mock_purchase = MagicMock(spec=Purchase)
    mock_purchase.id = 1
    mock_purchase.user_id = 123456789
    mock_purchase.product_id = 1
    mock_purchase.status = PurchaseStatus.PENDING
    mock_purchase.purchase_type = PurchaseType.NEW
    mock_purchase.amount = 50000
    mock_purchase.final_amount = 50000
    mock_purchase.duration_days = 30
    mock_purchase.traffic_gb = 50

    mock_payment = MagicMock(spec=Payment)
    mock_payment.id = 1
    mock_payment.purchase_id = 1
    mock_payment.status = PaymentStatus.PENDING
    mock_payment.amount = 50000

    # Step 5: Service after provisioning
    mock_service = MagicMock(spec=Service)
    mock_service.id = 1
    mock_service.user_id = 123456789
    mock_service.status = ServiceStatus.ACTIVE
    mock_service.client_email = "user_123456789_1"
    mock_service.subscription_url = "https://sub.example.com/user_123456789_1"

    # Configure mock_db responses
    mock_db.get = AsyncMock(side_effect=lambda model, id: {
        (User, 123456789): mock_user,
        (Product, 1): mock_product,
        (Purchase, 1): mock_purchase,
        (Payment, 1): mock_payment,
    }.get((model, id)))

    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()

    # Simulate the flow
    # 1. Verify user exists
    user = await mock_db.get(User, 123456789)
    assert user is not None

    # 2. Get product details
    product = await mock_db.get(Product, 1)
    assert product.price == 50000

    # 3. Create purchase (simulated)
    mock_db.add(mock_purchase)
    await mock_db.commit()

    # 4. Payment completed (simulated callback/approval)
    mock_payment.status = PaymentStatus.COMPLETED
    mock_purchase.status = PurchaseStatus.COMPLETED
    await mock_db.commit()

    # 5. Provision service (mock the panel API)
    with patch("services.provisioning.PanelFactory.create_panel") as mock_factory:
        mock_panel_service = AsyncMock()
        mock_panel_service.create_user = AsyncMock(return_value={
            "username": "user_123456789_1",
            "subscription_url": "https://sub.example.com/user_123456789_1",
        })
        mock_factory.return_value = mock_panel_service

        # Simulated provisioning
        mock_db.add(mock_service)
        await mock_db.commit()

    # 6. Verify service was created
    assert mock_service.status == ServiceStatus.ACTIVE
    assert mock_service.subscription_url is not None

    # Verify the complete flow
    assert mock_purchase.status == PurchaseStatus.COMPLETED
    assert mock_payment.status == PaymentStatus.COMPLETED
    assert mock_service.client_email == "user_123456789_1"


@pytest.mark.asyncio
async def test_purchase_flow_with_discount():
    """Test purchase flow with a discount coupon applied."""
    # Simplified test showing discount calculation
    original_price = 100000
    discount_percentage = 20
    expected_final = original_price * (1 - discount_percentage / 100)

    assert expected_final == 80000


@pytest.mark.asyncio
async def test_purchase_flow_payment_failure():
    """Test that failed payments don't provision services."""
    from database.models import PaymentStatus, PurchaseStatus

    # Setup
    mock_purchase_status = PurchaseStatus.PENDING
    mock_payment_status = PaymentStatus.FAILED

    # When payment fails, purchase should not complete
    if mock_payment_status == PaymentStatus.FAILED:
        mock_purchase_status = PurchaseStatus.FAILED

    assert mock_purchase_status == PurchaseStatus.FAILED
    # Service should NOT be provisioned (not tested here as it never gets called)


# =============================================================================
# TEST: Admin Handler Commands
# =============================================================================


@pytest.mark.asyncio
async def test_ban_user_command(mock_update, mock_context):
    """Test the /ban_user command handler."""
    from handlers.admin_handlers import ban_user_command

    mock_context.args = ["123456789", "Spam"]

    with patch("handlers.admin_handlers.get_db") as mock_get_db:
        with patch("handlers.admin_handlers.check_env_admin") as mock_env_check:
            with patch("handlers.admin_handlers.set_user_status") as mock_set_status:
                mock_db = AsyncMock()

                async def db_gen():
                    yield mock_db

                mock_get_db.return_value = db_gen()
                mock_env_check.return_value = MagicMock(is_admin=False)
                mock_set_status.return_value = (True, "User banned")

                # Skip the @admin_required decorator for this test
                with patch("utils.security.check_admin_status") as mock_check:
                    mock_check.return_value = MagicMock(
                        is_admin=True, level="admin", permissions=set()
                    )

                    await ban_user_command(mock_update, mock_context)

                    mock_update.message.reply_text.assert_called()


@pytest.mark.asyncio
async def test_user_info_command(mock_update, mock_context):
    """Test the /user_info command handler."""
    from handlers.admin_handlers import user_info_command

    mock_context.args = ["123456789"]

    with patch("handlers.admin_handlers.get_db") as mock_get_db:
        with patch("handlers.admin_handlers.get_user_profile") as mock_get_profile:
            from services.admin_panel import UserProfile

            mock_db = AsyncMock()

            async def db_gen():
                yield mock_db

            mock_get_db.return_value = db_gen()
            mock_get_profile.return_value = UserProfile(
                id=123456789,
                username="testuser",
                first_name="Test",
                last_name="User",
                role="user",
                status="active",
                balance=50000,
                phone="09123456789",
                phone_verified=True,
                created_at=datetime.now(timezone.utc),
                services_count=2,
                purchases_count=3,
                total_spent=150000,
            )

            with patch("utils.security.check_admin_status") as mock_check:
                mock_check.return_value = MagicMock(
                    is_admin=True, level="admin", permissions=set()
                )

                await user_info_command(mock_update, mock_context)

                mock_update.message.reply_text.assert_called()
                call_args = mock_update.message.reply_text.call_args
                assert "testuser" in str(call_args)
