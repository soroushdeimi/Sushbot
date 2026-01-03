"""
Security tests for RBAC and access control.

Tests:
- .env-based admin check (check_env_admin)
- Database-based admin check (check_admin_status)
- Admin decorator rejects non-admin users
- Admin decorator accepts valid admins
- Permission-based access control
- Level-based access control
- Silent vs non-silent rejection
- Negative testing: regular user attempting admin actions
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from utils.security import (
    AdminCheckResult,
    Permission,
    admin_required,
    check_admin_status,
    check_env_admin,
    sales_admin_required,
    super_admin_required,
    support_admin_required,
)


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def mock_update() -> MagicMock:
    """Create a mock Telegram Update object."""
    update = MagicMock()
    update.effective_user = MagicMock()
    update.effective_user.id = 12345
    update.effective_user.username = "testuser"
    update.callback_query = None
    update.message = MagicMock()
    update.message.reply_text = AsyncMock()
    return update


@pytest.fixture
def mock_callback_update() -> MagicMock:
    """Create a mock Telegram Update object with callback query."""
    update = MagicMock()
    update.effective_user = MagicMock()
    update.effective_user.id = 12345
    update.effective_user.username = "testuser"
    update.callback_query = MagicMock()
    update.callback_query.answer = AsyncMock()
    update.message = None
    return update


# =============================================================================
# TEST: .env-based admin check (check_env_admin)
# =============================================================================


def test_check_env_admin_super_admin():
    """Test that super_admin_telegram_id from .env is recognized as super_admin."""
    with patch("utils.security.settings") as mock_settings:
        mock_settings.is_super_admin.return_value = True
        mock_settings.is_env_admin.return_value = True

        result = check_env_admin(123456789)

        assert result.is_admin is True
        assert result.level == "super_admin"
        assert result.source == "env"
        # Super admin should have all permissions
        assert len(result.permissions) > 0


def test_check_env_admin_regular_admin():
    """Test that admin_ids from .env are recognized as admins."""
    with patch("utils.security.settings") as mock_settings:
        mock_settings.is_super_admin.return_value = False
        mock_settings.is_env_admin.return_value = True

        result = check_env_admin(987654321)

        assert result.is_admin is True
        assert result.level == "admin"
        assert result.source == "env"


def test_check_env_admin_not_in_env():
    """Test that users not in .env are correctly rejected."""
    with patch("utils.security.settings") as mock_settings:
        mock_settings.is_super_admin.return_value = False
        mock_settings.is_env_admin.return_value = False

        result = check_env_admin(111111111)

        assert result.is_admin is False
        assert result.reason == "not_in_env_admins"
        assert result.source == "env"


@pytest.fixture
def mock_context() -> MagicMock:
    """Create a mock Telegram context."""
    return MagicMock()


# =============================================================================
# TEST: check_admin_status
# =============================================================================


@pytest.mark.asyncio
async def test_check_admin_status_user_not_found():
    """Test that non-existent users are rejected."""
    with patch("database.session.get_db") as mock_get_db:
        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=None)

        async def mock_gen():
            yield mock_db

        mock_get_db.return_value = mock_gen()

        # Also patch check_env_admin to return False so it falls through to DB check
        with patch("utils.security.check_env_admin") as mock_env:
            mock_env.return_value = AdminCheckResult(is_admin=False, reason="not_in_env_admins", source="env")

            result = await check_admin_status(99999, check_env_first=False)

            assert result.is_admin is False
            assert result.reason == "user_not_found"


@pytest.mark.asyncio
async def test_check_admin_status_not_admin():
    """Test that regular users are correctly identified as non-admin."""
    with patch("database.session.get_db") as mock_get_db:
        # Create mock user with USER role
        mock_user = MagicMock()
        mock_user.role = MagicMock()
        mock_user.role.value = "user"

        # Need to mock the enum comparison
        from database.models import UserRole

        mock_user.role = UserRole.USER

        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=mock_user)

        async def mock_gen():
            yield mock_db

        mock_get_db.return_value = mock_gen()

        result = await check_admin_status(12345, check_env_first=False)

        assert result.is_admin is False
        assert result.reason == "not_admin"


@pytest.mark.asyncio
async def test_check_admin_status_valid_admin():
    """Test that admin users are correctly identified."""
    with patch("database.session.get_db") as mock_get_db:
        from database.models import UserRole
        from database.models.admin import AdminLevel

        # Create mock user with ADMIN role
        mock_user = MagicMock()
        mock_user.role = UserRole.ADMIN

        # Create mock admin record
        mock_admin = MagicMock()
        mock_admin.is_active = True
        mock_admin.level = AdminLevel.ADMIN
        mock_admin.permissions = '["manage_users", "manage_sales"]'

        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=mock_user)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_admin)
        mock_db.execute = AsyncMock(return_value=mock_result)

        async def mock_gen():
            yield mock_db

        mock_get_db.return_value = mock_gen()

        result = await check_admin_status(12345, check_env_first=False)

        assert result.is_admin is True
        assert result.level == "admin"
        assert "manage_users" in result.permissions
        assert "manage_sales" in result.permissions


@pytest.mark.asyncio
async def test_check_admin_status_inactive_admin():
    """Test that inactive admins are rejected."""
    with patch("database.session.get_db") as mock_get_db:
        from database.models import UserRole

        mock_user = MagicMock()
        mock_user.role = UserRole.ADMIN

        mock_admin = MagicMock()
        mock_admin.is_active = False  # Inactive admin

        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=mock_user)

        mock_result = MagicMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_admin)
        mock_db.execute = AsyncMock(return_value=mock_result)

        async def mock_gen():
            yield mock_db

        mock_get_db.return_value = mock_gen()

        result = await check_admin_status(12345, check_env_first=False)

        assert result.is_admin is False
        assert result.reason == "admin_inactive"


# =============================================================================
# TEST: @admin_required decorator
# =============================================================================


@pytest.mark.asyncio
async def test_admin_required_rejects_regular_user(mock_update, mock_context):
    """Test that @admin_required rejects non-admin users silently."""

    # Create handler decorated with @admin_required
    @admin_required()
    async def protected_handler(update, context):
        return "success"

    with patch("utils.security.check_admin_status") as mock_check:
        mock_check.return_value = AdminCheckResult(
            is_admin=False, reason="not_admin"
        )

        result = await protected_handler(mock_update, mock_context)

        assert result is None  # Handler should not execute
        mock_update.message.reply_text.assert_not_called()  # Silent rejection


@pytest.mark.asyncio
async def test_admin_required_accepts_admin(mock_update, mock_context):
    """Test that @admin_required accepts admin users."""

    @admin_required()
    async def protected_handler(update, context):
        return "success"

    with patch("utils.security.check_admin_status") as mock_check:
        mock_check.return_value = AdminCheckResult(
            is_admin=True, level="admin", permissions=set()
        )

        result = await protected_handler(mock_update, mock_context)

        assert result == "success"


@pytest.mark.asyncio
async def test_admin_required_non_silent_sends_message(mock_update, mock_context):
    """Test that @admin_required(silent=False) sends denial message."""

    @admin_required(silent=False, message="Access denied!")
    async def protected_handler(update, context):
        return "success"

    with patch("utils.security.check_admin_status") as mock_check:
        mock_check.return_value = AdminCheckResult(
            is_admin=False, reason="not_admin"
        )

        result = await protected_handler(mock_update, mock_context)

        assert result is None
        mock_update.message.reply_text.assert_called_once_with("Access denied!")


@pytest.mark.asyncio
async def test_admin_required_callback_query_denial(mock_callback_update, mock_context):
    """Test that @admin_required sends alert for callback queries."""

    @admin_required(silent=False, message="Not authorized!")
    async def protected_handler(update, context):
        return "success"

    with patch("utils.security.check_admin_status") as mock_check:
        mock_check.return_value = AdminCheckResult(
            is_admin=False, reason="not_admin"
        )

        result = await protected_handler(mock_callback_update, mock_context)

        assert result is None
        mock_callback_update.callback_query.answer.assert_called_once_with(
            "Not authorized!", show_alert=True
        )


# =============================================================================
# TEST: Level-based access control
# =============================================================================


@pytest.mark.asyncio
async def test_admin_required_level_check_pass(mock_update, mock_context):
    """Test that level requirement passes when user has correct level."""

    @admin_required(level="super_admin")
    async def protected_handler(update, context):
        return "success"

    with patch("utils.security.check_admin_status") as mock_check:
        mock_check.return_value = AdminCheckResult(
            is_admin=True, level="super_admin", permissions=set()
        )

        result = await protected_handler(mock_update, mock_context)

        assert result == "success"


@pytest.mark.asyncio
async def test_admin_required_level_check_fail(mock_update, mock_context):
    """Test that level requirement fails when user has wrong level."""

    @admin_required(level="super_admin")
    async def protected_handler(update, context):
        return "success"

    with patch("utils.security.check_admin_status") as mock_check:
        mock_check.return_value = AdminCheckResult(
            is_admin=True, level="support", permissions=set()
        )

        result = await protected_handler(mock_update, mock_context)

        assert result is None  # Rejected due to wrong level


@pytest.mark.asyncio
async def test_admin_required_multiple_levels(mock_update, mock_context):
    """Test that multiple allowed levels work correctly."""

    @admin_required(level=["admin", "super_admin"])
    async def protected_handler(update, context):
        return "success"

    with patch("utils.security.check_admin_status") as mock_check:
        # Test with admin level
        mock_check.return_value = AdminCheckResult(
            is_admin=True, level="admin", permissions=set()
        )
        result = await protected_handler(mock_update, mock_context)
        assert result == "success"

        # Test with super_admin level
        mock_check.return_value = AdminCheckResult(
            is_admin=True, level="super_admin", permissions=set()
        )
        result = await protected_handler(mock_update, mock_context)
        assert result == "success"


# =============================================================================
# TEST: Permission-based access control
# =============================================================================


@pytest.mark.asyncio
async def test_admin_required_permission_check_pass(mock_update, mock_context):
    """Test that permission requirement passes when user has permission."""

    @admin_required(permission=Permission.MANAGE_SALES)
    async def protected_handler(update, context):
        return "success"

    with patch("utils.security.check_admin_status") as mock_check:
        mock_check.return_value = AdminCheckResult(
            is_admin=True, level="sales", permissions={"manage_sales", "view_stats"}
        )

        result = await protected_handler(mock_update, mock_context)

        assert result == "success"


@pytest.mark.asyncio
async def test_admin_required_permission_check_fail(mock_update, mock_context):
    """Test that permission requirement fails when user lacks permission."""

    @admin_required(permission=Permission.BROADCAST)
    async def protected_handler(update, context):
        return "success"

    with patch("utils.security.check_admin_status") as mock_check:
        mock_check.return_value = AdminCheckResult(
            is_admin=True, level="support", permissions={"manage_support"}
        )

        result = await protected_handler(mock_update, mock_context)

        assert result is None  # Rejected due to missing permission


@pytest.mark.asyncio
async def test_super_admin_bypasses_permission_check(mock_update, mock_context):
    """Test that super_admin bypasses permission requirements."""

    @admin_required(permission=Permission.BROADCAST)
    async def protected_handler(update, context):
        return "success"

    with patch("utils.security.check_admin_status") as mock_check:
        mock_check.return_value = AdminCheckResult(
            is_admin=True, level="super_admin", permissions=set()  # No explicit permissions
        )

        result = await protected_handler(mock_update, mock_context)

        assert result == "success"  # Super admin bypasses permission check


# =============================================================================
# TEST: Shortcut decorators
# =============================================================================


@pytest.mark.asyncio
async def test_super_admin_required_decorator(mock_update, mock_context):
    """Test super_admin_required shortcut decorator."""

    @super_admin_required()
    async def protected_handler(update, context):
        return "success"

    with patch("utils.security.check_admin_status") as mock_check:
        # Should reject regular admin
        mock_check.return_value = AdminCheckResult(
            is_admin=True, level="admin", permissions=set()
        )
        result = await protected_handler(mock_update, mock_context)
        assert result is None

        # Should accept super_admin
        mock_check.return_value = AdminCheckResult(
            is_admin=True, level="super_admin", permissions=set()
        )
        result = await protected_handler(mock_update, mock_context)
        assert result == "success"


@pytest.mark.asyncio
async def test_sales_admin_required_decorator(mock_update, mock_context):
    """Test sales_admin_required shortcut decorator."""

    @sales_admin_required()
    async def protected_handler(update, context):
        return "success"

    with patch("utils.security.check_admin_status") as mock_check:
        # Should accept sales level with permission
        mock_check.return_value = AdminCheckResult(
            is_admin=True, level="sales", permissions={"manage_sales"}
        )
        result = await protected_handler(mock_update, mock_context)
        assert result == "success"


@pytest.mark.asyncio
async def test_support_admin_required_decorator(mock_update, mock_context):
    """Test support_admin_required shortcut decorator."""

    @support_admin_required()
    async def protected_handler(update, context):
        return "success"

    with patch("utils.security.check_admin_status") as mock_check:
        # Should accept support level with permission
        mock_check.return_value = AdminCheckResult(
            is_admin=True, level="support", permissions={"manage_support"}
        )
        result = await protected_handler(mock_update, mock_context)
        assert result == "success"


# =============================================================================
# TEST: Edge cases
# =============================================================================


@pytest.mark.asyncio
async def test_admin_required_no_effective_user(mock_context):
    """Test that @admin_required handles missing effective_user."""
    update = MagicMock()
    update.effective_user = None

    @admin_required()
    async def protected_handler(update, context):
        return "success"

    result = await protected_handler(update, mock_context)
    assert result is None


@pytest.mark.asyncio
async def test_admin_required_no_update_in_args(mock_context):
    """Test that @admin_required handles missing Update object."""

    @admin_required()
    async def protected_handler(some_arg, context):
        return "success"

    result = await protected_handler("not_an_update", mock_context)
    assert result is None


@pytest.mark.asyncio
async def test_admin_required_database_error(mock_update, mock_context):
    """Test that @admin_required handles database errors gracefully."""

    @admin_required()
    async def protected_handler(update, context):
        return "success"

    with patch("utils.security.check_admin_status") as mock_check:
        mock_check.return_value = AdminCheckResult(
            is_admin=False, reason="database_error"
        )

        result = await protected_handler(mock_update, mock_context)

        assert result is None  # Fail closed on errors


# =============================================================================
# NEGATIVE TESTING: Regular user attempting admin actions
# =============================================================================


@pytest.mark.asyncio
async def test_regular_user_clicking_admin_button(mock_callback_update, mock_context):
    """
    NEGATIVE TEST: Simulate a regular user clicking an admin button.

    This tests that a non-admin user attempting to access admin functionality
    is properly denied access without crashing the bot.
    """
    # Set up as a regular user (not in .env, not in database as admin)
    mock_callback_update.effective_user.id = 999999999  # Random user ID

    @admin_required(silent=False, message="⛔ Access denied!")
    async def admin_only_callback(update, context):
        return "admin_action_executed"

    with patch("utils.security.check_env_admin") as mock_env_check:
        with patch("utils.security.check_admin_status") as mock_db_check:
            # Both checks should fail
            mock_env_check.return_value = AdminCheckResult(
                is_admin=False, reason="not_in_env_admins", source="env"
            )
            mock_db_check.return_value = AdminCheckResult(
                is_admin=False, reason="not_admin", source="database"
            )

            result = await admin_only_callback(mock_callback_update, mock_context)

            # Assert access is denied
            assert result is None

            # Assert the denial message was sent
            mock_callback_update.callback_query.answer.assert_called_once_with(
                "⛔ Access denied!", show_alert=True
            )


@pytest.mark.asyncio
async def test_regular_user_silent_rejection(mock_update, mock_context):
    """
    NEGATIVE TEST: Regular user is silently rejected when silent=True.

    The bot should not crash and should not send any message.
    """
    mock_update.effective_user.id = 888888888  # Random user ID

    @admin_required(silent=True)  # Silent mode
    async def secret_admin_handler(update, context):
        return "secret_executed"

    with patch("utils.security.check_admin_status") as mock_check:
        mock_check.return_value = AdminCheckResult(
            is_admin=False, reason="not_admin", source="database"
        )

        result = await secret_admin_handler(mock_update, mock_context)

        # Assert access is denied
        assert result is None

        # Assert NO message was sent (silent rejection)
        mock_update.message.reply_text.assert_not_called()


@pytest.mark.asyncio
async def test_banned_admin_cannot_access(mock_update, mock_context):
    """
    NEGATIVE TEST: An admin who has been deactivated cannot access admin functions.
    """
    mock_update.effective_user.id = 777777777

    @admin_required()
    async def admin_handler(update, context):
        return "admin_executed"

    with patch("utils.security.check_admin_status") as mock_check:
        # Admin exists but is inactive
        mock_check.return_value = AdminCheckResult(
            is_admin=False, reason="admin_inactive", source="database"
        )

        result = await admin_handler(mock_update, mock_context)

        assert result is None


@pytest.mark.asyncio
async def test_user_with_wrong_permission_denied(mock_update, mock_context):
    """
    NEGATIVE TEST: Admin with insufficient permissions is denied access.
    """
    mock_update.effective_user.id = 666666666

    @admin_required(permission=Permission.BROADCAST)  # Requires BROADCAST permission
    async def broadcast_handler(update, context):
        return "broadcast_sent"

    with patch("utils.security.check_admin_status") as mock_check:
        # User is admin but only has support permission, not broadcast
        mock_check.return_value = AdminCheckResult(
            is_admin=True,
            level="support",
            permissions={"manage_support"},  # No BROADCAST permission
            source="database",
        )

        result = await broadcast_handler(mock_update, mock_context)

        assert result is None  # Denied due to missing permission


@pytest.mark.asyncio
async def test_log_unauthorized_access_attempt(mock_update, mock_context):
    """
    NEGATIVE TEST: Unauthorized access attempts are logged.
    """
    mock_update.effective_user.id = 555555555

    @admin_required()
    async def admin_handler(update, context):
        return "success"

    with patch("utils.security.check_admin_status") as mock_check:
        with patch("utils.security.logger") as mock_logger:
            mock_check.return_value = AdminCheckResult(
                is_admin=False, reason="not_admin", source="database"
            )

            result = await admin_handler(mock_update, mock_context)

            assert result is None

            # Verify that the attempt was logged
            mock_logger.debug.assert_called()
            log_call_args = str(mock_logger.debug.call_args)
            assert "555555555" in log_call_args or "not_admin" in log_call_args
