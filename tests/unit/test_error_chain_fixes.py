"""
tests/unit/test_error_chain_fixes.py — Regression tests for Fixes 1, 3/4, and 5.

Fix 1 — Auth-failure cache must be scoped to (session_id, provider, model_id).
    Two members on the same provider but *different* models must each make their
    own real HTTP call — a 401 on model A must not fast-fail model B.

Fix 3/4 — A provider 401 with a detailed body (e.g. "insufficient credit")
    must surface its provider_message in MemberResponse.error so the frontend
    sees the real cause, never just "credential rejected."

Fix 5 — An InvalidToken decrypt failure must surface as ProviderError
    (not AuthenticationError) and the UI-bound message must NOT say
    "credential rejected" — it must say something like "provider configuration
    error" or "provider error."
"""
from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.fernet import Fernet, InvalidToken

from app.adapters.security.key_vault import KeyVault, KeyVaultError
from app.core.exceptions import (
    AuthenticationError,
    ProviderError,
)
from app.orchestration.nodes.stage_1 import Stage1Task, stage_1_node
from app.orchestration.utils import _sanitize_error


# ---------------------------------------------------------------------------
# Shared helpers (mirrors test_stage_1_node.py helpers)
# ---------------------------------------------------------------------------

def _make_config(llm_router=None, vault=None, tracer=None) -> dict:
    from app.orchestration.context import GraphDependencies

    mock_tracer = tracer or AsyncMock()
    mock_tracer.start_span = AsyncMock(return_value=MagicMock())
    mock_tracer.end_span = AsyncMock()

    mock_repo = AsyncMock()
    mock_root_span = MagicMock()

    mock_vault = vault or MagicMock()

    mock_session = AsyncMock()
    result_mock = MagicMock()
    key_model = MagicMock()
    key_model.ciphertext_b64 = "FAKE_ENCRYPTED_KEY"
    key_model.last_test_ok = True
    key_model.key_fingerprint = "fp-test"
    result_mock.scalar_one_or_none.return_value = key_model
    mock_session.execute = AsyncMock(return_value=result_mock)
    mock_cm = AsyncMock()
    mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
    mock_cm.__aexit__ = AsyncMock(return_value=None)

    if vault is None:
        mock_vault.decrypt.return_value = "sk-decrypted-key"

    deps = GraphDependencies(
        vault=mock_vault,
        tracer=mock_tracer,
        repository=mock_repo,
        root_span=mock_root_span,
        llm_router=llm_router or AsyncMock(),
        db_session_factory=MagicMock(return_value=mock_cm),
    )
    return {"configurable": {"deps": deps}}


def _make_task(member_id: str = "m1", model_id: str = "openai/gpt-4.1-mini") -> Stage1Task:
    return {
        "member": {
            "member_id": member_id,
            "provider": "openrouter",
            "model_id": model_id,
            "display_label": f"Seat {member_id}",
            "role": "council_member",
            "api_key": None,
        },
        "user_query": "What is 2+2?",
        "research_digest": None,
        "user_id": "user-abc",
        "session_id": "session-xyz",
    }


# ---------------------------------------------------------------------------
# Fix 1: Auth-failure cache scoped per (session_id, provider, model_id)
# ---------------------------------------------------------------------------

class TestFix1AuthCacheScoping:
    """
    Two council members on the same provider but different models must each
    make their own real HTTP call, even when the first call returns a 401.

    This verifies the _auth_failures key is (session_id, provider, model_id),
    NOT (session_id, provider) alone.
    """

    @pytest.mark.asyncio
    async def test_401_on_model_a_does_not_fast_fail_model_b(self):
        """
        A cached AuthenticationError for (session, provider, model_a) must
        NOT block a call for (session, provider, model_b).
        """
        from app.core.llm_router import LLMRouter
        from app.domain.ports.provider_adapter import ChatResponse

        router = LLMRouter(max_attempts=1)
        session_id = "sess-fix1"
        provider = "openrouter"
        model_a = "openai/gpt-4o-mini"
        model_b = "anthropic/claude-3-haiku"

        # Seed the cache with a failure on model_a
        auth_exc = AuthenticationError(message="Rejected", provider=provider)
        router._auth_failures[(session_id, provider, model_a)] = auth_exc

        # model_b must NOT be blocked by the cache — we expect a real call attempt.
        # Patch the adapter so model_b returns success.
        mock_adapter = AsyncMock()
        mock_adapter.chat.return_value = ChatResponse(
            content="hello",
            model_id=model_b,
            tokens_in=5,
            tokens_out=5,
            latency_ms=100,
            cost_usd=0.0,
        )

        with patch(
            "app.core.llm_router.ProviderAdapterFactory.create",
            return_value=mock_adapter,
        ):
            # model_b should succeed despite model_a being cached as failed
            result = await router.chat(
                messages=[],
                model_id=model_b,
                provider=provider,
                api_key="sk-key",
                user_id="user-1",
                session_id=session_id,
            )

        assert result.content == "hello"
        # Verify the adapter was actually called for model_b (no fast-fail)
        mock_adapter.chat.assert_called_once()

    @pytest.mark.asyncio
    async def test_401_on_model_a_correctly_fast_fails_same_model(self):
        """
        A cached AuthenticationError for (session, provider, model_a) MUST
        fast-fail a subsequent call to the same (session, provider, model_a).
        """
        from app.core.llm_router import LLMRouter

        router = LLMRouter(max_attempts=1)
        session_id = "sess-fix1"
        provider = "openrouter"
        model_a = "openai/gpt-4o-mini"

        auth_exc = AuthenticationError(message="Rejected", provider=provider)
        router._auth_failures[(session_id, provider, model_a)] = auth_exc

        mock_adapter = AsyncMock()

        with patch(
            "app.core.llm_router.ProviderAdapterFactory.create",
            return_value=mock_adapter,
        ):
            with pytest.raises(AuthenticationError):
                await router.chat(
                    messages=[],
                    model_id=model_a,
                    provider=provider,
                    api_key="sk-key",
                    user_id="user-1",
                    session_id=session_id,
                )

        # The adapter must NOT have been called — cache hit
        mock_adapter.chat.assert_not_called()

    @pytest.mark.asyncio
    async def test_different_models_cached_independently(self, monkeypatch):
        """
        After a real 401 on model_a, (session, provider, model_a) is cached.
        model_b must NOT be in the cache — it should be called and can succeed.
        """
        from app.core.llm_router import LLMRouter
        from app.domain.ports.provider_adapter import ChatResponse

        router = LLMRouter(max_attempts=1)
        session_id = "sess-fix1-b"
        provider = "openrouter"
        model_a = "openai/gpt-4o-mini"
        model_b = "meta-llama/llama-4-scout"

        call_count = {"model_b": 0}

        async def mock_chat(messages, model_id, api_key, **kwargs):
            if model_id == model_a:
                raise AuthenticationError(
                    message="Rejected — insufficient credit for this model.",
                    provider=provider,
                    details={"provider_message": "You have insufficient credits."},
                )
            call_count["model_b"] += 1
            return ChatResponse(
                content="success",
                model_id=model_b,
                tokens_in=1,
                tokens_out=1,
                latency_ms=50,
                cost_usd=0.0,
            )

        mock_adapter = MagicMock()
        mock_adapter.chat = mock_chat

        with patch(
            "app.core.llm_router.ProviderAdapterFactory.create",
            return_value=mock_adapter,
        ):
            # First call on model_a — should 401 and be cached
            with pytest.raises(AuthenticationError):
                await router.chat(
                    messages=[],
                    model_id=model_a,
                    provider=provider,
                    api_key="sk-key",
                    user_id="user-1",
                    session_id=session_id,
                )

            # model_a is now in the cache
            assert (session_id, provider, model_a) in router._auth_failures
            # model_b must NOT be in the cache
            assert (session_id, provider, model_b) not in router._auth_failures

            # Call on model_b — must reach the adapter
            result = await router.chat(
                messages=[],
                model_id=model_b,
                provider=provider,
                api_key="sk-key",
                user_id="user-1",
                session_id=session_id,
            )

        assert result.content == "success"
        assert call_count["model_b"] == 1


# ---------------------------------------------------------------------------
# Fix 3/4: Provider-detailed 401 surfaces real message in MemberResponse
# ---------------------------------------------------------------------------

class TestFix34ProviderMessageThreading:
    """
    When OpenRouter returns a 401 with a body indicating "insufficient credit",
    the provider_message must flow through AuthenticationError.details and into
    MemberResponse.error.  The UI-visible string must NOT be a generic
    "credential rejected" template only.
    """

    @pytest.mark.asyncio
    async def test_401_with_provider_message_surfaces_in_member_response(self, monkeypatch):
        """
        A 401 that carries a specific provider message ('insufficient credit')
        must include that detail in the MemberResponse.error field.
        The message must NOT be the bare generic 'credential rejected' template.
        """
        provider_detail = "You have insufficient credits. Add more at openrouter.ai/credits."
        auth_exc = AuthenticationError(
            message="OpenRouter authentication failed — check your API key.",
            provider="openrouter",
            details={"provider_message": provider_detail},
        )

        mock_bus = AsyncMock()
        monkeypatch.setattr(
            "app.orchestration.nodes.stage_1.get_or_create_bus",
            AsyncMock(return_value=mock_bus),
        )

        async def _stream_raises(*args, **kwargs):
            raise auth_exc
            yield  # make it an async generator

        mock_router = MagicMock()
        mock_router.stream_chat = _stream_raises

        config = _make_config(llm_router=mock_router)
        result = await stage_1_node(_make_task(), config)

        resp = result["stage_1_responses"][0]
        assert resp["error"] is not None

        # The error string must contain the provider-supplied detail, not just
        # the generic credential-rejected template.
        assert provider_detail in resp["error"], (
            f"Expected provider detail in MemberResponse.error, got: {resp['error']!r}"
        )

    def test_sanitize_error_auth_message_does_not_say_credential_rejected_for_non_auth(self):
        """
        _sanitize_error must NOT produce the "credential rejected" phrase for
        non-AuthenticationError exceptions (e.g. ProviderError from decrypt failure).
        """
        provider = "openrouter"
        exc = ProviderError(message="Failed to decrypt API key.", provider=provider)
        msg = _sanitize_error(exc, provider)

        assert "credential" not in msg.lower() or "rejected" not in msg.lower(), (
            f"_sanitize_error returned a credential-rejected message for ProviderError: {msg!r}"
        )
        assert "provider" in msg.lower(), (
            f"Expected 'provider' in sanitized message, got: {msg!r}"
        )

    @pytest.mark.asyncio
    async def test_member_response_error_class_is_authentication_error_on_401(self, monkeypatch):
        """
        When the error class is AuthenticationError, MemberResponse.error_class
        must be 'AuthenticationError' so the frontend can branch on it.
        """
        auth_exc = AuthenticationError(
            message="OpenRouter authentication failed — check your API key.",
            provider="openrouter",
        )

        mock_bus = AsyncMock()
        monkeypatch.setattr(
            "app.orchestration.nodes.stage_1.get_or_create_bus",
            AsyncMock(return_value=mock_bus),
        )

        async def _stream_raises(*args, **kwargs):
            raise auth_exc
            yield

        mock_router = MagicMock()
        mock_router.stream_chat = _stream_raises

        config = _make_config(llm_router=mock_router)
        result = await stage_1_node(_make_task(), config)

        resp = result["stage_1_responses"][0]
        assert resp.get("error_class") == "AuthenticationError", (
            f"Expected error_class='AuthenticationError', got: {resp.get('error_class')!r}"
        )


# ---------------------------------------------------------------------------
# Fix 5: InvalidToken (decrypt failure) surfaces as ProviderError, not auth
# ---------------------------------------------------------------------------

class TestFix5DecryptFailureDistinction:
    """
    When the Fernet key has been rotated without re-encrypting stored rows,
    vault.decrypt() raises KeyVaultError (wrapping InvalidToken).
    This must flow through as ProviderError (not AuthenticationError) and
    the UI-visible message must NEVER say "credential rejected."
    """

    def test_key_vault_wrong_key_raises_key_vault_error_not_invalid_token(self):
        """
        vault.decrypt() with a wrong key must raise KeyVaultError, not the
        raw cryptography.fernet.InvalidToken.  KeyVaultError is the boundary
        type that orchestration code handles.
        """
        vault_a = KeyVault(encryption_key=Fernet.generate_key().decode())
        vault_b = KeyVault(encryption_key=Fernet.generate_key().decode())

        ciphertext = vault_a.encrypt("sk-my-key-123")

        with pytest.raises(KeyVaultError):
            vault_b.decrypt(ciphertext)

    def test_key_vault_error_is_not_authentication_error(self):
        """
        KeyVaultError must NOT be a subclass of AuthenticationError.
        Orchestration code uses isinstance() to distinguish them.
        """
        assert not issubclass(KeyVaultError, AuthenticationError), (
            "KeyVaultError must not extend AuthenticationError — "
            "a decrypt failure is a configuration error, not a bad API key."
        )

    @pytest.mark.asyncio
    async def test_decrypt_failure_raises_provider_error_not_auth_error(self):
        """
        When vault.decrypt() raises KeyVaultError (simulating a rotated
        CREDENTIAL_ENCRYPTION_KEY), fetch_decrypted_key must raise ProviderError,
        NOT AuthenticationError.
        """
        from app.orchestration.utils import fetch_decrypted_key

        vault_a = KeyVault(encryption_key=Fernet.generate_key().decode())
        vault_b = KeyVault(encryption_key=Fernet.generate_key().decode())

        # Simulate: key was encrypted with vault_a, but the process uses vault_b
        ciphertext_from_old_key = vault_a.encrypt("sk-real-key")

        mock_session = AsyncMock()
        result_mock = MagicMock()
        key_model = MagicMock()
        key_model.ciphertext_b64 = ciphertext_from_old_key
        key_model.last_test_ok = True
        key_model.key_fingerprint = "fp-rotated"
        result_mock.scalar_one_or_none.return_value = key_model
        mock_session.execute = AsyncMock(return_value=result_mock)

        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=None)

        deps = MagicMock()
        deps.vault = vault_b  # wrong key — decryption will fail
        deps.db_session_factory.return_value = mock_cm

        with pytest.raises(ProviderError) as exc_info:
            await fetch_decrypted_key(deps, user_id="user-1", provider="openrouter")

        # Must be ProviderError, NOT AuthenticationError
        assert not isinstance(exc_info.value, AuthenticationError), (
            "A decrypt failure (InvalidToken) must raise ProviderError, "
            "not AuthenticationError.  'credential rejected' is wrong for a "
            "key-rotation/misconfiguration scenario."
        )

    @pytest.mark.asyncio
    async def test_decrypt_failure_member_response_error_class_is_not_auth(self, monkeypatch):
        """
        End-to-end through stage_1_node: when the vault raises KeyVaultError
        (wrong encryption key), MemberResponse.error_class must be 'ProviderError'
        and MemberResponse.error must NOT say 'credential rejected.'
        """
        # Use a vault with a different key to force decrypt failure
        vault_a = KeyVault(encryption_key=Fernet.generate_key().decode())
        vault_b = KeyVault(encryption_key=Fernet.generate_key().decode())

        ciphertext = vault_a.encrypt("sk-original-key")

        # Patch the db so it returns the ciphertext encrypted by vault_a
        mock_session = AsyncMock()
        result_mock = MagicMock()
        key_model = MagicMock()
        key_model.ciphertext_b64 = ciphertext
        key_model.last_test_ok = True
        key_model.key_fingerprint = "fp-rotated"
        result_mock.scalar_one_or_none.return_value = key_model
        mock_session.execute = AsyncMock(return_value=result_mock)
        mock_cm = AsyncMock()
        mock_cm.__aenter__ = AsyncMock(return_value=mock_session)
        mock_cm.__aexit__ = AsyncMock(return_value=None)

        mock_bus = AsyncMock()
        monkeypatch.setattr(
            "app.orchestration.nodes.stage_1.get_or_create_bus",
            AsyncMock(return_value=mock_bus),
        )

        # vault_b cannot decrypt vault_a's ciphertext — simulates key rotation
        config = _make_config(vault=vault_b)
        # Patch the db_session_factory inside the deps to use our mock
        config["configurable"]["deps"].db_session_factory = MagicMock(return_value=mock_cm)

        result = await stage_1_node(_make_task(), config)

        resp = result["stage_1_responses"][0]
        assert resp["error"] is not None

        # error_class must be ProviderError, NOT AuthenticationError
        assert resp.get("error_class") == "ProviderError", (
            f"Expected error_class='ProviderError' for decrypt failure, "
            f"got: {resp.get('error_class')!r}"
        )

        # The message must NOT say 'credential rejected'
        error_lower = resp["error"].lower()
        assert "credential" not in error_lower or "rejected" not in error_lower, (
            f"Decrypt failure message must not say 'credential rejected', "
            f"got: {resp['error']!r}"
        )

    def test_sanitize_error_provider_error_message_differs_from_auth_message(self):
        """
        _sanitize_error must return a clearly different message for ProviderError
        vs AuthenticationError — the UI relies on this to show the right banner.
        """
        provider = "openrouter"
        auth_msg = _sanitize_error(
            AuthenticationError(message="Rejected", provider=provider), provider
        )
        provider_msg = _sanitize_error(
            ProviderError(message="Failed to decrypt API key.", provider=provider), provider
        )

        assert auth_msg != provider_msg, (
            "_sanitize_error must return different messages for "
            "AuthenticationError vs ProviderError"
        )
        # Auth message references credentials; provider message should not say "credential rejected"
        assert "credential" not in provider_msg.lower() or "rejected" not in provider_msg.lower()
