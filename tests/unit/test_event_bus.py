"""
tests/unit/test_event_bus.py — Unit tests for app/core/event_bus.py.

Tests are intentionally side-effect-free: no DB, no HTTP, no mocks.
Each test uses asyncio_mode = "strict" (configured in pyproject.toml) and
manages its own registry state so tests are fully independent.

Scenarios:
  1. Single subscriber receives a published event.
  2. Multiple independent subscribers each receive the same event.
  3. A full (small) queue never blocks the publisher.
  4. close() terminates the subscriber generator cleanly.
  5. get_or_create_bus() returns the same instance for the same session_id.
  6. close_bus() removes the entry from the registry.
"""
from __future__ import annotations

import asyncio
import uuid

import pytest

from app.core.event_bus import (
    MemberQueued,
    SessionEventBus,
    close_bus,
    get_bus,
    get_or_create_bus,
)


# ── Helpers ────────────────────────────────────────────────────────────────

def _new_session_id() -> str:
    """Generate a fresh UUID string so each test uses an isolated bus."""
    return str(uuid.uuid4())


def _make_event(session_id: str) -> MemberQueued:
    """Minimal concrete event for publish/subscribe tests."""
    return MemberQueued(
        session_id=session_id,
        member_id="member_abc",
        display_label="Seat 1",
        provider="openrouter",
    )


# ── Tests ──────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_publish_received_by_subscriber() -> None:
    """A single published event is received by a single subscriber."""
    session_id = _new_session_id()
    bus = SessionEventBus(session_id)
    event = _make_event(session_id)

    received: list = []

    async def _collect() -> None:
        async for e in bus.subscribe():
            received.append(e)
            break  # take one event then exit

    task = asyncio.create_task(_collect())
    # Give the subscriber coroutine a chance to register its queue
    await asyncio.sleep(0)

    await bus.publish(event)
    await asyncio.wait_for(task, timeout=2.0)

    assert received == [event]


@pytest.mark.asyncio
async def test_multiple_subscribers_each_receive_event() -> None:
    """Two independent subscribers both receive the same published event."""
    session_id = _new_session_id()
    bus = SessionEventBus(session_id)
    event = _make_event(session_id)

    received_a: list = []
    received_b: list = []

    async def _collect(store: list) -> None:
        async for e in bus.subscribe():
            store.append(e)
            break

    task_a = asyncio.create_task(_collect(received_a))
    task_b = asyncio.create_task(_collect(received_b))
    # Allow both subscribers to register before publishing
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    await bus.publish(event)
    await asyncio.wait_for(asyncio.gather(task_a, task_b), timeout=2.0)

    assert received_a == [event], "Subscriber A did not receive the event"
    assert received_b == [event], "Subscriber B did not receive the event"


@pytest.mark.asyncio
async def test_slow_subscriber_does_not_block_publisher() -> None:
    """
    Publishing to a full queue must never raise or block.

    We create a bus with maxsize=1 so the second publish() would overflow a
    naive implementation.  All 10 publishes must complete without error.
    """
    session_id = _new_session_id()
    # maxsize=1 forces QueueFull on the second event for a slow subscriber
    bus = SessionEventBus(session_id, maxsize=1)
    event = _make_event(session_id)

    # Register a subscriber that never drains its queue (simulates stalled client)
    q: asyncio.Queue = asyncio.Queue(maxsize=1)
    async with bus._lock:
        bus._subscribers.append(q)  # type: ignore[arg-type]

    # All 10 publishes must complete quickly with no exception
    for _ in range(10):
        await bus.publish(event)  # should not raise even when queue is full


@pytest.mark.asyncio
async def test_close_terminates_subscriber() -> None:
    """
    close() sends a sentinel that causes subscribe() to return cleanly,
    without raising and without hanging.
    """
    session_id = _new_session_id()
    bus = SessionEventBus(session_id)

    events_received: list = []
    generator_finished = asyncio.Event()

    async def _drain() -> None:
        async for e in bus.subscribe():
            events_received.append(e)
        generator_finished.set()

    task = asyncio.create_task(_drain())
    # Let the subscriber register
    await asyncio.sleep(0)

    # Publish one real event, then close
    await bus.publish(_make_event(session_id))
    await bus.close()

    # The generator should finish promptly after the sentinel
    await asyncio.wait_for(generator_finished.wait(), timeout=2.0)

    assert len(events_received) == 1, "Expected exactly one real event before close"
    assert bus.is_closed
    assert bus.subscriber_count == 0

    # Confirm the background task completed without error
    await asyncio.wait_for(task, timeout=1.0)


@pytest.mark.asyncio
async def test_get_or_create_bus_returns_same_instance() -> None:
    """
    Calling get_or_create_bus() twice with the same session_id returns
    the exact same SessionEventBus object (identity equality).
    """
    session_id = _new_session_id()
    try:
        bus_first = await get_or_create_bus(session_id)
        bus_second = await get_or_create_bus(session_id)
        assert bus_first is bus_second, (
            "get_or_create_bus() must return the same instance for the same session_id"
        )
    finally:
        # Clean up registry so the test does not affect other tests
        await close_bus(session_id)


@pytest.mark.asyncio
async def test_close_bus_removes_from_registry() -> None:
    """
    After close_bus(), get_bus() returns None for that session_id.
    """
    session_id = _new_session_id()

    # Create and verify it exists
    await get_or_create_bus(session_id)
    assert await get_bus(session_id) is not None

    # Close and verify it's gone
    await close_bus(session_id)
    assert await get_bus(session_id) is None
