"""
tests/unit/test_key_vault.py — Unit tests for KeyVault symmetric encryption.

Exercises the encrypt/decrypt round-trip, the sanity check that ciphertext
differs from plaintext, wrong-key decryption, and the empty-string edge case.

No live I/O — a fresh Fernet key is generated per fixture.
"""
from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from app.adapters.security.key_vault import KeyVault, KeyVaultError


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture()
def vault() -> KeyVault:
    """Return a fresh KeyVault instance backed by a newly generated Fernet key."""
    key = Fernet.generate_key().decode("utf-8")
    return KeyVault(encryption_key=key)


@pytest.fixture()
def second_vault() -> KeyVault:
    """Return a *different* KeyVault instance with an independent Fernet key."""
    key = Fernet.generate_key().decode("utf-8")
    return KeyVault(encryption_key=key)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_encrypt_decrypt_roundtrip(vault: KeyVault) -> None:
    """Encrypting then decrypting a known plaintext string returns the original value."""
    plaintext = "tvly-test-api-key-123"
    ciphertext = vault.encrypt(plaintext)
    recovered = vault.decrypt(ciphertext)
    assert recovered == plaintext


def test_encrypted_value_differs_from_plaintext(vault: KeyVault) -> None:
    """The encrypted output must not be identical to the raw plaintext string."""
    plaintext = "sk-openrouter-abc"
    ciphertext = vault.encrypt(plaintext)
    assert ciphertext != plaintext


def test_decrypt_wrong_key_raises(vault: KeyVault, second_vault: KeyVault) -> None:
    """Decrypting with a different KeyVault instance (different key) raises KeyVaultError."""
    ciphertext = vault.encrypt("super-secret-key")
    with pytest.raises(KeyVaultError):
        second_vault.decrypt(ciphertext)


def test_empty_string_roundtrip(vault: KeyVault) -> None:
    """Encrypting and decrypting an empty string returns an empty string, not an error."""
    plaintext = ""
    ciphertext = vault.encrypt(plaintext)
    recovered = vault.decrypt(ciphertext)
    assert recovered == plaintext
