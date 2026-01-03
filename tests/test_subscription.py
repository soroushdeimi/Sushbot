"""Tests for services/subscription.py - subscription link helpers."""

from __future__ import annotations

import base64
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from services.subscription import (
    build_subscription_payload,
    ensure_service_sub_token,
    subscription_url_from_token,
)


class TestBuildSubscriptionPayload:
    """Tests for build_subscription_payload function."""

    def test_single_link(self):
        """Single link should be base64 encoded."""
        links = ["vmess://abc123"]
        payload = build_subscription_payload(links)
        decoded = base64.b64decode(payload).decode("utf-8")
        assert "vmess://abc123" in decoded

    def test_multiple_links(self):
        """Multiple links should be joined with newlines."""
        links = ["vmess://link1", "vless://link2", "trojan://link3"]
        payload = build_subscription_payload(links)
        decoded = base64.b64decode(payload).decode("utf-8")
        assert "vmess://link1" in decoded
        assert "vless://link2" in decoded
        assert "trojan://link3" in decoded

    def test_links_separated_by_newline(self):
        """Links should be separated by newlines."""
        links = ["link1", "link2"]
        payload = build_subscription_payload(links)
        decoded = base64.b64decode(payload).decode("utf-8")
        lines = decoded.strip().split("\n")
        assert len(lines) == 2

    def test_empty_links_filtered(self):
        """Empty links should be filtered out."""
        links = ["link1", "", "link2", None, "link3"]  # type: ignore
        payload = build_subscription_payload(links)
        decoded = base64.b64decode(payload).decode("utf-8")
        lines = decoded.strip().split("\n")
        assert len(lines) == 3

    def test_whitespace_stripped(self):
        """Whitespace around links should be stripped."""
        links = ["  link1  ", "\tlink2\t", "\nlink3\n"]
        payload = build_subscription_payload(links)
        decoded = base64.b64decode(payload).decode("utf-8")
        assert "  link1  " not in decoded
        assert "link1" in decoded

    def test_empty_list(self):
        """Empty list should return base64 of just newline."""
        links: list[str] = []
        payload = build_subscription_payload(links)
        decoded = base64.b64decode(payload).decode("utf-8")
        assert decoded == "\n"

    def test_returns_ascii(self):
        """Payload should be ASCII (valid base64)."""
        links = ["vmess://test"]
        payload = build_subscription_payload(links)
        assert payload.isascii()


class TestSubscriptionUrlFromToken:
    """Tests for subscription_url_from_token function."""

    def test_with_public_base_url(self):
        """Should build URL when public_base_url is set."""
        with patch("services.subscription.settings") as mock_settings:
            mock_settings.public_base_url = "https://example.com"
            url = subscription_url_from_token("abc123token")
            assert url == "https://example.com/api/sub/abc123token"

    def test_without_public_base_url(self):
        """Should return None when public_base_url not set."""
        with patch("services.subscription.settings") as mock_settings:
            mock_settings.public_base_url = None
            url = subscription_url_from_token("abc123token")
            assert url is None

    def test_trailing_slash_removed(self):
        """Trailing slash in base URL should be handled."""
        with patch("services.subscription.settings") as mock_settings:
            mock_settings.public_base_url = "https://example.com/"
            url = subscription_url_from_token("token123")
            assert url == "https://example.com/api/sub/token123"

    def test_empty_base_url(self):
        """Empty string base URL should return None."""
        with patch("services.subscription.settings") as mock_settings:
            mock_settings.public_base_url = ""
            url = subscription_url_from_token("token")
            # Empty string is falsy, should return None
            assert url is None


class TestEnsureServiceSubToken:
    """Tests for ensure_service_sub_token function."""

    @pytest.mark.asyncio
    async def test_existing_token_returned(self):
        """Should return existing token if present."""
        mock_db = AsyncMock()
        mock_service = MagicMock()
        mock_service.sub_token = "existing_token_123"

        token = await ensure_service_sub_token(mock_db, mock_service)

        assert token == "existing_token_123"
        mock_db.commit.assert_not_called()

    @pytest.mark.asyncio
    async def test_generates_new_token(self):
        """Should generate new token if none exists."""
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_service = MagicMock()
        mock_service.sub_token = None

        token = await ensure_service_sub_token(mock_db, mock_service)

        assert len(token) > 0
        assert mock_service.sub_token is not None
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_generated_token_is_urlsafe(self):
        """Generated token should be URL-safe."""
        mock_db = AsyncMock()
        mock_db.commit = AsyncMock()
        mock_service = MagicMock()
        mock_service.sub_token = None

        token = await ensure_service_sub_token(mock_db, mock_service)

        # token_urlsafe generates URL-safe base64
        # Should not contain characters that need URL encoding
        unsafe_chars = ["+", "/", "="]
        for char in unsafe_chars:
            assert char not in token or token.replace("-", "").replace("_", "").isalnum()
