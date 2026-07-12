"""
domain/rules/ranking.py — Borda-count aggregation Strategy.

Computes normalised aggregate scores from Stage 2 peer rankings.

Design:
  - Implements the Borda count method: each ballot assigns N-1 points to the
    top-ranked answer, N-2 to second, …, 0 to last.  Scores are then
    normalised to [0, 1] so they are comparable regardless of panel size.
  - The Strategy pattern keeps this algorithm swappable: a future weighted-rank
    or Condorcet implementation is a new module that satisfies the same
    AggregationStrategy protocol — the Ranking Aggregator node just calls
    aggregate() without caring which strategy is active.
  - All functions are pure (no I/O, no state) — the node passes in data,
    gets back data.

Pattern: Strategy (AggregationStrategy protocol), pure function.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from app.domain.council_state import RankingEntry


# ── Protocol (interface for Strategy pattern) ─────────────────────────────

class AggregationStrategy(Protocol):
    """
    Callable protocol that any ranking algorithm must satisfy.

    Args:
        ballots:    All Stage 2 RankingEntry records.
        member_ids: Ordered list of de-anonymised member IDs for output keys.
        anon_map:   anonymization_map (member_id → anonymized_label) so we can
                    translate ballot labels back to member IDs.

    Returns:
        A dict mapping member_id → normalised score in [0, 1].
        Higher score = more favourably ranked by peers.
    """
    def __call__(
        self,
        ballots: list[RankingEntry],
        member_ids: list[str],
        anon_map: dict[str, str],
    ) -> dict[str, float]: ...


# ── Borda count implementation ─────────────────────────────────────────────

def borda_count(
    ballots: list[RankingEntry],
    member_ids: list[str],
    anon_map: dict[str, str],
) -> dict[str, float]:
    """
    Compute normalised Borda count scores.

    Algorithm:
        1. Invert anon_map to get label → member_id.
        2. For each ballot, assign n-1-rank points to the label at rank index.
        3. Sum points per member_id across all ballots.
        4. Normalise to [0, 1] by dividing by the theoretical maximum.

    Args:
        ballots:    List of RankingEntry from Stage 2.
        member_ids: Full list of member IDs in the session.
        anon_map:   member_id → anonymized_label mapping.

    Returns:
        Normalised score dict: {member_id: float}.  Absent members score 0.0.

    Example:
        3 members, 3 ballots, one member is ranked first by all three:
        raw = 3 × 2 = 6; max = 3 ballots × 2 points = 6; score = 1.0
    """
    # Build reverse map: label → member_id
    label_to_id: dict[str, str] = {v: k for k, v in anon_map.items()}

    raw_scores: dict[str, float] = {mid: 0.0 for mid in member_ids}
    n = len(member_ids)

    for ballot in ballots:
        ranking = ballot["ranking_order"]
        for rank_index, label in enumerate(ranking):
            member_id = label_to_id.get(label)
            if member_id and member_id in raw_scores:
                points = (n - 1) - rank_index
                raw_scores[member_id] += max(0, points)

    # Theoretical maximum: all ballots rank this member first
    max_possible = len(ballots) * (n - 1) if n > 1 else 1

    if max_possible == 0:
        return {mid: 0.0 for mid in member_ids}

    return {
        mid: round(score / max_possible, 4)
        for mid, score in raw_scores.items()
    }


# ── Chairman selection ─────────────────────────────────────────────────────

def elect_chairman(
    aggregate_scores: dict[str, float],
    *,
    pinned_member_id: str | None = None,
) -> str:
    """
    Determine the Chairman member_id for Stage 3.

    Logic:
        - If the user has pinned a specific model as Chairman and it is present
          in the scores dict, use that member unconditionally.
        - Otherwise, elect the member with the highest aggregate score.
        - Ties are broken by dict insertion order (stable in Python 3.7+).

    Args:
        aggregate_scores:  Output of borda_count() or any AggregationStrategy.
        pinned_member_id:  Optional user override.

    Returns:
        The member_id of the elected Chairman.

    Raises:
        ValueError: if aggregate_scores is empty.
    """
    if not aggregate_scores:
        raise ValueError("Cannot elect a Chairman from an empty scores dict.")

    if pinned_member_id and pinned_member_id in aggregate_scores:
        return pinned_member_id

    return max(aggregate_scores, key=lambda mid: aggregate_scores[mid])
