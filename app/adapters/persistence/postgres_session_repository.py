"""
adapters/persistence/postgres_session_repository.py — SessionRepository implementation.

Concrete implementation of the domain's SessionRepository port, backed by
Supabase PostgreSQL via SQLAlchemy async.

Every method translates between:
  - Domain TypedDict (CouncilState) — what the orchestration layer works with.
  - ORM model (CouncilSessionModel) — what sits in the database.

Pattern: Repository (DDD), Adapter (Hexagonal), Unit of Work (session commit
         is the atomic boundary — a crash mid-write does not half-update state).
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.persistence.models import CouncilSessionModel
from app.core.exceptions import ConflictError, NotFoundError
from app.domain.council_state import CouncilState
from app.domain.ports.session_repository import SessionRepository

logger = logging.getLogger(__name__)


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class PostgresSessionRepository(SessionRepository):
    """
    Supabase-PostgreSQL-backed SessionRepository.

    Args:
        db: An AsyncSession injected per-request via FastAPI Depends().
    """

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    # ── Write operations ──────────────────────────────────────────────────

    async def create(self, state: CouncilState) -> CouncilState:
        existing = await self._db.get(CouncilSessionModel, state["session_id"])
        if existing:
            raise ConflictError(
                message=f"Session '{state['session_id']}' already exists.",
                details={"session_id": state["session_id"]},
            )

        now = _utcnow_iso()
        state_with_ts: CouncilState = {**state, "created_at": now, "updated_at": now}

        model = CouncilSessionModel(
            id=state["session_id"],
            user_id=state.get("user_id", ""),           # injected by the API layer
            stage=state["stage"],
            state=dict(state_with_ts),                  # full JSONB snapshot
            user_query=state["user_query"],
            member_count=len(state.get("members", [])),
            total_cost_usd=0.0,
            trace_id=state.get("trace_id"),
        )
        self._db.add(model)
        await self._db.flush()                          # write within UoW, no commit yet
        logger.info("Session created: %s", state["session_id"])
        return state_with_ts

    async def save_checkpoint(self, state: CouncilState) -> None:
        """
        Atomically overwrite the session's state snapshot after each stage
        transition. Also updates the denormalised `stage` column.
        """
        model = await self._db.get(CouncilSessionModel, state["session_id"])
        if model is None:
            raise NotFoundError(
                message=f"Session '{state['session_id']}' not found for checkpoint.",
                details={"session_id": state["session_id"]},
            )

        updated_state: CouncilState = {**state, "updated_at": _utcnow_iso()}
        model.state = dict(updated_state)
        model.stage = state["stage"]
        model.total_cost_usd = _sum_costs(state)
        model.notion_page_url = state.get("notion_page_url")

        await self._db.flush()
        logger.debug("Checkpoint saved for session %s (stage=%s)", state["session_id"], state["stage"])

    # ── Read operations ───────────────────────────────────────────────────

    async def load(self, session_id: str) -> Optional[CouncilState]:
        model = await self._db.get(CouncilSessionModel, session_id)
        if model is None or model.is_deleted:
            return None
        return model.state  # type: ignore[return-value]

    async def list_sessions(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
    ) -> list[CouncilState]:
        stmt = (
            select(CouncilSessionModel)
            .where(
                CouncilSessionModel.user_id == user_id,
                CouncilSessionModel.is_deleted.is_(False),
            )
            .order_by(CouncilSessionModel.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        result = await self._db.execute(stmt)
        models = result.scalars().all()
        return [m.state for m in models]  # type: ignore[return-value]

    async def delete(self, session_id: str) -> None:
        model = await self._db.get(CouncilSessionModel, session_id)
        if model is None:
            raise NotFoundError(
                message=f"Session '{session_id}' not found.",
                details={"session_id": session_id},
            )
        model.is_deleted = True
        await self._db.flush()
        logger.info("Session soft-deleted: %s", session_id)


# ── Internal helpers ───────────────────────────────────────────────────────

def _sum_costs(state: CouncilState) -> float:
    """Sum cost_usd across all member responses for the running total."""
    total = 0.0
    for resp in state.get("stage_1_responses", []):
        total += resp.get("cost_usd", 0.0)
    for resp in state.get("stage_2_responses", []):
        total += resp.get("cost_usd", 0.0)
    return round(total, 6)
