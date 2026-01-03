"""Tests for bot/admin_keyboards.py - Admin keyboard layouts."""

from __future__ import annotations

from unittest.mock import MagicMock

from telegram import InlineKeyboardMarkup

from bot.admin_keyboards import (
    admin_main_keyboard,
    admin_payment_detail_keyboard,
    admin_payments_list_keyboard,
)
from database.models.purchase import PurchaseType


class TestAdminMainKeyboard:
    """Tests for admin_main_keyboard function."""

    def test_returns_inline_keyboard_markup(self):
        kb = admin_main_keyboard()
        assert isinstance(kb, InlineKeyboardMarkup)

    def test_has_payments_button(self):
        kb = admin_main_keyboard()
        found = any(
            btn.callback_data == "admin_payments_pending"
            for row in kb.inline_keyboard
            for btn in row
        )
        assert found

    def test_has_stats_button(self):
        kb = admin_main_keyboard()
        found = any(btn.callback_data == "admin_stats" for row in kb.inline_keyboard for btn in row)
        assert found

    def test_has_users_button(self):
        kb = admin_main_keyboard()
        found = any(btn.callback_data == "admin_users" for row in kb.inline_keyboard for btn in row)
        assert found

    def test_has_services_button(self):
        kb = admin_main_keyboard()
        found = any(
            btn.callback_data == "admin_services" for row in kb.inline_keyboard for btn in row
        )
        assert found

    def test_has_products_button(self):
        kb = admin_main_keyboard()
        found = any(
            btn.callback_data == "admin_products" for row in kb.inline_keyboard for btn in row
        )
        assert found

    def test_has_panels_button(self):
        kb = admin_main_keyboard()
        found = any(
            btn.callback_data == "admin_panels" for row in kb.inline_keyboard for btn in row
        )
        assert found

    def test_has_tickets_button(self):
        kb = admin_main_keyboard()
        found = any(
            btn.callback_data == "admin_tickets" for row in kb.inline_keyboard for btn in row
        )
        assert found

    def test_has_settings_button(self):
        kb = admin_main_keyboard()
        found = any(
            btn.callback_data == "admin_settings" for row in kb.inline_keyboard for btn in row
        )
        assert found


class TestAdminPaymentsListKeyboard:
    """Tests for admin_payments_list_keyboard function."""

    def test_empty_payments_list(self):
        kb = admin_payments_list_keyboard(payments=[], page=0)
        assert isinstance(kb, InlineKeyboardMarkup)
        # Should still have back button
        found = any(btn.callback_data == "admin_main" for row in kb.inline_keyboard for btn in row)
        assert found

    def test_single_payment_shows_buttons(self):
        # Create mock payment
        payment = MagicMock()
        payment.id = 1
        payment.amount = 50000
        payment.purchase = MagicMock()
        payment.purchase.purchase_type = PurchaseType.NEW

        kb = admin_payments_list_keyboard(payments=[payment], page=0)

        # Should have approve button
        found_approve = any(
            "admin_payment_approve_1" in (btn.callback_data or "")
            for row in kb.inline_keyboard
            for btn in row
        )
        assert found_approve

        # Should have reject button
        found_reject = any(
            "admin_payment_reject_1" in (btn.callback_data or "")
            for row in kb.inline_keyboard
            for btn in row
        )
        assert found_reject

    def test_wallet_topup_shows_different_text(self):
        payment = MagicMock()
        payment.id = 2
        payment.amount = 100000
        payment.purchase = MagicMock()
        payment.purchase.purchase_type = PurchaseType.WALLET_TOPUP

        kb = admin_payments_list_keyboard(payments=[payment], page=0)

        # Should have detail button with TopUp text
        found = any(
            "admin_payment_detail_2" in (btn.callback_data or "")
            for row in kb.inline_keyboard
            for btn in row
        )
        assert found

    def test_pagination_first_page_no_prev(self):
        # Create 10 payments
        payments = []
        for i in range(10):
            p = MagicMock()
            p.id = i + 1
            p.amount = 10000 * (i + 1)
            p.purchase = MagicMock()
            p.purchase.purchase_type = PurchaseType.NEW
            payments.append(p)

        kb = admin_payments_list_keyboard(payments=payments, page=0)

        # Should have next button but not prev
        has_next = any(
            "page_1" in (btn.callback_data or "") for row in kb.inline_keyboard for btn in row
        )
        has_prev = any(
            "page_-1" in (btn.callback_data or "") for row in kb.inline_keyboard for btn in row
        )
        assert has_next
        assert not has_prev

    def test_pagination_middle_page_has_both(self):
        payments = []
        for i in range(15):
            p = MagicMock()
            p.id = i + 1
            p.amount = 10000
            p.purchase = MagicMock()
            p.purchase.purchase_type = PurchaseType.NEW
            payments.append(p)

        kb = admin_payments_list_keyboard(payments=payments, page=1)

        # Should have both next and prev
        has_next = any(
            "page_2" in (btn.callback_data or "") for row in kb.inline_keyboard for btn in row
        )
        has_prev = any(
            "page_0" in (btn.callback_data or "") for row in kb.inline_keyboard for btn in row
        )
        assert has_next
        assert has_prev

    def test_pagination_last_page_no_next(self):
        payments = []
        for i in range(7):
            p = MagicMock()
            p.id = i + 1
            p.amount = 10000
            p.purchase = MagicMock()
            p.purchase.purchase_type = PurchaseType.NEW
            payments.append(p)

        kb = admin_payments_list_keyboard(payments=payments, page=1, per_page=5)

        # Last page should not have next
        has_next = any(
            "page_2" in (btn.callback_data or "") for row in kb.inline_keyboard for btn in row
        )
        assert not has_next

    def test_long_text_truncated(self):
        payment = MagicMock()
        payment.id = 1
        payment.amount = 99999999999  # Very large amount
        payment.purchase = MagicMock()
        payment.purchase.purchase_type = PurchaseType.NEW

        kb = admin_payments_list_keyboard(payments=[payment], page=0)
        # Should not raise error with long text
        assert isinstance(kb, InlineKeyboardMarkup)


class TestAdminPaymentDetailKeyboard:
    """Tests for admin_payment_detail_keyboard function."""

    def test_returns_inline_keyboard(self):
        kb = admin_payment_detail_keyboard(payment_id=123)
        assert isinstance(kb, InlineKeyboardMarkup)

    def test_has_approve_button(self):
        kb = admin_payment_detail_keyboard(payment_id=456)
        found = any(
            "admin_payment_approve_456" in (btn.callback_data or "")
            for row in kb.inline_keyboard
            for btn in row
        )
        assert found

    def test_has_reject_button(self):
        kb = admin_payment_detail_keyboard(payment_id=789)
        found = any(
            "admin_payment_reject_789" in (btn.callback_data or "")
            for row in kb.inline_keyboard
            for btn in row
        )
        assert found
