# Contributing

## Setup

```bash
git clone https://github.com/your-username/sushbotseller.git
cd sushbotseller
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.template .env
alembic upgrade head
pytest
```

## Code Style

Python 3.12+ required.

Rules:
- Type hints on all function signatures
- Async/await for all I/O operations
- Loguru for logging (no print statements)
- Google-style docstrings for public functions

```python
async def do_thing(user_id: int, amount: float | None = None) -> dict[str, Any]:
    """
    Does the thing.

    Args:
        user_id: Target user
        amount: Optional amount in Tomans

    Returns:
        Result dict with status

    Raises:
        PanelError: If panel is unreachable
    """
    logger.info(f"Doing thing for user {user_id}")
    ...
```

## PR Requirements

```
[ ] Type hints on all functions
[ ] No print() statements
[ ] Tests pass (pytest)
[ ] No secrets or credentials in code
[ ] Linting passes (ruff check .)
```

## Adding a VPN Panel

1. Create `integrations/yourpanel/service.py`
2. Implement `VPNPanelInterface` from `integrations/base.py`
3. Register in `integrations/factory.py`

## Adding a Payment Gateway

1. Create `integrations/payments/yourgateway.py`
2. Add webhook route in `api/routes/payments.py`
3. Add configuration to settings

## Questions

Open an issue. Search existing issues first.
