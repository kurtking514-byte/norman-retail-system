"""
Phase 5 integration tests for AI Reply & Messenger Send API.
(Updated for Phase 9 — now uses DeepSeek instead of Gemini.)

Covers:
- ``generate_reply``: normal product question, handoff keywords, DeepSeek API
  errors, context excludes cost_price.
- ``send_message``: dev-mode skip when token is unset.
- Full webhook integration: User + Bot rows, notification_queue on handoff.

All DeepSeek and Send API calls are mocked — no real network requests are made.
"""

import json
import os

# ---------------------------------------------------------------------------
# Environment setup – must happen *before* any app imports
# ---------------------------------------------------------------------------
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-phase5-testing")
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
import pytest_asyncio  # noqa: E402
from httpx import ASGITransport  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.main import app  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.database import async_session_factory  # noqa: E402
from app.models.customer import Customer  # noqa: E402
from app.models.notification import ConversationLog, NotificationQueue  # noqa: E402
from app.models.product import Brand, Category, Product  # noqa: E402
from app.models.business import FAQ  # noqa: E402
from app.schemas.ai_response import AIReplyResult  # noqa: E402

# ---------------------------------------------------------------------------
# Test helpers
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


async def _seed_test_data():
    """Seed a product and FAQ that the tests can query."""
    session = async_session_factory()
    try:
        # Ensure brand_id=1 and category_id=1 exist
        result = await session.execute(select(Brand).where(Brand.id == 1))
        if not result.scalar_one_or_none():
            session.add(Brand(id=1, name="Default Brand"))
            await session.commit()

        result = await session.execute(select(Category).where(Category.id == 1))
        if not result.scalar_one_or_none():
            session.add(Category(id=1, name="Default Category"))
            await session.commit()

        # Insert a test product (if not already present)
        result = await session.execute(
            select(Product).where(Product.model_number == "TEST-S23-ULTRA")
        )
        if not result.scalar_one_or_none():
            session.add(
                Product(
                    brand_id=1,
                    category_id=1,
                    name="Samsung Galaxy S23 Ultra",
                    model_number="TEST-S23-ULTRA",
                    description="Flagship phone with 200MP camera",
                    cost_price=45000.00,
                    selling_price=54999.00,
                    is_active=True,
                )
            )
            await session.commit()

        # Insert a test FAQ
        result = await session.execute(
            select(FAQ).where(FAQ.question == "Do you offer warranty?")
        )
        if not result.scalar_one_or_none():
            session.add(
                FAQ(
                    question="Do you offer warranty?",
                    answer="Yes, all our phones come with a 12-month warranty.",
                    category="General",
                )
            )
            await session.commit()

    finally:
        await session.close()


async def _cleanup_test_data():
    """Remove test rows by SAMPLE_SENDER_ID."""
    session = async_session_factory()
    try:
        await session.execute(
            NotificationQueue.__table__.delete().where(
                NotificationQueue.recipient_id == SAMPLE_SENDER_ID
            )
        )
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


# ---------------------------------------------------------------------------
# Phase-5-specific seed data — tables already created by conftest's setup_db.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session", autouse=True)
def seed_phase5_data():
    """Seed default data needed by Phase 5 tests."""
    asyncio.run(_seed_test_data())
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
async def cleanup_test_data():
    """Auto-run before each test to clean up test-specific rows."""
    await _cleanup_test_data()
    yield
    await _cleanup_test_data()


# ---------------------------------------------------------------------------
# Mocks
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def mock_deepseek_api(monkeypatch):
    """Mock the DeepSeek API HTTP call so no real API call is made.

    Intercepts httpx.AsyncClient.post to api.deepseek.com and returns
    a simulated response.
    """

        # Set a fake API key so the DeepSeek service passes its API key check
    # and reaches the HTTP mock below.
    monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", "fake-deepseek-api-key-for-testing")

    original_post = httpx.AsyncClient.post

    async def _mock_httpx_post(self, url, *args, **kwargs):
        if "api.deepseek.com" in str(url):
            # Determine response based on content
            body = kwargs.get("json", {})
            messages = body.get("messages", [])
            user_text = ""
            for msg in messages:
                if msg.get("role") == "user" and isinstance(msg.get("content"), str):
                    user_text = msg["content"]

            full_text = user_text.lower()
            if "refund" in full_text or "complaint" in full_text:
                content = "[UNCERTAIN] I'm not confident about this. Could you ask about our products?"
            else:
                content = (
                    "Our Samsung Galaxy S23 Ultra is available for ₱54,999.00! "
                    "It has a 200MP camera and comes with a 12-month warranty. "
                    "Would you like to know more?"
                )

            return httpx.Response(
                status_code=200,
                request=httpx.Request("POST", url),
                json={
                    "id": "mock-deepseek-response",
                    "object": "chat.completion",
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": content,
                            },
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 100,
                        "completion_tokens": 50,
                        "total_tokens": 150,
                    },
                },
            )
        return await original_post(self, url, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "post", _mock_httpx_post)


@pytest.fixture(autouse=True)
def mock_send_api(monkeypatch):
    """Mock ``send_api_service.send_message`` so no real HTTP call is made.

    Always returns True (simulating successful send, or dev-mode skip).
    """

    async def _mock_send_message(recipient_id: str, message_text: str) -> bool:
        return True

    monkeypatch.setattr(
        "app.services.send_api_service.send_message", _mock_send_message
    )


# ---------------------------------------------------------------------------
# Helper to test context excludes cost_price
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def mock_send_api_check_http(monkeypatch):
    """An additional mock that tracks whether httpx was ever called.

    This is used in test_send_message_dev_mode_skips_http to assert no real
    HTTP call was made.
    """
    # We track via a separate fixture the call to httpx.AsyncClient.post
    original_post = httpx.AsyncClient.post

    call_count = 0

    async def tracking_post(self, url, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        # If it looks like a Graph API call, raise
        if "graph.facebook.com" in str(url):
            raise RuntimeError(f"Real HTTP call to {url} should not happen")
        return await original_post(self, url, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "post", tracking_post)

    # Store the counter on the module so tests can read it
    yield
    # We don't need to check here; tests check the counter via a flag


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_reply_normal_product_question(db_session):
    """A normal product question returns a non-handoff reply with context."""
    from app.services.deepseek_service import generate_reply

    result = await generate_reply(
        db_session,
        customer_message="How much is the Samsung Galaxy S23 Ultra?",
        conversation_history=[],
    )

    assert isinstance(result, AIReplyResult)
    assert result.needs_human_handoff is False, (
        f"Expected no handoff, got handoff_reason={result.handoff_reason}"
    )
    assert result.reply_text, "reply_text should be non-empty"
    assert len(result.reply_text) > 10, "reply_text seems too short"


@pytest.mark.asyncio
async def test_context_excludes_cost_price(db_session):
    """The grounding context passed to DeepSeek does NOT contain cost_price values."""
    from app.services.deepseek_service import build_shop_context

    context = await build_shop_context(db_session)

    # The seeded product has cost_price=45000.00 — this value must NOT appear
    assert "45000" not in context, (
        "Cost price value appeared in shop context — "
        "build_shop_context must exclude cost_price"
    )

    # But selling_price (54999.00) SHOULD appear
    assert "54999" in context or "54,999" in context, (
        "Selling price should appear in shop context"
    )

    # Product name should be present
    assert "Samsung Galaxy S23 Ultra" in context


@pytest.mark.asyncio
async def test_generate_reply_refund_triggers_handoff(db_session):
    """A message containing 'refund' triggers handoff."""
    from app.services.deepseek_service import generate_reply

    result = await generate_reply(
        db_session,
        customer_message="I want a refund, this product is terrible!",
        conversation_history=[],
    )

    assert result.needs_human_handoff is True
    assert result.handoff_reason is not None
    assert "refund" in result.handoff_reason.lower() or "keyword" in result.handoff_reason.lower()
    assert result.reply_text is not None
    assert len(result.reply_text) > 0


@pytest.mark.asyncio
async def test_generate_reply_deepseek_exception(db_session, monkeypatch):
    """If DeepSeek API raises, function catches and returns handoff fallback."""
    from app.services.deepseek_service import generate_reply

    async def _mock_post_raises(self, url, *args, **kwargs):
        if "api.deepseek.com" in str(url):
            raise RuntimeError("Simulated DeepSeek API failure")
        return await original_post(self, url, *args, **kwargs)

    original_post = httpx.AsyncClient.post
    monkeypatch.setattr(httpx.AsyncClient, "post", _mock_post_raises)

    result = await generate_reply(
        db_session,
        customer_message="What's the price of S23 Ultra?",
        conversation_history=[],
    )

    assert result.needs_human_handoff is True
    assert result.handoff_reason is not None
    assert "error" in result.handoff_reason.lower() or "deepseek" in result.handoff_reason.lower()
    assert result.reply_text is not None
    assert len(result.reply_text) > 0


@pytest.mark.asyncio
async def test_send_message_dev_mode_skips_http(monkeypatch):
    """send_message with empty MESSENGER_PAGE_ACCESS_TOKEN skips HTTP call."""
    from app.services.send_api_service import send_message

    # Ensure token is empty
    old_token = settings.MESSENGER_PAGE_ACCESS_TOKEN
    settings.MESSENGER_PAGE_ACCESS_TOKEN = ""

    # Track whether httpx.AsyncClient.post was called with a Graph API URL
    call_log = []

    original_post = httpx.AsyncClient.post

    async def tracking_post(self, url, *args, **kwargs):
        call_log.append(str(url))
        return await original_post(self, url, *args, **kwargs)

    monkeypatch.setattr(httpx.AsyncClient, "post", tracking_post)

    try:
        result = await send_message(
            recipient_id=SAMPLE_SENDER_ID,
            message_text="Hello from test!",
        )

        assert result is True, "send_message should return True in dev mode"
        # No HTTP call should have been made to Graph API
        graph_calls = [u for u in call_log if "graph.facebook.com" in u]
        assert len(graph_calls) == 0, (
            f"Expected no Graph API calls, got {len(graph_calls)}: {graph_calls}"
        )
    finally:
        settings.MESSENGER_PAGE_ACCESS_TOKEN = old_token


@pytest.mark.asyncio
async def test_full_webhook_integration(client, db_session):
    """Full webhook POST: User + Bot rows created in conversation_logs.

    This tests the full pipeline end-to-end with mocked DeepSeek + Send API.
    """
    settings.META_APP_SECRET = ""
    settings.STAFF_HANDOFF_ENABLED = True

    raw_body = _sample_payload(text="How much is the Samsung Galaxy S23 Ultra?")
    response = await client.post(
        "/api/v1/webhook",
        content=raw_body,
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 200

    # Verify Customer row
    result = await db_session.execute(
        select(Customer).where(Customer.messenger_user_id == SAMPLE_SENDER_ID)
    )
    customer = result.scalar_one_or_none()
    assert customer is not None, "Customer should exist"

    # Verify both User and Bot rows in conversation_logs
    result = await db_session.execute(
        select(ConversationLog)
        .where(ConversationLog.messenger_user_id == SAMPLE_SENDER_ID)
        .order_by(ConversationLog.id)
    )
    logs = result.scalars().all()

    speakers = [log.speaker for log in logs]
    assert "User" in speakers, "Should have a User log"
    assert "Bot" in speakers, "Should have a Bot log"

    # At least 2 rows
    assert len(logs) >= 2, f"Expected at least 2 log rows, got {len(logs)}"


@pytest.mark.asyncio
async def test_full_webhook_handoff_creates_notification(client, db_session):
    """A handoff-triggering message creates a notification_queue row."""
    settings.META_APP_SECRET = ""
    settings.STAFF_HANDOFF_ENABLED = True

    raw_body = _sample_payload(text="I want a refund, this is a scam!")
    response = await client.post(
        "/api/v1/webhook",
        content=raw_body,
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 200

    # Verify notification_queue row was created
    result = await db_session.execute(
        select(NotificationQueue)
        .where(NotificationQueue.recipient_id == SAMPLE_SENDER_ID)
        .where(NotificationQueue.status == "Pending")
    )
    nq_rows = result.scalars().all()
    assert len(nq_rows) >= 1, (
        f"Expected at least 1 notification_queue row with status=Pending, "
        f"got {len(nq_rows)}"
    )

    # Verify the channel is Dashboard
    assert nq_rows[0].channel == "Dashboard"
    # Verify the payload contains a reason
    payload = nq_rows[0].payload
    assert payload is not None
    assert "reason" in payload, "Payload should contain a handoff reason"


@pytest.mark.asyncio
async def test_staff_handoff_disabled_no_bot_reply(client, db_session):
    """When STAFF_HANDOFF_ENABLED=False, no Bot reply is generated."""
    settings.META_APP_SECRET = ""
    settings.STAFF_HANDOFF_ENABLED = False

    raw_body = _sample_payload(text="How much is the S23 Ultra?")
    response = await client.post(
        "/api/v1/webhook",
        content=raw_body,
        headers={"Content-Type": "application/json"},
    )
    assert response.status_code == 200

    # Only User row, no Bot row
    result = await db_session.execute(
        select(ConversationLog)
        .where(ConversationLog.messenger_user_id == SAMPLE_SENDER_ID)
        .order_by(ConversationLog.id)
    )
    logs = result.scalars().all()
    speakers = [log.speaker for log in logs]
    assert "User" in speakers
    assert "Bot" not in speakers, "Bot reply should not exist when STAFF_HANDOFF_ENABLED=False"
    assert len(logs) == 1, f"Expected only 1 log row, got {len(logs)}"


@pytest.mark.asyncio
async def test_unsupported_topic_triggers_handoff(db_session):
    """Asking about repair status triggers handoff (unsupported feature)."""
    from app.services.deepseek_service import generate_reply

    result = await generate_reply(
        db_session,
        customer_message="What's the status of my repair?",
        conversation_history=[],
    )

    assert result.needs_human_handoff is True
    assert result.handoff_reason is not None
    assert "repair" in result.handoff_reason.lower() or "unsupported" in result.handoff_reason.lower()
