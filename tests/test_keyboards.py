"""Tests for bot/keyboards.py - Telegram keyboard layouts."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from telegram import InlineKeyboardMarkup, ReplyKeyboardMarkup

from bot.keyboards import (
    main_menu_keyboard,
    main_reply_keyboard,
    product_detail_keyboard,
    support_keyboard,
    wallet_menu_keyboard,
)


class TestMainMenuKeyboard:
    """Tests for main_menu_keyboard function."""

    def test_returns_inline_keyboard_markup(self):
        with patch("bot.keyboards.is_enabled", return_value=True):
            kb = main_menu_keyboard()
            assert isinstance(kb, InlineKeyboardMarkup)

    def test_has_buttons_when_features_enabled(self):
        with patch("bot.keyboards.is_enabled", return_value=True):
            kb = main_menu_keyboard()
            # Should have at least some buttons
            assert len(kb.inline_keyboard) > 0

    def test_no_buttons_when_features_disabled(self):
        with patch("bot.keyboards.is_enabled", return_value=False):
            kb = main_menu_keyboard()
            # No buttons when all features disabled
            assert len(kb.inline_keyboard) == 0

    def test_purchase_button_when_enabled(self):
        def feature_check(name):
            return name == "purchase"

        with patch("bot.keyboards.is_enabled", side_effect=feature_check):
            kb = main_menu_keyboard()
            # Find purchase button
            found = False
            for row in kb.inline_keyboard:
                for btn in row:
                    if btn.callback_data == "purchase":
                        found = True
            assert found

    def test_with_user_object(self):
        user = MagicMock()
        user.language_code = "en"
        with patch("bot.keyboards.is_enabled", return_value=True):
            kb = main_menu_keyboard(user=user)
            assert isinstance(kb, InlineKeyboardMarkup)

    def test_trial_button_when_enabled(self):
        def feature_check(name):
            return name == "trial"

        with patch("bot.keyboards.is_enabled", side_effect=feature_check):
            kb = main_menu_keyboard()
            found = any(
                btn.callback_data == "trial"
                for row in kb.inline_keyboard
                for btn in row
            )
            assert found

    def test_support_button_when_enabled(self):
        def feature_check(name):
            return name == "support"

        with patch("bot.keyboards.is_enabled", side_effect=feature_check):
            kb = main_menu_keyboard()
            found = any(
                btn.callback_data == "support"
                for row in kb.inline_keyboard
                for btn in row
            )
            assert found


class TestMainReplyKeyboard:
    """Tests for main_reply_keyboard function."""

    def test_returns_reply_keyboard_markup(self):
        kb = main_reply_keyboard()
        assert isinstance(kb, ReplyKeyboardMarkup)

    def test_is_persistent(self):
        kb = main_reply_keyboard()
        assert kb.is_persistent is True

    def test_resize_keyboard(self):
        kb = main_reply_keyboard()
        assert kb.resize_keyboard is True

    def test_has_menu_button(self):
        kb = main_reply_keyboard()
        # Should have at least one button row
        assert len(kb.keyboard) > 0

    def test_with_user_object(self):
        user = MagicMock()
        user.language_code = "fa"
        kb = main_reply_keyboard(user=user)
        assert isinstance(kb, ReplyKeyboardMarkup)

    def test_has_input_placeholder(self):
        kb = main_reply_keyboard()
        assert kb.input_field_placeholder is not None


class TestWalletMenuKeyboard:
    """Tests for wallet_menu_keyboard function."""

    def test_returns_inline_keyboard(self):
        kb = wallet_menu_keyboard()
        assert isinstance(kb, InlineKeyboardMarkup)

    def test_has_balance_button(self):
        kb = wallet_menu_keyboard()
        found = any(
            btn.callback_data == "wallet_balance"
            for row in kb.inline_keyboard
            for btn in row
        )
        assert found

    def test_has_topup_button(self):
        kb = wallet_menu_keyboard()
        found = any(
            btn.callback_data == "wallet_topup"
            for row in kb.inline_keyboard
            for btn in row
        )
        assert found

    def test_has_gift_code_button(self):
        kb = wallet_menu_keyboard()
        found = any(
            btn.callback_data == "gift_code"
            for row in kb.inline_keyboard
            for btn in row
        )
        assert found

    def test_has_back_button(self):
        kb = wallet_menu_keyboard()
        found = any(
            btn.callback_data == "menu"
            for row in kb.inline_keyboard
            for btn in row
        )
        assert found

    def test_with_user_language(self):
        user = MagicMock()
        user.language_code = "en"
        kb = wallet_menu_keyboard(user=user)
        assert isinstance(kb, InlineKeyboardMarkup)


class TestSupportKeyboard:
    """Tests for support_keyboard function."""

    def test_returns_inline_keyboard(self):
        kb = support_keyboard()
        assert isinstance(kb, InlineKeyboardMarkup)

    def test_has_create_ticket_button(self):
        kb = support_keyboard()
        found = any(
            btn.callback_data == "create_ticket"
            for row in kb.inline_keyboard
            for btn in row
        )
        assert found

    def test_has_my_tickets_button(self):
        kb = support_keyboard()
        found = any(
            btn.callback_data == "my_tickets"
            for row in kb.inline_keyboard
            for btn in row
        )
        assert found

    def test_has_back_button(self):
        kb = support_keyboard()
        found = any(
            btn.callback_data == "menu"
            for row in kb.inline_keyboard
            for btn in row
        )
        assert found


class TestProductDetailKeyboard:
    """Tests for product_detail_keyboard function."""

    def test_returns_inline_keyboard(self):
        kb = product_detail_keyboard(product_id=1)
        assert isinstance(kb, InlineKeyboardMarkup)

    def test_has_purchase_button_with_product_id(self):
        kb = product_detail_keyboard(product_id=42)
        found = any(
            "confirm_purchase_42" in (btn.callback_data or "")
            for row in kb.inline_keyboard
            for btn in row
        )
        assert found

    def test_has_discount_code_button(self):
        kb = product_detail_keyboard(product_id=1)
        found = any(
            "discount" in (btn.callback_data or "")
            for row in kb.inline_keyboard
            for btn in row
        )
        assert found

    def test_with_user_object(self):
        user = MagicMock()
        user.language_code = "en"
        kb = product_detail_keyboard(product_id=5, user=user)
        assert isinstance(kb, InlineKeyboardMarkup)
