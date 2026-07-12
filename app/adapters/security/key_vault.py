"""
adapters/security/key_vault.py — Fernet-based symmetric encryption for provider keys.

All user-supplied API keys (OpenRouter, NVIDIA NIM, Tavily, Anakin, Notion)
are stored encrypted at rest in Supabase PostgreSQL.  This module is the ONLY
place that imports cryptographic primitives.

Security guarantees:
  - Fernet uses AES-128-CBC with HMAC-SHA256 for authenticated encryption.
    A tampered ciphertext will raise InvalidToken rather than decrypt silently.
  - The CREDENTIAL_ENCRYPTION_KEY env var must be a URL-safe base64-encoded
    32-byte key (generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())").
  - Keys are NEVER logged, NEVER returned to the frontend, NEVER included in
    LangSmith traces.

Pattern: Singleton (one Fernet instance per process — instantiation is
         expensive; a module-level instance is thread-safe once created).
"""
from __future__ import annotations

import base64
import logging

from cryptography.fernet import Fernet, InvalidToken

from app.core.config import settings

logger = logging.getLogger(__name__)


class KeyVaultError(Exception):
    """Raised when encryption or decryption fails."""


class KeyVault:
    """
    Singleton service for encrypting and decrypting provider API keys.

    Usage:
        vault = KeyVault.instance()
        ciphertext = vault.encrypt("sk-my-openrouter-key")
        plaintext  = vault.decrypt(ciphertext)
    """

    _instance: KeyVault | None = None

    def __init__(self, encryption_key: str) -> None:
        try:
            # Validate that the key is proper Fernet key material
            self._fernet = Fernet(encryption_key.encode())
        except Exception as exc:
            raise KeyVaultError(
                "Invalid CREDENTIAL_ENCRYPTION_KEY. "
                "Generate one with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
            ) from exc

    @classmethod
    def instance(cls) -> "KeyVault":
        """Return the process-level singleton, creating it on first call."""
        if cls._instance is None:
            cls._instance = cls(settings.CREDENTIAL_ENCRYPTION_KEY)
        return cls._instance

    def encrypt(self, plaintext: str) -> str:
        """
        Encrypt a plaintext API key and return a URL-safe base64 ciphertext string.

        Args:
            plaintext: The raw API key string.

        Returns:
            Encrypted, base64-encoded string safe to store in the database.

        Raises:
            KeyVaultError: if encryption fails.
        """
        try:
            token = self._fernet.encrypt(plaintext.encode("utf-8"))
            return token.decode("utf-8")
        except Exception as exc:
            raise KeyVaultError("Encryption failed.") from exc

    def decrypt(self, ciphertext: str) -> str:
        """
        Decrypt a ciphertext string back to the plaintext API key.

        Args:
            ciphertext: The encrypted string retrieved from the database.

        Returns:
            The original plaintext API key string.

        Raises:
            KeyVaultError: if the ciphertext is invalid, tampered, or expired.
        """
        try:
            plaintext = self._fernet.decrypt(ciphertext.encode("utf-8"))
            return plaintext.decode("utf-8")
        except InvalidToken as exc:
            raise KeyVaultError(
                "Decryption failed: invalid or tampered ciphertext."
            ) from exc
        except Exception as exc:
            raise KeyVaultError("Decryption failed.") from exc

    @staticmethod
    def generate_key() -> str:
        """
        Generate a new valid Fernet key for use in CREDENTIAL_ENCRYPTION_KEY.

        This is a utility method for first-time setup / key rotation.
        """
        return Fernet.generate_key().decode("utf-8")
