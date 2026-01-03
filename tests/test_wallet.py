"""Tests for services/wallet.py - wallet operations."""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from database.models import WalletTxType
from services.wallet import apply_wallet_tx


class TestApplyWalletTx:
    """Tests for apply_wallet_tx function."""

    @pytest.fixture
    def mock_db(self):
        """Create a mock async database session."""
        db = AsyncMock()
        db.commit = AsyncMock()
        db.refresh = AsyncMock()
        db.add = MagicMock()
        return db

    @pytest.fixture
    def mock_user(self):
        """Create a mock user with balance."""
        user = MagicMock()
        user.id = 12345
        user.balance = Decimal("50000")
        return user

    @pytest.mark.asyncio
    async def test_topup_increases_balance(self, mock_db, mock_user):
        """Test that top-up increases user balance."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_user
        mock_db.execute = AsyncMock(return_value=mock_result)

        await apply_wallet_tx(
            mock_db,
            user_id=12345,
            amount=10000,
            tx_type=WalletTxType.TOPUP,
            ref="test_ref",
            note="Test topup",
        )

        # Balance should be updated
        assert mock_user.balance == 60000  # 50000 + 10000
        # Transaction should be added
        mock_db.add.assert_called_once()
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_debit_decreases_balance(self, mock_db, mock_user):
        """Test that debit decreases user balance."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_user
        mock_db.execute = AsyncMock(return_value=mock_result)

        await apply_wallet_tx(
            mock_db,
            user_id=12345,
            amount=-20000,  # Negative for debit
            tx_type=WalletTxType.PURCHASE,
        )

        assert mock_user.balance == 30000  # 50000 - 20000

    @pytest.mark.asyncio
    async def test_insufficient_balance_raises(self, mock_db, mock_user):
        """Test that insufficient balance raises ValueError."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_user
        mock_db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(ValueError, match="Insufficient balance"):
            await apply_wallet_tx(
                mock_db,
                user_id=12345,
                amount=-100000,  # More than balance
                tx_type=WalletTxType.PURCHASE,
            )

    @pytest.mark.asyncio
    async def test_user_not_found_raises(self, mock_db):
        """Test that missing user raises ValueError."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        mock_db.execute = AsyncMock(return_value=mock_result)

        with pytest.raises(ValueError, match="User not found"):
            await apply_wallet_tx(
                mock_db,
                user_id=99999,
                amount=1000,
                tx_type=WalletTxType.TOPUP,
            )

    @pytest.mark.asyncio
    async def test_transaction_has_correct_fields(self, mock_db, mock_user):
        """Test that created transaction has correct fields."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_user
        mock_db.execute = AsyncMock(return_value=mock_result)

        await apply_wallet_tx(
            mock_db,
            user_id=12345,
            amount=5000,
            tx_type=WalletTxType.REFERRAL_REWARD,
            ref="affiliate_123",
            note="Affiliate reward",
        )

        # Get the transaction that was added
        call_args = mock_db.add.call_args[0][0]
        assert call_args.user_id == 12345
        assert call_args.amount == 5000
        assert call_args.tx_type == WalletTxType.REFERRAL_REWARD
        assert call_args.ref == "affiliate_123"
        assert call_args.note == "Affiliate reward"
        assert call_args.balance_after == 55000  # 50000 + 5000

    @pytest.mark.asyncio
    async def test_zero_amount_allowed(self, mock_db, mock_user):
        """Test that zero amount is allowed (edge case)."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_user
        mock_db.execute = AsyncMock(return_value=mock_result)

        # Zero amount shouldn't raise
        await apply_wallet_tx(
            mock_db,
            user_id=12345,
            amount=0,
            tx_type=WalletTxType.ADJUST,
        )

        assert mock_user.balance == 50000  # Unchanged

    @pytest.mark.asyncio
    async def test_exact_balance_debit_succeeds(self, mock_db, mock_user):
        """Test debiting exact balance succeeds (boundary case)."""
        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = mock_user
        mock_db.execute = AsyncMock(return_value=mock_result)

        await apply_wallet_tx(
            mock_db,
            user_id=12345,
            amount=-50000,  # Exactly the balance
            tx_type=WalletTxType.PURCHASE,
        )

        assert mock_user.balance == 0
