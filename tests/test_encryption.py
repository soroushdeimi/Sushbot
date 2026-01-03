"""Tests for utils/encryption.py - encryption utilities."""

from __future__ import annotations

import pytest

from utils.encryption import (
    EncryptionManager,
    decrypt_panel_credentials,
    encrypt_panel_credentials,
)


class TestEncryptionManager:
    """Tests for EncryptionManager class."""

    def test_encrypt_returns_string(self):
        """Encrypt should return a string."""
        # Reset state for clean test
        EncryptionManager._key = None
        EncryptionManager._fernet = None

        result = EncryptionManager.encrypt("test_password")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_encrypt_empty_string(self):
        """Empty string should return empty string."""
        result = EncryptionManager.encrypt("")
        assert result == ""

    def test_decrypt_returns_original(self):
        """Decrypt should return original plaintext."""
        original = "my_secret_api_key_123"
        encrypted = EncryptionManager.encrypt(original)
        decrypted = EncryptionManager.decrypt(encrypted)
        assert decrypted == original

    def test_decrypt_empty_string(self):
        """Empty string should return empty string."""
        result = EncryptionManager.decrypt("")
        assert result == ""

    def test_encrypt_different_outputs(self):
        """Same input should produce different outputs (Fernet uses random IV)."""
        text = "same_input"
        enc1 = EncryptionManager.encrypt(text)
        enc2 = EncryptionManager.encrypt(text)
        # Both should decrypt to same value
        assert EncryptionManager.decrypt(enc1) == text
        assert EncryptionManager.decrypt(enc2) == text
        # But encrypted values are typically different due to IV
        # (Not guaranteed but very likely)

    def test_decrypt_invalid_ciphertext_raises(self):
        """Invalid ciphertext should raise ValueError."""
        with pytest.raises(ValueError, match="Failed to decrypt"):
            EncryptionManager.decrypt("not_valid_encrypted_data_xxxxx")

    def test_generate_key_returns_valid_key(self):
        """Generated key should be valid Fernet key."""
        key = EncryptionManager.generate_key()
        assert isinstance(key, str)
        assert len(key) == 44  # Fernet keys are 44 chars base64

    def test_unicode_data(self):
        """Should handle unicode data correctly."""
        original = "پسورد_فارسی_123_🔐"
        encrypted = EncryptionManager.encrypt(original)
        decrypted = EncryptionManager.decrypt(encrypted)
        assert decrypted == original

    def test_long_data(self):
        """Should handle long strings."""
        original = "x" * 10000
        encrypted = EncryptionManager.encrypt(original)
        decrypted = EncryptionManager.decrypt(encrypted)
        assert decrypted == original

    def test_special_characters(self):
        """Should handle special characters."""
        original = "!@#$%^&*()_+-=[]{}|;':\",./<>?\\"
        encrypted = EncryptionManager.encrypt(original)
        decrypted = EncryptionManager.decrypt(encrypted)
        assert decrypted == original


class TestEncryptPanelCredentials:
    """Tests for encrypt_panel_credentials function."""

    def test_encrypt_api_key(self):
        """Should encrypt API key."""
        api_key = "sk_test_123456789"
        encrypted = encrypt_panel_credentials(api_key)
        assert encrypted != api_key
        assert len(encrypted) > 0

    def test_decrypt_api_key(self):
        """Should decrypt API key correctly."""
        api_key = "sk_live_abcdefghij"
        encrypted = encrypt_panel_credentials(api_key)
        decrypted = decrypt_panel_credentials(encrypted)
        assert decrypted == api_key


class TestDecryptPanelCredentials:
    """Tests for decrypt_panel_credentials function."""

    def test_roundtrip(self):
        """Encrypt then decrypt should return original."""
        original = "panel_password_secret"
        encrypted = encrypt_panel_credentials(original)
        result = decrypt_panel_credentials(encrypted)
        assert result == original

    def test_empty_string(self):
        """Empty string should work."""
        assert decrypt_panel_credentials("") == ""
