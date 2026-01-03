"""Application settings and configuration management."""

from __future__ import annotations

import secrets
from pathlib import Path
from typing import Final

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings with environment variable support."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Bot Configuration
    bot_token: str = Field(..., description="Telegram bot token")
    bot_username: str = Field(default="sushbotseller_bot", description="Bot username")
    webhook_url: str | None = Field(default=None, description="Webhook URL for production")
    webhook_port: int = Field(default=8443, description="Webhook port")

    # Database
    database_url: str = Field(
        ...,
        description="PostgreSQL database URL",
    )
    database_pool_size: int = Field(default=10, description="Database connection pool size")
    database_max_overflow: int = Field(default=20, description="Database max overflow")
    run_migrations_on_startup: bool = Field(
        default=True, description="Run Alembic migrations on startup"
    )

    # PasarGuard Integration
    pasarguard_api_url: str = Field(
        default="",
        description="PasarGuard panel URL (base URL, not /api). Note: Not used with direct DB access. Leave empty if using direct database access.",
    )
    pasarguard_username: str = Field(
        default="admin",
        description="PasarGuard panel username (deprecated: not used with direct DB access)",
    )
    pasarguard_password: str = Field(
        default="",
        description="PasarGuard panel password (deprecated: not used with direct DB access)",
    )
    pasarguard_node_id: int = Field(default=3, description="Default PasarGuard node ID")
    pasarguard_default_protocol: str = Field(default="vless", description="Default protocol")
    pasarguard_default_port: int = Field(default=8443, description="Default port")

    # Payment Gateways
    nowpayments_api_key: str | None = Field(default=None, description="NowPayments API key")
    nowpayments_ipn_secret: str | None = Field(default=None, description="NowPayments IPN secret")
    aqayepardakht_api_key: str | None = Field(default=None, description="Aqayepardakht API key")
    aqayepardakht_gateway_id: str | None = Field(
        default=None, description="Aqayepardakht gateway ID"
    )
    public_base_url: str | None = Field(
        default=None, description="Public base URL for webhook/callbacks (https://...)"
    )

    # Card-to-card
    card_to_card_number: str | None = Field(
        default=None, description="Destination card number for card-to-card payments"
    )
    card_to_card_owner: str | None = Field(
        default=None, description="Card owner name for card-to-card payments"
    )

    # Security
    secret_key: str = Field(
        default_factory=lambda: secrets.token_urlsafe(32),
        description="Secret key for encryption",
    )
    jwt_secret: str = Field(
        default_factory=lambda: secrets.token_urlsafe(32),
        description="JWT secret key",
    )
    encryption_key: str | None = Field(
        default=None,
        description="Fernet encryption key for panel credentials (base64-encoded). Generate with: python -c 'from utils.encryption import EncryptionManager; print(EncryptionManager.generate_key())'",
    )
    phone_verification_enabled: bool = Field(default=True, description="Enable phone verification")
    rate_limit_per_minute: int = Field(default=20, description="Rate limit per minute")

    # Admin Configuration
    super_admin_telegram_id: int = Field(..., description="Super admin Telegram user ID")
    admin_ids: list[int] = Field(
        default_factory=list,
        description="Comma-separated list of admin Telegram user IDs (in addition to super_admin)",
    )
    admin_channel_id: str | None = Field(default=None, description="Admin channel ID")

    @property
    def all_admin_ids(self) -> set[int]:
        """Get all admin IDs including super admin."""
        admins = set(self.admin_ids)
        if self.super_admin_telegram_id and self.super_admin_telegram_id != 0:
            admins.add(self.super_admin_telegram_id)
        return admins

    def is_env_admin(self, user_id: int) -> bool:
        """Check if user_id is in the .env admin list."""
        return user_id in self.all_admin_ids

    def is_super_admin(self, user_id: int) -> bool:
        """Check if user_id is the super admin from .env."""
        return user_id == self.super_admin_telegram_id

    # Channel Membership
    required_channel_username: str | None = Field(
        default=None,
        description="Required channel username for purchases",
    )
    required_channel_id: str | None = Field(default=None, description="Required channel ID")

    # Trial Settings
    trial_enabled: bool = Field(default=True, description="Enable trial accounts")
    trial_duration_days: int = Field(default=1, description="Trial duration in days")
    trial_traffic_gb: int = Field(default=5, description="Trial traffic in GB")

    # Usage Sync (PasarGuard DB -> bot DB)
    usage_sync_enabled: bool = Field(
        default=False, description="Enable periodic sync of usage from PasarGuard"
    )
    usage_sync_interval_seconds: int = Field(
        default=300, description="Usage sync interval in seconds"
    )
    usage_sync_batch_size: int = Field(default=50, description="Max services to sync per run")

    # Automation
    automation_enabled: bool = Field(default=True, description="Enable background automation jobs")
    expiry_reminder_enabled: bool = Field(default=True, description="Enable expiry reminders")
    expiry_reminder_threshold_hours: int = Field(
        default=48, description="Notify when expiry within threshold hours"
    )
    low_traffic_reminder_enabled: bool = Field(
        default=True, description="Enable low traffic reminders"
    )
    low_traffic_threshold_gb: int = Field(
        default=2, description="Notify when remaining traffic <= threshold GB"
    )
    payment_reconcile_enabled: bool = Field(
        default=False, description="Enable payment reconciliation for online gateways"
    )
    payment_reconcile_interval_seconds: int = Field(
        default=300, description="Reconcile interval in seconds"
    )

    # Web Panel
    web_panel_enabled: bool = Field(default=True, description="Enable web panel")
    web_panel_port: int = Field(default=8080, description="Web panel port")
    web_panel_host: str = Field(default="0.0.0.0", description="Web panel host")
    web_panel_secret_key: str = Field(
        default_factory=lambda: secrets.token_urlsafe(32),
        description="Web panel secret key",
    )

    # Logging
    log_level: str = Field(default="INFO", description="Log level")
    log_file: Path = Field(default=Path("logs/sushbotseller.log"), description="Log file path")

    # Redis
    redis_url: str = Field(default="redis://localhost:6379/0", description="Redis URL")
    redis_enabled: bool = Field(default=False, description="Enable Redis caching")

    # Timezone
    timezone: str = Field(default="Asia/Tehran", description="Application timezone")

    # Feature Flags
    subscription_version: bool = Field(
        default=False,
        description="Enable subscription version features",
    )
    reseller_enabled: bool = Field(default=False, description="Enable reseller features")
    bulk_purchase_enabled: bool = Field(default=True, description="Enable bulk purchases")

    # Affiliate / Referral (Premium)
    affiliate_enabled: bool = Field(default=True, description="Enable affiliate/referral program")
    affiliate_first_purchase_only: bool = Field(
        default=True, description="Reward only on the referred user's first completed purchase"
    )
    affiliate_commission_percent: int = Field(
        default=5, description="Affiliate commission percentage (0-100)"
    )
    affiliate_fixed_reward: int = Field(
        default=0, description="Fixed affiliate reward amount in IRR to add on top of percent"
    )
    affiliate_min_purchase_amount: int = Field(
        default=0, description="Minimum final_amount (IRR) to qualify for affiliate reward"
    )

    @property
    def base_dir(self) -> Path:
        """Get base directory of the project."""
        return Path(__file__).parent.parent

    @property
    def log_dir(self) -> Path:
        """Get log directory."""
        log_dir = self.base_dir / self.log_file.parent
        log_dir.mkdir(parents=True, exist_ok=True)
        return log_dir

    def model_post_init(self, __context: object) -> None:
        """Post-initialization validation."""
        # Ensure log directory exists
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # Validate payment gateways
        if not any([self.nowpayments_api_key, self.aqayepardakht_api_key]):
            import warnings

            warnings.warn("No payment gateway configured!", UserWarning)


# Global settings instance
settings: Final[Settings] = Settings()
