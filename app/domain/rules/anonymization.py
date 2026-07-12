"""
domain/rules/anonymization.py — Pure anonymization / redaction functions.

This module is a Deterministic Utility — no I/O, no randomness in production
(seed is injectable for tests), no LLM calls.

Responsibilities:
  1. Assign a random label ("Member A", "Member B", …) to each council member
     for the duration of Stage 2, ensuring no model can infer its own identity
     from label ordering alone.
  2. Strip provider-specific formatting tics and model-name mentions from
     Stage 1 response text before handing it to Stage 2 reviewers.

These rules are enforced by the Orchestrator, not prompted to the models.

Pattern: Strategy (anonymization algorithm is a pluggable pure function),
         pure function composition (no side effects, fully unit-testable).
"""
from __future__ import annotations

import random
import re
import string
from typing import Optional

from app.domain.council_state import CouncilMemberConfig, MemberResponse


# ── Label generation ──────────────────────────────────────────────────────

def _generate_labels(n: int) -> list[str]:
    """
    Produce N unique uppercase letter labels: "Member A", "Member B", …

    For n > 26, extends to "Member AA", "Member AB", … (no practical ceiling
    for council sizes the product supports, which max at 6).
    """
    labels: list[str] = []
    for i in range(n):
        if i < 26:
            labels.append(f"Member {string.ascii_uppercase[i]}")
        else:
            # Two-letter suffix for very large panels (edge case)
            first = string.ascii_uppercase[(i // 26) - 1]
            second = string.ascii_uppercase[i % 26]
            labels.append(f"Member {first}{second}")
    return labels


def build_anonymization_map(
    members: list[CouncilMemberConfig],
    *,
    seed: Optional[int] = None,
) -> dict[str, str]:
    """
    Create a randomised member_id → anonymized_label mapping.

    The shuffle ensures no member can infer position from alphabetical label
    assignment (e.g., "Member A is probably the first model I added").

    Args:
        members: The full list of council members.
        seed:    Optional RNG seed for deterministic test fixtures.

    Returns:
        A dict mapping each member_id to its anonymized label for this run.
    """
    rng = random.Random(seed)
    ids = [m["member_id"] for m in members]
    labels = _generate_labels(len(ids))
    rng.shuffle(labels)
    return dict(zip(ids, labels))


# ── Per-member shuffle for Stage 2 ───────────────────────────────────────

def shuffle_responses_for_reviewer(
    responses: list[MemberResponse],
    anonymization_map: dict[str, str],
    reviewer_member_id: str,
    *,
    seed: Optional[int] = None,
) -> list[MemberResponse]:
    """
    Return a shuffled copy of `responses` with anonymized_label set.

    The order is randomised independently for each reviewer so that no two
    reviewers see the same ordering — further preventing position bias.

    The reviewer's own response is included (it will be labelled like any
    other — the reviewer cannot know which one is theirs).

    Args:
        responses:           Stage 1 responses to anonymise.
        anonymization_map:   member_id → label mapping from build_anonymization_map.
        reviewer_member_id:  The member who will receive this shuffled bundle.
        seed:                Optional RNG seed.

    Returns:
        A new list of MemberResponse with anonymized_label populated and
        member_id stripped from the content.
    """
    rng = random.Random(f"{seed}-{reviewer_member_id}" if seed is not None else None)
    labelled: list[MemberResponse] = []
    for resp in responses:
        label = anonymization_map.get(resp["member_id"], "Member ?")
        cleaned = redact_identity(resp["content"], resp["member_id"])
        labelled.append({**resp, "anonymized_label": label, "content": cleaned})
    rng.shuffle(labelled)
    return labelled


# ── Content redaction ─────────────────────────────────────────────────────

# Patterns that might reveal provider/model identity in response text.
# These are heuristics — not guaranteed to be exhaustive — but they cover the
# most common self-revealing tics.
_IDENTITY_PATTERNS: list[re.Pattern] = [
    # Explicit model name mentions: "As Claude, I…", "As GPT-4, …"
    re.compile(
        r"\b(as (claude|gpt|gemini|llama|mistral|qwen|phi|deepseek|nemotron|grok))[, ]",
        re.IGNORECASE,
    ),
    # Provider branding in prose: "Anthropic's approach", "OpenAI suggests"
    re.compile(
        r"\b(anthropic|openai|google deepmind|meta ai|nvidia ai|mistral ai)\b",
        re.IGNORECASE,
    ),
    # "I am a large language model trained by …"
    re.compile(r"i am (a |an )?(large language model|llm|ai assistant)", re.IGNORECASE),
    # Training cutoff self-reveals: "my training data ends in …"
    re.compile(r"my (training|knowledge) (data |)(ends|cut.?off)", re.IGNORECASE),
]

_REPLACEMENT = "[REDACTED]"


def redact_identity(text: str, member_id: str) -> str:
    """
    Strip common self-identifying strings from model output.

    Args:
        text:      Raw Stage 1 response content.
        member_id: Stable member ID (used to strip any literal occurrences).

    Returns:
        Cleaned text safe for Stage 2 anonymised review bundle.
    """
    result = text
    for pattern in _IDENTITY_PATTERNS:
        result = pattern.sub(_REPLACEMENT, result)
    # Also strip the literal member_id string in case a model somehow echoes it
    result = result.replace(member_id, _REPLACEMENT)
    return result
