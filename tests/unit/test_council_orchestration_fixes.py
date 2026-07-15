import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.core.exceptions import AuthenticationError, CircuitOpenError, ProviderError
from app.core.circuit_breaker import CircuitBreaker, get_breaker
from app.core.llm_router import LLMRouter
from app.orchestration.graph import route_after_stage_1, route_after_chairman_validation
from app.domain.rules.ranking import elect_chairman, borda_count

@pytest.mark.asyncio
async def test_authentication_error_does_not_record_circuit_breaker_failure():
    """Verify that raising AuthenticationError does not trip the circuit breaker."""
    breaker = CircuitBreaker(provider="openrouter", failure_threshold=2)
    breaker.reset()
    
    async def failing_call():
        raise AuthenticationError(message="Invalid API Key", provider="openrouter")
        
    with pytest.raises(AuthenticationError):
        await breaker.call(failing_call)
        
    # Failure count should still be 0 because AuthenticationError is ignored by the circuit breaker
    assert breaker._failure_count == 0

@pytest.mark.asyncio
async def test_llm_router_auth_fail_fast():
    """Verify that LLMRouter fast-fails subsequent calls in the same run/session if an auth error occurs."""
    router = LLMRouter(max_attempts=1)
    
    # Mock adapter
    mock_adapter = MagicMock()
    mock_adapter.chat = AsyncMock(side_effect=AuthenticationError(message="Invalid API Key", provider="openrouter"))
    
    with patch("app.adapters.llm_providers.factory.ProviderAdapterFactory.create", return_value=mock_adapter):
        # First call should execute and raise AuthenticationError
        with pytest.raises(AuthenticationError):
            await router.chat(
                messages=[],
                model_id="gpt-4",
                provider="openrouter",
                api_key="fake-key",
                user_id="user-1",
                session_id="session-xyz"
            )
            
        # Second call with the same session_id and provider should fast-fail without calling the adapter
        mock_adapter.chat.reset_mock()
        with pytest.raises(AuthenticationError):
            await router.chat(
                messages=[],
                model_id="gpt-4",
                provider="openrouter",
                api_key="fake-key",
                user_id="user-1",
                session_id="session-xyz"
            )
        mock_adapter.chat.assert_not_called()

def test_route_after_stage_1_guards():
    """Verify routing logic based on the number of successful Stage 1 responses."""
    # 0 successful responses -> route to finish
    state_0 = {"successful_member_ids": []}
    assert route_after_stage_1(state_0) == "finish"
    
    # 1 successful response -> degraded path, route to stage_3_setup
    state_1 = {"successful_member_ids": ["member_a"]}
    assert route_after_stage_1(state_1) == "stage_3_setup"
    
    # >=2 successful responses -> route to stage_2_setup
    state_2 = {"successful_member_ids": ["member_a", "member_b"]}
    assert route_after_stage_1(state_2) == "stage_2_setup"

def test_route_after_chairman_validation():
    """Verify chairman validation routing."""
    # No effective chairman -> finish
    state_no_chairman = {"effective_chairman_id": ""}
    assert route_after_chairman_validation(state_no_chairman) == "finish"
    
    # Has effective chairman -> proceed to stage 3 synthesis
    state_with_chairman = {"effective_chairman_id": "member_a"}
    assert route_after_chairman_validation(state_with_chairman) == "stage_3_synthesis"

def test_borda_count_excludes_failed_members():
    """Verify borda count scores are calculated only for successful members."""
    anon_map = {
        "member_a": "Member A",
        "member_b": "Member B",
        "member_c": "Member C",
    }
    
    # member_c failed Stage 1, so only member_a and member_b are successful
    successful_member_ids = ["member_a", "member_b"]
    
    # Mock ballot containing ranking for Member C (which shouldn't be counted)
    ballots = [
        {
            "ranked_by_member_id": "member_a",
            "ranking_order": ["Member B", "Member C", "Member A"],
            "justification": "review"
        }
    ]
    
    scores = borda_count(
        ballots=ballots,
        member_ids=successful_member_ids,
        anon_map=anon_map
    )
    
    # member_c should be excluded from scores completely
    assert "member_c" not in scores
    assert "member_a" in scores
    assert "member_b" in scores
