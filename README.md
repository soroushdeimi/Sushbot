# SushBotSeller

Telegram bot for selling VPN services. Supports PasarGuard and Marzban panels.

**Stack**: Python 3.12+ | SQLAlchemy 2.0 (async) | PostgreSQL | python-telegram-bot | FastAPI

## Quick Start

```bash
# Clone & setup
git clone <repo-url> && cd sushbotseller
python -m venv venv && source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Configure
cp .env.template .env
# Edit .env - set BOT_TOKEN, DATABASE_URL, SUPER_ADMIN_TELEGRAM_ID

# Database
alembic upgrade head

# Run
python -m bot.main
```

### Docker (recommended for prod)

```bash
docker compose up -d
docker compose logs -f sushbotseller
```

## Features

**Users**: Purchase VPN, manage services, free trials, wallet, affiliate referrals, support tickets, QR codes for configs

**Admins**: RBAC (Super Admin/Admin/Sales/Support), payment approval, user management, panel management, stats dashboard, reseller system

**Payments**: Card-to-Card (manual), NowPayments (crypto), Aqayepardakht

**Panels**: PasarGuard (direct DB), Marzban (HTTP API) — extensible via `VPNPanelInterface`

## Configuration

All config via `.env`. See [.env.template](.env.template) for full list.

**Required:**
```env
BOT_TOKEN=your_bot_token
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/sushbotseller
SUPER_ADMIN_TELEGRAM_ID=123456789  # Your Telegram ID. Set to 0 to auto-promote first user.
```

**Optional (examples):**
```env
NOWPAYMENTS_API_KEY=xxx
CARD_TO_CARD_NUMBER=6037-xxxx-xxxx-xxxx
TRIAL_TRAFFIC_GB=5
AFFILIATE_COMMISSION_PERCENT=5
```

## Project Structure

```
sushbotseller/
├── bot/           # Telegram bot entry point
├── handlers/      # Bot command/callback handlers
├── api/           # FastAPI admin panel + webhooks
├── database/      # SQLAlchemy models + migrations
├── services/      # Business logic (provisioning, payments, sync)
├── integrations/  # VPN panel clients (pasarguard/, marzban/)
├── utils/         # Helpers (i18n, encryption, security)
└── config/        # Settings, feature flags
```

## Admin Commands

```bash
# Service ops
/sync <service_id>       # Sync usage from panel
/renew <service_id> <days>
/addgb <service_id> <gb>
/rotate <service_id>     # Rotate credentials

# Payments
/payapprove <payment_id>
/payreject <payment_id>

# Users
/addbal <user_id> <amount>
/ban_user <user_id>
/user_info <user_id>

# Admin panel (GUI)
/admin
```

## Adding a New Panel

1. Create `integrations/yourpanel/service.py`
2. Implement `VPNPanelInterface` from `integrations/base.py`
3. Register in `integrations/factory.py`

```python
# Example usage
from integrations.factory import PanelFactory

panel_service = await PanelFactory.create_panel(panel)
try:
    await panel_service.create_user(username="user123", data_limit_gb=50)
finally:
    await panel_service.close()
```

## Database Migrations

```bash
alembic revision --autogenerate -m "add feature X"
alembic upgrade head
alembic downgrade -1  # rollback
```

## Testing

```bash
pytest                    # Run all
pytest tests/ -v          # Verbose
pytest --cov=. tests/     # With coverage
```

## Troubleshooting

| Issue | Fix |
|-------|-----|
| Bot not responding | Check `BOT_TOKEN`, verify bot is running, check `logs/` |
| DB connection failed | Verify `DATABASE_URL`, check PostgreSQL is up |
| Panel connection failed | Test via `/admin` → Panel Management → Test Connection |
| Payment webhook not working | Ensure `PUBLIC_BASE_URL` is correct and publicly accessible |

💡 **Protip**: Enable debug logging with `LOG_LEVEL=DEBUG` in `.env`

## API Docs

When running, Swagger UI at `http://localhost:8080/docs`

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md). TL;DR: Fork → branch → PR. Use type hints. No `print()`.

## License

AGPL-3.0
