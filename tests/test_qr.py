"""
Unit tests for QR code generation.
"""

from __future__ import annotations

import io

import pytest


def test_generate_qr_image_returns_png():
    """Test that generate_qr_image returns a valid PNG buffer."""
    from utils.qr import generate_qr_image

    data = "vless://uuid@example.com:443?security=tls#MyVPN"
    result = generate_qr_image(data)

    assert result is not None
    assert isinstance(result, io.BytesIO)
    
    # Check PNG magic bytes
    content = result.getvalue()
    assert len(content) > 0
    assert content[:8] == b'\x89PNG\r\n\x1a\n'


def test_generate_qr_image_handles_long_urls():
    """Test QR generation with long VPN config URLs."""
    from utils.qr import generate_qr_image

    # Typical long vless URL
    long_url = (
        "vless://aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        "@vpn.example.com:443"
        "?encryption=none&security=tls&sni=vpn.example.com"
        "&type=ws&host=vpn.example.com&path=/websocket#MyConfig"
    )
    
    result = generate_qr_image(long_url)
    
    assert result is not None
    assert len(result.getvalue()) > 0


def test_generate_qr_image_unicode():
    """Test QR generation with Persian/Unicode text."""
    from utils.qr import generate_qr_image

    data = "سابسکریپشن سرویس #123"
    result = generate_qr_image(data)

    assert result is not None
    assert len(result.getvalue()) > 0


def test_generate_qr_image_empty_string():
    """Test QR generation with empty string."""
    from utils.qr import generate_qr_image

    result = generate_qr_image("")
    
    # Should still work (empty QR code is valid)
    assert result is not None


def test_qr_available_flag():
    """Test QR_AVAILABLE flag is True when qrcode is installed."""
    from utils.qr import QR_AVAILABLE
    
    assert QR_AVAILABLE is True
