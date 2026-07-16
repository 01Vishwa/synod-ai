import pytest
from app.orchestration.graph import validate_stage_1, setup_stage_2, route_stage_2, OrchestratorState

@pytest.mark.asyncio
async def test_stage_2_candidate_exclusion_contract():
    """
    Scenario:
    Council: Member 1 successful, Member 2 successful, Member 3 Stage 1 RATE_LIMIT failure
    Expected:
    successful_stage_1_member_ids: [member_1, member_2]
    Stage 2 candidate set: [member_1, member_2]
    Stage 2 reviewer set: [member_1, member_2]
    Member 3 remains: excluded_member_ids
    """
    members = [
        {"member_id": "member_1", "display_label": "Member 1"},
        {"member_id": "member_2", "display_label": "Member 2"},
        {"member_id": "member_3", "display_label": "Member 3"}
    ]
    
    stage_1_responses = [
        {"member_id": "member_1", "content": "hello", "error": None},
        {"member_id": "member_2", "content": "world", "error": None},
        {"member_id": "member_3", "content": "", "error": "rate limit error"}
    ]
    
    state = OrchestratorState(
        members=members,
        stage_1_responses=stage_1_responses,
        session_id="test",
        user_id="user1",
        user_query="test",
        stage="stage_1"
    )
    
    class MockConfig:
        pass
        
    class MockDeps:
        class Repo:
            async def save_checkpoint(self, state):
                pass
        repository = Repo()
        
    from unittest.mock import patch
    
    with patch("app.orchestration.graph.get_deps", return_value=MockDeps()):
        # Run validate_stage_1 to get successful members
        updates = await validate_stage_1(state, MockConfig())
        assert updates["successful_member_ids"] == ["member_1", "member_2"]
        assert updates["excluded_member_ids"] == ["member_3"]
        
        # Apply updates
        state = {**state, **updates}
        
        # Run setup_stage_2 to get anonymization map
        setup_updates = await setup_stage_2(state, MockConfig())
        anon_map = setup_updates["anonymization_map"]
        
        # Check candidate set (anonymized candidates)
        assert "member_1" in anon_map
        assert "member_2" in anon_map
        assert "member_3" not in anon_map
        assert len(anon_map) == 2
        
        # Apply updates
        state = {**state, **setup_updates}
        
        # Run route_stage_2 to get reviewers
        tasks = route_stage_2(state)
        
        # Tasks are sent to Send("stage_2_review", task)
        reviewer_ids = [t.arg["member"]["member_id"] for t in tasks]
        
        # Check reviewer set
        assert reviewer_ids == ["member_1", "member_2"]
        assert "member_3" not in reviewer_ids
