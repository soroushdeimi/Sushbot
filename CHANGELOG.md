# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)
Versioning: [Semantic Versioning](https://semver.org/)

---

## [1.0.0] - 2026-01-03

Major release. Dynamic configuration, protocol selection, feature flags.

**Tests:** 91 passing  
**Security:** Bandit clean, Docker hardened

### Added

**Dynamic Config**

Runtime-editable settings stored in database. No restarts required.

- `/settings` command for Telegram-based config editing
- Categories: Sales, AI, Protocols, Security, Notifications, System
- Bool settings toggle on click. Input validation enforced.
- In-memory cache with hot reload on write.

```python
from services.config_manager import config
margin = await config.get("pricing.profit_margin", default=10)
await config.set("ai.enabled", True, updated_by=admin_id)
```

**Protocol Selection**

Users choose VPN protocol (VLESS, VMess, Trojan) before checkout.

- Per-product configuration via `allowed_protocols` field
- Multi-protocol products show picker, single-protocol skips to payment
- Feature flag: `FEATURE_PROTOCOL_SELECTION`

```sql
UPDATE products SET allowed_protocols = '["vless", "vmess", "trojan"]' WHERE id = 1;
```

**Feature Flags**

35 feature toggles via environment variables:

```env
FEATURE_PROTOCOL_SELECTION=false
FEATURE_TRIAL=false
FEATURE_RESELLER=true
```

**Integration Tests**

- HTTP mocking via `respx` (no real panels needed)
- Protocol normalization coverage
- Panel compatibility tests

### Security

- Bandit scan: zero findings
- 91 tests passing (unit + integration)
- Docker: `read_only`, `no-new-privileges`, non-root user
- Protocol names normalized to lowercase before API calls

### Fixed

- `wg` alias now maps to `wireguard`
- VLESS flow parameter (`xtls-rprx-vision`) only set for VLESS
- VMess no longer receives flow parameter
- Protocol case sensitivity issues resolved

### Migration

> Run migrations before starting the new version.

```bash
alembic upgrade head
docker compose down && docker compose up -d
```

Verify settings seeded:

```bash
docker compose exec sushbotseller python -c "
from services.config_manager import config
import asyncio
print(asyncio.run(config.get('pricing.profit_margin')))
"
```

### Dependencies

- Added: `respx>=0.22.0` (dev, integration tests)

---

## [Unreleased]

### Added

- RBAC decorator with `.env` admin support (`@admin_required`)
- Admin dashboard handlers (`/ban_user`, `/user_info`, `/stats`)

### Changed

- Error handling with context-aware messages
- All dependencies pinned in `requirements.txt`

### Fixed

- Panel relationship foreign key ambiguity
- Model attribute naming consistency


