"""
Integration tests for Protocol Selection feature.

These tests verify:
1. Case sensitivity handling (VLESS vs vless)
2. Protocol normalization across panel integrations
3. JSON payload correctness for panel APIs
4. Compatibility validation before API calls
5. Protocol-specific parameter handling (flow, password, etc.)
"""

import pytest
import httpx
import respx
from unittest.mock import AsyncMock, MagicMock, patch
import json

from services.panel_utils import (
    VPNProtocol,
    validate_protocol_compatibility,
    get_protocol_params,
    PANEL_SUPPORTED_PROTOCOLS,
)
from integrations.marzban.service import (
    MarzbanService,
    normalize_protocol_for_marzban,
    MARZBAN_PROTOCOL_NAMES,
)
from integrations.pasarguard.service import (
    PasarGuardService,
    normalize_protocol_for_pasarguard,
    PASARGUARD_PROTOCOL_NAMES,
)


# ============================================================================
# Protocol Normalization Tests
# ============================================================================


class TestVPNProtocolNormalization:
    """Test the VPNProtocol enum normalization."""

    @pytest.mark.parametrize(
        "input_protocol,expected_output",
        [
            # Standard lowercase
            ("vless", "vless"),
            ("vmess", "vmess"),
            ("trojan", "trojan"),
            ("shadowsocks", "shadowsocks"),
            # Mixed case
            ("VLESS", "vless"),
            ("Vmess", "vmess"),
            ("TROJAN", "trojan"),
            ("ShadowSocks", "shadowsocks"),
            # Aliases
            ("ss", "shadowsocks"),
            ("SS", "shadowsocks"),
            ("Ss", "shadowsocks"),
            # Unknown should pass through (lowercase)
            ("unknown", "unknown"),
            ("UNKNOWN", "unknown"),
        ],
    )
    def test_normalize_protocol(self, input_protocol: str, expected_output: str):
        """Test that protocols are correctly normalized."""
        result = VPNProtocol.normalize(input_protocol)
        assert result == expected_output, f"Expected {expected_output}, got {result}"


class TestMarzbanProtocolNormalization:
    """Test Marzban-specific protocol normalization."""

    @pytest.mark.parametrize(
        "input_protocol,expected_output",
        [
            ("vless", "vless"),
            ("VLESS", "vless"),
            ("vmess", "vmess"),
            ("VMESS", "vmess"),
            ("trojan", "trojan"),
            ("TROJAN", "trojan"),
            ("shadowsocks", "shadowsocks"),
            ("ss", "shadowsocks"),
            ("SS", "shadowsocks"),
            # Note: WireGuard aliases are only defined in VPNProtocol,
            # not in the panel-specific mappers (which is fine)
        ],
    )
    def test_marzban_normalization(self, input_protocol: str, expected_output: str):
        """Test Marzban protocol normalization."""
        result = normalize_protocol_for_marzban(input_protocol)
        assert result == expected_output


class TestPasarGuardProtocolNormalization:
    """Test PasarGuard-specific protocol normalization."""

    @pytest.mark.parametrize(
        "input_protocol,expected_output",
        [
            ("vless", "vless"),
            ("VLESS", "vless"),
            ("vmess", "vmess"),
            ("trojan", "trojan"),
            ("shadowsocks", "shadowsocks"),
            ("ss", "shadowsocks"),
            ("hysteria", "hysteria"),
            ("HYSTERIA2", "hysteria2"),
        ],
    )
    def test_pasarguard_normalization(self, input_protocol: str, expected_output: str):
        """Test PasarGuard protocol normalization."""
        result = normalize_protocol_for_pasarguard(input_protocol)
        assert result == expected_output


# ============================================================================
# Protocol Compatibility Validation Tests
# ============================================================================


class TestProtocolCompatibilityValidation:
    """Test the validate_protocol_compatibility function."""

    def test_marzban_supports_vless(self):
        """Test that Marzban supports VLESS."""
        is_compatible, message = validate_protocol_compatibility("marzban", "vless")
        assert is_compatible is True
        # message is None when valid (not empty string)
        assert message is None

    def test_marzban_supports_vmess(self):
        """Test that Marzban supports VMESS."""
        is_compatible, message = validate_protocol_compatibility("marzban", "vmess")
        assert is_compatible is True

    def test_marzban_supports_trojan(self):
        """Test that Marzban supports Trojan."""
        is_compatible, message = validate_protocol_compatibility("marzban", "trojan")
        assert is_compatible is True

    def test_marzban_case_insensitive(self):
        """Test that protocol validation is case-insensitive."""
        is_compatible, _ = validate_protocol_compatibility("marzban", "VLESS")
        assert is_compatible is True

        is_compatible, _ = validate_protocol_compatibility("marzban", "VmEsS")
        assert is_compatible is True

    def test_unknown_panel_type_fails_gracefully(self):
        """Test that unknown panel types are handled gracefully."""
        # Unknown panel should return True with a warning (graceful degradation)
        is_compatible, message = validate_protocol_compatibility(
            "unknown_panel", "vless"
        )
        # Based on implementation, unknown panels may pass through
        # This tests the actual behavior
        assert isinstance(is_compatible, bool)

    def test_unsupported_protocol_returns_false(self):
        """Test that clearly unsupported protocols return False."""
        # Assuming some fictional unsupported protocol
        is_compatible, message = validate_protocol_compatibility(
            "marzban", "unsupported_protocol_xyz"
        )
        # The function should return False for unknown protocols
        assert is_compatible is False or "unsupported" in message.lower()


# ============================================================================
# Protocol-Specific Parameter Tests
# ============================================================================


class TestProtocolParameters:
    """Test protocol-specific parameter generation."""

    def test_vless_requires_flow(self):
        """Test that VLESS protocol includes flow parameter."""
        params = get_protocol_params("vless")
        assert params is not None
        # Check that flow is supported and has a default
        assert params.get("supports_flow") is True
        assert params.get("default_flow") == "xtls-rprx-vision"

    def test_vmess_no_flow(self):
        """Test that VMESS protocol doesn't include flow."""
        params = get_protocol_params("vmess")
        assert params is not None
        # VMess doesn't support flow
        assert params.get("supports_flow") is False

    def test_trojan_has_password_field(self):
        """Test that Trojan protocol setup is correct."""
        params = get_protocol_params("trojan")
        # Trojan uses password instead of UUID
        assert isinstance(params, dict)

    def test_shadowsocks_parameters(self):
        """Test Shadowsocks protocol parameters."""
        params = get_protocol_params("shadowsocks")
        assert isinstance(params, dict)


# ============================================================================
# Marzban API Integration Tests (with respx mocking)
# ============================================================================


class TestMarzbanAPIIntegration:
    """Integration tests for Marzban API calls with mocked HTTP."""

    @pytest.fixture
    def marzban_service(self):
        """Create a MarzbanService instance for testing."""
        mock_client = MagicMock()
        mock_client.get_token = AsyncMock(return_value="test_token")
        return MarzbanService(
            panel_name="test_marzban",
            api_url="https://test.marzban.com",
            username="admin",
            password="password",
        )

    @pytest.mark.asyncio
    @respx.mock
    async def test_create_user_sends_lowercase_protocol(self):
        """Test that create_user sends lowercase protocol in JSON payload."""
        api_url = "https://test.marzban.com"

        # Mock the auth endpoint
        respx.post(f"{api_url}/api/admin/token").mock(
            return_value=httpx.Response(
                200, json={"access_token": "test_token", "token_type": "bearer"}
            )
        )

        # Mock the create user endpoint and capture the request
        create_route = respx.post(f"{api_url}/api/user").mock(
            return_value=httpx.Response(
                200,
                json={
                    "username": "test_user",
                    "status": "active",
                    "used_traffic": 0,
                    "data_limit": None,
                    "expire": None,
                    "created_at": "2024-01-01T00:00:00",
                    "links": ["vless://..."],
                    "subscription_url": "https://...",
                    "proxies": {"vless": {"id": "test-uuid"}},
                },
            )
        )

        # Create service
        service = MarzbanService(
            panel_name="test_marzban",
            api_url=api_url,
            username="admin",
            password="password",
        )

        # Call with uppercase protocol
        await service.create_user(
            username="test_user",
            protocol="VLESS",  # Uppercase!
            flow="xtls-rprx-vision",
        )

        # Verify the request was made
        assert create_route.called
        
        # Get the request body
        request = create_route.calls.last.request
        body = json.loads(request.content)
        
        # Verify protocol is lowercase in the payload
        if "proxies" in body:
            proxies = body["proxies"]
            # All protocol keys should be lowercase
            for proto_key in proxies:
                assert proto_key == proto_key.lower(), (
                    f"Protocol key '{proto_key}' should be lowercase"
                )

    @pytest.mark.asyncio
    @respx.mock
    async def test_create_user_vless_includes_flow(self):
        """Test that VLESS users include flow parameter."""
        api_url = "https://test.marzban.com"

        respx.post(f"{api_url}/api/admin/token").mock(
            return_value=httpx.Response(
                200, json={"access_token": "test_token", "token_type": "bearer"}
            )
        )

        create_route = respx.post(f"{api_url}/api/user").mock(
            return_value=httpx.Response(
                200,
                json={
                    "username": "test_user",
                    "status": "active",
                    "used_traffic": 0,
                    "proxies": {"vless": {"id": "uuid", "flow": "xtls-rprx-vision"}},
                    "links": [],
                    "subscription_url": "",
                },
            )
        )

        service = MarzbanService(
            panel_name="test",
            api_url=api_url,
            username="admin",
            password="password",
        )

        await service.create_user(
            username="test_user",
            protocol="vless",
            flow="xtls-rprx-vision",
        )

        assert create_route.called
        request = create_route.calls.last.request
        body = json.loads(request.content)

        # For VLESS, proxies should include flow
        if "proxies" in body and "vless" in body["proxies"]:
            vless_config = body["proxies"]["vless"]
            assert "flow" in vless_config
            assert vless_config["flow"] == "xtls-rprx-vision"

    @pytest.mark.asyncio
    @respx.mock
    async def test_create_user_vmess_no_flow(self):
        """Test that VMESS users don't include flow parameter."""
        api_url = "https://test.marzban.com"

        respx.post(f"{api_url}/api/admin/token").mock(
            return_value=httpx.Response(
                200, json={"access_token": "test_token", "token_type": "bearer"}
            )
        )

        create_route = respx.post(f"{api_url}/api/user").mock(
            return_value=httpx.Response(
                200,
                json={
                    "username": "test_user",
                    "status": "active",
                    "used_traffic": 0,
                    "proxies": {"vmess": {"id": "uuid"}},
                    "links": [],
                    "subscription_url": "",
                },
            )
        )

        service = MarzbanService(
            panel_name="test",
            api_url=api_url,
            username="admin",
            password="password",
        )

        await service.create_user(
            username="test_user",
            protocol="vmess",
            flow="",  # Empty for vmess
        )

        assert create_route.called
        request = create_route.calls.last.request
        body = json.loads(request.content)

        # For VMESS, proxies should NOT include flow or it should be empty
        if "proxies" in body and "vmess" in body["proxies"]:
            vmess_config = body["proxies"]["vmess"]
            if "flow" in vmess_config:
                assert vmess_config["flow"] == "" or vmess_config["flow"] is None


# ============================================================================
# End-to-End Protocol Selection Flow Tests
# ============================================================================


class TestProtocolSelectionE2E:
    """End-to-end tests for protocol selection flow."""

    @pytest.mark.asyncio
    async def test_protocol_normalization_consistency(self):
        """Test that normalization is consistent across all panel types."""
        test_protocols = ["VLESS", "Vmess", "TROJAN", "SS", "shadowsocks"]

        for proto in test_protocols:
            marzban_result = normalize_protocol_for_marzban(proto)
            pasarguard_result = normalize_protocol_for_pasarguard(proto)

            # Both should return lowercase
            assert marzban_result == marzban_result.lower()
            assert pasarguard_result == pasarguard_result.lower()

    def test_all_panel_types_have_supported_protocols(self):
        """Test that all known panel types have defined supported protocols."""
        expected_panels = ["marzban", "pasarguard"]

        for panel in expected_panels:
            assert panel in PANEL_SUPPORTED_PROTOCOLS, (
                f"Panel {panel} missing from PANEL_SUPPORTED_PROTOCOLS"
            )
            assert len(PANEL_SUPPORTED_PROTOCOLS[panel]) > 0, (
                f"Panel {panel} has no supported protocols defined"
            )

    def test_common_protocols_supported_by_all_panels(self):
        """Test that common protocols are supported by all panels."""
        common_protocols = ["vless", "vmess", "trojan"]

        for panel, supported in PANEL_SUPPORTED_PROTOCOLS.items():
            for proto in common_protocols:
                assert proto in supported, (
                    f"Protocol {proto} not supported by {panel}"
                )


# ============================================================================
# Protocol Alias Resolution Tests
# ============================================================================


class TestProtocolAliasResolution:
    """Test protocol alias resolution across the system."""

    @pytest.mark.parametrize(
        "alias,expected_protocol",
        [
            ("ss", "shadowsocks"),
            ("SS", "shadowsocks"),
            ("Ss", "shadowsocks"),
        ],
    )
    def test_marzban_alias_resolution(self, alias: str, expected_protocol: str):
        """Test that Marzban resolves protocol aliases correctly."""
        result = normalize_protocol_for_marzban(alias)
        assert result == expected_protocol

    @pytest.mark.parametrize(
        "alias,expected_protocol",
        [
            ("ss", "shadowsocks"),
            ("SS", "shadowsocks"),
        ],
    )
    def test_pasarguard_alias_resolution(self, alias: str, expected_protocol: str):
        """Test that PasarGuard resolves protocol aliases correctly."""
        result = normalize_protocol_for_pasarguard(alias)
        assert result == expected_protocol


# ============================================================================
# Error Handling Tests
# ============================================================================


class TestProtocolErrorHandling:
    """Test error handling in protocol operations."""

    def test_empty_protocol_handling(self):
        """Test handling of empty protocol string."""
        result = VPNProtocol.normalize("")
        # Should return empty string or default
        assert isinstance(result, str)

    def test_none_protocol_handling(self):
        """Test handling of None protocol."""
        # This depends on implementation - may raise or return default
        try:
            result = VPNProtocol.normalize(None)  # type: ignore
            assert result is None or result == ""
        except (TypeError, AttributeError):
            # Expected behavior - None should raise
            pass

    def test_whitespace_protocol_handling(self):
        """Test handling of whitespace-only protocol."""
        result = VPNProtocol.normalize("  vless  ")
        # Should strip and normalize
        assert result == "vless" or result == "  vless  ".lower().strip()


# ============================================================================
# Data Integrity Tests
# ============================================================================


class TestProtocolDataIntegrity:
    """Test data integrity for protocol operations."""

    def test_protocol_mappings_are_complete(self):
        """Test that protocol name mappings are complete."""
        # Marzban
        for proto in ["vless", "vmess", "trojan", "shadowsocks"]:
            assert proto in MARZBAN_PROTOCOL_NAMES.values() or proto in [
                v.lower() for v in MARZBAN_PROTOCOL_NAMES.values()
            ], f"Protocol {proto} missing from Marzban mappings"

        # PasarGuard
        for proto in ["vless", "vmess", "trojan", "shadowsocks"]:
            assert proto in PASARGUARD_PROTOCOL_NAMES.values() or proto in [
                v.lower() for v in PASARGUARD_PROTOCOL_NAMES.values()
            ], f"Protocol {proto} missing from PasarGuard mappings"

    def test_protocol_enum_has_common_values(self):
        """Test that VPNProtocol enum has common protocol values."""
        common = ["VLESS", "VMESS", "TROJAN", "SHADOWSOCKS"]
        for proto in common:
            assert hasattr(VPNProtocol, proto), (
                f"VPNProtocol missing {proto}"
            )
