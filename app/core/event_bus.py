"""
core/event_bus.py — In-memory publish/subscribe event bus.

Powers all real-time streaming updates in Synod-AI.  Every council node
publishes typed events here; the SSE generator for a session subscribes
and drains events directly to the HTTP response — no DB polling required.

Design:
  - One SessionEventBus instance per active session, keyed by session_id.
  - Each subscriber gets its own asyncio.Queue so slow readers never stall
    the publisher or other subscribers.
  - Events are dropped (not buffered indefinitely) for queues that are full
    so a stuck browser connection never blocks the orchestration graph.
  - close() sends a None sentinel to every subscriber, causing subscribe()
    generators to return cleanly, and marks the bus as closed so late
    publish() calls are silently swallowed.

Usage (inside a LangGraph node):
    bus = await get_or_create_bus(session_id)
    await bus.publish(ProviderConnecting(session_id=..., member_id=...))

Usage (inside the SSE event generator):
    bus = await get_or_create_bus(session_id)
    async for event in bus.subscribe():
        yield _event_to_sse(event)

Cleanup (at session finish/error):
    await close_bus(session_id)

Pattern: Observer (bus registry), Producer/Consumer (per-subscriber queue),
         Sentinel (None closes the generator loop).
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import AsyncGenerator, ClassVar, Union

logger = logging.getLogger(__name__)


# ── Typed event dataclasses ────────────────────────────────────────────────
#
# Every event is a frozen dataclass so it can be safely shared across
# multiple subscriber queues without copying.  The `event_type` ClassVar
# lets SSE serialisers dispatch without isinstance chains.

@dataclass(frozen=True)
class MemberQueued:
    """Emitted when a council member is added to the execution queue."""
    event_type: ClassVar[str] = "member.queued"
    session_id: str
    member_id: str
    display_label: str
    provider: str


@dataclass(frozen=True)
class MemberStarted:
    """Emitted when execution for a member begins (key fetch / span open)."""
    event_type: ClassVar[str] = "member.started"
    session_id: str
    member_id: str
    stage: str


@dataclass(frozen=True)
class ProviderConnecting:
    """Emitted immediately before the HTTP request is sent to the provider."""
    event_type: ClassVar[str] = "member.connecting"
    session_id: str
    member_id: str


@dataclass(frozen=True)
class FirstToken:
    """Emitted when the very first token arrives from the provider stream."""
    event_type: ClassVar[str] = "member.first_token"
    session_id: str
    member_id: str
    stage: str


@dataclass(frozen=True)
class StreamChunk:
    """
    Emitted for each streaming token (or micro-batch of tokens).

    delta       — the raw text fragment emitted by the model
    token_count — running total tokens received so far for this member/stage
    """
    event_type: ClassVar[str] = "member.stream_chunk"
    session_id: str
    member_id: str
    stage: str
    delta: str
    token_count: int


@dataclass(frozen=True)
class MemberCompleted:
    """Emitted when a member finishes its stage successfully."""
    event_type: ClassVar[str] = "member.completed"
    session_id: str
    member_id: str
    stage: str
    latency_ms: int
    tokens_in: int
    tokens_out: int
    cost_usd: float


@dataclass(frozen=True)
class MemberFailed:
    """
    Emitted when a member fails at any stage.

    error_class   — one of: "timeout", "auth", "rate_limit", "unknown"
    error_message — user-friendly (sanitised) message; never a raw traceback
    """
    event_type: ClassVar[str] = "member.failed"
    session_id: str
    member_id: str
    stage: str
    error_class: str
    error_message: str


@dataclass(frozen=True)
class PeerReviewStarted:
    """Emitted when Stage 2 fan-out begins."""
    event_type: ClassVar[str] = "peer_review.started"
    session_id: str


@dataclass(frozen=True)
class PeerReviewProgress:
    """
    Emitted each time one peer reviewer finishes, showing partial progress.

    completed — number of peer reviews finished so far
    total     — total number of peer reviews expected
    """
    event_type: ClassVar[str] = "peer_review.progress"
    session_id: str
    completed: int
    total: int


@dataclass(frozen=True)
class RankingUpdated:
    """
    Emitted after each peer review completes and Borda scores are recalculated.

    rankings        — list of RankingEntry dicts (serialisable)
    aggregate_scores — member_id → current Borda score
    """
    event_type: ClassVar[str] = "ranking.updated"
    session_id: str
    rankings: tuple          # immutable snapshot; callers cast to list for JSON
    aggregate_scores: tuple  # tuple of (member_id, score) pairs


@dataclass(frozen=True)
class ChairmanStarted:
    """Emitted when the Chairman node begins its synthesis call."""
    event_type: ClassVar[str] = "chairman.started"
    session_id: str
    chairman_id: str


@dataclass(frozen=True)
class ChairmanStreamChunk:
    """Emitted for each streaming token from the Chairman synthesis."""
    event_type: ClassVar[str] = "chairman.stream_chunk"
    session_id: str
    delta: str


@dataclass(frozen=True)
class ChairmanCompleted:
    """Emitted when the Chairman has finished producing the final report."""
    event_type: ClassVar[str] = "chairman.completed"
    session_id: str


@dataclass(frozen=True)
class SessionCompleted:
    """Emitted when the entire session reaches the 'done' stage."""
    event_type: ClassVar[str] = "session.completed"
    session_id: str


@dataclass(frozen=True)
class SessionFailed:
    """
    Emitted when the session reaches the 'error' stage.

    error — user-friendly summary; never a raw Python traceback
    """
    event_type: ClassVar[str] = "session.failed"
    session_id: str
    error: str


# Union type covering all 15 event variants.  Use this for type annotations
# in publishers and subscriber handlers.
SessionEvent = Union[
    MemberQueued,
    MemberStarted,
    ProviderConnecting,
    FirstToken,
    StreamChunk,
    MemberCompleted,
    MemberFailed,
    PeerReviewStarted,
    PeerReviewProgress,
    RankingUpdated,
    ChairmanStarted,
    ChairmanStreamChunk,
    ChairmanCompleted,
    SessionCompleted,
    SessionFailed,
]


# ── SessionEventBus ────────────────────────────────────────────────────────

class SessionEventBus:
    """
    Fan-out publish/subscribe bus for one council session.

    Each call to subscribe() returns an independent async generator backed
    by its own asyncio.Queue.  publish() fan-outs to every live queue.

    Slow subscribers have events dropped (QueueFull is silently caught) so
    a stalled browser connection can never starve the orchestration graph or
    other subscribers.

    close() sends a None sentinel to every queue, causing all subscribe()
    generators to return.  Subsequent publish() calls are no-ops.

    Thread-safety: the internal _lock is an asyncio.Lock (not a threading
    lock) — the bus must be used from a single event loop thread, which is
    the standard FastAPI / uvicorn deployment model.
    """

    def __init__(self, session_id: str, maxsize: int = 1000) -> None:
        self._session_id = session_id
        self._maxsize = maxsize
        # Each subscriber gets its own queue appended here on subscribe().
        self._subscribers: list[asyncio.Queue[SessionEvent | None]] = []
        self._lock: asyncio.Lock = asyncio.Lock()
        self._closed: bool = False

    # ── Publisher ─────────────────────────────────────────────────────────

    async def publish(self, event: SessionEvent) -> None:
        """
        Fan-out an event to every active subscriber queue.

        Never raises.  QueueFull for any individual subscriber is silently
        swallowed — events are dropped rather than blocking the publisher.
        """
        if self._closed:
            return
        async with self._lock:
            for q in self._subscribers:
                try:
                    q.put_nowait(event)
                except asyncio.QueueFull:
                    # Slow subscriber — drop this event rather than block.
                    logger.debug(
                        "SessionEventBus: dropped event %s for session %s "
                        "(subscriber queue full)",
                        getattr(event, "event_type", type(event).__name__),
                        self._session_id,
                    )

    # ── Subscriber ────────────────────────────────────────────────────────

    async def subscribe(self) -> AsyncGenerator[SessionEvent, None]:
        """
        Yield events as they are published.

        Yields until:
          - close() is called (None sentinel received), or
          - 30 s of silence (asyncio.TimeoutError — caller should reconnect).

        The subscriber queue is registered in __aenter__ style: appended
        before yielding, removed in the finally block so it is always cleaned
        up even on GeneratorExit (client disconnects mid-stream).
        """
        q: asyncio.Queue[SessionEvent | None] = asyncio.Queue(maxsize=self._maxsize)
        async with self._lock:
            self._subscribers.append(q)
        try:
            while True:
                try:
                    event = await asyncio.wait_for(q.get(), timeout=30.0)
                except asyncio.TimeoutError:
                    # 30 s idle — the SSE generator should emit a keepalive
                    # or reconnect.  Return cleanly so the caller can decide.
                    logger.debug(
                        "SessionEventBus: subscriber idle timeout for session %s",
                        self._session_id,
                    )
                    return
                if event is None:  # sentinel — bus was closed
                    return
                yield event
        finally:
            # Always deregister — handles GeneratorExit (client disconnect).
            async with self._lock:
                try:
                    self._subscribers.remove(q)
                except ValueError:
                    pass  # already removed by close()

    # ── Lifecycle ─────────────────────────────────────────────────────────

    async def close(self) -> None:
        """
        Signal all subscribers to stop and mark the bus closed.

        Sends a None sentinel to every subscriber queue so their generators
        return cleanly.  Clears the subscriber list to release references.
        Subsequent publish() calls are silently ignored.
        """
        async with self._lock:
            if self._closed:
                return
            self._closed = True
            for q in self._subscribers:
                try:
                    q.put_nowait(None)
                except asyncio.QueueFull:
                    # Queue is full; the subscriber will drain naturally and
                    # eventually hit the sentinel when it catches up, or the
                    # idle timeout will fire.
                    pass
            self._subscribers.clear()
        logger.debug(
            "SessionEventBus: closed for session %s", self._session_id
        )

    # ── Diagnostics ───────────────────────────────────────────────────────

    @property
    def subscriber_count(self) -> int:
        """Current number of active subscribers (useful for metrics/tests)."""
        return len(self._subscribers)

    @property
    def is_closed(self) -> bool:
        return self._closed

    def __repr__(self) -> str:
        return (
            f"SessionEventBus(session_id={self._session_id!r}, "
            f"subscribers={self.subscriber_count}, "
            f"closed={self._closed})"
        )


# ── Global bus registry ────────────────────────────────────────────────────
#
# One SessionEventBus per live session, keyed by session_id (UUID string).
# The registry lock is an asyncio.Lock — do NOT hold it across await points
# other than the minimal dict mutation inside the lock body.

_buses: dict[str, SessionEventBus] = {}
_registry_lock: asyncio.Lock = asyncio.Lock()


async def get_or_create_bus(session_id: str) -> SessionEventBus:
    """
    Return the existing bus for `session_id`, or create and register a new one.

    Idempotent: multiple callers racing on the same session_id will all
    receive the same instance (double-checked locking pattern).
    """
    # Fast path — no lock needed for the read
    existing = _buses.get(session_id)
    if existing is not None:
        return existing

    async with _registry_lock:
        # Re-check under the lock (another coroutine may have just created it)
        if session_id not in _buses:
            _buses[session_id] = SessionEventBus(session_id)
            logger.debug(
                "SessionEventBus: created new bus for session %s", session_id
            )
        return _buses[session_id]


async def get_bus(session_id: str) -> SessionEventBus | None:
    """
    Return the bus for `session_id` if it exists, else None.

    Never creates a new bus.  Use this in the SSE endpoint to avoid
    accidentally creating a bus for a session that hasn't started yet.
    """
    return _buses.get(session_id)


async def close_bus(session_id: str) -> None:
    """
    Close and deregister the bus for `session_id`.

    Safe to call even if no bus exists for the session (no-op).
    After this call, get_bus(session_id) returns None.
    """
    async with _registry_lock:
        bus = _buses.pop(session_id, None)
    if bus is not None:
        await bus.close()
        logger.info(
            "SessionEventBus: deregistered bus for session %s", session_id
        )
