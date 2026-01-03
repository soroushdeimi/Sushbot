"""Encryption utilities for sensitive data like panel credentials."""

from __future__ import annotations

import base64

from cryptography.fernet import Fernet
from loguru import logger

from config.settings import settings


class EncryptionManager:
    """Manages encryption/decryption of sensitive data using Fernet."""

    _key: bytes | None = None
    _fernet: Fernet | None = None

    @classmethod
    def _get_key(cls) -> bytes:
        """Get or generate encryption key."""
        if cls._key is None:
            # Try to get from settings, or generate a new one
            encryption_key = getattr(settings, "encryption_key", None)
            if encryption_key:
                cls._key = (
                    encryption_key.encode() if isinstance(encryption_key, str) else encryption_key
                )
            else:
                # Generate a new key (should be set in production!)
                cls._key = Fernet.generate_key()
                logger.warning(
                    "No encryption key found in settings. Generated a new key. "
                    "This key will be lost on restart! Set ENCRYPTION_KEY in .env for production."
                )
        return cls._key

    @classmethod
    def _get_fernet(cls) -> Fernet:
        """Get or create Fernet instance."""
        if cls._fernet is None:
            key = cls._get_key()
            # Ensure key is valid Fernet key (32 bytes, base64url encoded)
            if len(key) != 44:  # Fernet keys are 44 bytes when base64url encoded
                # Try to decode if it's base64
                try:
                    key = base64.urlsafe_b64decode(key)
                except Exception:
                    # Generate new key if invalid
                    key = Fernet.generate_key()
                    logger.warning("Invalid encryption key format. Generated a new key.")
            cls._fernet = Fernet(key)
        return cls._fernet

    @classmethod
    def encrypt(cls, plaintext: str) -> str:
        """
        Encrypt a plaintext string.

        Args:
            plaintext: String to encrypt

        Returns:
            Base64-encoded encrypted string

        Example:
            >>> encrypted = EncryptionManager.encrypt("my_password")
            >>> decrypted = EncryptionManager.decrypt(encrypted)
        """
        if not plaintext:
            return ""
        try:
            fernet = cls._get_fernet()
            encrypted_bytes = fernet.encrypt(plaintext.encode("utf-8"))
            return base64.urlsafe_b64encode(encrypted_bytes).decode("utf-8")
        except Exception as e:
            logger.error(f"Encryption failed: {e}", exc_info=True)
            raise ValueError(f"Failed to encrypt data: {e}") from e

    @classmethod
    def decrypt(cls, ciphertext: str) -> str:
        """
        Decrypt an encrypted string.

        Args:
            ciphertext: Base64-encoded encrypted string

        Returns:
            Decrypted plaintext string

        Raises:
            ValueError: If decryption fails (invalid key or corrupted data)
        """
        if not ciphertext:
            return ""
        try:
            fernet = cls._get_fernet()
            encrypted_bytes = base64.urlsafe_b64decode(ciphertext.encode("utf-8"))
            decrypted_bytes = fernet.decrypt(encrypted_bytes)
            return decrypted_bytes.decode("utf-8")
        except Exception as e:
            logger.error(f"Decryption failed: {e}", exc_info=True)
            raise ValueError(f"Failed to decrypt data: {e}") from e

    @classmethod
    def generate_key(cls) -> str:
        """
        Generate a new Fernet encryption key.

        Returns:
            Base64-encoded key string (safe to store in .env)

        Example:
            >>> key = EncryptionManager.generate_key()
            >>> # Store this in ENCRYPTION_KEY environment variable
        """
        key = Fernet.generate_key()
        return key.decode("utf-8")


def encrypt_panel_credentials(api_key: str) -> str:
    """
    Encrypt panel API key/password for storage.

    Args:
        api_key: Plaintext API key or password

    Returns:
        Encrypted string
    """
    return EncryptionManager.encrypt(api_key)


def decrypt_panel_credentials(encrypted_key: str) -> str:
    """
    Decrypt panel API key/password for use.

    Args:
        encrypted_key: Encrypted API key or password

    Returns:
        Decrypted plaintext string
    """
    return EncryptionManager.decrypt(encrypted_key)
