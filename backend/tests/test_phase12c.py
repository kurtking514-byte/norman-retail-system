"""
Phase 12c integration tests for Live SSE Updates for Staff Chat Dashboard.

Covers:
- The ``GET /api/v1/conversations/stream`` SSE endpoint accepts a valid JWT
  token via query parameter and returns ``text/event-stream``.
- The SSE endpoint emits a ``connected`` event on first connection.
- When a new message is logged via ``log_conversation``, an SSE event is
  fired and received by connected clients.
- When ``thread_state`` is updated, an SSE event is fired.

All external API calls (Messenger Send API) are mocked.

NOTE: Because httpx+ASGITransport buffers Starlette's StreamingResponse,
the event-reception tests attach a test subscriber directly to the
``sse_manager`` and assert that events are published — functionally
equivalent to connecting a real SSE client.
"""

import asyncio
import json
import os

# ---------------------------------------------------------------------------
# Environment setup – must happen *before* any app imports
# ---------------------------------------------------------------------------
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-phase12c")
os.environ.setdefault("ADMIN_USERNAME", "admin")

import bcrypt  # noqa: E402

HASHED_PW = bcrypt.hashpw(b"changeme123", bcrypt.gensalt(12)).decode()
os.environ.setdefault("ADMIN_PASSWORD_HASH", HASHED_PW)

if "META_APP_SECRET" in os.environ:
    del os.environ["META_APP_SECRET"]

# ---- Imports -------------------------------------------------------------
import httpx  # noqa: E402
import pytest  # noqa: E402
from httpx import ASGITransport  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.main import app  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.database import async_session_factory  # noqa: E402
from app.core.security import create_access_token  # noqa: E402
from app.models.customer import Customer  # noqa: E402
from app.models.notification import ConversationLog  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SENDER_ID_A = "messenger-user-12c-a"
LOGIN_URL = "/api/v1/auth/login"

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def client():
    """Provide an httpx.AsyncClient wired to the FastAPI app via ASGITransport."""
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def db_session():
    """Provide a fresh AsyncSession for direct DB queries in tests."""
    session = async_session_factory()
    try:
        yield session
    finally:
        await session.close()


@pytest.fixture(autouse=True)
async def cleanup_phase12c_data():
    """Auto-run before each test to clean up Phase-12c-specific rows."""
    session = async_session_factory()
    try:
        await session.execute(
            ConversationLog.__table__.delete().where(
                ConversationLog.messenger_user_id == SENDER_ID_A
            )
        )
        await session.execute(
            Customer.__table__.delete().where(
                Customer.messenger_user_id == SENDER_ID_A
            )
        )
        await session.commit()
    finally:
        await session.close()


@pytest.fixture(autouse=True)
def mock_send_api(monkeypatch):
    """Mock ``send_api_service.send_message`` so no real HTTP call is made."""

    async def _mock_send_message(recipient_id: str, message_text: str) -> bool:
        return True

    monkeypatch.setattr(
        "app.services.send_api_service.send_message", _mock_send_message
    )


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


async def _get_admin_token(client) -> str:
    """Log in as admin and return a valid JWT token."""
    login_payload = {"username": "admin", "password": "changeme123"}
    resp = await client.post(LOGIN_URL, json=login_payload)
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    data = resp.json()
    return data["access_token"]


def _get_test_token() -> str:
    """Create a JWT token directly for testing."""
    return create_access_token({"sub": "admin"})


async def _seed_customer(
    messenger_user_id: str,
    thread_state: str = "AI_CONTROLLED",
):
    """Insert a Customer row with the given thread_state."""
    session = async_session_factory()
    try:
        result = await session.execute(
            select(Customer).where(Customer.messenger_user_id == messenger_user_id)
        )
        existing = result.scalar_one_or_none()
        if not existing:
            cust = Customer(
                first_name="Phase12c",
                last_name="User",
                phone_number=f"pending-{messenger_user_id}",
                messenger_user_id=messenger_user_id,
                thread_state=thread_state,
            )
            session.add(cust)
            await session.commit()
        else:
            existing.thread_state = thread_state
            await session.commit()
    finally:
        await session.close()


# ===================================================================
# Tests – HTTP endpoint
# ===================================================================


@pytest.mark.asyncio
async def test_sse_endpoint_accepts_valid_token():
    """The SSE endpoint yields a ``connected`` event on connection.

    Because httpx's ASGITransport cannot cancel an infinite
    StreamingResponse, we call ``stream_conversations`` directly,
    extract the generator from the returned StreamingResponse,
    iterate the first few events, and then close the generator
    — functionally equivalent to a real SSE connection.
    """
    from app.api.v1.endpoints.conversations import stream_conversations
    from app.services.sse_service import sse_manager

    token = _get_test_token()

    # Call the endpoint directly
    response = await stream_conversations(token=token)

    # It should be a StreamingResponse
    assert hasattr(response, "body_iterator"), (
        "Endpoint should return StreamingResponse"
    )

    gen = response.body_iterator

    # First event MUST be the "connected" heartbeat
    first = await gen.__anext__()
    assert "event: connected" in first, (
        f"First SSE event should be 'connected', got: {first!r}"
    )

    # ---- Now prove the full pipeline works: emit an event through
    #      sse_manager and verify the generator forwards it ---------------
    await sse_manager.emit({
        "type": "test",
        "value": "hello-from-generator-test",
    })

    # The generator should yield this event (SSE-formatted)
    second = None
    while True:
        try:
            ev = await gen.__anext__()
            if "hello-from-generator-test" in ev:
                second = ev
                break
        except StopAsyncIteration:
            break

    assert second is not None, (
        "The SSE generator should forward the emitted event"
    )
    assert "event: message" in second, (
        f"SSE event should be 'message' type, got: {second!r}"
    )

    # Clean up: close the generator to unsubscribe the queue
    try:
        await gen.aclose()
    except Exception:
        pass


@pytest.mark.asyncio
async def test_sse_endpoint_rejects_missing_token(client):
    """The SSE endpoint rejects requests without a token."""
    response = await client.get("/api/v1/conversations/stream")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_sse_endpoint_rejects_invalid_token(client):
    """The SSE endpoint rejects requests with an invalid token."""
    response = await client.get(
        "/api/v1/conversations/stream?token=invalid-jwt-token"
    )
    assert response.status_code == 401


# ===================================================================
# Tests – SSE event publishing (direct subscriber)
# ===================================================================

# These tests subscribe to the SSEManager directly rather than trying
# to stream over ASGITransport.  They prove that the emit() calls in
# log_conversation / update_thread_state actually fire — which is the
# end-to-end guarantee we need.  The StreamingResponse plumbing (which
# forwards those events to EventSource) is trivially correct and
# covered by test_sse_endpoint_accepts_valid_token above.


@pytest.mark.asyncio
async def test_sse_receives_new_message_event():
    """When a new message is logged, an SSE event is published."""
    await _seed_customer(SENDER_ID_A)

    from app.services.sse_service import sse_manager

    # Subscribe to the in-process manager
    queue = await sse_manager.subscribe()

    try:
        # Log a message (this should emit an SSE event)
        from app.services.messenger_service import log_conversation

        session = async_session_factory()
        try:
            await log_conversation(
                session,
                messenger_user_id=SENDER_ID_A,
                speaker="User",
                message_text="Hello! This is a test message for SSE.",
            )
        finally:
            await session.close()

        # Collect events from the queue with a short timeout
        events: list[dict] = []
        while True:
            try:
                ev = await asyncio.wait_for(queue.get(), timeout=2.0)
                events.append(ev)
                if ev.get("type") == "new_message":
                    break
            except asyncio.TimeoutError:
                break

        new_message_events = [
            e for e in events if e.get("type") == "new_message"
        ]
        assert len(new_message_events) >= 1, (
            f"Expected at least one new_message event, "
            f"got {len(new_message_events)}: {events}"
        )

        msg = new_message_events[0]
        assert msg["messenger_user_id"] == SENDER_ID_A
        assert msg["speaker"] == "User"
        assert msg["message"] == "Hello! This is a test message for SSE."
        assert msg["timestamp"] != ""
    finally:
        await sse_manager.unsubscribe(queue)


@pytest.mark.asyncio
async def test_sse_receives_thread_state_event():
    """When thread_state is updated, an SSE event is published."""
    await _seed_customer(SENDER_ID_A, thread_state="AI_CONTROLLED")

    from app.services.sse_service import sse_manager

    # Subscribe to the in-process manager
    queue = await sse_manager.subscribe()

    try:
        # Update thread state (this should emit an SSE event)
        from app.services.thread_state_service import update_thread_state

        session = async_session_factory()
        try:
            result = await session.execute(
                select(Customer).where(
                    Customer.messenger_user_id == SENDER_ID_A
                )
            )
            customer = result.scalar_one()
            await update_thread_state(
                session, customer, "HUMAN_CONTROLLED", clear_pin=True
            )
        finally:
            await session.close()

        # Collect events from the queue with a short timeout
        events: list[dict] = []
        while True:
            try:
                ev = await asyncio.wait_for(queue.get(), timeout=2.0)
                events.append(ev)
                if ev.get("type") == "thread_state_changed":
                    break
            except asyncio.TimeoutError:
                break

        state_events = [
            e for e in events if e.get("type") == "thread_state_changed"
        ]
        assert len(state_events) >= 1, (
            f"Expected at least one thread_state_changed event, "
            f"got {len(state_events)}: {events}"
        )

        ev = state_events[0]
        assert ev["messenger_user_id"] == SENDER_ID_A
        assert ev["old_state"] == "AI_CONTROLLED"
        assert ev["new_state"] == "HUMAN_CONTROLLED"
        assert ev["timestamp"] != ""
    finally:
        await sse_manager.unsubscribe(queue)


@pytest.mark.asyncio
async def test_sse_new_message_appends_to_thread(client):
    """Verify existing REST endpoints are unaffected: log a message and
    fetch the conversation history via the REST API."""
    await _seed_customer(SENDER_ID_A)
    token = await _get_admin_token(client)

    # Log a user message
    from app.services.messenger_service import log_conversation

    session = async_session_factory()
    try:
        await log_conversation(
            session,
            messenger_user_id=SENDER_ID_A,
            speaker="User",
            message_text="Pre-SSE message",
        )
    finally:
        await session.close()

    # Verify the message exists in the conversation history (REST endpoint)
    resp = await client.get(
        f"/api/v1/conversations/{SENDER_ID_A}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    messages = resp.json()
    assert len(messages) >= 1
    assert messages[-1]["message_text"] == "Pre-SSE message"
    assert messages[-1]["speaker"] == "User"


@pytest.mark.asyncio
async def test_list_conversations_still_works(client):
    """Verify GET /conversations is unaffected."""
    token = await _get_admin_token(client)
    resp = await client.get(
        "/api/v1/conversations",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
