# Security

## Reporting Vulnerabilities

Do not open public issues for security bugs.


Include: description, reproduction steps, impact assessment, suggested fix (if any).

Response time: 48 hours.

---

## Secrets Management

- `.env` is gitignored. Never commit it.
- Rotate secrets on a schedule.
- Generate encryption key:

```bash
python -c "from utils.encryption import EncryptionManager; print(EncryptionManager.generate_key())"
```

> If you lose the encryption key, panel credentials stored in the database are unrecoverable. Back it up.

## Database

- Use strong PostgreSQL passwords (32+ chars, random)
- Enable SSL for database connections in production
- Restrict database access to application server IP only

## Panel Credentials

All panel API keys and passwords are encrypted at rest using Fernet symmetric encryption. Decryption occurs only in-memory when needed.

## Payment Security

- Validate all IPN/webhook callbacks
- Verify cryptographic signatures (NowPayments HMAC)
- Use HTTPS for all webhook URLs
- Idempotency keys prevent double-processing

## Deployment

```bash
# Docker runs as non-root by default
docker compose up -d
```

Firewall rules:
- Expose only port 443 (nginx/caddy)
- Do not expose 8080 directly
- Use reverse proxy with TLS termination

## Pre-Deploy Checklist

```
[ ] .env configured with production secrets
[ ] Encryption key generated and backed up offline
[ ] Strong database password set
[ ] PUBLIC_BASE_URL uses HTTPS
[ ] Payment gateway credentials configured
[ ] Firewall: only 443 exposed
[ ] Bot token is fresh (regenerate if previously leaked)
```

