# SushBotSeller

Telegram bot that automates VPN service sales. Handles the entire flow: product catalog, payments, panel provisioning, usage tracking.

```bash
cp .env.template .env && $EDITOR .env
docker compose up -d
```

That's it. Bot is running.

---

## Table of Contents

- [Architecture](#architecture)
- [Quick Start](#quick-start)
- [Configuration](#configuration)
- [Features](#features)
  - [Protocol Selection](#protocol-selection)
  - [Dynamic Config](#dynamic-config)
  - [Admin Commands](#admin-commands)
  - [Background Jobs](#background-jobs)
- [Panel Integrations](#panel-integrations)
- [Payments](#payments)
- [Database](#database)
- [Development](#development)
- [Security](#security)
- [Troubleshooting](#troubleshooting)

---

## Architecture

```
Stack:
  Bot Framework    python-telegram-bot 21.x (async)
  API              FastAPI + Uvicorn
  ORM              SQLAlchemy 2.0 (async, asyncpg)
  Database         PostgreSQL 15+
  Build            Hatchling
  Migrations       Alembic

Layout:
  bot/             Entry point, keyboards
  handlers/        Commands, callbacks, message handlers
  api/             REST API (admin panel, webhooks)
  database/        Models, migrations
  services/        Business logic
  integrations/    VPN panel clients (Marzban, PasarGuard)
  config/          Settings, feature flags
  utils/           Helpers (encryption, i18n, QR)
```

---

## Quick Start

### Docker (recommended)

```bash
git clone <repo> && cd sushbotseller
cp .env.template .env
# Edit: BOT_TOKEN, DATABASE_URL, SUPER_ADMIN_TELEGRAM_ID (minimum)
docker compose up -d
docker compose logs -f sushbotseller
```

### Manual

```bash
python3.12 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.template .env && $EDITOR .env
alembic upgrade head
python -m bot.main
```

> If SUPER_ADMIN_TELEGRAM_ID is set to 0, the first user to /start becomes super admin. Use this for fresh deployments only.

---

## Configuration

### Required

```env
BOT_TOKEN=123456:ABCxyz
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/sushbotseller
SUPER_ADMIN_TELEGRAM_ID=123456789
```

### Payments

At least one payment method must be configured:

```env
# Card-to-card (manual approval by admin)
CARD_TO_CARD_NUMBER=6037-xxxx-xxxx-xxxx
CARD_TO_CARD_OWNER=Card Holder Name

# Crypto via NowPayments.io
NOWPAYMENTS_API_KEY=xxx
NOWPAYMENTS_IPN_SECRET=xxx

# Iranian gateway
AQAYEPARDAKHT_API_KEY=xxx
AQAYEPARDAKHT_GATEWAY_ID=xxx
```

### Feature Flags

Kill switches for every major feature. All boolean, all optional:

```env
FEATURE_PURCHASE=true            # Core purchase flow
FEATURE_TRIAL=true               # Free trials
FEATURE_PROTOCOL_SELECTION=true  # Let users pick protocol
FEATURE_WALLET=true              # User wallet system
FEATURE_AFFILIATE=true           # Referral commissions
FEATURE_DISCOUNT=true            # Promo codes
FEATURE_SUPPORT=true             # Ticket system
FEATURE_PHONE_VERIFICATION=false # Require phone number
FEATURE_CHANNEL_MEMBERSHIP=false # Require Telegram channel join
FEATURE_PAY_CARD_TO_CARD=true    # Manual card payment
FEATURE_PAY_NOWPAYMENTS=true     # Crypto
FEATURE_PAY_AQAYEPARDAKHT=true   # Iranian gateway
FEATURE_RESELLER=false           # Reseller mode
FEATURE_REFUNDS=false            # Allow refunds
FEATURE_SERVICE_REMOVAL=false    # Allow service deletion
FEATURE_SERVICE_TRANSFER=false   # Allow ownership transfer
```

Full list: 35 flags in `config/features.py`.

---

## Features

### Protocol Selection

Users choose their VPN protocol (VLESS, VMess, Trojan, Shadowsocks) before checkout.

Enable per product:

```sql
UPDATE products SET allowed_protocols = '["vless", "vmess", "trojan"]' WHERE id = 1;
```

Or via Admin Panel: Products, Edit, set allowed_protocols.

Disable globally:

```env
FEATURE_PROTOCOL_SELECTION=false
```

> Marzban's API expects lowercase protocol names. The bot normalizes automatically, but if you're hitting the API directly, use `vless` not `VLESS`.

Protocol aliases:
- `ss` maps to `shadowsocks`
- `wg` maps to `wireguard`

Single-protocol products skip the selection step entirely.

---

### Dynamic Config

Edit settings from Telegram without touching .env or restarting the bot.

Access: `/settings` (admin only)

Categories:
- Sales: profit margin, currency rate, min/max order
- AI: vision toggle, provider selection
- Protocols: default protocol, allowed list
- Security: rate limits, auto-ban thresholds
- Notifications: expiry warning hours, low traffic threshold
- System: sync interval, debug mode

Programmatic access:

```python
from services.config_manager import config

# Read (cached in memory)
margin = await config.get("pricing.profit_margin", default=10)

# Write (persists to DB, updates cache)
await config.set("ai.enabled", True, updated_by=admin_id)

# Toggle boolean
await config.toggle("ux.maintenance_mode", updated_by=admin_id)
```

Settings are stored in `app_settings` table. Changes take effect immediately without restart.

---

### Admin Commands

User commands:

```
/start           Register, show main menu
/menu            Main menu
/help            Help text
/services        List my services
/trial           Get free trial
/support         Open support ticket
/tickets         View my tickets
/topen <subj>    Create ticket
/treply <id> <m> Reply to ticket
/tclose <id>     Close ticket
/setpass <pass>  Set service password
```

Admin commands:

```
/admin                          Full admin panel UI
/stats                          Sales and revenue stats
/addbal <user_id> <amount>      Add wallet balance
/sync <service_id>              Sync usage from panel
/renew <service_id> <days>      Extend service
/addgb <service_id> <gb>        Add traffic
/rotate <service_id>            Rotate credentials
/payapprove <payment_id>        Approve card payment
/payreject <payment_id>         Reject card payment
/setcard <number> <owner>       Set card-to-card details
/setnowpay <api_key>            Set NowPayments key
/setaqaye <api_key> <gw_id>     Set Aqayepardakht
/setfaq <text>                  Update FAQ content
/settutorial <text>             Update tutorial content
/refund <payment_id>            Process refund
/removesvc <service_id>         Delete service
/transfersvc <svc_id> <user_id> Transfer ownership
/settings                       Dynamic config editor
```

Admin Panel UI (`/admin`):
- Pending payments with photo preview
- Panel management (add, test, delete)
- User management (search, ban, view history)
- Service ops (sync, renew, add GB, rotate)
- Product CRUD with protocol configs
- Ticket management
- Stats dashboard

---

### Background Jobs

Defined in `services/automation.py`:

```
job_expiry_and_traffic_reminders   Warns users before expiry/low traffic
job_payment_reconcile              Checks pending gateway payments
job_cleanup                        Purges stale data
job_admin_daily_report             Daily summary to admin channel
```

Usage sync runs periodically to pull stats from panels.

---

## Panel Integrations

Supported panels:

| Panel     | Method          | Notes                              |
|-----------|-----------------|-----------------------------------|
| Marzban   | HTTP API        | Full CRUD, stats, multi-node      |
| PasarGuard| Direct DB access| Requires DB credentials           |

Adding a new panel:

1. Create `integrations/yourpanel/service.py`
2. Implement `VPNPanelInterface`:

```python
class YourPanelService(VPNPanelInterface):
    async def create_user(self, username: str, data_limit_bytes: int, ...) -> dict
    async def get_user(self, username: str) -> dict | None
    async def delete_user(self, username: str) -> bool
    async def update_user(self, username: str, **kwargs) -> dict
    async def get_user_stats(self, username: str) -> dict
    async def test_connection(self) -> bool
    async def get_system_stats(self) -> dict
```

3. Register in `integrations/factory.py`

Usage:

```python
from integrations.factory import PanelFactory

panel = await PanelFactory.create_panel(db_panel)
await panel.create_user(username="user123", data_limit_bytes=50*1024**3)
```

---

## Payments

Three gateways supported:

**Card-to-Card**: User sends payment, uploads receipt photo. Admin approves/rejects manually.

**NowPayments**: Crypto payments. BTC, ETH, USDT, etc. Automatic via IPN webhook.

**Aqayepardakht**: Iranian payment gateway. Automatic callback.

Payment flow:
1. User selects product
2. User picks payment method
3. Payment created in `pending` state
4. Gateway webhook or admin action moves to `completed`/`failed`
5. On `completed`, service provisioning triggers automatically

> Webhook URL must be publicly accessible. Set PUBLIC_BASE_URL correctly.

---

## Database

Migrations via Alembic:

```bash
alembic upgrade head                        # Apply all
alembic revision --autogenerate -m "desc"   # Generate new
alembic downgrade -1                        # Rollback one
```

Key tables:

```
users              Telegram users, phone, ban status
admins             Admin accounts with roles
products           VPN packages, pricing, protocols
product_categories Category grouping
services           Active subscriptions
purchases          Orders linking user, product, payment
payments           Payment records with gateway details
panels             VPN panel configs (encrypted creds)
app_settings       Dynamic config (key-value)
wallet_transactions User wallet history
discount_codes     Promo codes
support_tickets    Ticket system
support_messages   Ticket replies
trial_accounts     Trial tracking
audit_logs         Admin action audit trail
```

---

## Development

### Setup

```bash
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.template .env
alembic upgrade head
```

### Testing

```bash
pytest                                       # All 91+ tests
pytest tests/test_flows.py -v               # Unit tests
pytest tests/test_protocol_integration.py -v # Integration
pytest --cov=. tests/                        # Coverage
```

Integration tests use `respx` to mock HTTP. No real panel needed.

### Linting

```bash
ruff check .
black --check .
mypy .
```

### Code Style

- Python 3.12+ with type hints on all functions
- Async/await for all I/O
- Loguru for logging (no print statements)
- Google-style docstrings for public functions

### API Docs

Swagger UI at `http://localhost:8080/docs` when running.

Key endpoints:

```
POST /api/auth/login     Admin login
GET  /api/users          List users
GET  /api/services       List services
POST /api/panels         Add panel
GET  /api/reports/revenue Revenue stats
```

---

## Security

Secrets:
- Never commit .env (gitignored)
- Rotate secrets regularly
- Generate encryption key: `python -c "from utils.encryption import EncryptionManager; print(EncryptionManager.generate_key())"`

> If you lose the encryption key, panel credentials in DB are unrecoverable. Back it up.

Panel credentials are encrypted at rest (Fernet). Decrypted only in-memory when needed.

Payment webhooks:
- Validate all IPN callbacks
- Verify signatures
- Use HTTPS
- Idempotency keys prevent double-processing

Deployment:
- Docker runs as non-root by default
- Don't expose port 8080 directly, use nginx/caddy with TLS
- Restrict DB access to app server only

---

## Troubleshooting

| Problem                  | Fix                                                    |
|--------------------------|--------------------------------------------------------|
| Bot not responding       | Check BOT_TOKEN. Run docker compose logs.              |
| DB connection failed     | Verify DATABASE_URL. Is Postgres running?              |
| Panel API errors         | Check panel URL/credentials. Test via /admin, Panels.  |
| Payments stuck pending   | Verify PUBLIC_BASE_URL is correct and publicly reachable. |
| "Feature disabled" error | Check FEATURE_* flags in .env or app_settings table.  |
| Protocol picker missing  | Set allowed_protocols on the product.                  |

Enable debug logging:

```env
LOG_LEVEL=DEBUG
```

---

## Feature Manifest

Complete list of features found in codebase scan:

```
User Features:
  - Registration and main menu
  - Product browsing and purchase
  - Protocol selection (VLESS/VMess/Trojan/Shadowsocks)
  - Discount code application
  - Wallet (balance, top-up, history)
  - Affiliate referrals with commission
  - Gift code redemption
  - Service management (view, renew, rotate)
  - QR code generation for configs
  - Free trials
  - Support ticket system
  - FAQ and tutorial content
  - Channel membership checks
  - Phone verification

Admin Features:
  - Full admin panel UI via /admin
  - User management (search, ban, balance)
  - Service ops (sync, renew, addgb, rotate)
  - Payment approval/rejection
  - Panel management (CRUD, test connection)
  - Product management with protocol configs
  - Ticket management
  - Revenue and stats reporting
  - Dynamic config editor
  - Reseller mode
  - Refunds
  - Service transfers

Integrations:
  - Marzban (HTTP API)
  - PasarGuard (direct DB)
  - NowPayments (crypto)
  - Aqayepardakht (Iranian gateway)
  - Card-to-Card (manual)

Background Jobs:
  - Expiry and traffic reminders
  - Payment reconciliation
  - Data cleanup
  - Daily admin reports
  - Usage sync from panels

Database Models (21):
  - User, Admin, UserState
  - Product, ProductCategory
  - Service, Purchase, Payment
  - Panel, DiscountCode
  - WalletTransaction, TrialAccount
  - SupportTicket, SupportMessage
  - AppSetting, ServiceConfiguration
  - ResellerPricing, ResellerQuota
  - AuditLog

Feature Flags (35):
  See config/features.py for full list.
```

---

## License

MIT. See LICENSE.

---

## Contributing

Fork, branch, PR. Type hints required. No print() debugging. See CONTRIBUTING.md.

AGPL-3.0
