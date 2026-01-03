"""seed default app settings

Revision ID: 0021_seed_app_settings
Revises: 0020_add_allowed_protocols
Create Date: 2026-01-03

Populates app_settings with default values for dynamic config.
"""

import sqlalchemy as sa
from alembic import op

# revision identifiers
revision = "0021_seed_app_settings"
down_revision = "0020_add_allowed_protocols"
branch_labels = None
depends_on = None


# Default settings to seed
DEFAULT_SETTINGS = [
    # === SALES ===
    {
        "key": "pricing.profit_margin",
        "value": "10",
        "setting_type": "int",
        "category": "💰 Sales",
        "description": "Default profit margin percentage",
        "default_value": "10",
    },
    {
        "key": "pricing.currency_rate",
        "value": "60000",
        "setting_type": "int",
        "category": "💰 Sales",
        "description": "Toman to Dollar rate",
        "default_value": "60000",
    },
    {
        "key": "sales.max_discount_percent",
        "value": "50",
        "setting_type": "int",
        "category": "💰 Sales",
        "description": "Maximum discount code percentage",
        "default_value": "50",
    },
    # === AI ===
    {
        "key": "ai.enabled",
        "value": "false",
        "setting_type": "bool",
        "category": "🤖 AI",
        "description": "Enable AI-powered features",
        "default_value": "false",
    },
    {
        "key": "ai.vision_enabled",
        "value": "false",
        "setting_type": "bool",
        "category": "🤖 AI",
        "description": "Enable AI image analysis for receipts",
        "default_value": "false",
    },
    {
        "key": "ai.provider",
        "value": "ollama",
        "setting_type": "string",
        "category": "🤖 AI",
        "description": "AI provider: ollama, gemini, openai",
        "default_value": "ollama",
    },
    # === PROTOCOLS ===
    {
        "key": "protocols.default",
        "value": "vless",
        "setting_type": "string",
        "category": "🔌 Protocols",
        "description": "Default VPN protocol",
        "default_value": "vless",
    },
    {
        "key": "protocols.allowed",
        "value": '["vless", "vmess", "trojan"]',
        "setting_type": "json",
        "category": "🔌 Protocols",
        "description": "Allowed protocols for new products",
        "default_value": '["vless", "vmess", "trojan"]',
    },
    {
        "key": "protocols.default_flow",
        "value": "xtls-rprx-vision",
        "setting_type": "string",
        "category": "🔌 Protocols",
        "description": "Default flow for VLESS",
        "default_value": "xtls-rprx-vision",
    },
    # === UX ===
    {
        "key": "ux.welcome_message",
        "value": "خوش آمدید! 👋",
        "setting_type": "string",
        "category": "✨ UX",
        "description": "Bot welcome message",
        "default_value": "خوش آمدید! 👋",
    },
    {
        "key": "ux.support_message",
        "value": "برای پشتیبانی با ما تماس بگیرید.",
        "setting_type": "string",
        "category": "✨ UX",
        "description": "Support section message",
        "default_value": "برای پشتیبانی با ما تماس بگیرید.",
    },
    {
        "key": "ux.maintenance_mode",
        "value": "false",
        "setting_type": "bool",
        "category": "✨ UX",
        "description": "Enable maintenance mode (blocks purchases)",
        "default_value": "false",
    },
    # === NOTIFICATIONS ===
    {
        "key": "notifications.expiry_hours",
        "value": "48",
        "setting_type": "int",
        "category": "🔔 Notifications",
        "description": "Hours before expiry to send reminder",
        "default_value": "48",
    },
    {
        "key": "notifications.low_traffic_gb",
        "value": "2",
        "setting_type": "int",
        "category": "🔔 Notifications",
        "description": "GB threshold for low traffic alert",
        "default_value": "2",
    },
    {
        "key": "notifications.admin_on_purchase",
        "value": "true",
        "setting_type": "bool",
        "category": "🔔 Notifications",
        "description": "Notify admins on new purchases",
        "default_value": "true",
    },
    # === SECURITY ===
    {
        "key": "security.rate_limit_per_minute",
        "value": "20",
        "setting_type": "int",
        "category": "🛡️ Security",
        "description": "Max requests per minute per user",
        "default_value": "20",
    },
    {
        "key": "security.ban_on_abuse",
        "value": "true",
        "setting_type": "bool",
        "category": "🛡️ Security",
        "description": "Auto-ban users who abuse rate limits",
        "default_value": "true",
    },
    # === PAYMENTS ===
    {
        "key": "payments.min_wallet_topup",
        "value": "50000",
        "setting_type": "int",
        "category": "💳 Payments",
        "description": "Minimum wallet top-up (Toman)",
        "default_value": "50000",
    },
    {
        "key": "payments.card_approval_timeout_hours",
        "value": "24",
        "setting_type": "int",
        "category": "💳 Payments",
        "description": "Hours before card payment expires",
        "default_value": "24",
    },
    # === SYSTEM ===
    {
        "key": "system.usage_sync_interval",
        "value": "300",
        "setting_type": "int",
        "category": "⚙️ System",
        "description": "Panel usage sync interval (seconds)",
        "default_value": "300",
    },
    {
        "key": "system.debug_mode",
        "value": "false",
        "setting_type": "bool",
        "category": "⚙️ System",
        "description": "Enable debug logging",
        "default_value": "false",
    },
]


def upgrade() -> None:
    # First, ensure the table has the new columns
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    columns = [c["name"] for c in inspector.get_columns("app_settings")]

    if "setting_type" not in columns:
        op.add_column("app_settings", sa.Column("setting_type", sa.String(20), nullable=True))
        op.execute("UPDATE app_settings SET setting_type = 'string' WHERE setting_type IS NULL")
        op.alter_column("app_settings", "setting_type", nullable=False, server_default="string")

    if "category" not in columns:
        op.add_column("app_settings", sa.Column("category", sa.String(50), nullable=True))
        op.execute("UPDATE app_settings SET category = '⚙️ System' WHERE category IS NULL")
        op.alter_column("app_settings", "category", nullable=False, server_default="⚙️ System")

    if "description" not in columns:
        op.add_column(
            "app_settings",
            sa.Column("description", sa.String(255), nullable=True, server_default=""),
        )

    if "is_sensitive" not in columns:
        op.add_column(
            "app_settings",
            sa.Column("is_sensitive", sa.Boolean(), nullable=True, server_default="false"),
        )

    if "default_value" not in columns:
        op.add_column("app_settings", sa.Column("default_value", sa.Text(), nullable=True))

    if "updated_by" not in columns:
        op.add_column("app_settings", sa.Column("updated_by", sa.BigInteger(), nullable=True))

    # Insert default settings (skip if key exists)
    for setting in DEFAULT_SETTINGS:
        op.execute(
            sa.text("""
                INSERT INTO app_settings (key, value, setting_type, category, description, default_value, is_sensitive)
                VALUES (:key, :value, :setting_type, :category, :description, :default_value, false)
                ON CONFLICT (key) DO NOTHING
            """),
            setting,
        )


def downgrade() -> None:
    # Remove seeded settings
    for setting in DEFAULT_SETTINGS:
        op.execute(
            sa.text("DELETE FROM app_settings WHERE key = :key"),
            {"key": setting["key"]},
        )

    # Don't drop columns - they might have user data
