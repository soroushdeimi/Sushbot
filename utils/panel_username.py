"""Generate stable PasarGuard usernames based on Telegram username."""

from __future__ import annotations

import re

_SAFE_RE = re.compile(r"[^a-z0-9_.-]+")


def make_panel_username(*, telegram_username: str | None, user_id: int, suffix: str) -> str:
    """
    Create a stable, unique, <=128 char username for PasarGuard.
    Format: <sanitized_telegram_username>-<user_id>-<suffix>
    Includes suffix to ensure uniqueness across multiple purchases/products.
    """
    if not telegram_username:
        # Fallback: use user_id if no username
        base = f"user_{int(user_id)}_{suffix}"
    else:
        telegram_clean = telegram_username.strip().lstrip("@").lower()
        telegram_clean = _SAFE_RE.sub("_", telegram_clean)
        telegram_clean = telegram_clean.strip("._-") or f"user_{int(user_id)}"
        
        # Format: <telegram_username>-<user_id>-<suffix>
        base = f"{telegram_clean}-{int(user_id)}-{suffix}"
    
    # Truncate to 128 chars max (PasarGuard username limit)
    if len(base) > 128:
        # Truncate from the front (telegram username part) while preserving suffix
        suffix_part = f"-{int(user_id)}-{suffix}"
        max_base_len = 128 - len(suffix_part)
        if max_base_len > 0:
            telegram_part = base[:max_base_len]
            base = f"{telegram_part}{suffix_part}"
        else:
            # If suffix itself is too long, just use minimal format
            base = f"user_{int(user_id)}_{suffix}"[:128]
    
    return base



