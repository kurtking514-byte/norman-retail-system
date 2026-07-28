"""
Phase 8 integration tests for Live Chat Backend (Conversations & Notifications).

Covers:
- ``GET /api/v1/conversations`` — auth required, thread grouping, summaries.
- ``GET /api/v1/conversations/{messenger_user_id}`` — full message history.
- ``POST /api/v1/conversations/{messenger_user_id}/reply`` — staff reply.
- ``GET /api/v1/notifications`` — default Pending filter.
- ``PATCH /api/v1/notifications/{id}`` — status update, invalid status → 422.

All Send API calls are mocked — no real network requests are made.
"""

import json
import os

# ---------------------------------------------------------------------------
# Environment setup – must happen *before* any app imports
# ---------------------------------------------------------------------------
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-phase8-testing")
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

SENDER_ID_A = "messenger-user-8-a"
SENDER_ID_B = "messenger-user-8-b"

LOGIN_URL = "/api/v1/auth/login"

# ---------------------------------------------------------------------------
# Phase-8-specific seed data — tables already created by conftest's setup_db.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session", autouse=True)
def seed_phase8_data():
    """Seed default data needed by Phase 8 tests."""
    # No additional seed data needed beyond table creation
    yield


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
async def cleanup_phase8_data():
    """Auto-run before each test to clean up Phase-8-specific rows."""
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


async def _seed_conversation_log(
    messenger_user_id: str,
    speaker: str,
    message_text: str,
):
    """Insert a ConversationLog row directly, using a throwaway session."""
    session = async_session_factory()
    try:
        # Ensure a Customer row exists for this messenger_user_id
        result = await session.execute(
            select(Customer).where(
                Customer.messenger_user_id == messenger_user_id
            )
        )
        if not result.scalar_one_or_none():
            cust = Customer(
                first_name="Test",
                last_name="User",
                phone_number=f"pending-{messenger_user_id}",
                messenger_user_id=messenger_user_id,
            )
            session.add(cust)
            await session.commit()

        log_entry = ConversationLog(
            messenger_user_id=messenger_user_id,
            speaker=speaker,
            message_text=message_text,
        )
        session.add(log_entry)
        await session.commit()
    finally:
        await session.close()


async def _seed_notification(
    messenger_user_id: str,
    status: str = "Pending",
):
    """Insert a NotificationQueue row for a given messenger_user_id."""
    session = async_session_factory()
    try:
        nq = NotificationQueue(
            recipient_id=messenger_user_id,
            channel="Dashboard",
            payload={
                "messenger_user_id": messenger_user_id,
                "reason": "Test handoff reason",
                "customer_message": "Test customer message",
            },
            status=status,
        )
        session.add(nq)
        await session.commit()
    finally:
        await session.close()


# ===================================================================
# Tests
# ===================================================================


@pytest.mark.asyncio
async def test_conversations_requires_auth(client):
    """GET /api/v1/conversations without auth returns 401."""
    resp = await client.get("/api/v1/conversations")
    assert resp.status_code == 401
    # The body should indicate not authenticated
    body = resp.json()
    assert body.get("error", {}).get("code") == "UNAUTHORIZED" or "detail" in body


@pytest.mark.asyncio
async def test_conversations_one_thread_per_user(client):
    """Two messages from the same user → one thread summary with last message."""
    # Seed 2 messages for SENDER_ID_A
    await _seed_conversation_log(SENDER_ID_A, "User", "Hello, how much is S23?")
    await _seed_conversation_log(
        SENDER_ID_A, "Bot", "The S23 Ultra is ₱54,999.00!"
    )

    token = await _get_admin_token(client)
    resp = await client.get(
        "/api/v1/conversations",
        headers=_auth_headers(token),
    )
    assert resp.status_code == 200

    data = resp.json()
    # Find our test user among the results
    matches = [t for t in data if t["messenger_user_id"] == SENDER_ID_A]
    assert len(matches) == 1, (
        f"Expected exactly one thread for {SENDER_ID_A}, got {len(matches)}"
    )
    thread = matches[0]
    assert thread["last_message_text"] == "The S23 Ultra is ₱54,999.00!"
    assert thread["messenger_user_id"] == SENDER_ID_A
    # customer_name should be "Test User" (from our seed)
    assert thread["customer_name"] == "Test User"


@pytest.mark.asyncio
async def test_conversation_messages_chronological(client):
    """GET /conversations/{id} returns messages in chronological order."""
    await _seed_conversation_log(SENDER_ID_A, "User", "First message")
    await _seed_conversation_log(SENDER_ID_A, "Bot", "Second message")

    token = await _get_admin_token(client)
    resp = await client.get(
        f"/api/v1/conversations/{SENDER_ID_A}",
        headers=_auth_headers(token),
    )
    assert resp.status_code == 200

    data = resp.json()
    assert len(data) == 2
    assert data[0]["message_text"] == "First message"
    assert data[0]["speaker"] == "User"
    assert data[1]["message_text"] == "Second message"
    assert data[1]["speaker"] == "Bot"


@pytest.mark.asyncio
async def test_staff_reply_creates_log_entry(client, db_session):
    """POST /conversations/{id}/reply creates a Staff log entry and calls Send API."""
    # First seed a customer + message so the user exists
    await _seed_conversation_log(SENDER_ID_A, "User", "I need help!")

    token = await _get_admin_token(client)
    reply_payload = {"message_text": "How can I help you?"}
    resp = await client.post(
        f"/api/v1/conversations/{SENDER_ID_A}/reply",
        json=reply_payload,
        headers=_auth_headers(token),
    )
    assert resp.status_code == 201
    data = resp.json()
    assert data["speaker"] == "Staff"
    assert data["message_text"] == "How can I help you?"

    # Verify the log entry was persisted
    verify_session = async_session_factory()
    try:
        result = await verify_session.execute(
            select(ConversationLog)
            .where(ConversationLog.messenger_user_id == SENDER_ID_A)
            .where(ConversationLog.speaker == "Staff")
        )
        rows = result.scalars().all()
        assert len(rows) == 1
        assert rows[0].message_text == "How can I help you?"
    finally:
        await verify_session.close()


@pytest.mark.asyncio
async def test_notifications_defaults_to_pending(client):
    """GET /notifications with no filter returns only Pending items."""
    # Seed one Pending and one Sent notification
    await _seed_notification(SENDER_ID_A, status="Pending")
    await _seed_notification(SENDER_ID_B, status="Sent")

    token = await _get_admin_token(client)
    resp = await client.get(
        "/api/v1/notifications",
        headers=_auth_headers(token),
    )
    assert resp.status_code == 200

    data = resp.json()
    # Should only include Pending items
    assert len(data) >= 1
    for item in data:
        assert item["status"] == "Pending", (
            f"Expected only Pending, got {item['status']}"
        )


@pytest.mark.asyncio
async def test_notification_patch_status(client):
    """PATCH /notifications/{id} updates status successfully."""
    # Seed a notification
    await _seed_notification(SENDER_ID_A, status="Pending")

    # Find its ID
    token = await _get_admin_token(client)
    list_resp = await client.get(
        "/api/v1/notifications",
        headers=_auth_headers(token),
    )
    assert list_resp.status_code == 200
    notifications = list_resp.json()
    pending = [n for n in notifications if n["recipient_id"] == SENDER_ID_A]
    assert len(pending) >= 1
    nq_id = pending[0]["id"]

    # Patch to Resolved
    patch_resp = await client.patch(
        f"/api/v1/notifications/{nq_id}",
        json={"status": "Resolved"},
        headers=_auth_headers(token),
    )
    assert patch_resp.status_code == 200
    patched = patch_resp.json()
    assert patched["status"] == "Resolved"
    assert patched["id"] == nq_id

    # Verify it's no longer returned in default (Pending) filter
    list_resp2 = await client.get(
        "/api/v1/notifications",
        headers=_auth_headers(token),
    )
    remaining = list_resp2.json()
    matching = [n for n in remaining if n["id"] == nq_id]
    assert len(matching) == 0, (
        "Resolved notification should not appear in default Pending filter"
    )


@pytest.mark.asyncio
async def test_notification_patch_invalid_status_422(client):
    """PATCH /notifications/{id} with invalid status returns 422."""
    # Seed a notification
    await _seed_notification(SENDER_ID_A, status="Pending")

    # Find its ID
    token = await _get_admin_token(client)
    list_resp = await client.get(
        "/api/v1/notifications",
        headers=_auth_headers(token),
    )
    notifications = list_resp.json()
    pending = [n for n in notifications if n["recipient_id"] == SENDER_ID_A]
    assert len(pending) >= 1
    nq_id = pending[0]["id"]

    # Patch with invalid status
    patch_resp = await client.patch(
        f"/api/v1/notifications/{nq_id}",
        json={"status": "InvalidStatus"},
        headers=_auth_headers(token),
    )
    assert patch_resp.status_code == 422
