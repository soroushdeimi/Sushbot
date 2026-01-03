"""Input validation utilities."""

from __future__ import annotations

import re
from typing import Any

from pydantic import BaseModel, EmailStr, Field, field_validator


def validate_email(email: str) -> bool:
    """Validate email format."""
    pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    return bool(re.match(pattern, email))


def validate_uuid(uuid_string: str) -> bool:
    """Validate UUID format."""
    pattern = r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
    return bool(re.match(pattern, uuid_string.lower()))


def validate_telegram_username(username: str) -> bool:
    """Validate Telegram username format."""
    if not username:
        return False
    pattern = r"^[a-zA-Z0-9_]{5,32}$"
    return bool(re.match(pattern, username))


def sanitize_input(text: str, max_length: int = 1000) -> str:
    """Sanitize user input."""
    if not text:
        return ""
    # Remove null bytes and control characters
    cleaned = "".join(char for char in text if ord(char) >= 32 or char == "\n" or char == "\t")
    # Limit length
    return cleaned[:max_length]


def validate_amount(amount: int | float, min_amount: int = 1000, max_amount: int = 100000000) -> bool:
    """Validate payment amount."""
    try:
        amount_int = int(amount)
        return min_amount <= amount_int <= max_amount
    except (ValueError, TypeError):
        return False


class PurchaseValidation(BaseModel):
    """Validation model for purchase requests."""

    product_id: int = Field(..., gt=0)
    quantity: int = Field(default=1, gt=0, le=10)
    discount_code: str | None = Field(default=None, max_length=50)

    @field_validator("discount_code")
    @classmethod
    def validate_discount_code(cls, v: str | None) -> str | None:
        """Validate discount code format."""
        if v is None:
            return None
        v = v.strip().upper()
        if not re.match(r"^[A-Z0-9]{3,50}$", v):
            raise ValueError("Invalid discount code format")
        return v


def validate_card_number(card_number: str) -> bool:
    """Validate Iranian card number (16 digits)."""
    cleaned = re.sub(r"\D", "", card_number)
    return len(cleaned) == 16 and cleaned.isdigit()


def validate_shaba_number(shaba: str) -> bool:
    """Validate Iranian SHABA number (26 digits starting with IR)."""
    if not shaba.upper().startswith("IR"):
        return False
    cleaned = re.sub(r"\D", "", shaba)
    return len(cleaned) == 24  # 2 letters + 24 digits

