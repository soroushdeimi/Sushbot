"""Tests for config/features.py - feature flag registry."""

from __future__ import annotations

import pytest

from config.features import (
    REGISTRY,
    Feature,
    enabled_payment_gateways,
    is_enabled,
)


class TestFeatureDataclass:
    """Tests for Feature dataclass."""

    def test_feature_creation(self):
        f = Feature("TEST_KEY", True, description="Test feature")
        assert f.env_key == "TEST_KEY"
        assert f.default is True
        assert f.description == "Test feature"
        assert f.deps == ()

    def test_feature_with_deps(self):
        f = Feature("CHILD", True, deps=("parent",))
        assert f.deps == ("parent",)

    def test_feature_is_frozen(self):
        f = Feature("TEST", True)
        with pytest.raises(AttributeError):
            f.default = False  # type: ignore


class TestRegistry:
    """Tests for REGISTRY dictionary."""

    def test_registry_has_purchase(self):
        assert "purchase" in REGISTRY
        assert REGISTRY["purchase"].env_key == "FEATURE_PURCHASE"

    def test_registry_has_trial(self):
        assert "trial" in REGISTRY

    def test_registry_has_wallet(self):
        assert "wallet" in REGISTRY

    def test_registry_has_support(self):
        assert "support" in REGISTRY

    def test_registry_has_affiliate(self):
        assert "affiliate" in REGISTRY

    def test_registry_has_payment_gateways(self):
        assert "pay_card_to_card" in REGISTRY
        assert "pay_nowpayments" in REGISTRY
        assert "pay_aqayepardakht" in REGISTRY


class TestIsEnabled:
    """Tests for is_enabled function."""

    def test_unknown_feature_returns_false(self):
        assert is_enabled("nonexistent_feature_xyz") is False

    def test_feature_enabled_by_default(self):
        # purchase defaults to True
        # Using actual os.environ with feature enabled
        assert is_enabled("purchase") is True  # Default enabled

    def test_feature_disabled_by_env(self):
        env = {"FEATURE_PURCHASE": "false"}
        assert is_enabled("purchase", env=env) is False  # type: ignore

    def test_feature_enabled_by_env(self):
        env = {"FEATURE_PURCHASE": "true"}
        assert is_enabled("purchase", env=env) is True  # type: ignore

    def test_feature_with_1_is_enabled(self):
        env = {"FEATURE_PURCHASE": "1"}
        assert is_enabled("purchase", env=env) is True  # type: ignore

    def test_feature_with_0_is_disabled(self):
        env = {"FEATURE_PURCHASE": "0"}
        assert is_enabled("purchase", env=env) is False  # type: ignore

    def test_feature_with_yes_is_enabled(self):
        env = {"FEATURE_PURCHASE": "yes"}
        assert is_enabled("purchase", env=env) is True  # type: ignore

    def test_feature_with_no_is_disabled(self):
        env = {"FEATURE_PURCHASE": "no"}
        assert is_enabled("purchase", env=env) is False  # type: ignore

    def test_feature_with_on_is_enabled(self):
        env = {"FEATURE_PURCHASE": "on"}
        assert is_enabled("purchase", env=env) is True  # type: ignore

    def test_feature_with_off_is_disabled(self):
        env = {"FEATURE_PURCHASE": "off"}
        assert is_enabled("purchase", env=env) is False  # type: ignore

    def test_feature_case_insensitive(self):
        env = {"FEATURE_PURCHASE": "TRUE"}
        assert is_enabled("purchase", env=env) is True  # type: ignore
        env2 = {"FEATURE_PURCHASE": "FALSE"}
        assert is_enabled("purchase", env=env2) is False  # type: ignore

    def test_feature_with_whitespace(self):
        env = {"FEATURE_PURCHASE": "  true  "}
        assert is_enabled("purchase", env=env) is True  # type: ignore

    def test_dependency_required(self):
        # pay_card_to_card depends on purchase
        env = {"FEATURE_PURCHASE": "false", "FEATURE_PAY_CARD_TO_CARD": "true"}
        # If purchase is disabled, pay_card_to_card should be disabled
        assert is_enabled("pay_card_to_card", env=env) is False  # type: ignore

    def test_dependency_satisfied(self):
        env = {"FEATURE_PURCHASE": "true", "FEATURE_PAY_CARD_TO_CARD": "true"}
        assert is_enabled("pay_card_to_card", env=env) is True  # type: ignore

    def test_circular_dependency_protection(self):
        # The _seen set should prevent infinite loops
        # Even if somehow circular deps were introduced
        assert is_enabled("purchase") is True  # Should not hang


class TestEnabledPaymentGateways:
    """Tests for enabled_payment_gateways function."""

    def test_all_gateways_enabled_by_default(self):
        env = {"FEATURE_PURCHASE": "true"}
        gateways = enabled_payment_gateways(env=env)  # type: ignore
        assert "card" in gateways
        assert "nowpayments" in gateways
        assert "aqayepardakht" in gateways

    def test_no_gateways_when_purchase_disabled(self):
        env = {"FEATURE_PURCHASE": "false"}
        gateways = enabled_payment_gateways(env=env)  # type: ignore
        # All gateways depend on purchase
        assert len(gateways) == 0

    def test_specific_gateway_disabled(self):
        env = {"FEATURE_PURCHASE": "true", "FEATURE_PAY_CARD_TO_CARD": "false"}
        gateways = enabled_payment_gateways(env=env)  # type: ignore
        assert "card" not in gateways
        assert "nowpayments" in gateways
        assert "aqayepardakht" in gateways

    def test_only_card_enabled(self):
        env = {
            "FEATURE_PURCHASE": "true",
            "FEATURE_PAY_CARD_TO_CARD": "true",
            "FEATURE_PAY_NOWPAYMENTS": "false",
            "FEATURE_PAY_AQAYEPARDAKHT": "false",
        }
        gateways = enabled_payment_gateways(env=env)  # type: ignore
        assert gateways == {"card"}

    def test_returns_set(self):
        gateways = enabled_payment_gateways()
        assert isinstance(gateways, set)
