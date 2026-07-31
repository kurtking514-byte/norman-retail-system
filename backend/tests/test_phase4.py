"""
Phase 4 integration tests for Meta Messenger webhook endpoints.

Covers:
- GET /api/v1/webhook — verification handshake (valid & invalid tokens)
- POST /api/v1/webhook — event ingestion, signature validation, customer
  creation/deduplication, conversation logging.

Uses the same separate test database (test_norman_shop.db) as Phase 2.
"""

import asyncio
import hashlib
import hmac
import json
import os

# ---------------------------------------------------------------------------
# Environment setup – must happen *before* any app imports
# ---------------------------------------------------------------------------
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-phase4-testing")
os.environ.setdefault("ADMIN_USERNAME", "admin")

import bcrypt  # noqa: E402
import pytest_asyncio

HASHED_PW = bcrypt.hashpw(b"changeme123", bcrypt.gensalt(12)).decode()
os.environ.setdefault("ADMIN_PASSWORD_HASH", HASHED_PW)
# DATABASE_URL is set by conftest.py — no need to override here.

# Ensure META_APP_SECRET is *not* set for most tests (we'll override per-test)
# so that signature validation is skipped.
if "META_APP_SECRET" in os.environ:
    del os.environ["META_APP_SECRET"]

# ---- Imports -------------------------------------------------------------
import httpx  # noqa: E402
import pytest  # noqa: E402
from httpx import ASGITransport  # noqa: E402
from sqlalchemy import select, func  # noqa: E402

from app.main import app  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.database import async_session_factory  # noqa: E402
from app.models.customer import Customer  # noqa: E402
from app.models.notification import ConversationLog  # noqa: E402
from app.models.product import Brand, Category  # noqa: E402
from app.services.messenger_service import verify_signature  # noqa: E402
from contextlib import contextmanager  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SAMPLE_SENDER_ID = "messenger-user-12345"


def _sample_payload(sender_id: str = SAMPLE_SENDER_ID, text: str = "Hello") -> bytes:
    """Build a realistic (simplified) Meta webhook POST body."""
    payload = {
        "object": "page",
        "entry": [
            {
                "id": "page-1",
                "time": 1234567890,
                "messaging": [
                    {
                        "sender": {"id": sender_id},
                        "recipient": {"id": "page-1"},
                        "timestamp": 1234567890,
                        "message": {
                            "mid": "mid.$cAAJ1test",
                            "text": text,
                        },
                    }
                ],
            }
        ],
    }
    return json.dumps(payload).encode("utf-8")


def _compute_signature(raw_body: bytes, secret: str) -> str:
    """Compute the ``X-Hub-Signature-256`` value for *raw_body*."""
    h = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256)
    return f"sha256={h.hexdigest()}"


async def _seed_default_data():
    """Ensure brand_id=1 and category_id=1 exist (same as Phase 2)."""
    session = async_session_factory()
    try:
        result = await session.execute(select(Brand).where(Brand.id == 1))
        if not result.scalar_one_or_none():
            session.add(Brand(id=1, name="Default Brand"))
        result = await session.execute(select(Category).where(Category.id == 1))
        if not result.scalar_one_or_none():
            session.add(Category(id=1, name="Default Category"))
        await session.commit()
    finally:
        await session.close()


# ---------------------------------------------------------------------------
# Phase-4-specific seed data — tables already created by conftest's setup_db.
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="session", autouse=True)
async def seed_phase4_data():
    """Seed default data needed by Phase 4 tests."""
    await _seed_default_data()
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


async def _cleanup_test_data():
    """Remove test customers and conversation logs so tests are isolated."""
    session = async_session_factory()
    try:
        await session.execute(
            ConversationLog.__table__.delete().where(
                ConversationLog.messenger_user_id == SAMPLE_SENDER_ID
            )
        )
        await session.execute(
            Customer.__table__.delete().where(
                Customer.messenger_user_id == SAMPLE_SENDER_ID
            )
        )
        await session.commit()
    finally:
        await session.close()


@pytest.fixture(autouse=True)
async def cleanup_test_data():
    """Auto-run before each test to clean up test-specific rows."""
    await _cleanup_test_data()
    yield
    await _cleanup_test_data()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_webhook_verify_valid_token(client: httpx.AsyncClient):
    """GET /api/v1/webhook with correct verify_token → 200 + plain-text challenge."""
    response = await client.get(
        "/api/v1/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": settings.MESSENGER_VERIFY_TOKEN,
            "hub.challenge": "12345",
        },
    )
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    # Must be plain text, not JSON-wrapped
    assert response.text == "12345", f"Expected '12345', got {response.text!r}"
    assert response.headers.get("content-type", "").startswith("text/plain")


@pytest.mark.asyncio
async def test_webhook_verify_invalid_token(client: httpx.AsyncClient):
    """GET /api/v1/webhook with wrong verify_token → 403."""
    response = await client.get(
        "/api/v1/webhook",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong-token",
            "hub.challenge": "12345",
        },
    )
    assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
    body = response.json()
    assert body["success"] is False
    assert "error" in body


@pytest.mark.asyncio
async def test_webhook_post_no_secret(client: httpx.AsyncClient, db_session):
    """POST /api/v1/webhook with no META_APP_SECRET → 200 + DB rows created.

    When META_APP_SECRET is empty, signature validation is skipped.
    """
    # Ensure secret is empty
    settings.META_APP_SECRET = ""

    raw_body = _sample_payload()
    response = await client.post(
        "/api/v1/webhook",
        content=raw_body,
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    assert response.json() == {"status": "EVENT_RECEIVED"}

    # Verify Customer row was created
    result = await db_session.execute(
        select(Customer).where(Customer.messenger_user_id == SAMPLE_SENDER_ID)
    )
    customer = result.scalar_one_or_none()
    assert customer is not None, "Customer should have been created"
    assert customer.messenger_user_id == SAMPLE_SENDER_ID
    assert customer.first_name == "Messenger"
    assert customer.last_name == "User"
    assert customer.phone_number == f"pending-{SAMPLE_SENDER_ID}"

    # Verify ConversationLog row exists
    result = await db_session.execute(
        select(ConversationLog).where(
            ConversationLog.messenger_user_id == SAMPLE_SENDER_ID,
            ConversationLog.speaker == "User",
        )
    )
    log_entry = result.scalar_one_or_none()
    assert log_entry is not None, "ConversationLog should have been created"
    assert log_entry.message_text == "Hello"


@pytest.mark.asyncio
async def test_webhook_post_deduplicates_customer(client: httpx.AsyncClient, db_session):
    """POST /api/v1/webhook sent twice with same sender.id → one Customer, two ConversationLogs."""
    settings.META_APP_SECRET = ""

    raw_body = _sample_payload(text="First message")
    resp1 = await client.post(
        "/api/v1/webhook",
        content=raw_body,
        headers={"Content-Type": "application/json"},
    )
    assert resp1.status_code == 200

    raw_body2 = _sample_payload(text="Second message")
    resp2 = await client.post(
        "/api/v1/webhook",
        content=raw_body2,
        headers={"Content-Type": "application/json"},
    )
    assert resp2.status_code == 200

    # Exactly one Customer row
    result = await db_session.execute(
        select(Customer).where(Customer.messenger_user_id == SAMPLE_SENDER_ID)
    )
    customers = result.scalars().all()
    assert len(customers) == 1, f"Expected 1 customer, got {len(customers)}"

    # Two ConversationLog rows
    result = await db_session.execute(
        select(ConversationLog).where(
            ConversationLog.messenger_user_id == SAMPLE_SENDER_ID,
            ConversationLog.speaker == "User",
        ).order_by(ConversationLog.id)
    )
    logs = result.scalars().all()
    assert len(logs) == 2, f"Expected 2 conversation logs, got {len(logs)}"
    assert logs[0].message_text == "First message"
    assert logs[1].message_text == "Second message"


@pytest.mark.asyncio
async def test_webhook_post_with_valid_signature(client: httpx.AsyncClient):
    """POST /api/v1/webhook with correct X-Hub-Signature-256 → 200."""
    secret = "test_app_secret_123"
    settings.META_APP_SECRET = secret

    raw_body = _sample_payload()
    sig = _compute_signature(raw_body, secret)

    response = await client.post(
        "/api/v1/webhook",
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": sig,
        },
    )
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    assert response.json() == {"status": "EVENT_RECEIVED"}

    # Reset for other tests
    settings.META_APP_SECRET = ""


@pytest.mark.asyncio
async def test_webhook_post_with_invalid_signature(client: httpx.AsyncClient):
    """POST /api/v1/webhook with wrong X-Hub-Signature-256 → 403 + INVALID_SIGNATURE."""
    secret = "test_app_secret_123"
    settings.META_APP_SECRET = secret

    raw_body = _sample_payload()
    wrong_sig = "sha256=0000000000000000000000000000000000000000000000000000000000000000"

    response = await client.post(
        "/api/v1/webhook",
        content=raw_body,
        headers={
            "Content-Type": "application/json",
            "X-Hub-Signature-256": wrong_sig,
        },
    )
    assert response.status_code == 403, f"Expected 403, got {response.status_code}: {response.text}"
    body = response.json()
    assert body["success"] is False
    assert body["error"]["code"] == "INVALID_SIGNATURE"

    # Reset for other tests
    settings.META_APP_SECRET = ""


# ---------------------------------------------------------------------------
# Unit-style test for verify_signature
# ---------------------------------------------------------------------------


class TestVerifySignature:
    def test_valid_signature(self):
        body = b'{"test": "payload"}'
        secret = "my_secret"
        sig = _compute_signature(body, secret)
        assert verify_signature(body, sig, secret) is True

    def test_missing_header(self):
        assert verify_signature(b"body", None, "secret") is False

    def test_empty_header(self):
        assert verify_signature(b"body", "", "secret") is False

    def test_malformed_header(self):
        assert verify_signature(b"body", "not-sha256-format", "secret") is False

    def test_wrong_signature(self):
        body = b'{"test": "payload"}'
        secret = "my_secret"
        wrong_sig = "sha256=abcdef1234567890abcdef1234567890abcdef1234567890abcdef1234567890"
        assert verify_signature(body, wrong_sig, secret) is False

    def test_constant_time_comparison(self):
        """Verify that a valid signature passes (indirectly tests compare_digest)."""
        body = b"constant_time_test"
        secret = "constant_secret"
        sig = _compute_signature(body, secret)
        assert verify_signature(body, sig, secret) is True
        # Tampered signature
        assert verify_signature(body, sig + "x", secret) is False
