"""Central feature flag registry (ENV-driven).

Design:
- ENV is the source of truth for enabling/disabling a feature.
- Keep feature evaluation cheap and side-effect free.
- UI/handlers/routes/jobs must check flags before exposing functionality.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _parse_bool(v: str | None, default: bool) -> bool:
    if v is None:
        return default
    s = v.strip().lower()
    if s in {"1", "true", "t", "yes", "y", "on"}:
        return True
    if s in {"0", "false", "f", "no", "n", "off"}:
        return False
    return default


@dataclass(frozen=True, slots=True)
class Feature:
    """A feature flag with optional dependencies."""

    env_key: str
    default: bool
    deps: tuple[str, ...] = ()
    description: str = ""


# NOTE: Feature keys are stable identifiers used across bot/api/jobs.
REGISTRY: dict[str, Feature] = {
    # Core flows
    "purchase": Feature("FEATURE_PURCHASE", True, description="Enable purchase flow"),
    "trial": Feature("FEATURE_TRIAL", True, description="Enable trial flow"),
    "services": Feature("FEATURE_SERVICES", True, description="Enable my services / service management UI"),
    "support": Feature("FEATURE_SUPPORT", True, description="Enable support tickets"),
    "wallet": Feature("FEATURE_WALLET", True, description="Enable wallet and top-up"),
    "discount": Feature("FEATURE_DISCOUNT", True, description="Enable discount codes"),
    "affiliate": Feature("FEATURE_AFFILIATE", True, description="Enable affiliate/referral UI and rewards"),
    "content_cms": Feature("FEATURE_CONTENT_CMS", True, description="Enable FAQ/Tutorial/text customization from DB"),
    # Restrictions / verification
    "phone_verification": Feature("FEATURE_PHONE_VERIFICATION", True, description="Require phone verification (Telegram contact)"),
    "channel_membership": Feature("FEATURE_CHANNEL_MEMBERSHIP", False, description="Require channel membership checks"),
    "require_phone_for_purchase": Feature(
        "FEATURE_REQUIRE_PHONE_FOR_PURCHASE",
        True,
        deps=("phone_verification", "purchase"),
        description="Require verified phone before purchase",
    ),
    "require_phone_for_trial": Feature(
        "FEATURE_REQUIRE_PHONE_FOR_TRIAL",
        True,
        deps=("phone_verification", "trial"),
        description="Require verified phone before trial",
    ),
    "require_channel_for_purchase": Feature(
        "FEATURE_REQUIRE_CHANNEL_FOR_PURCHASE",
        True,
        deps=("channel_membership", "purchase"),
        description="Require channel membership before purchase",
    ),
    "require_channel_for_trial": Feature(
        "FEATURE_REQUIRE_CHANNEL_FOR_TRIAL",
        False,
        deps=("channel_membership", "trial"),
        description="Require channel membership before trial",
    ),
    # Payments
    "pay_card_to_card": Feature("FEATURE_PAY_CARD_TO_CARD", True, deps=("purchase",), description="Enable card-to-card"),
    "pay_nowpayments": Feature("FEATURE_PAY_NOWPAYMENTS", True, deps=("purchase",), description="Enable NowPayments"),
    "pay_aqayepardakht": Feature("FEATURE_PAY_AQAYEPARDAKHT", True, deps=("purchase",), description="Enable Aqayepardakht"),
    "pay_rial_exchange": Feature("FEATURE_PAY_RIAL_EXCHANGE", False, deps=("purchase",), description="Enable Rial exchange gateways"),
    # Admin / web
    "admin_web": Feature("FEATURE_ADMIN_WEB", True, description="Enable FastAPI admin panel"),
    "admin_telegram": Feature("FEATURE_ADMIN_TELEGRAM", True, description="Enable Telegram admin commands"),
    "reporting": Feature("FEATURE_REPORTING", True, description="Enable reports/stats"),
    # Advanced ops
    "inventory": Feature("FEATURE_INVENTORY", True, description="Enable inventory enforcement for products"),
    "reseller": Feature("FEATURE_RESELLER", False, description="Enable reseller workflows"),
    "bulk_purchase": Feature("FEATURE_BULK_PURCHASE", False, description="Enable bulk purchase flow"),
    "refunds": Feature("FEATURE_REFUNDS", False, description="Enable refunds"),
    "service_removal": Feature("FEATURE_SERVICE_REMOVAL", False, description="Enable service removal/deprovision"),
    "service_transfer": Feature("FEATURE_SERVICE_TRANSFER", False, description="Enable transfer services between users"),
    "service_location_change": Feature("FEATURE_SERVICE_LOCATION_CHANGE", False, description="Enable location/inbound change"),
}


def is_enabled(feature_key: str, *, env: os._Environ[str] = os.environ, _seen: set[str] | None = None) -> bool:
    """Check if a feature is enabled, including dependencies."""
    ft = REGISTRY.get(feature_key)
    if not ft:
        # Unknown feature defaults to disabled for safety.
        return False
    if _seen is None:
        _seen = set()
    if feature_key in _seen:
        return False
    _seen.add(feature_key)
    ok = _parse_bool(env.get(ft.env_key), ft.default)
    if not ok:
        return False
    for dep in ft.deps:
        if not is_enabled(dep, env=env, _seen=_seen):
            return False
    return True


def enabled_payment_gateways(*, env: os._Environ[str] = os.environ) -> set[str]:
    """Return enabled payment gateways ids: card|nowpayments|aqayepardakht."""
    out: set[str] = set()
    if is_enabled("pay_card_to_card", env=env):
        out.add("card")
    if is_enabled("pay_nowpayments", env=env):
        out.add("nowpayments")
    if is_enabled("pay_aqayepardakht", env=env):
        out.add("aqayepardakht")
    return out


