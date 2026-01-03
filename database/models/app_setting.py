"""Runtime app settings stored in DB (admin-managed).

Dynamic Configuration System - change settings via Telegram without restart.
"""

from __future__ import annotations

import json
from enum import Enum
from typing import Any

from sqlalchemy import Boolean, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class SettingType(str, Enum):
    """Setting value types for proper casting."""

    BOOL = "bool"
    INT = "int"
    FLOAT = "float"
    STRING = "string"
    JSON = "json"  # Dict or List
    LIST = "list"  # Comma-separated -> List[str]


class SettingCategory(str, Enum):
    """Setting categories for UI grouping."""

    SALES = "💰 Sales"
    AI = "🤖 AI"
    SECURITY = "🛡️ Security"
    UX = "✨ UX"
    PROTOCOLS = "🔌 Protocols"
    PAYMENTS = "💳 Payments"
    NOTIFICATIONS = "🔔 Notifications"
    SYSTEM = "⚙️ System"


class AppSetting(Base, TimestampMixin):
    """
    Dynamic application setting stored in database.

    Replaces hardcoded values for runtime-changeable config.
    """

    __tablename__ = "app_settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)

    # Metadata
    setting_type: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="string",
    )
    category: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        default="system",
    )
    description: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        default="",
    )

    # Security & validation
    is_sensitive: Mapped[bool] = mapped_column(Boolean, default=False)
    default_value: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Audit
    updated_by: Mapped[int | None] = mapped_column(nullable=True)

    def get_typed_value(self) -> Any:
        """Cast stored string to native Python type."""
        if not self.value:
            return self.default_value

        try:
            if self.setting_type == "bool":
                return self.value.lower() in ("true", "1", "yes", "on")
            elif self.setting_type == "int":
                return int(self.value)
            elif self.setting_type == "float":
                return float(self.value)
            elif self.setting_type == "json":
                return json.loads(self.value)
            elif self.setting_type == "list":
                if not self.value.strip():
                    return []
                return [v.strip() for v in self.value.split(",")]
            return self.value
        except (ValueError, json.JSONDecodeError):
            return self.value

    def set_typed_value(self, value: Any) -> None:
        """Convert native Python value to string for storage."""
        if self.setting_type == "bool":
            self.value = "true" if value else "false"
        elif self.setting_type == "json":
            self.value = json.dumps(value, ensure_ascii=False)
        elif self.setting_type == "list" and isinstance(value, list):
            self.value = ", ".join(str(v) for v in value)
        else:
            self.value = str(value)

    def validate(self, value: Any) -> tuple[bool, str | None]:
        """Validate value before setting."""
        try:
            if self.setting_type == "int":
                int(value)
            elif self.setting_type == "float":
                float(value)
            elif self.setting_type == "json" and isinstance(value, str):
                json.loads(value)
            return True, None
        except (ValueError, json.JSONDecodeError) as e:
            return False, f"Invalid {self.setting_type}: {e}"

    @property
    def display_value(self) -> str:
        """Get display-safe value (masks sensitive data)."""
        if self.is_sensitive and self.value:
            return "••••••••"
        return self.value or "(empty)"

    @property
    def emoji(self) -> str:
        """Get status emoji for bools."""
        if self.setting_type == "bool":
            return "✅" if self.get_typed_value() else "❌"
        return "📝"
