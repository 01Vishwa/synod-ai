"""
tests/unit/test_session_create_request_schema.py

Regression suite for the chairman_member_id field on SessionCreateRequest.

Locks in two invariants caught by the router/schema drift bug
(routers/sessions.py:94 referenced req.pinned_chairman_member_id which never
existed):

  1. The field is named `chairman_member_id` — not `pinned_chairman_member_id`
     or any other variant.
  2. The field is optional — omitting it must not raise a ValidationError
     (the orchestrator elects the top Stage-2 scorer when it is unset,
     per PRD Section 6.5 step 4).

Run with: pytest tests/unit/test_session_create_request_schema.py -v
"""
from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.api.v1.schemas.sessions import SessionCreateRequest


# ── helpers ───────────────────────────────────────────────────────────────────

def _base_payload(**overrides) -> dict:
    """Minimal valid SessionCreateRequest payload (election mode — no chairman)."""
    return {
        "user_query": "What is the trade-off between microservices and a monolith?",
        "members": [
            {
                "member_id": "member_a1b2c3d",
                "provider": "openrouter",
                "model_id": "anthropic/claude-sonnet-4.5",
                "display_label": "Seat A",
                "role": "member",
            },
            {
                "member_id": "member_e4f5g6h",
                "provider": "nvidia_nim",
                "model_id": "meta/llama-3.3-70b-instruct",
                "display_label": "Seat B",
                "role": "member",
            },
            {
                "member_id": "member_j7k8m9n",
                "provider": "openrouter",
                "model_id": "openai/gpt-4.1",
                "display_label": "Seat C",
                "role": "member",
            },
        ],
        "research_enabled": False,
        **overrides,
    }


# ── 1. Field name is exactly `chairman_member_id` ────────────────────────────

def test_chairman_member_id_attribute_exists() -> None:
    """
    SessionCreateRequest must expose the attribute `chairman_member_id`.

    This is the regression test for the drift bug where the router
    accessed `req.pinned_chairman_member_id` which raised AttributeError.
    """
    req = SessionCreateRequest(**_base_payload())
    # The attribute must be reachable — AttributeError means the field name drifted
    _ = req.chairman_member_id  # would raise AttributeError if name is wrong


def test_pinned_chairman_member_id_does_not_exist() -> None:
    """
    The ghost field name `pinned_chairman_member_id` must NOT exist.

    If this test ever fails it means someone added the wrong alias back.
    """
    req = SessionCreateRequest(**_base_payload())
    assert not hasattr(req, "pinned_chairman_member_id"), (
        "SessionCreateRequest must not have a 'pinned_chairman_member_id' attribute. "
        "The canonical field is 'chairman_member_id'."
    )


# ── 2. Field is optional — omitting it must not raise ────────────────────────

def test_chairman_member_id_is_optional_defaults_to_none() -> None:
    """
    Omitting chairman_member_id must not raise ValidationError.

    When unset the orchestrator elects the top-ranked Stage-2 member
    (PRD §6.5 step 4). The default must be None so the router can
    forward `""` (falsy → orchestrator election path).
    """
    req = SessionCreateRequest(**_base_payload())  # chairman_member_id absent
    assert req.chairman_member_id is None


def test_chairman_member_id_explicitly_none_is_accepted() -> None:
    """Passing chairman_member_id=None explicitly is equivalent to omitting it."""
    req = SessionCreateRequest(**_base_payload(chairman_member_id=None))
    assert req.chairman_member_id is None


# ── 3. When set, it must match a member with role='chairman' ─────────────────

def test_chairman_member_id_round_trips_when_valid() -> None:
    """A valid chairman_member_id is stored verbatim on the request object."""
    payload = _base_payload()
    # Promote Seat C to chairman so the validator accepts chairman_member_id
    payload["members"][2]["role"] = "chairman"
    payload["chairman_member_id"] = "member_j7k8m9n"

    req = SessionCreateRequest(**payload)
    assert req.chairman_member_id == "member_j7k8m9n"


def test_unknown_chairman_member_id_raises() -> None:
    """chairman_member_id must correspond to an actual member in the council."""
    payload = _base_payload()
    payload["members"][0]["role"] = "chairman"
    payload["chairman_member_id"] = "member_xxxxxxx"  # not in members

    with pytest.raises(ValidationError, match="chairman_member_id does not correspond"):
        SessionCreateRequest(**payload)
