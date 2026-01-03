# Contributing

## Quick Start

```bash
git clone https://github.com/your-username/sushbotseller.git
cd sushbotseller
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp .env.template .env  # Configure
alembic upgrade head
pytest  # Make sure tests pass
```

## Code Style

- **Python 3.12+** with type hints everywhere
- **Async/await** for all I/O
- **Loguru** for logging (no `print()`)
- **Google-style docstrings** for public functions

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

## PR Checklist

- [ ] Type hints on all functions
- [ ] No `print()` statements
- [ ] Tests pass (`pytest`)
- [ ] No secrets/credentials in code

## Adding Features

### New VPN Panel

1. `integrations/yourpanel/service.py` — implement `VPNPanelInterface`
2. Register in `integrations/factory.py`

### New Payment Gateway

1. `integrations/payments/yourgateway.py`
2. Add webhook route in `api/routes/payments.py`
3. Wire up in settings

## Questions?

Open an issue. Check existing ones first.
