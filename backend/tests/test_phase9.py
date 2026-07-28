"""
Phase 9 integration tests for DeepSeek AI Reply & Tool-Calling.

Covers:
- ``generate_reply``: normal product question, handoff keywords, DeepSeek API
  errors, context excludes cost_price.
- Tool-calling: ``check_product_availability``, ``create_reservation_via_chat``
  24-hour guardrail, 3-round-trip cap.
- Full webhook integration: User + Bot rows in conversation_logs.

All DeepSeek API calls are mocked — no real network requests are made.
"""

import json
import os

# ---------------------------------------------------------------------------
# Environment setup – must happen *before* any app imports
# ---------------------------------------------------------------------------
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-phase9-testing")
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
from app.models.business import FAQ  # noqa: E402
from app.models.reservation import Reservation  # noqa: E402
from app.models.repair import RepairRequest  # noqa: E402
from app.schemas.ai_response import AIReplyResult  # noqa: E402

# ---------------------------------------------------------------------------
# Test helpers
# ---------------------------------------------------------------------------

SAMPLE_SENDER_ID = "messenger-user-phase9"
SAMPLE_PRODUCT_NAME = "Phase 9 Test Phone"
SAMPLE_MODEL_NUMBER = "PHASE9-TEST-001"
SAMPLE_PRODUCT_ID = 9000
SAMPLE_INVENTORY_SERIAL = "SN-PHASE9-001"


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
    """Seed product, FAQ, inventory, and customer for testing."""
    session = async_session_factory()
    try:
        # Ensure brand_id=1 and category_id=1 exist
        result = await session.execute(select(Brand).where(Brand.id == 1))
        if not result.scalar_one_or_none():
            session.add(Brand(id=1, name="Default Brand Phase9"))
            await session.commit()

        result = await session.execute(select(Category).where(Category.id == 1))
        if not result.scalar_one_or_none():
            session.add(Category(id=1, name="Default Category Phase9"))
            await session.commit()

        # Insert test product (if not already present)
        result = await session.execute(
            select(Product).where(Product.model_number == SAMPLE_MODEL_NUMBER)
        )
        if not result.scalar_one_or_none():
            session.add(
                Product(
                    id=SAMPLE_PRODUCT_ID,
                    brand_id=1,
                    category_id=1,
                    name=SAMPLE_PRODUCT_NAME,
                    model_number=SAMPLE_MODEL_NUMBER,
                    description="Test product for Phase 9",
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

        # Insert customer with Phase 9 messenger_user_id
        result = await session.execute(
            select(Customer).where(Customer.messenger_user_id == SAMPLE_SENDER_ID)
        )
        if not result.scalar_one_or_none():
            session.add(
                Customer(
                    first_name="Phase9",
                    last_name="User",
                    phone_number="+63-999-111-2222",
                    messenger_user_id=SAMPLE_SENDER_ID,
                )
            )
            await session.commit()

    finally:
        await session.close()


async def _cleanup_test_data():
    """Remove test-specific rows."""
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
            Reservation.__table__.delete().where(
                Reservation.product_id == SAMPLE_PRODUCT_ID
            )
        )
        await session.execute(
            Inventory.__table__.delete().where(
                Inventory.product_id == SAMPLE_PRODUCT_ID
            )
        )
        cust_result = await session.execute(
            select(Customer.id).where(
                Customer.messenger_user_id == SAMPLE_SENDER_ID
            )
        )
        cust_id = cust_result.scalar_one_or_none()
        if cust_id:
            await session.execute(
                RepairRequest.__table__.delete().where(
                    RepairRequest.customer_id == cust_id
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
# Phase-9-specific seed data — tables already created by conftest's setup_db.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session", autouse=True)
def seed_phase9_data():
    """Seed default data needed by Phase 9 tests."""
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
    """Mock the DeepSeek HTTP API call so no real network request is made.

    Also sets a fake DEEPSEEK_API_KEY so the function passes the API key
    check and reaches the mocked HTTP call.

    Returns a normal reply for most queries, and an [UNCERTAIN] marker
    for refund/complaint messages (after passing step 1 handoff detection).
    """

    # Set a fake API key so the function passes the API key check
    monkeypatch.setattr(settings, "DEEPSEEK_API_KEY", "fake-deepseek-api-key-for-testing")

    async def _mock_httpx_post(self, url, *args, **kwargs):
        """Intercept httpx.AsyncClient.post to mock DeepSeek API responses."""
        # Only intercept DeepSeek API calls
        if "api.deepseek.com" in str(url):
            # Determine response based on content
            body = kwargs.get("json", {})
            messages = body.get("messages", [])
            user_text = ""
            for msg in messages:
                if msg.get("role") == "user" and isinstance(msg.get("content"), str):
                    user_text = msg["content"]

            full_text = user_text.lower()

            # Check if there are tool_calls in the assistant messages (ongoing tool loop)
            # For simplicity, we return a plain response
            if "refund" in full_text or "complaint" in full_text:
                content = "[UNCERTAIN] I'm not confident about this. Could you ask about our products?"
            else:
                content = (
                    "Our Phase 9 Test Phone is available for ₱54,999.00! "
                    "It comes with a 12-month warranty. "
                    "Would you like to know more?"
                )

            mock_response = httpx.Response(
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
            return mock_response

        # Fall through to actual httpx for non-DeepSeek calls
        return await original_post(self, url, *args, **kwargs)

    # Save original post
    original_post = httpx.AsyncClient.post
    monkeypatch.setattr(httpx.AsyncClient, "post", _mock_httpx_post)


@pytest.fixture(autouse=True)
def mock_send_api(monkeypatch):
    """Mock ``send_api_service.send_message`` so no real HTTP call is made."""

    async def _mock_send_message(recipient_id: str, message_text: str) -> bool:
        return True

    monkeypatch.setattr(
        "app.services.send_api_service.send_message", _mock_send_message
    )


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_generate_reply_normal_product_question(db_session):
    """A normal product question returns a non-handoff reply with context."""
    from app.services.deepseek_service import generate_reply

    result = await generate_reply(
        db_session,
        customer_message="How much is the Phase 9 Test Phone?",
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
    assert "Phase 9 Test Phone" in context


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
        customer_message="What's the price of the Phase 9 Test Phone?",
        conversation_history=[],
    )

    assert result.needs_human_handoff is True
    assert result.handoff_reason is not None
    assert "error" in result.handoff_reason.lower() or "deepseek" in result.handoff_reason.lower()
    assert result.reply_text is not None
    assert len(result.reply_text) > 0


@pytest.mark.asyncio
async def test_check_product_availability_tool_call(db_session, monkeypatch):
    """When DeepSeek responds with a tool call for check_product_availability,
    the function executes the tool and returns the result."""
    from app.services.deepseek_service import generate_reply

    # Seed inventory for the product
    inv = Inventory(
        product_id=SAMPLE_PRODUCT_ID,
        serial_number=SAMPLE_INVENTORY_SERIAL,
        status="In Stock",
        location="Main Store",
    )
    db_session.add(inv)
    await db_session.commit()

    # Mock DeepSeek to return a tool call, then a final response
    call_count = [0]  # Use list for mutable closure

    async def _mock_post_tool(self, url, *args, **kwargs):
        if "api.deepseek.com" in str(url):
            call_count[0] += 1
            if call_count[0] == 1:
                # First call: return a tool call
                return httpx.Response(
                    status_code=200,
                    request=httpx.Request("POST", url),
                    json={
                        "id": "mock-deepseek-tool",
                        "object": "chat.completion",
                        "choices": [
                            {
                                "index": 0,
                                "message": {
                                    "role": "assistant",
                                    "content": None,
                                    "tool_calls": [
                                        {
                                            "id": "call_1",
                                            "type": "function",
                                            "function": {
                                                "name": "check_product_availability",
                                                "arguments": json.dumps({
                                                    "product_name_or_model": SAMPLE_PRODUCT_NAME,
                                                }),
                                            },
                                        }
                                    ],
                                },
                                "finish_reason": "tool_calls",
                            }
                        ],
                        "usage": {
                            "prompt_tokens": 100,
                            "completion_tokens": 20,
                            "total_tokens": 120,
                        },
                    },
                )
            else:
                # Second call: return a final text response
                return httpx.Response(
                    status_code=200,
                    request=httpx.Request("POST", url),
                    json={
                        "id": "mock-deepseek-final",
                        "object": "chat.completion",
                        "choices": [
                            {
                                "index": 0,
                                "message": {
                                    "role": "assistant",
                                    "content": "The Phase 9 Test Phone is in stock with 1 unit available at ₱54,999.00!",
                                },
                                "finish_reason": "stop",
                            }
                        ],
                        "usage": {
                            "prompt_tokens": 150,
                            "completion_tokens": 30,
                            "total_tokens": 180,
                        },
                    },
                )
        return await original_post(self, url, *args, **kwargs)

    original_post = httpx.AsyncClient.post
    monkeypatch.setattr(httpx.AsyncClient, "post", _mock_post_tool)

    result = await generate_reply(
        db_session,
        customer_message="Do you have the Phase 9 Test Phone in stock?",
        conversation_history=[],
    )

    assert result.needs_human_handoff is False
    assert result.reply_text is not None
    assert len(result.reply_text) > 0
    # The response should mention stock/availability info
    assert "stock" in result.reply_text.lower() or "available" in result.reply_text.lower()


@pytest.mark.asyncio
async def test_create_reservation_24h_guardrail(db_session, monkeypatch):
    """The 24-hour guardrail for create_reservation_via_chat is still enforced."""
    from app.services.deepseek_service import generate_reply

    # Seed inventory items
    inv1 = Inventory(
        product_id=SAMPLE_PRODUCT_ID,
        serial_number="SN-PHASE9-RES-001",
        status="In Stock",
        location="Main Store",
    )
    db_session.add(inv1)
    await db_session.commit()

    # Seed customer (cleanup runs before each test and deletes the customer)
    cust = Customer(
        first_name="Phase9",
        last_name="User",
        phone_number="+63-999-111-2222",
        messenger_user_id=SAMPLE_SENDER_ID,
    )
    db_session.add(cust)
    await db_session.commit()

    call_count = [0]

    async def _mock_post_guardrail(self, url, *args, **kwargs):
        if "api.deepseek.com" in str(url):
            call_count[0] += 1
            if call_count[0] == 1:
                # First call: request a reservation
                return httpx.Response(
                    status_code=200,
                    request=httpx.Request("POST", url),
                    json={
                        "id": "mock-ds-guard-1",
                        "object": "chat.completion",
                        "choices": [
                            {
                                "index": 0,
                                "message": {
                                    "role": "assistant",
                                    "content": None,
                                    "tool_calls": [
                                        {
                                            "id": "call_res_1",
                                            "type": "function",
                                            "function": {
                                                "name": "create_reservation_via_chat",
                                                "arguments": json.dumps({
                                                    "messenger_user_id": SAMPLE_SENDER_ID,
                                                    "product_name_or_model": SAMPLE_PRODUCT_NAME,
                                                }),
                                            },
                                        }
                                    ],
                                },
                                "finish_reason": "tool_calls",
                            }
                        ],
                        "usage": {
                            "prompt_tokens": 100,
                            "completion_tokens": 20,
                            "total_tokens": 120,
                        },
                    },
                )
            else:
                # Second call: final response (tool executed, result used)
                return httpx.Response(
                    status_code=200,
                    request=httpx.Request("POST", url),
                    json={
                        "id": "mock-ds-guard-2",
                        "object": "chat.completion",
                        "choices": [
                            {
                                "index": 0,
                                "message": {
                                    "role": "assistant",
                                    "content": "Your reservation has been created.",
                                },
                                "finish_reason": "stop",
                            }
                        ],
                        "usage": {
                            "prompt_tokens": 200,
                            "completion_tokens": 20,
                            "total_tokens": 220,
                        },
                    },
                )
        return await original_post(self, url, *args, **kwargs)

    original_post = httpx.AsyncClient.post
    monkeypatch.setattr(httpx.AsyncClient, "post", _mock_post_guardrail)

    # First reservation call (no history, fresh)
    # Note: the guardrail is enforced inside ai_tools_service itself
    # (24-hour check). The mock will call the real tool function.
    # The first call should succeed since there are no prior reservations.

    # Actually, we need to test the tool directly to verify the guardrail,
    # since the mock response might not reach the tool in a way that's testable.
    # Let's use the direct tool approach for this guardrail test.

    from app.services.ai_tools_service import create_reservation_via_chat

    # First reservation — should succeed
    result1 = await create_reservation_via_chat(
        db_session,
        messenger_user_id=SAMPLE_SENDER_ID,
        product_name_or_model=SAMPLE_PRODUCT_NAME,
    )
    assert result1["success"] is True, f"First reservation failed: {result1}"

    # Second reservation (same customer, within 24h) — should fail
    result2 = await create_reservation_via_chat(
        db_session,
        messenger_user_id=SAMPLE_SENDER_ID,
        product_name_or_model=SAMPLE_PRODUCT_NAME,
    )
    assert result2["success"] is False, (
        f"Second reservation should fail due to 24h guardrail, got {result2}"
    )
    assert "reason" in result2
    assert "24 hours" in result2["reason"].lower() or "already" in result2["reason"].lower()


@pytest.mark.asyncio
async def test_max_tool_roundtrips_returns_handoff(db_session, monkeypatch):
    """If DeepSeek requests 4+ tool calls, the loop stops at 3 and returns handoff."""
    from app.services.deepseek_service import generate_reply, MAX_TOOL_ROUNDTRIPS

    # Seed inventory for the product
    inv = Inventory(
        product_id=SAMPLE_PRODUCT_ID,
        serial_number="SN-PHASE9-CAP-001",
        status="In Stock",
        location="Main Store",
    )
    db_session.add(inv)
    await db_session.commit()

    # Mock DeepSeek to ALWAYS return a tool call (so we hit the cap)
    async def _mock_post_always_tool(self, url, *args, **kwargs):
        if "api.deepseek.com" in str(url):
            return httpx.Response(
                status_code=200,
                request=httpx.Request("POST", url),
                json={
                    "id": "mock-ds-tool-loop",
                    "object": "chat.completion",
                    "choices": [
                        {
                            "index": 0,
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "call_loop",
                                        "type": "function",
                                        "function": {
                                            "name": "check_product_availability",
                                            "arguments": json.dumps({
                                                "product_name_or_model": "Phase 9 Test Phone",
                                            }),
                                        },
                                    }
                                ],
                            },
                            "finish_reason": "tool_calls",
                        }
                    ],
                    "usage": {
                        "prompt_tokens": 100,
                        "completion_tokens": 20,
                        "total_tokens": 120,
                    },
                },
            )
        return await original_post(self, url, *args, **kwargs)

    original_post = httpx.AsyncClient.post
    monkeypatch.setattr(httpx.AsyncClient, "post", _mock_post_always_tool)

    result = await generate_reply(
        db_session,
        customer_message="Do you have phones in stock?",
        conversation_history=[],
    )

    # Should hit the round-trip cap and return the holding message
    assert result.reply_text is not None
    assert len(result.reply_text) > 0
    # It should be the holding message (handoff) because we hit the cap
    assert "Thanks for reaching out" in result.reply_text or "team members" in result.reply_text


@pytest.mark.asyncio
async def test_full_webhook_integration(client, db_session):
    """Full webhook POST: User + Bot rows created in conversation_logs.

    This tests the full pipeline end-to-end with mocked DeepSeek + Send API.
    """
    settings.META_APP_SECRET = ""
    settings.STAFF_HANDOFF_ENABLED = True

    raw_body = _sample_payload(text="How much is the Phase 9 Test Phone?")
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
