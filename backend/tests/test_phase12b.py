"""
Phase 12b integration tests for 12-Hour Idle-Timeout Auto-Resume.

Covers:
- A HUMAN_CONTROLLED thread with `thread_state_updated_at` > 12 hours ago
  auto-resumes to AI_CONTROLLED on the next incoming message, and the bot
  actually replies (not skipped).
- A HUMAN_CONTROLLED thread with `thread_state_updated_at` < 12 hours ago
  does NOT auto-resume.
- A HUMAN_CONTROLLED + `thread_state_pinned=true` thread does NOT
  auto-resume even after 12+ hours.
- Manually flipping the toggle clears `thread_state_pinned`.
- Regression: Phase 10's skip-when-human-controlled test and Phase 12a's
  tests still pass (run via the full suite).

All DeepSeek and Send API calls are mocked — no real network requests.
"""

import json
import os

# ---------------------------------------------------------------------------
# Environment setup – must happen *before* any app imports
# ---------------------------------------------------------------------------
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-phase12b-testing")
os.environ.setdefault("ADMIN_USERNAME", "admin")

import bcrypt  # noqa: E402

HASHED_PW = bcrypt.hashpw(b"changeme123", bcrypt.gensalt(12)).decode()
os.environ.setdefault("ADMIN_PASSWORD_HASH", HASHED_PW)
# DATABASE_URL is set by conftest.py — no need to override here.

if "META_APP_SECRET" in os.environ:
    del os.environ["META_APP_SECRET"]

# ---- Imports -------------------------------------------------------------
import asyncio  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402

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

SENDER_ID_A = "messenger-user-12b-a"
SENDER_ID_B = "messenger-user-12b-b"
SENDER_ID_C = "messenger-user-12b-c"
SENDER_ID_D = "messenger-user-12b-d"

LOGIN_URL = "/api/v1/auth/login"

# Time threshold: 12 hours
IDLE_TIMEOUT_HOURS = 12


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
async def cleanup_phase12b_data():
    """Auto-run before each test to clean up Phase-12b-specific rows."""
    session = async_session_factory()
    try:
        await session.execute(
            NotificationQueue.__table__.delete().where(
                NotificationQueue.recipient_id.in_(
                    [SENDER_ID_A, SENDER_ID_B, SENDER_ID_C, SENDER_ID_D]
                )
            )
        )
        await session.execute(
            ConversationLog.__table__.delete().where(
                ConversationLog.messenger_user_id.in_(
                    [SENDER_ID_A, SENDER_ID_B, SENDER_ID_C, SENDER_ID_D]
                )
            )
        )
        await session.execute(
            Customer.__table__.delete().where(
                Customer.messenger_user_id.in_(
                    [SENDER_ID_A, SENDER_ID_B, SENDER_ID_C, SENDER_ID_D]
                )
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
    DeepSeek is called during tests.
    """
    monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", "fake-deepseek-key-phase12b")

    original_post = httpx.AsyncClient.post
    deepseek_call_count = [0]  # mutable closure to track calls

    async def _mock_post(self, url, *args, **kwargs):
        if "api.deepseek.com" in str(url):
            deepseek_call_count[0] += 1
            return httpx.Response(
                status_code=200,
                request=httpx.Request("POST", url),
                json={
                    "id": "mock-ds-phase12b",
                    "object": "chat.completion",
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": "This is a mock reply for Phase 12b testing.",
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
    thread_state_pinned: bool = False,
    thread_state_updated_at: datetime | None = None,
):
    """Insert a Customer row with the given thread_state and timestamps."""
    session = async_session_factory()
    try:
        result = await session.execute(
            select(Customer).where(Customer.messenger_user_id == messenger_user_id)
        )
        existing = result.scalar_one_or_none()
        if not existing:
            cust = Customer(
                first_name="Phase12b",
                last_name="User",
                phone_number=f"pending-{messenger_user_id}",
                messenger_user_id=messenger_user_id,
                thread_state=thread_state,
                thread_state_pinned=thread_state_pinned,
                thread_state_updated_at=thread_state_updated_at,
            )
            session.add(cust)
            await session.commit()
        else:
            existing.thread_state = thread_state
            existing.thread_state_pinned = thread_state_pinned
            existing.thread_state_updated_at = thread_state_updated_at
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
# Tests — Phase 12b: Idle-Timeout Auto-Resume
# ===================================================================


@pytest.mark.asyncio
async def test_auto_resume_after_12_hours_on_incoming_message(
    client, db_session, mock_deepseek_api, mock_send_api
):
    """A HUMAN_CONTROLLED thread with thread_state_updated_at > 12 hours ago
    auto-resumes to AI_CONTROLLED on the next incoming message, and the bot
    actually replies (not skipped)."""
    # Arrange: seed customer HUMAN_CONTROLLED with timestamp > 12 hours ago
    old_time = datetime.now() - timedelta(hours=IDLE_TIMEOUT_HOURS + 1)
    await _seed_customer(
        SENDER_ID_A,
        thread_state="HUMAN_CONTROLLED",
        thread_state_updated_at=old_time,
    )

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
                            "mid": "mid.$cAAJ1test-12b-a",
                            "text": "Hello, is anyone there?",
                        },
                    }
                ],
            }
        ],
    }
    raw_body = json.dumps(payload).encode("utf-8")

    # Act: send a webhook message
    response = await client.post(
        "/api/v1/webhook",
        content=raw_body,
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 200

    # Assert: The thread should now be AI_CONTROLLED
    result = await db_session.execute(
        select(Customer).where(Customer.messenger_user_id == SENDER_ID_A)
    )
    customer = result.scalar_one()
    assert customer.thread_state == "AI_CONTROLLED", (
        f"Expected auto-resume to AI_CONTROLLED, got {customer.thread_state}"
    )

    # Assert: Both User and Bot messages were logged (bot replied)
    log_result = await db_session.execute(
        select(ConversationLog)
        .where(ConversationLog.messenger_user_id == SENDER_ID_A)
        .order_by(ConversationLog.id)
    )
    logs = log_result.scalars().all()
    speakers = [log.speaker for log in logs]

    assert "User" in speakers, "User message should be logged"
    assert "Bot" in speakers, (
        f"Bot SHOULD reply after auto-resume. Got speakers: {speakers}"
    )

    # Assert: DeepSeek was called
    assert mock_deepseek_api[0] >= 1, (
        f"DeepSeek should be called after auto-resume, "
        f"but was called {mock_deepseek_api[0]} time(s)"
    )


@pytest.mark.asyncio
async def test_no_auto_resume_before_12_hours(
    client, db_session, mock_deepseek_api, mock_send_api
):
    """A HUMAN_CONTROLLED thread with thread_state_updated_at < 12 hours ago
    does NOT auto-resume."""
    # Arrange: seed customer HUMAN_CONTROLLED with timestamp < 12 hours ago
    recent_time = datetime.now() - timedelta(hours=IDLE_TIMEOUT_HOURS - 1)
    await _seed_customer(
        SENDER_ID_B,
        thread_state="HUMAN_CONTROLLED",
        thread_state_updated_at=recent_time,
    )

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
                        "sender": {"id": SENDER_ID_B},
                        "recipient": {"id": "page-1"},
                        "timestamp": 1234567890,
                        "message": {
                            "mid": "mid.$cAAJ1test-12b-b",
                            "text": "Still waiting for help...",
                        },
                    }
                ],
            }
        ],
    }
    raw_body = json.dumps(payload).encode("utf-8")

    # Reset DeepSeek call count
    mock_deepseek_api[0] = 0

    # Act: send a webhook message
    response = await client.post(
        "/api/v1/webhook",
        content=raw_body,
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 200

    # Assert: Thread should still be HUMAN_CONTROLLED
    result = await db_session.execute(
        select(Customer).where(Customer.messenger_user_id == SENDER_ID_B)
    )
    customer = result.scalar_one()
    assert customer.thread_state == "HUMAN_CONTROLLED", (
        f"Expected still HUMAN_CONTROLLED, got {customer.thread_state}"
    )

    # Assert: Only the User message was logged (no Bot reply)
    log_result = await db_session.execute(
        select(ConversationLog)
        .where(ConversationLog.messenger_user_id == SENDER_ID_B)
        .order_by(ConversationLog.id)
    )
    logs = log_result.scalars().all()
    speakers = [log.speaker for log in logs]

    assert "User" in speakers, "User message should be logged"
    assert "Bot" not in speakers, (
        f"Bot should NOT reply before 12 hours. Got speakers: {speakers}"
    )

    # Assert: DeepSeek was NOT called
    assert mock_deepseek_api[0] == 0, (
        f"DeepSeek should not be called before 12 hours, "
        f"but was called {mock_deepseek_api[0]} time(s)"
    )


@pytest.mark.asyncio
async def test_pinned_thread_does_not_auto_resume(
    client, db_session, mock_deepseek_api, mock_send_api
):
    """A HUMAN_CONTROLLED + thread_state_pinned=true thread does NOT
    auto-resume even after 12+ hours."""
    # Arrange: seed customer with pin=True and old timestamp
    old_time = datetime.now() - timedelta(hours=IDLE_TIMEOUT_HOURS + 2)
    await _seed_customer(
        SENDER_ID_C,
        thread_state="HUMAN_CONTROLLED",
        thread_state_pinned=True,
        thread_state_updated_at=old_time,
    )

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
                        "sender": {"id": SENDER_ID_C},
                        "recipient": {"id": "page-1"},
                        "timestamp": 1234567890,
                        "message": {
                            "mid": "mid.$cAAJ1test-12b-c",
                            "text": "I need help with a complex issue!",
                        },
                    }
                ],
            }
        ],
    }
    raw_body = json.dumps(payload).encode("utf-8")

    # Reset DeepSeek call count
    mock_deepseek_api[0] = 0

    # Act: send a webhook message
    response = await client.post(
        "/api/v1/webhook",
        content=raw_body,
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 200

    # Assert: Thread should still be HUMAN_CONTROLLED (pinned)
    result = await db_session.execute(
        select(Customer).where(Customer.messenger_user_id == SENDER_ID_C)
    )
    customer = result.scalar_one()
    assert customer.thread_state == "HUMAN_CONTROLLED", (
        f"Expected HUMAN_CONTROLLED (pinned), got {customer.thread_state}"
    )

    # Assert: thread_state_pinned is still True
    assert customer.thread_state_pinned is True, (
        "Expected thread_state_pinned to still be True"
    )

    # Assert: Only the User message was logged (no Bot reply)
    log_result = await db_session.execute(
        select(ConversationLog)
        .where(ConversationLog.messenger_user_id == SENDER_ID_C)
        .order_by(ConversationLog.id)
    )
    logs = log_result.scalars().all()
    speakers = [log.speaker for log in logs]

    assert "User" in speakers, "User message should be logged"
    assert "Bot" not in speakers, (
        f"Bot should NOT reply when pinned. Got speakers: {speakers}"
    )

    # Assert: DeepSeek was NOT called
    assert mock_deepseek_api[0] == 0, (
        f"DeepSeek should not be called when pinned, "
        f"but was called {mock_deepseek_api[0]} time(s)"
    )


@pytest.mark.asyncio
async def test_manual_toggle_clears_pin(client, db_session):
    """Manually flipping the toggle clears thread_state_pinned."""
    # Arrange: seed customer with pin=True and HUMAN_CONTROLLED
    old_time = datetime.now() - timedelta(hours=IDLE_TIMEOUT_HOURS + 1)
    await _seed_customer(
        SENDER_ID_D,
        thread_state="HUMAN_CONTROLLED",
        thread_state_pinned=True,
        thread_state_updated_at=old_time,
    )

    token = await _get_admin_token(client)

    # Act: manually toggle to AI_CONTROLLED
    resp = await client.patch(
        f"/api/v1/conversations/{SENDER_ID_D}/thread-state",
        json={"thread_state": "AI_CONTROLLED"},
        headers=_auth_headers(token),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["thread_state"] == "AI_CONTROLLED"

    # Assert: thread_state_pinned should now be False
    assert data["thread_state_pinned"] is False, (
        f"Expected thread_state_pinned=False after toggle, got {data['thread_state_pinned']}"
    )

    # Verify in DB
    result = await db_session.execute(
        select(Customer).where(Customer.messenger_user_id == SENDER_ID_D)
    )
    customer = result.scalar_one()
    assert customer.thread_state_pinned is False, (
        "Expected thread_state_pinned to be cleared in DB after manual toggle"
    )

    # Also verify that toggling back to HUMAN_CONTROLLED clears it
    resp2 = await client.patch(
        f"/api/v1/conversations/{SENDER_ID_D}/thread-state",
        json={"thread_state": "HUMAN_CONTROLLED"},
        headers=_auth_headers(token),
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["thread_state"] == "HUMAN_CONTROLLED"
    assert data2["thread_state_pinned"] is False, (
        "Expected thread_state_pinned=False after toggle back to HUMAN_CONTROLLED"
    )


@pytest.mark.asyncio
async def test_pin_endpoint_toggle(client, db_session):
    """The pin endpoint can set and clear thread_state_pinned independently."""
    await _seed_customer(SENDER_ID_A, thread_state="HUMAN_CONTROLLED")
    token = await _get_admin_token(client)

    # Set pin to True
    resp1 = await client.patch(
        f"/api/v1/conversations/{SENDER_ID_A}/thread-state/pin",
        json={"thread_state_pinned": True},
        headers=_auth_headers(token),
    )
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["thread_state_pinned"] is True

    # Verify in DB
    result = await db_session.execute(
        select(Customer).where(Customer.messenger_user_id == SENDER_ID_A)
    )
    customer = result.scalar_one()
    assert customer.thread_state_pinned is True

    # Set pin back to False
    resp2 = await client.patch(
        f"/api/v1/conversations/{SENDER_ID_A}/thread-state/pin",
        json={"thread_state_pinned": False},
        headers=_auth_headers(token),
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["thread_state_pinned"] is False

    # Verify in DB
    await db_session.refresh(customer)
    assert customer.thread_state_pinned is False


@pytest.mark.asyncio
async def test_auto_resume_on_get_conversations(
    client, db_session, mock_deepseek_api, mock_send_api
):
    """Lazy check: GET /conversations auto-resumes a stale HUMAN_CONTROLLED thread."""
    old_time = datetime.now() - timedelta(hours=IDLE_TIMEOUT_HOURS + 1)
    await _seed_customer(
        SENDER_ID_B,
        thread_state="HUMAN_CONTROLLED",
        thread_state_updated_at=old_time,
    )
    await _seed_conversation_log(SENDER_ID_B, "User", "Old message")

    token = await _get_admin_token(client)

    # Act: GET /conversations
    resp = await client.get(
        "/api/v1/conversations",
        headers=_auth_headers(token),
    )
    assert resp.status_code == 200

    # Assert: thread is now AI_CONTROLLED
    result = await db_session.execute(
        select(Customer).where(Customer.messenger_user_id == SENDER_ID_B)
    )
    customer = result.scalar_one()
    assert customer.thread_state == "AI_CONTROLLED", (
        f"Expected auto-resume on GET /conversations, got {customer.thread_state}"
    )

    # Assert: response reflects the new state
    data = resp.json()
    match = [t for t in data if t["messenger_user_id"] == SENDER_ID_B]
    assert len(match) == 1
    assert match[0]["thread_state"] == "AI_CONTROLLED"


@pytest.mark.asyncio
async def test_auto_resume_on_get_conversation_messages(
    client, db_session, mock_deepseek_api, mock_send_api
):
    """Lazy check: GET /conversations/{id} auto-resumes a stale HUMAN_CONTROLLED thread."""
    old_time = datetime.now() - timedelta(hours=IDLE_TIMEOUT_HOURS + 1)
    await _seed_customer(
        SENDER_ID_C,
        thread_state="HUMAN_CONTROLLED",
        thread_state_updated_at=old_time,
    )
    await _seed_conversation_log(SENDER_ID_C, "User", "Old message")

    token = await _get_admin_token(client)

    # Act: GET /conversations/{id}
    resp = await client.get(
        f"/api/v1/conversations/{SENDER_ID_C}",
        headers=_auth_headers(token),
    )
    assert resp.status_code == 200

    # Assert: thread is now AI_CONTROLLED
    result = await db_session.execute(
        select(Customer).where(Customer.messenger_user_id == SENDER_ID_C)
    )
    customer = result.scalar_one()
    assert customer.thread_state == "AI_CONTROLLED", (
        f"Expected auto-resume on GET messages, got {customer.thread_state}"
    )
