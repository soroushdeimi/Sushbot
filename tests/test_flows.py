"""
Flow tests for purchase, admin panel, and user journeys.

Tests:
- Complete purchase flow (select product → pay → service creation)
- Wallet topup flow
- Coupon redemption flow
- Admin panel analytics
- Broadcasting flow
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

if TYPE_CHECKING:
    pass


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_db() -> AsyncMock:
    """Create a mock async database session."""
    db = AsyncMock(spec=["get", "execute", "add", "commit", "rollback", "refresh", "scalar"])
    db.commit = AsyncMock()
    db.rollback = AsyncMock()
    return db


@pytest.fixture
def mock_telegram_bot() -> MagicMock:
    """Create a mock Telegram Bot."""
    bot = MagicMock()
    bot.send_message = AsyncMock()
    return bot


@pytest.fixture
def mock_user() -> MagicMock:
    """Create a mock database User."""
    from database.models import UserRole, UserStatus

    user = MagicMock()
    user.id = 12345
    user.username = "testuser"
    user.first_name = "Test"
    user.last_name = "User"
    user.role = UserRole.USER
    user.status = UserStatus.ACTIVE
    user.balance = Decimal("50000")
    user.phone = "989123456789"
    user.phone_verified = True
    user.created_at = datetime.now(UTC) - timedelta(days=30)
    user.updated_at = datetime.now(UTC)
    return user


@pytest.fixture
def mock_product() -> MagicMock:
    """Create a mock Product."""
    product = MagicMock()
    product.id = 1
    product.name = "VPN 30 Days"
    product.price = Decimal("100000")
    product.duration_days = 30
    product.traffic_gb = 50
    product.protocol = "vmess"
    product.is_active = True
    return product


@pytest.fixture
def mock_panel() -> MagicMock:
    """Create a mock Panel."""
    from database.models import PanelStatus

    panel = MagicMock()
    panel.id = 1
    panel.name = "Test Panel"
    panel.api_url = "https://panel.example.com"
    panel.username = "admin"
    panel.password = "secret"
    panel.panel_type = "marzban"
    panel.status = PanelStatus.ACTIVE
    return panel


@pytest.fixture
def mock_purchase() -> MagicMock:
    """Create a mock Purchase."""
    from database.models import PurchaseStatus
    from database.models.purchase import PurchaseType

    purchase = MagicMock()
    purchase.id = 100
    purchase.user_id = 12345
    purchase.product_id = 1
    purchase.service_id = None
    purchase.purchase_type = PurchaseType.NEW
    purchase.status = PurchaseStatus.PENDING
    purchase.amount = Decimal("100000")
    purchase.discount_amount = Decimal("0")
    purchase.final_amount = Decimal("100000")
    purchase.duration_days = 30
    purchase.traffic_gb = 50
    purchase.protocol = "vmess"
    purchase.created_at = datetime.now(UTC)
    return purchase


@pytest.fixture
def mock_service() -> MagicMock:
    """Create a mock Service."""
    from database.models import ServiceStatus

    service = MagicMock()
    service.id = 500
    service.user_id = 12345
    service.panel_id = 1
    service.client_email = "test@vpn.local"
    service.status = ServiceStatus.ACTIVE
    service.protocol = "vmess"
    service.expiry_date = datetime.now(UTC) + timedelta(days=30)
    service.total_traffic_gb = 50
    service.used_traffic = 0
    service.remaining_traffic_gb = 50.0
    return service


# =============================================================================
# TEST: Purchase Flow
# =============================================================================


@pytest.mark.asyncio
async def test_fulfill_purchase_new_service(mock_db, mock_purchase, mock_panel, mock_service):
    """Test complete flow for new service purchase fulfillment."""
    from services.fulfillment import fulfill_purchase

    mock_purchase.purchase_type.value = "new"
    mock_purchase.service_id = None

    with patch("services.fulfillment.provision_purchase") as mock_provision:
        mock_provision.return_value = mock_service

        result = await fulfill_purchase(mock_db, purchase=mock_purchase)

        mock_provision.assert_called_once_with(mock_db, purchase=mock_purchase)
        assert result == mock_service


@pytest.mark.asyncio
async def test_fulfill_purchase_wallet_topup(mock_db, mock_purchase, mock_user):
    """Test wallet top-up purchase flow."""
    from database.models.purchase import PurchaseType
    from services.fulfillment import fulfill_purchase

    mock_purchase.purchase_type = PurchaseType.WALLET_TOPUP
    mock_purchase.final_amount = Decimal("50000")
    mock_purchase.user_id = mock_user.id

    # Mock no existing transaction
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = None
    mock_db.execute.return_value = mock_result

    with patch("services.fulfillment.apply_wallet_tx") as mock_apply_wallet:
        mock_apply_wallet.return_value = None

        result = await fulfill_purchase(mock_db, purchase=mock_purchase)

        assert result is None  # Wallet topup returns None
        mock_apply_wallet.assert_called_once()
        call_kwargs = mock_apply_wallet.call_args.kwargs
        assert call_kwargs["user_id"] == mock_user.id
        assert call_kwargs["amount"] == 50000


@pytest.mark.asyncio
async def test_fulfill_purchase_idempotent_wallet_topup(mock_db, mock_purchase, mock_user):
    """Test that wallet top-up is idempotent (doesn't duplicate transactions)."""
    from database.models.purchase import PurchaseType
    from services.fulfillment import fulfill_purchase

    mock_purchase.purchase_type = PurchaseType.WALLET_TOPUP
    mock_purchase.final_amount = Decimal("50000")

    # Mock existing transaction (already processed)
    existing_tx = MagicMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.first.return_value = existing_tx
    mock_db.execute.return_value = mock_result

    with patch("services.fulfillment.apply_wallet_tx") as mock_apply_wallet:
        result = await fulfill_purchase(mock_db, purchase=mock_purchase)

        assert result is None
        mock_apply_wallet.assert_not_called()  # Should NOT call again


@pytest.mark.asyncio
async def test_fulfill_purchase_renewal(mock_db, mock_purchase, mock_service, mock_panel):
    """Test service renewal purchase flow."""
    from database.models.purchase import PurchaseType
    from services.fulfillment import fulfill_purchase

    mock_purchase.purchase_type = PurchaseType.RENEWAL
    mock_purchase.service_id = mock_service.id
    mock_purchase.duration_days = 30

    mock_db.get = AsyncMock(side_effect=[mock_service, mock_panel])

    # Mock panel service
    mock_panel_service = AsyncMock()
    mock_panel_service.renew_user = AsyncMock()
    mock_panel_service.close = AsyncMock()

    with patch("services.fulfillment.PanelFactory.create_panel") as mock_factory:
        mock_factory.return_value = mock_panel_service

        result = await fulfill_purchase(mock_db, purchase=mock_purchase)

        mock_panel_service.renew_user.assert_called_once()
        mock_db.commit.assert_called()
        assert result == mock_service


# =============================================================================
# TEST: Coupon Flow
# =============================================================================


@pytest.mark.asyncio
async def test_create_coupon_success(mock_db):
    """Test creating a new discount coupon."""
    from services.admin_panel import create_coupon

    mock_db.scalar = AsyncMock(return_value=None)  # No existing coupon

    success, message, coupon = await create_coupon(
        mock_db,
        code="SUMMER20",
        discount_type="percentage",
        discount_value=20.0,
        max_uses=100,
        admin_id=1,
    )

    assert success is True
    assert "created" in message.lower()
    mock_db.add.assert_called_once()
    mock_db.commit.assert_called()


@pytest.mark.asyncio
async def test_create_coupon_duplicate_code(mock_db):
    """Test that duplicate coupon codes are rejected."""
    from services.admin_panel import create_coupon

    # Mock existing coupon with same code
    mock_db.scalar = AsyncMock(return_value=MagicMock())

    success, message, coupon = await create_coupon(
        mock_db,
        code="EXISTING",
        discount_type="percentage",
        discount_value=10.0,
    )

    assert success is False
    assert "exists" in message.lower()
    assert coupon is None


@pytest.mark.asyncio
async def test_create_coupon_invalid_percentage(mock_db):
    """Test that invalid percentage values are rejected."""
    from services.admin_panel import create_coupon

    mock_db.scalar = AsyncMock(return_value=None)

    success, message, coupon = await create_coupon(
        mock_db,
        code="INVALID",
        discount_type="percentage",
        discount_value=150.0,  # Invalid: > 100%
    )

    assert success is False
    assert "percentage" in message.lower()


@pytest.mark.asyncio
async def test_delete_coupon_success(mock_db):
    """Test deleting a coupon."""
    from services.admin_panel import delete_coupon

    mock_coupon = MagicMock()
    mock_db.scalar = AsyncMock(return_value=mock_coupon)
    mock_db.delete = AsyncMock()

    success, message = await delete_coupon(mock_db, code="TODELETE", admin_id=1)

    assert success is True
    assert "deleted" in message.lower()
    mock_db.delete.assert_called_once_with(mock_coupon)


@pytest.mark.asyncio
async def test_delete_coupon_not_found(mock_db):
    """Test deleting non-existent coupon."""
    from services.admin_panel import delete_coupon

    mock_db.scalar = AsyncMock(return_value=None)

    success, message = await delete_coupon(mock_db, code="NOTEXIST", admin_id=1)

    assert success is False
    assert "not found" in message.lower()


# =============================================================================
# TEST: Analytics Flow
# =============================================================================


@pytest.mark.asyncio
async def test_get_live_analytics(mock_db):
    """Test retrieving live analytics snapshot."""
    from services.admin_panel import get_live_analytics

    # Mock all scalar queries
    mock_db.scalar = AsyncMock(side_effect=[
        100,    # total_users
        25,     # active_users_today
        80,     # active_users_month
        5,      # new_users_today
        30,     # new_users_month
        5000000,  # total_revenue
        100000,   # revenue_today
        500000,   # revenue_week
        2000000,  # revenue_month
        45,     # active_services
        10,     # expired_services
        3,      # pending_payments
        750000,  # total_wallet_balance
        1073741824,  # total_bandwidth (1 GB in bytes)
    ])

    analytics = await get_live_analytics(mock_db)

    assert analytics.total_users == 100
    assert analytics.active_users_today == 25
    assert analytics.new_users_today == 5
    assert analytics.revenue_today == 100000
    assert analytics.active_services == 45
    assert analytics.pending_payments == 3


@pytest.mark.asyncio
async def test_format_analytics_message_fa():
    """Test formatting analytics message in Farsi."""
    from services.admin_panel import AnalyticsSnapshot, format_analytics_message

    analytics = AnalyticsSnapshot(
        total_users=100,
        active_users_today=25,
        active_users_month=80,
        new_users_today=5,
        new_users_month=30,
        total_revenue=5000000,
        revenue_today=100000,
        revenue_week=500000,
        revenue_month=2000000,
        active_services=45,
        expired_services=10,
        pending_payments=3,
        total_wallet_balance=750000,
        total_bandwidth_gb=1.5,
        timestamp=datetime.now(UTC),
    )

    message = format_analytics_message(analytics, lang="fa")

    assert "آمار زنده" in message
    assert "100" in message  # total_users
    assert "45" in message   # active_services


# =============================================================================
# TEST: User Management Flow
# =============================================================================


@pytest.mark.asyncio
async def test_search_users_by_id(mock_db, mock_user):
    """Test searching users by ID."""
    from services.admin_panel import search_users

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_user]
    mock_db.execute = AsyncMock(return_value=mock_result)

    users = await search_users(mock_db, query="12345", limit=10)

    assert len(users) == 1
    assert users[0].id == 12345


@pytest.mark.asyncio
async def test_get_user_profile(mock_db, mock_user):
    """Test getting detailed user profile."""
    from services.admin_panel import get_user_profile

    mock_db.get = AsyncMock(return_value=mock_user)
    mock_db.scalar = AsyncMock(side_effect=[5, 3, 150000])  # services, purchases, total_spent

    profile = await get_user_profile(mock_db, user_id=12345)

    assert profile is not None
    assert profile.id == 12345
    assert profile.username == "testuser"
    assert profile.services_count == 5
    assert profile.purchases_count == 3
    assert profile.total_spent == 150000


@pytest.mark.asyncio
async def test_adjust_user_balance_add(mock_db, mock_user):
    """Test adding balance to user wallet."""
    from services.admin_panel import adjust_user_balance

    mock_db.get = AsyncMock(return_value=mock_user)
    mock_user.balance = Decimal("50000")

    success, message = await adjust_user_balance(
        mock_db,
        user_id=12345,
        amount=10000,  # Add 10000
        admin_id=1,
        reason="Compensation",
    )

    assert success is True
    assert mock_user.balance == 60000  # 50000 + 10000
    mock_db.commit.assert_called()


@pytest.mark.asyncio
async def test_adjust_user_balance_deduct_insufficient(mock_db, mock_user):
    """Test that deducting more than balance fails."""
    from services.admin_panel import adjust_user_balance

    mock_db.get = AsyncMock(return_value=mock_user)
    mock_user.balance = Decimal("10000")

    success, message = await adjust_user_balance(
        mock_db,
        user_id=12345,
        amount=-50000,  # Try to deduct more than balance
        admin_id=1,
    )

    assert success is False
    assert "insufficient" in message.lower()


@pytest.mark.asyncio
async def test_set_user_status_ban(mock_db, mock_user):
    """Test banning a user."""
    from database.models import UserStatus
    from services.admin_panel import set_user_status

    mock_db.get = AsyncMock(return_value=mock_user)

    success, message = await set_user_status(
        mock_db,
        user_id=12345,
        status=UserStatus.BANNED,
        admin_id=1,
        reason="ToS violation",
    )

    assert success is True
    assert mock_user.status == UserStatus.BANNED
    mock_db.commit.assert_called()


@pytest.mark.asyncio
async def test_set_user_status_cannot_ban_admin(mock_db, mock_user):
    """Test that admin users cannot be banned."""
    from database.models import UserRole, UserStatus
    from services.admin_panel import set_user_status

    mock_user.role = UserRole.ADMIN
    mock_db.get = AsyncMock(return_value=mock_user)

    success, message = await set_user_status(
        mock_db,
        user_id=12345,
        status=UserStatus.BANNED,
        admin_id=1,
    )

    assert success is False
    assert "admin" in message.lower()


# =============================================================================
# TEST: Broadcasting Flow
# =============================================================================


@pytest.mark.asyncio
async def test_broadcast_message_success(mock_db, mock_telegram_bot):
    """Test broadcasting message to users."""
    from services.admin_panel import broadcast_message

    # Mock user IDs
    mock_result = MagicMock()
    mock_result.fetchall.return_value = [(1,), (2,), (3,)]
    mock_db.execute = AsyncMock(return_value=mock_result)

    result = await broadcast_message(
        mock_telegram_bot,
        mock_db,
        message_text="<b>Test Broadcast</b>",
        delay_between_messages=0.001,  # Fast for testing
        batch_delay=0.001,
    )

    assert result.total_users == 3
    assert result.sent_count == 3
    assert mock_telegram_bot.send_message.call_count == 3


@pytest.mark.asyncio
async def test_broadcast_message_handles_blocked_users(mock_db, mock_telegram_bot):
    """Test that broadcast handles blocked/deactivated users gracefully."""
    from services.admin_panel import broadcast_message

    mock_result = MagicMock()
    mock_result.fetchall.return_value = [(1,), (2,), (3,)]
    mock_db.execute = AsyncMock(return_value=mock_result)

    # Simulate one blocked user
    mock_telegram_bot.send_message = AsyncMock(
        side_effect=[None, Exception("Forbidden: user is deactivated"), None]
    )

    result = await broadcast_message(
        mock_telegram_bot,
        mock_db,
        message_text="Test",
        delay_between_messages=0.001,
        batch_delay=0.001,
    )

    assert result.total_users == 3
    assert result.sent_count == 2
    assert result.skipped_count == 1


# =============================================================================
# TEST: Server Health Flow
# =============================================================================


@pytest.mark.asyncio
async def test_check_panel_health_online(mock_db, mock_panel):
    """Test checking health of an online panel."""
    from services.admin_panel import check_panel_health

    mock_db.get = AsyncMock(return_value=mock_panel)

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client

        # Mock successful auth
        mock_auth_response = MagicMock()
        mock_auth_response.raise_for_status = MagicMock()
        mock_auth_response.json.return_value = {"access_token": "test_token"}

        # Mock system stats
        mock_stats_response = MagicMock()
        mock_stats_response.json.return_value = {"users_count": 50, "online_users": 10}

        mock_client.post = AsyncMock(return_value=mock_auth_response)
        mock_client.get = AsyncMock(return_value=mock_stats_response)

        result = await check_panel_health(mock_db, panel_id=1)

        assert result.is_online is True
        assert result.panel_name == "Test Panel"
        assert result.users_count == 50
        assert result.online_users == 10


@pytest.mark.asyncio
async def test_check_panel_health_not_found(mock_db):
    """Test checking health of non-existent panel."""
    from services.admin_panel import check_panel_health

    mock_db.get = AsyncMock(return_value=None)

    result = await check_panel_health(mock_db, panel_id=999)

    assert result.is_online is False
    assert "not found" in result.error.lower()


@pytest.mark.asyncio
async def test_check_panel_health_connection_error(mock_db, mock_panel):
    """Test health check when panel is unreachable."""
    from services.admin_panel import check_panel_health

    mock_db.get = AsyncMock(return_value=mock_panel)

    with patch("httpx.AsyncClient") as mock_client_class:
        mock_client = AsyncMock()
        mock_client_class.return_value.__aenter__.return_value = mock_client
        mock_client.post = AsyncMock(side_effect=Exception("Connection timeout"))

        result = await check_panel_health(mock_db, panel_id=1)

        assert result.is_online is False
        assert "timeout" in result.error.lower()


# =============================================================================
# TEST: Full User Journey
# =============================================================================


@pytest.mark.asyncio
async def test_full_purchase_journey(mock_db, mock_user, mock_product, mock_panel, mock_service):
    """
    Test complete user journey from product selection to service activation.

    Steps:
    1. User selects product
    2. Purchase record created
    3. Payment processed
    4. Purchase marked completed
    5. Service provisioned on panel
    6. User receives service credentials
    """
    from database.models import PaymentStatus, PurchaseStatus
    from database.models.purchase import PurchaseType
    from services.fulfillment import fulfill_purchase

    # Step 1 & 2: Create purchase (mocking the handler part)
    purchase = MagicMock()
    purchase.id = 100
    purchase.user_id = mock_user.id
    purchase.product_id = mock_product.id
    purchase.purchase_type = PurchaseType.NEW
    purchase.status = PurchaseStatus.PENDING
    purchase.final_amount = mock_product.price
    purchase.duration_days = mock_product.duration_days
    purchase.traffic_gb = mock_product.traffic_gb
    purchase.protocol = mock_product.protocol
    purchase.service_id = None

    # Step 3: Payment processing (mocked)
    payment = MagicMock()
    payment.status = PaymentStatus.COMPLETED

    # Step 4: Mark purchase completed
    purchase.status = PurchaseStatus.COMPLETED

    # Step 5: Fulfill purchase - provision service
    with patch("services.fulfillment.provision_purchase") as mock_provision:
        mock_provision.return_value = mock_service

        result = await fulfill_purchase(mock_db, purchase=purchase)

        # Verify service was provisioned
        mock_provision.assert_called_once()
        assert result == mock_service
        assert result.status.value == "active"
        assert result.user_id == mock_user.id

    # Step 6: Verify service has credentials
    assert mock_service.client_email is not None
    assert mock_service.protocol == "vmess"
