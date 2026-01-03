"""Tests for utils/validators.py - input validation utilities."""

from __future__ import annotations

import pytest

from utils.validators import (
    PurchaseValidation,
    sanitize_input,
    validate_amount,
    validate_card_number,
    validate_email,
    validate_shaba_number,
    validate_telegram_username,
    validate_uuid,
)


class TestValidateEmail:
    """Tests for email validation."""

    def test_valid_email_simple(self):
        assert validate_email("user@example.com") is True

    def test_valid_email_with_subdomain(self):
        assert validate_email("user@mail.example.co.uk") is True

    def test_valid_email_with_plus(self):
        assert validate_email("user+tag@example.com") is True

    def test_valid_email_with_dots(self):
        assert validate_email("first.last@example.com") is True

    def test_invalid_email_no_at(self):
        assert validate_email("userexample.com") is False

    def test_invalid_email_no_domain(self):
        assert validate_email("user@") is False

    def test_invalid_email_no_tld(self):
        assert validate_email("user@example") is False

    def test_invalid_email_empty(self):
        assert validate_email("") is False


class TestValidateUUID:
    """Tests for UUID validation."""

    def test_valid_uuid_lowercase(self):
        assert validate_uuid("550e8400-e29b-41d4-a716-446655440000") is True

    def test_valid_uuid_uppercase(self):
        assert validate_uuid("550E8400-E29B-41D4-A716-446655440000") is True

    def test_valid_uuid_mixed_case(self):
        assert validate_uuid("550e8400-E29B-41d4-A716-446655440000") is True

    def test_invalid_uuid_wrong_format(self):
        assert validate_uuid("550e8400e29b41d4a716446655440000") is False

    def test_invalid_uuid_too_short(self):
        assert validate_uuid("550e8400-e29b-41d4-a716") is False

    def test_invalid_uuid_bad_chars(self):
        assert validate_uuid("xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx") is False


class TestValidateTelegramUsername:
    """Tests for Telegram username validation."""

    def test_valid_username_simple(self):
        assert validate_telegram_username("testuser") is True

    def test_valid_username_with_underscore(self):
        assert validate_telegram_username("test_user_123") is True

    def test_valid_username_numbers(self):
        assert validate_telegram_username("user12345") is True

    def test_valid_username_5_chars(self):
        assert validate_telegram_username("abcde") is True

    def test_valid_username_32_chars(self):
        assert validate_telegram_username("a" * 32) is True

    def test_invalid_username_too_short(self):
        assert validate_telegram_username("abcd") is False

    def test_invalid_username_too_long(self):
        assert validate_telegram_username("a" * 33) is False

    def test_invalid_username_special_chars(self):
        assert validate_telegram_username("user@name") is False

    def test_invalid_username_empty(self):
        assert validate_telegram_username("") is False


class TestSanitizeInput:
    """Tests for input sanitization."""

    def test_normal_text(self):
        assert sanitize_input("Hello World") == "Hello World"

    def test_text_with_newlines(self):
        assert sanitize_input("Line1\nLine2") == "Line1\nLine2"

    def test_text_with_tabs(self):
        assert sanitize_input("Col1\tCol2") == "Col1\tCol2"

    def test_removes_null_bytes(self):
        assert sanitize_input("Hello\x00World") == "HelloWorld"

    def test_removes_control_chars(self):
        assert sanitize_input("Hello\x01\x02World") == "HelloWorld"

    def test_respects_max_length(self):
        assert sanitize_input("a" * 100, max_length=10) == "a" * 10

    def test_empty_string(self):
        assert sanitize_input("") == ""


class TestValidateAmount:
    """Tests for payment amount validation."""

    def test_valid_amount_min(self):
        assert validate_amount(1000) is True

    def test_valid_amount_max(self):
        assert validate_amount(100000000) is True

    def test_valid_amount_mid(self):
        assert validate_amount(50000) is True

    def test_valid_amount_float(self):
        assert validate_amount(50000.5) is True

    def test_invalid_amount_below_min(self):
        assert validate_amount(999) is False

    def test_invalid_amount_above_max(self):
        assert validate_amount(100000001) is False

    def test_invalid_amount_negative(self):
        assert validate_amount(-1000) is False

    def test_invalid_amount_string(self):
        assert validate_amount("invalid") is False

    def test_invalid_amount_none(self):
        assert validate_amount(None) is False

    def test_custom_min_max(self):
        assert validate_amount(500, min_amount=100, max_amount=1000) is True
        assert validate_amount(50, min_amount=100, max_amount=1000) is False


class TestPurchaseValidation:
    """Tests for PurchaseValidation Pydantic model."""

    def test_valid_purchase(self):
        pv = PurchaseValidation(product_id=1, quantity=2, discount_code="SUMMER20")
        assert pv.product_id == 1
        assert pv.quantity == 2
        assert pv.discount_code == "SUMMER20"

    def test_default_quantity(self):
        pv = PurchaseValidation(product_id=5)
        assert pv.quantity == 1

    def test_discount_code_uppercase(self):
        pv = PurchaseValidation(product_id=1, discount_code="summer20")
        assert pv.discount_code == "SUMMER20"

    def test_discount_code_none(self):
        pv = PurchaseValidation(product_id=1, discount_code=None)
        assert pv.discount_code is None

    def test_invalid_product_id_zero(self):
        with pytest.raises(ValueError):
            PurchaseValidation(product_id=0)

    def test_invalid_product_id_negative(self):
        with pytest.raises(ValueError):
            PurchaseValidation(product_id=-1)

    def test_invalid_quantity_zero(self):
        with pytest.raises(ValueError):
            PurchaseValidation(product_id=1, quantity=0)

    def test_invalid_quantity_too_high(self):
        with pytest.raises(ValueError):
            PurchaseValidation(product_id=1, quantity=11)

    def test_invalid_discount_code_format(self):
        with pytest.raises(ValueError):
            PurchaseValidation(product_id=1, discount_code="INVALID-CODE!")


class TestValidateCardNumber:
    """Tests for Iranian card number validation."""

    def test_valid_card_16_digits(self):
        assert validate_card_number("6037991234567890") is True

    def test_valid_card_with_dashes(self):
        assert validate_card_number("6037-9912-3456-7890") is True

    def test_valid_card_with_spaces(self):
        assert validate_card_number("6037 9912 3456 7890") is True

    def test_invalid_card_15_digits(self):
        assert validate_card_number("603799123456789") is False

    def test_invalid_card_17_digits(self):
        assert validate_card_number("60379912345678901") is False

    def test_invalid_card_letters(self):
        assert validate_card_number("6037991234567abc") is False


class TestValidateShabaNumber:
    """Tests for Iranian SHABA number validation."""

    def test_valid_shaba(self):
        assert validate_shaba_number("IR012345678901234567890123") is True

    def test_valid_shaba_lowercase(self):
        assert validate_shaba_number("ir012345678901234567890123") is True

    def test_invalid_shaba_no_ir_prefix(self):
        assert validate_shaba_number("012345678901234567890123") is False

    def test_invalid_shaba_too_short(self):
        assert validate_shaba_number("IR01234567890123456789") is False

    def test_invalid_shaba_too_long(self):
        assert validate_shaba_number("IR0123456789012345678901234") is False
