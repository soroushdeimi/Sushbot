# Security

## Reporting Vulnerabilities

**DO NOT** open public issues for security bugs. Email: [your-email@example.com]

Include: description, repro steps, impact, suggested fix (if any). We'll respond within 48h.

---

## Key Security Points

### Secrets

- Never commit `.env` — it's gitignored
- Rotate secrets regularly
- Generate encryption key: `python -c "from utils.encryption import EncryptionManager; print(EncryptionManager.generate_key())"`

⚠️ **Gotcha**: If you lose the encryption key, panel credentials stored in DB are unrecoverable.

### Database

- Use strong PostgreSQL passwords
- Enable SSL for DB connections in prod
- Restrict DB access to app server only

### Panel Credentials

All panel API keys/passwords are encrypted at rest (Fernet). Decrypted only in-memory when needed.

### Payments

- Validate all IPN callbacks
- Verify signatures (NowPayments)
- Use HTTPS for webhook URLs
- Idempotency keys prevent double-processing

### Deployment

```bash
# Docker: runs as non-root by default
docker compose up -d

# Firewall: only expose ports 443 (nginx), not 8080 directly
# Use nginx/caddy as reverse proxy with TLS
```

## Pre-Deploy Checklist

- [ ] `.env` configured with real secrets
- [ ] Encryption key generated and backed up
- [ ] Strong DB password set
- [ ] `PUBLIC_BASE_URL` uses HTTPS
- [ ] Payment gateway secrets configured
- [ ] Firewall configured (only 443 exposed)
- [ ] Bot token is fresh (regenerate if leaked)

