"""
domain/identity.py — Council execution identity validation helpers.

Provides require_uuid() — the single validation gate that every persistence
boundary must call before using session_id or user_id in a SQL query.

Design:
  - Validation happens in the domain layer, not in the adapter, so the domain
    contract is enforced regardless of which repository implementation is used.
  - Raises CouncilStateValidationError (not asyncpg DataError) so callers
    receive a structured, machine-readable exception before any SQL executes.
  - Never logs the raw invalid value to prevent accidental sensitive-data capture.

Pattern: Guard Clause.
"""
from __future__ import annotations

from uuid import UUID

from app.core.exceptions import CouncilStateValidationError


def require_uuid(value: object, *, field_name: str) -> UUID:
    """
    Validate that ``value`` is a non-empty, parseable UUID.

    Accepts:
      - uuid.UUID instances (returned as-is)
      - Hyphenated UUID strings  (e.g. "6a9142c0-e5c1-4ce6-a8db-5be994e7f773")
      - 32-character bare hex strings

    Raises:
      CouncilStateValidationError: if ``value`` is None, empty, not a string,
          or cannot be parsed as a UUID.

    Returns:
      A validated uuid.UUID object.
    """
    if value is None:
        raise CouncilStateValidationError(
            f"{field_name} is required but was not present in state.",
            field=field_name,
        )

    if isinstance(value, UUID):
        return value

    if not isinstance(value, str):
        raise CouncilStateValidationError(
            f"{field_name} must be a UUID string.",
            field=field_name,
        )

    stripped = value.strip()

    if not stripped:
        raise CouncilStateValidationError(
            f"{field_name} cannot be empty.",
            field=field_name,
        )

    # Reject obvious sentinel values that should never reach persistence.
    _INVALID_SENTINELS = {"undefined", "null", "none", "n/a"}
    if stripped.lower() in _INVALID_SENTINELS:
        raise CouncilStateValidationError(
            f"{field_name} contains an invalid sentinel value.",
            field=field_name,
        )

    try:
        return UUID(stripped)
    except ValueError as exc:
        raise CouncilStateValidationError(
            f"{field_name} must be a valid UUID (received an unparseable value).",
            field=field_name,
        ) from exc
