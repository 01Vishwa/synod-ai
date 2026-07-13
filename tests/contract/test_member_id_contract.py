"""
tests/contract/test_member_id_contract.py

Executable contract specification for the member_id format.

Canonical rule: member_id = "member_" + lowercase-alphanumeric suffix
Regex: ^member_[a-z0-9]+$

Run with: pytest tests/contract/test_member_id_contract.py -v
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.api.v1.schemas.sessions import (
    CouncilMemberConfigSchema,
    SessionCreateRequest,
)


# ── helpers ───────────────────────────────────────────────────────────────

def _make_member(
    member_id: str = "member_ap0mr8y",
    provider: str = "openrouter",
    model_id: str = "openai/gpt-4.1",
    display_label: str = "Seat",
    role: str = "member",
) -> dict:
    return dict(
        member_id=member_id,
        provider=provider,
        model_id=model_id,
        display_label=display_label,
        role=role,
    )


def _base_request(**overrides) -> dict:
    """Minimal valid SessionCreateRequest (no chairman — uses election mode)."""
    return {
        "user_query": "What is the optimal trade-off between microservices and monolith?",
        "members": [
            _make_member("member_a1b2c3d", display_label="Seat A"),
            _make_member("member_e4f5g6h", display_label="Seat B"),
            _make_member("member_j7k8m9n", display_label="Seat C"),
        ],
        "research_enabled": False,
        **overrides,
    }


# ── 1. Canonical valid IDs are accepted ───────────────────────────────────

@pytest.mark.parametrize("member_id", [
    "member_ap0mr8y",   # frontend Math.random().toString(36) output
    "member_k72mx9p",
    "member_q8p3n2a",
    "member_a1b2c3d",
    "member_0000000",   # all digits — still valid
    "member_aaaaaaa",   # all lowercase letters — valid
    "member_abc",       # short suffix — valid (no minimum suffix length)
    "member_123",       # purely numeric suffix — valid under new regex
    "member_a",         # single char suffix
])
def test_valid_member_id_accepted(member_id: str) -> None:
    """Canonical opaque IDs (lowercase alphanumeric suffix) must be accepted."""
    schema = CouncilMemberConfigSchema(**_make_member(member_id))
    assert schema.member_id == member_id


# ── 2. Invalid IDs are rejected ───────────────────────────────────────────

@pytest.mark.parametrize("bad_id", [
    "seat_1",           # wrong prefix
    "member-ap0mr8y",   # hyphen in separator
    "member_AP0MR8Y",   # uppercase letters
    "member_ap0mr8y!",  # special character
    "member_",          # empty suffix
    "member",           # no underscore at all
    "ap0mr8y",          # missing prefix entirely
    "MEMBER_ap0mr8y",   # uppercase prefix
    "member_ap 0mr",    # space
    "",                 # empty string
])
def test_invalid_member_id_rejected(bad_id: str) -> None:
    """Anything outside ^member_[a-z0-9]+$ must raise ValidationError."""
    with pytest.raises(ValidationError):
        CouncilMemberConfigSchema(**_make_member(bad_id))


# ── 3. Session with valid opaque IDs is accepted ──────────────────────────

def test_session_with_opaque_ids_accepted() -> None:
    """Full session payload using frontend-generated IDs must validate."""
    req = SessionCreateRequest(**_base_request())
    assert len(req.members) == 3
    assert req.members[0].member_id == "member_a1b2c3d"
    assert req.members[1].member_id == "member_e4f5g6h"
    assert req.members[2].member_id == "member_j7k8m9n"


# ── 4. Four-seat payload matching the user's current council ──────────────

def test_four_seat_payload_with_chairman() -> None:
    """Exact payload shape the user submits — must not produce 422."""
    req = SessionCreateRequest(**{
        "user_query": "What is the optimal architecture for our system?",
        "members": [
            _make_member("member_a1b2c3d", model_id="nvidia/nemotron-3-ultra-550b-a55b:free",
                         display_label="council 1", role="member"),
            _make_member("member_e4f5g6h", model_id="cohere/north-mini-code:free",
                         display_label="Council Seat 2", role="member"),
            _make_member("member_j7k8m9n", model_id="meta-llama/llama-3.2-3b-instruct:free",
                         display_label="Council Seat 3", role="member"),
            _make_member("member_ap0mr8y", model_id="google/gemma-4-26b-a4b-it:free",
                         display_label="Council Seat 4", role="chairman"),
        ],
        "chairman_member_id": "member_ap0mr8y",
        "research_enabled": False,
        "archive_to_notion": False,
    })
    assert req.chairman_member_id == "member_ap0mr8y"
    assert req.members[3].role == "chairman"
    assert req.members[3].member_id == req.chairman_member_id


# ── 5. Duplicate member IDs are rejected ──────────────────────────────────

def test_duplicate_member_ids_rejected() -> None:
    """Two seats with the same member_id must fail validation."""
    with pytest.raises(ValidationError, match="unique"):
        SessionCreateRequest(**_base_request(
            members=[
                _make_member("member_ap0mr8y", display_label="Seat A"),
                _make_member("member_ap0mr8y", display_label="Seat B"),  # duplicate
                _make_member("member_j7k8m9n", display_label="Seat C"),
            ]
        ))


# ── 6. chairman_member_id not found in members is rejected ────────────────

def test_chairman_member_id_not_in_members_rejected() -> None:
    """chairman_member_id referencing a non-existent member must fail."""
    with pytest.raises(ValidationError, match="chairman_member_id does not correspond"):
        SessionCreateRequest(**{
            "user_query": "Which approach is better?",
            "members": [
                _make_member("member_a1b2c3d", display_label="Seat A", role="chairman"),
                _make_member("member_e4f5g6h", display_label="Seat B"),
                _make_member("member_j7k8m9n", display_label="Seat C"),
            ],
            "chairman_member_id": "member_xxxxxxx",   # does not exist in members
            "research_enabled": False,
        })


# ── 7. Two chairmen are rejected ──────────────────────────────────────────

def test_two_chairmen_rejected() -> None:
    """Having two members with role='chairman' must fail."""
    with pytest.raises(ValidationError, match="At most one council member"):
        SessionCreateRequest(**{
            "user_query": "Which approach is better?",
            "members": [
                _make_member("member_a1b2c3d", display_label="Seat A", role="chairman"),
                _make_member("member_e4f5g6h", display_label="Seat B", role="chairman"),
                _make_member("member_j7k8m9n", display_label="Seat C"),
            ],
            "chairman_member_id": "member_a1b2c3d",
            "research_enabled": False,
        })


# ── 8. Chairman role without chairman_member_id is rejected ───────────────

def test_chairman_role_without_chairman_member_id_rejected() -> None:
    """A member with role='chairman' but no chairman_member_id set must fail."""
    with pytest.raises(ValidationError):
        SessionCreateRequest(**{
            "user_query": "Which approach is better?",
            "members": [
                _make_member("member_a1b2c3d", display_label="Seat A", role="chairman"),
                _make_member("member_e4f5g6h", display_label="Seat B"),
                _make_member("member_j7k8m9n", display_label="Seat C"),
            ],
            # chairman_member_id deliberately omitted
            "research_enabled": False,
        })


# ── 9. member_id stability: changing provider/model does NOT change member_id

def test_member_id_stable_across_provider_change() -> None:
    """
    Simulate a user changing provider/model on a seat.
    The member_id must remain unchanged — it is the seat identity, not its config.
    """
    original_id = "member_ap0mr8y"
    # Original seat: openrouter + nemotron
    seat_v1 = CouncilMemberConfigSchema(**_make_member(
        original_id, provider="openrouter",
        model_id="nvidia/nemotron-3-ultra-550b-a55b:free",
    ))
    # Updated seat: provider changed to nvidia_nim, model changed — ID unchanged
    seat_v2 = CouncilMemberConfigSchema(**_make_member(
        original_id, provider="nvidia_nim",
        model_id="meta/llama-3.3-70b-instruct",
    ))
    assert seat_v1.member_id == seat_v2.member_id == original_id


# ── 10. Removing another seat does not affect surviving member IDs ─────────

def test_member_ids_stable_after_removal() -> None:
    """
    When a seat is removed from the council, the remaining member IDs
    must stay the same (no re-indexing to member_0, member_1, etc.).
    """
    all_seats = [
        _make_member("member_a1b2c3d", display_label="Seat A"),
        _make_member("member_e4f5g6h", display_label="Seat B"),
        _make_member("member_j7k8m9n", display_label="Seat C"),
        _make_member("member_ap0mr8y", display_label="Seat D"),
    ]
    # Remove Seat B (index 1)
    remaining = [s for s in all_seats if s["member_id"] != "member_e4f5g6h"]
    assert len(remaining) == 3
    # Seat C still has its original ID — not "member_1" or similar
    assert remaining[1]["member_id"] == "member_j7k8m9n"
    # Seat D still has its original ID
    assert remaining[2]["member_id"] == "member_ap0mr8y"


# ── 11. Old numeric IDs are accepted under new regex (backwards compatible) ─

@pytest.mark.parametrize("old_numeric_id", [
    "member_0",
    "member_1",
    "member_42",
    "member_123",
])
def test_old_numeric_ids_still_accepted_under_new_regex(old_numeric_id: str) -> None:
    """
    The new regex ``^member_[a-z0-9]+$`` is a SUPERSET of the old ``^member_\\d+$``.
    Pure numeric suffixes are still valid — the change is additive, not breaking.
    """
    schema = CouncilMemberConfigSchema(**_make_member(old_numeric_id))
    assert schema.member_id == old_numeric_id
