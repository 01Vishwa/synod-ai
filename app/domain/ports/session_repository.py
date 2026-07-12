"""
domain/ports/session_repository.py — Port for session persistence.

Defines the interface all session storage adapters must satisfy. The
orchestration layer never writes SQL or calls any database SDK directly —
it only ever calls methods on this ABC.

Pattern: Repository (DDD), Port (Hexagonal Architecture driven port).
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from app.domain.council_state import CouncilState


class SessionRepository(ABC):
    """
    Driven port: persistence interface for council sessions.

    Concrete implementation: adapters/persistence/postgres_session_repository.py
    """

    @abstractmethod
    async def create(self, state: CouncilState) -> CouncilState:
        """
        Persist a new session and return the persisted state.

        Raises:
            ConflictError: if session_id already exists.
        """
        ...

    @abstractmethod
    async def save_checkpoint(self, state: CouncilState) -> None:
        """
        Atomically update the session record with the latest state snapshot.

        This is the Unit of Work write — called after every stage transition.
        The write must be atomic; a crash mid-write should not leave
        CouncilState half-updated.
        """
        ...

    @abstractmethod
    async def load(self, session_id: str) -> Optional[CouncilState]:
        """
        Load the latest checkpoint for `session_id`.

        Returns:
            The stored CouncilState, or None if no session with that ID exists.
        """
        ...

    @abstractmethod
    async def list_sessions(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
    ) -> list[CouncilState]:
        """
        Return a paginated list of sessions owned by `user_id`, newest first.
        """
        ...

    @abstractmethod
    async def delete(self, session_id: str) -> None:
        """Permanently remove a session and all its checkpoints."""
        ...
