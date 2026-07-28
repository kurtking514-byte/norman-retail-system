"""
Phase 12a integration tests for Auto-Pause AI When Staff Sends a Manual Reply.

Covers:
- POST /api/v1/conversations/{id}/reply auto-pauses AI (sets thread_state=HUMAN_CONTROLLED).
- Sending a manual reply to an already-paused conversation is a no-op.
- The existing manual toggle (PATCH thread-state) still works independently.
- After auto-pause, incoming webhook messages do NOT trigger AI replies.

All DeepSeek and Send API calls are mocked — no real network requests.
"""

import json
import os

# ---------------------------------------------------------------------------
# Environment setup – must happen *before* any app imports
# ---------------------------------------------------------------------------
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-phase12a-testing")
os.environ.setdefault("ADMIN_USERNAME", "admin")

import bcrypt  # noqa: E402

HASHED_PW = bcrypt.hashpw(b"changeme123", bcrypt.gensalt(12)).decode()
os.environ.setdefault("ADMIN_PASSWORD_HASH", HASHED_PW)
# DATABASE_URL is set by conftest.py — no need to override here.

if "META_APP_SECRET" in os.environ:
    del os.environ["META_APP_SECRET"]

# ---- Imports -------------------------------------------------------------
import asyncio  # noqa: E402

import httpx  # noqa: E402
import pytest  # noqa: E402
from httpx import ASGITransport  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.main import app  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.database import async_session_factory  # noqa: E402
from app.models.customer import Customer  # noqa: E402
from app.models.notification import ConversationLog, NotificationQueue  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SENDER_ID_A = "messenger-user-12a-a"
SENDER_ID_B = "messenger-user-12a-b"

LOGIN_URL = "/api/v1/auth/login"

# ---------------------------------------------------------------------------
# Phase-12a-specific seed data — tables already created by conftest's setup_db.
# ---------------------------------------------------------------------------


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
async def cleanup_phase12a_data():
    """Auto-run before each test to clean up Phase-12a-specific rows."""
    session = async_session_factory()
    try:
        await session.execute(
            NotificationQueue.__table__.delete().where(
                NotificationQueue.recipient_id.in_([SENDER_ID_A, SENDER_ID_B])
            )
        )
        await session.execute(
            ConversationLog.__table__.delete().where(
                ConversationLog.messenger_user_id.in_([SENDER_ID_A, SENDER_ID_B])
            )
        )
        await session.execute(
            Customer.__table__.delete().where(
                Customer.messenger_user_id.in_([SENDER_ID_A, SENDER_ID_B])
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


@pytest.fixture(autouse=True)
def mock_deepseek_api(monkeypatch):
    """Mock DeepSeek API so no real HTTP call is made.

    We set a fake key and mock the HTTP post so we can detect if
    DeepSeek is called during the HUMAN_CONTROLLED test.
    """
    monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", "fake-deepseek-key-phase12a")

    original_post = httpx.AsyncClient.post
    deepseek_call_count = [0]  # mutable closure to track calls

    async def _mock_post(self, url, *args, **kwargs):
        if "api.deepseek.com" in str(url):
            deepseek_call_count[0] += 1
            return httpx.Response(
                status_code=200,
                request=httpx.Request("POST", url),
                json={
                    "id": "mock-ds-phase12a",
                    "object": "chat.completion",
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": "This is a mock reply for Phase 12a testing.",
                            },
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 50,
                        "completion_tokens": 20,
                        "total_tokens": 70,
                    },
                },
            )
        return await original_post(self, url, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "post", _mock_post)

    # Provide a way for tests to check the DeepSeek call count
    return deepseek_call_count


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


def _auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


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
                first_name="Phase12a",
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


async def _seed_conversation_log(
    messenger_user_id: str,
    speaker: str,
    message_text: str,
):
    """Insert a ConversationLog row (also ensures a Customer exists)."""
    session = async_session_factory()
    try:
        await _seed_customer(messenger_user_id)
        log_entry = ConversationLog(
            messenger_user_id=messenger_user_id,
            speaker=speaker,
            message_text=message_text,
        )
        session.add(log_entry)
        await session.commit()
    finally:
        await session.close()


# ===================================================================
# Tests
# ===================================================================


@pytest.mark.asyncio
async def test_send_reply_pauses_unpaused_conversation(client, db_session):
    """Sending a manual staff reply to an unpaused (AI_CONTROLLED) conversation
    results in the conversation becoming HUMAN_CONTROLLED (paused)."""
    # Arrange: seed customer with AI_CONTROLLED
    await _seed_customer(SENDER_ID_A, thread_state="AI_CONTROLLED")
    token = await _get_admin_token(client)

    # Act: send a staff reply
    resp = await client.post(
        f"/api/v1/conversations/{SENDER_ID_A}/reply",
        json={"message_text": "I can help with that!"},
        headers=_auth_headers(token),
    )
    assert resp.status_code == 201, f"Reply failed: {resp.text}"

    # Assert: thread_state is now HUMAN_CONTROLLED
    result = await db_session.execute(
        select(Customer).where(Customer.messenger_user_id == SENDER_ID_A)
    )
    customer = result.scalar_one()
    assert customer.thread_state == "HUMAN_CONTROLLED", (
        f"Expected HUMAN_CONTROLLED after staff reply, got {customer.thread_state}"
    )


@pytest.mark.asyncio
async def test_send_reply_to_already_paused_is_noop(client, db_session):
    """Sending a manual staff reply to an already-paused (HUMAN_CONTROLLED)
    conversation does not error and leaves it paused."""
    # Arrange: seed customer already HUMAN_CONTROLLED
    await _seed_customer(SENDER_ID_A, thread_state="HUMAN_CONTROLLED")
    token = await _get_admin_token(client)

    # Act: send a staff reply
    resp = await client.post(
        f"/api/v1/conversations/{SENDER_ID_A}/reply",
        json={"message_text": "I'm already here!"},
        headers=_auth_headers(token),
    )
    assert resp.status_code == 201, f"Reply failed: {resp.text}"

    # Assert: still HUMAN_CONTROLLED
    result = await db_session.execute(
        select(Customer).where(Customer.messenger_user_id == SENDER_ID_A)
    )
    customer = result.scalar_one()
    assert customer.thread_state == "HUMAN_CONTROLLED", (
        f"Expected HUMAN_CONTROLLED (unchanged), got {customer.thread_state}"
    )


@pytest.mark.asyncio
async def test_manual_toggle_unaffected_by_auto_pause(client, db_session):
    """The existing manual toggle (PATCH thread-state) still pauses/resumes
    correctly on its own, unaffected by the auto-pause change."""
    await _seed_customer(SENDER_ID_A, thread_state="AI_CONTROLLED")
    token = await _get_admin_token(client)

    # Toggle to HUMAN_CONTROLLED manually
    resp1 = await client.patch(
        f"/api/v1/conversations/{SENDER_ID_A}/thread-state",
        json={"thread_state": "HUMAN_CONTROLLED"},
        headers=_auth_headers(token),
    )
    assert resp1.status_code == 200
    assert resp1.json()["thread_state"] == "HUMAN_CONTROLLED"

    # Verify persisted
    result = await db_session.execute(
        select(Customer).where(Customer.messenger_user_id == SENDER_ID_A)
    )
    customer = result.scalar_one()
    assert customer.thread_state == "HUMAN_CONTROLLED"

    # Toggle back to AI_CONTROLLED manually
    resp2 = await client.patch(
        f"/api/v1/conversations/{SENDER_ID_A}/thread-state",
        json={"thread_state": "AI_CONTROLLED"},
        headers=_auth_headers(token),
    )
    assert resp2.status_code == 200
    assert resp2.json()["thread_state"] == "AI_CONTROLLED"

    # Verify persisted
    await db_session.refresh(customer)
    assert customer.thread_state == "AI_CONTROLLED"


@pytest.mark.asyncio
async def test_auto_pause_respected_by_incoming_message(
    client, db_session, mock_deepseek_api, mock_send_api
):
    """After auto-pause triggers (via staff reply), an incoming customer message
    does NOT generate an AI reply — confirms the pause check is respected."""
    # Arrange: seed an AI_CONTROLLED customer
    await _seed_customer(SENDER_ID_A, thread_state="AI_CONTROLLED")
    token = await _get_admin_token(client)

    # Act: staff sends a reply (this auto-pauses to HUMAN_CONTROLLED)
    resp = await client.post(
        f"/api/v1/conversations/{SENDER_ID_A}/reply",
        json={"message_text": "Let me take this one."},
        headers=_auth_headers(token),
    )
    assert resp.status_code == 201

    # Reset DeepSeek call count before the webhook test
    mock_deepseek_api[0] = 0

    # Now simulate an incoming customer message via webhook
    settings.META_APP_SECRET = ""
    settings.STAFF_HANDOFF_ENABLED = True

    payload = {
        "object": "page",
        "entry": [
            {
                "id": "page-1",
                "time": 1234567890,
                "messaging": [
                    {
                        "sender": {"id": SENDER_ID_A},
                        "recipient": {"id": "page-1"},
                        "timestamp": 1234567890,
                        "message": {
                            "mid": "mid.$cAAJ1test-12a",
                            "text": "What about the warranty?",
                        },
                    }
                ],
            }
        ],
    }
    raw_body = json.dumps(payload).encode("utf-8")

    response = await client.post(
        "/api/v1/webhook",
        content=raw_body,
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 200

    # Assert: User message was logged, but Bot reply was NOT generated
    result = await db_session.execute(
        select(ConversationLog)
        .where(ConversationLog.messenger_user_id == SENDER_ID_A)
        .order_by(ConversationLog.id)
    )
    logs = result.scalars().all()
    speakers = [log.speaker for log in logs]

    assert "User" in speakers, "User message should be logged"
    # The Staff message and User message should exist, but no Bot reply
    assert "Bot" not in speakers, (
        f"Bot should NOT reply after auto-pause. Got speakers: {speakers}"
    )

    # Assert: DeepSeek was never called
    call_count = mock_deepseek_api[0]
    assert call_count == 0, (
        f"DeepSeek should not be called after auto-pause, "
        f"but was called {call_count} time(s)"
    )
