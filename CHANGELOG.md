# Changelog

Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) | [Semantic Versioning](https://semver.org/)

## [Unreleased]

### Added
- RBAC decorator with `.env` admin support (`@admin_required`)
- Admin dashboard handlers (`/ban_user`, `/user_info`, `/stats`, etc.)
- Comprehensive test suite for security and admin features

### Changed
- Enhanced error handling with context-aware messages
- Pinned all dependencies in `requirements.txt`

### Fixed
- Panel relationship foreign key ambiguity
- Model attribute naming consistency

## [1.0.0] - 2024-01-XX

Initial production release.

### Features
- Multi-panel support (PasarGuard, Marzban) with factory pattern
- Telegram bot: purchases, trials, wallet, affiliate, support tickets
- FastAPI admin panel with RBAC
- Payment gateways: Card-to-Card, NowPayments, Aqayepardakht
- Async everywhere (SQLAlchemy 2.0, asyncpg)
- Background jobs: usage sync, reminders
- Multi-language: Persian, English, Bilingual


