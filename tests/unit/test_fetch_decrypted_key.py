"""
tests/unit/test_fetch_decrypted_key.py — Regression tests for Bug 1.

Verifies that fetch_decrypted_key() reads the correct ORM column (ciphertext_b64)
and raises ProviderError when the key is not found.
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.adapters.persistence.models import ProviderKeyModel
from app.core.exceptions import ProviderError
from app.orchestration.utils import fetch_decrypted_key


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_model(ciphertext_b64: str = "FAKE_CIPHER") -> MagicMock:
    """
    Build a minimal ProviderKeyModel-like mock with the correct column populated.

    We deliberately use MagicMock rather than instantiating the real ORM class
    because SQLAlchemy's descriptor machinery requires a live session to set
    mapped attributes on an unmapped instance.  The mock is sufficient to verify
    that the code reads `ciphertext_b64` (and not `encrypted_key`).
    """
    m = MagicMock()
    m.ciphertext_b64 = ciphertext_b64
    # Explicitly ensure there is no `encrypted_key` attribute — if the code
    # tries to access it, MagicMock would auto-create it but the attribute check
    # test below ensures the production model does not have this attribute.
    del m.encrypted_key  # removing from mock ensures getattr raises AttributeError
    return m


def _make_deps(model: ProviderKeyModel | None, decrypted: str = "plaintext-key") -> MagicMock:
    """Return a GraphDependencies-like mock."""
    deps = MagicMock()

    # Vault
    deps.vault.decrypt.return_value = decrypted

    # db_session_factory as an async context manager
    mock_session = AsyncMock()
    result_mock = MagicMock()
    result_mock.scalar_one_or_none.return_value = model
    mock_session.execute = AsyncMock(return_value=result_mock)

    cm = AsyncMock()
    cm.__aenter__ = AsyncMock(return_value=mock_session)
    cm.__aexit__ = AsyncMock(return_value=None)
    deps.db_session_factory.return_value = cm

    return deps


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fetch_decrypted_key_reads_ciphertext_b64():
    """
    Bug 1 regression: fetch_decrypted_key must read model.ciphertext_b64.
    Previously read model.encrypted_key which raised AttributeError.
    """
    model = _make_model(ciphertext_b64="ENCRYPTED_BLOB")
    deps = _make_deps(model=model, decrypted="sk-live-key-123")

    result = await fetch_decrypted_key(deps, user_id="user-1", provider="openrouter")

    assert result == "sk-live-key-123"
    # Vault.decrypt must have been called with the ciphertext_b64 value
    deps.vault.decrypt.assert_called_once_with("ENCRYPTED_BLOB")


@pytest.mark.asyncio
async def test_fetch_decrypted_key_no_encrypted_key_attribute():
    """
    Verify the ProviderKeyModel class does NOT define an 'encrypted_key' column.
    If someone adds the wrong column back, this test will catch it.

    We inspect the SQLAlchemy mapper column keys directly — this is stable
    and does not require instantiating an ORM object without a session.
    """
    from sqlalchemy import inspect as sa_inspect
    from app.adapters.persistence.models import ProviderKeyModel

    mapper = sa_inspect(ProviderKeyModel)
    column_keys = [col.key for col in mapper.columns]

    assert "encrypted_key" not in column_keys, (
        "ProviderKeyModel must NOT have an 'encrypted_key' column. "
        "The correct column is 'ciphertext_b64'."
    )
    assert "ciphertext_b64" in column_keys, (
        "ProviderKeyModel must have a 'ciphertext_b64' column."
    )


@pytest.mark.asyncio
async def test_fetch_decrypted_key_raises_provider_error_when_missing():
    """
    When no key row exists for (user_id, provider), ProviderError must be raised.
    This prevents a silent None→decrypt() crash.
    """
    deps = _make_deps(model=None)

    with pytest.raises(ProviderError) as exc_info:
        await fetch_decrypted_key(deps, user_id="user-1", provider="openrouter")

    assert "openrouter" in str(exc_info.value).lower() or "openrouter" in str(exc_info.value.details)


@pytest.mark.asyncio
async def test_fetch_decrypted_key_provider_name_in_error():
    """The ProviderError details must include the provider name for frontend diagnostics."""
    deps = _make_deps(model=None)

    with pytest.raises(ProviderError) as exc_info:
        await fetch_decrypted_key(deps, user_id="user-42", provider="nvidia_nim")

    assert exc_info.value.details.get("provider") == "nvidia_nim"
