"""
Phase 10 integration tests for AI-Pause Toggle & Customer Profile Data.

Covers:
- ``PATCH /api/v1/conversations/{id}/thread-state`` — toggle AI control.
- ``process_incoming_message`` skipped when thread_state=HUMAN_CONTROLLED.
- ``GET /api/v1/conversations`` includes thread_state in summaries.
- Customer Profile Panel data (reservations/repairs by customer_id).

All DeepSeek and Send API calls are mocked — no real network requests.
"""

import json
import os

# ---------------------------------------------------------------------------
# Environment setup – must happen *before* any app imports
# ---------------------------------------------------------------------------
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-phase10-testing")
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
from app.models.product import Brand, Category, Product, Inventory  # noqa: E402
from app.models.reservation import Reservation  # noqa: E402
from app.models.repair import RepairRequest  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SENDER_ID_A = "messenger-user-10-a"
SENDER_ID_B = "messenger-user-10-b"
PRODUCT_ID = 10001
PRODUCT_NAME = "Phase 10 Test Phone"
MODEL_NUMBER = "PHASE10-TEST-001"

LOGIN_URL = "/api/v1/auth/login"

# ---------------------------------------------------------------------------
# Phase-10-specific seed data — tables already created by conftest's setup_db.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session", autouse=True)
def seed_phase10_data():
    """Seed default data needed by Phase 10 tests."""
    async def _seed():
        session = async_session_factory()
        try:
            result = await session.execute(select(Brand).where(Brand.id == 1))
            if not result.scalar_one_or_none():
                session.add(Brand(id=1, name="Default Brand Phase10"))
                await session.commit()

            result = await session.execute(select(Category).where(Category.id == 1))
            if not result.scalar_one_or_none():
                session.add(Category(id=1, name="Default Category Phase10"))
                await session.commit()

            result = await session.execute(
                select(Product).where(Product.model_number == MODEL_NUMBER)
            )
            if not result.scalar_one_or_none():
                session.add(
                    Product(
                        id=PRODUCT_ID,
                        brand_id=1,
                        category_id=1,
                        name=PRODUCT_NAME,
                        model_number=MODEL_NUMBER,
                        description="Test product for Phase 10",
                        cost_price=30000.00,
                        selling_price=39999.00,
                        is_active=True,
                    )
                )
                await session.commit()

            # Seed inventory
            result = await session.execute(
                select(Inventory).where(Inventory.serial_number == "SN-PHASE10-001")
            )
            if not result.scalar_one_or_none():
                session.add(
                    Inventory(
                        product_id=PRODUCT_ID,
                        serial_number="SN-PHASE10-001",
                        status="In Stock",
                        location="Main Store",
                    )
                )
                await session.commit()
        finally:
            await session.close()

    asyncio.run(_seed())
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
async def cleanup_phase10_data():
    """Auto-run before each test to clean up Phase-10-specific rows."""
    session = async_session_factory()
    try:
        # Find customer IDs for our test users first
        result = await session.execute(
            select(Customer.id).where(
                Customer.messenger_user_id.in_([SENDER_ID_A, SENDER_ID_B])
            )
        )
        cust_ids = [row[0] for row in result.all()]

        if cust_ids:
            await session.execute(
                RepairRequest.__table__.delete().where(
                    RepairRequest.customer_id.in_(cust_ids)
                )
            )
            await session.execute(
                Reservation.__table__.delete().where(
                    Reservation.customer_id.in_(cust_ids)
                )
            )
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
    monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", "fake-deepseek-key-phase10")

    original_post = httpx.AsyncClient.post
    deepseek_call_count = [0]  # mutable closure to track calls

    async def _mock_post(self, url, *args, **kwargs):
        if "api.deepseek.com" in str(url):
            deepseek_call_count[0] += 1
            return httpx.Response(
                status_code=200,
                request=httpx.Request("POST", url),
                json={
                    "id": "mock-ds-phase10",
                    "object": "chat.completion",
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": "This is a mock reply for Phase 10 testing.",
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
                first_name="Phase10",
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
    """Insert a ConversationLog row."""
    session = async_session_factory()
    try:
        # Ensure customer exists
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


async def _seed_reservation(
    customer_id: int,
    status: str = "Pending",
):
    """Insert a Reservation row for testing."""
    session = async_session_factory()
    try:
        res = Reservation(
            customer_id=customer_id,
            product_id=PRODUCT_ID,
            reservation_date=datetime.now(timezone.utc).replace(tzinfo=None),
            expiry_date=datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=48),
            status=status,
        )
        session.add(res)
        await session.commit()
    finally:
        await session.close()


async def _seed_repair(
    customer_id: int,
    status: str = "Pending",
):
    """Insert a RepairRequest row for testing."""
    session = async_session_factory()
    try:
        rep = RepairRequest(
            customer_id=customer_id,
            device_model="iPhone 15",
            issue_description="Broken screen",
            estimated_cost=5000.00,
            status=status,
        )
        session.add(rep)
        await session.commit()
    finally:
        await session.close()


# ===================================================================
# Tests
# ===================================================================


@pytest.mark.asyncio
async def test_conversations_includes_thread_state(client):
    """GET /api/v1/conversations includes thread_state in summaries."""
    await _seed_conversation_log(SENDER_ID_A, "User", "Hello")

    token = await _get_admin_token(client)
    resp = await client.get(
        "/api/v1/conversations",
        headers=_auth_headers(token),
    )
    assert resp.status_code == 200

    data = resp.json()
    matches = [t for t in data if t["messenger_user_id"] == SENDER_ID_A]
    assert len(matches) == 1
    thread = matches[0]
    assert "thread_state" in thread, "thread_state should be present in response"
    # Default should be AI_CONTROLLED
    assert thread["thread_state"] == "AI_CONTROLLED", (
        f"Expected AI_CONTROLLED, got {thread['thread_state']}"
    )


@pytest.mark.asyncio
async def test_thread_state_toggle_ai_controlled(client, db_session):
    """PATCH /conversations/{id}/thread-state toggles to HUMAN_CONTROLLED and back."""
    await _seed_customer(SENDER_ID_A, thread_state="AI_CONTROLLED")

    token = await _get_admin_token(client)

    # Toggle to HUMAN_CONTROLLED
    resp1 = await client.patch(
        f"/api/v1/conversations/{SENDER_ID_A}/thread-state",
        json={"thread_state": "HUMAN_CONTROLLED"},
        headers=_auth_headers(token),
    )
    assert resp1.status_code == 200
    data1 = resp1.json()
    assert data1["thread_state"] == "HUMAN_CONTROLLED"
    assert data1["messenger_user_id"] == SENDER_ID_A

    # Verify persisted
    result = await db_session.execute(
        select(Customer).where(Customer.messenger_user_id == SENDER_ID_A)
    )
    customer = result.scalar_one()
    assert customer.thread_state == "HUMAN_CONTROLLED"

    # Toggle back to AI_CONTROLLED
    resp2 = await client.patch(
        f"/api/v1/conversations/{SENDER_ID_A}/thread-state",
        json={"thread_state": "AI_CONTROLLED"},
        headers=_auth_headers(token),
    )
    assert resp2.status_code == 200
    data2 = resp2.json()
    assert data2["thread_state"] == "AI_CONTROLLED"

    # Verify persisted
    await db_session.refresh(customer)
    assert customer.thread_state == "AI_CONTROLLED"


@pytest.mark.asyncio
async def test_thread_state_invalid_value_422(client):
    """PATCH with invalid thread_state returns 422."""
    await _seed_customer(SENDER_ID_A)

    token = await _get_admin_token(client)
    resp = await client.patch(
        f"/api/v1/conversations/{SENDER_ID_A}/thread-state",
        json={"thread_state": "INVALID_STATE"},
        headers=_auth_headers(token),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_thread_state_not_found_404(client):
    """PATCH for a non-existent messenger_user_id returns 404."""
    token = await _get_admin_token(client)
    resp = await client.patch(
        "/api/v1/conversations/nonexistent-user/thread-state",
        json={"thread_state": "HUMAN_CONTROLLED"},
        headers=_auth_headers(token),
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_process_incoming_message_skips_ai_when_human_controlled(
    client, db_session, mock_deepseek_api, mock_send_api
):
    """When thread_state=HUMAN_CONTROLLED, incoming messages do NOT trigger DeepSeek.

    The message is still logged to conversation_logs, but no Bot reply is
    generated and no notification is created.
    """
    # Arrange: seed customer with HUMAN_CONTROLLED state
    await _seed_customer(SENDER_ID_A, thread_state="HUMAN_CONTROLLED")

    # Act: send a webhook message
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
                            "mid": "mid.$cAAJ1test",
                            "text": "How much is the Phase 10 Test Phone?",
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

    # Assert: Only the User message was logged (no Bot reply)
    result = await db_session.execute(
        select(ConversationLog)
        .where(ConversationLog.messenger_user_id == SENDER_ID_A)
        .order_by(ConversationLog.id)
    )
    logs = result.scalars().all()
    speakers = [log.speaker for log in logs]

    assert "User" in speakers, "User message should be logged"
    assert "Bot" not in speakers, (
        f"Bot should NOT reply when HUMAN_CONTROLLED. Got speakers: {speakers}"
    )
    # Exactly 1 message (the user's)
    assert len(logs) == 1, (
        f"Expected exactly 1 log entry (User), got {len(logs)}"
    )

    # Assert: No notification was created
    notif_result = await db_session.execute(
        select(NotificationQueue).where(
            NotificationQueue.recipient_id == SENDER_ID_A
        )
    )
    notifications = notif_result.scalars().all()
    assert len(notifications) == 0, (
        "No notification should be created when HUMAN_CONTROLLED"
    )

    # Assert: DeepSeek was never called
    call_count = mock_deepseek_api[0]  # mutable list
    assert call_count == 0, (
        f"DeepSeek should not be called when HUMAN_CONTROLLED, "
        f"but was called {call_count} time(s)"
    )


@pytest.mark.asyncio
async def test_process_incoming_message_ai_replies_when_ai_controlled(
    client, db_session, mock_deepseek_api, mock_send_api
):
    """When thread_state=AI_CONTROLLED (default), AI replies work normally."""
    # Arrange: seed customer with AI_CONTROLLED (default)
    await _seed_customer(SENDER_ID_B, thread_state="AI_CONTROLLED")

    # Act: send a webhook message
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
                            "mid": "mid.$cAAJ1test",
                            "text": "What is the price of the Phase 10 Test Phone?",
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

    # Assert: Both User and Bot messages were logged
    result = await db_session.execute(
        select(ConversationLog)
        .where(ConversationLog.messenger_user_id == SENDER_ID_B)
        .order_by(ConversationLog.id)
    )
    logs = result.scalars().all()
    speakers = [log.speaker for log in logs]

    assert "User" in speakers, "User message should be logged"
    assert "Bot" in speakers, (
        f"Bot should reply when AI_CONTROLLED. Got speakers: {speakers}"
    )
    # At least 2 messages (User + Bot)
    assert len(logs) >= 2, (
        f"Expected at least 2 log entries, got {len(logs)}"
    )

    # Assert: DeepSeek was called
    call_count = mock_deepseek_api[0]  # mutable list
    assert call_count >= 1, (
        f"DeepSeek should be called when AI_CONTROLLED, "
        f"but was called {call_count} time(s)"
    )


@pytest.mark.asyncio
async def test_customer_profile_reservations_and_repairs(client, db_session):
    """Customer profile endpoint data — reservations and repairs filtered by customer_id.

    This tests the data path that the CustomerProfile frontend component uses.
    """
    # Seed a customer
    await _seed_customer(SENDER_ID_A)
    result = await db_session.execute(
        select(Customer).where(Customer.messenger_user_id == SENDER_ID_A)
    )
    customer = result.scalar_one()
    cust_id = customer.id

    # Seed reservations: 1 active (Pending), 1 cancelled
    await _seed_reservation(cust_id, status="Pending")
    await _seed_reservation(cust_id, status="Cancelled")

    # Seed repairs: 1 active (In Progress), 1 released
    await _seed_repair(cust_id, status="In Progress")
    await _seed_repair(cust_id, status="Released")

    token = await _get_admin_token(client)

    # Fetch reservations filtered by customer_id
    res_resp = await client.get(
        "/api/v1/reservations",
        params={"customer_id": cust_id},
        headers=_auth_headers(token),
    )
    assert res_resp.status_code == 200
    reservations = res_resp.json()
    assert len(reservations) >= 2, f"Expected at least 2 reservations, got {len(reservations)}"

    # Fetch repairs filtered by customer_id
    rep_resp = await client.get(
        "/api/v1/repairs",
        params={"customer_id": cust_id},
        headers=_auth_headers(token),
    )
    assert rep_resp.status_code == 200
    repairs = rep_resp.json()
    assert len(repairs) >= 2, f"Expected at least 2 repairs, got {len(repairs)}"

    # Verify filtering works — our reservations have different statuses
    statuses = [r["status"] for r in reservations]
    assert "Pending" in statuses
    assert "Cancelled" in statuses

    # Verify repairs
    rep_statuses = [r["status"] for r in repairs]
    assert "In Progress" in rep_statuses
    assert "Released" in rep_statuses
