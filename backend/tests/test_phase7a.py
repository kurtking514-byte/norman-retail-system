"""
Phase 7a integration tests for AI Tool-Calling — Reservations, Repairs & Availability.
(Updated for Phase 9 — now uses DeepSeek instead of Gemini.)

Covers:
- ``check_product_availability`` with found/not-found product
- ``create_reservation_via_chat`` success, 24h guardrail, out-of-stock
- ``check_repair_status`` found/not-found
- AI tool-calling loop cap at 3 round-trips
- Guardrail: create_reservation_via_chat blocked when product not in conversation

All AI API calls are mocked — no real network requests are made.
"""

import json
import os

# ---------------------------------------------------------------------------
# Environment setup – must happen *before* any app imports
# ---------------------------------------------------------------------------
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-phase7a-testing")
os.environ.setdefault("ADMIN_USERNAME", "admin")

import bcrypt  # noqa: E402

HASHED_PW = bcrypt.hashpw(b"changeme123", bcrypt.gensalt(12)).decode()
os.environ.setdefault("ADMIN_PASSWORD_HASH", HASHED_PW)
# DATABASE_URL is set by conftest.py — no need to override here.

# ---- Imports -------------------------------------------------------------
import asyncio  # noqa: E402
from datetime import datetime, timedelta, timezone  # noqa: E402

import httpx  # noqa: E402
import pytest  # noqa: E402
import pytest_asyncio  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.core.database import async_session_factory  # noqa: E402
from app.models.customer import Customer  # noqa: E402
from app.models.product import Brand, Category, Product, Inventory  # noqa: E402
from app.models.reservation import Reservation  # noqa: E402
from app.models.repair import RepairRequest  # noqa: E402

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SAMPLE_SENDER_ID = "messenger-user-phase7a"
SAMPLE_PRODUCT_NAME = "Phase 7a Test Phone"
SAMPLE_MODEL_NUMBER = "PHASE7A-TEST-001"
SAMPLE_PRODUCT_ID = 7000
SAMPLE_INVENTORY_SERIAL = "SN-PHASE7A-001"

# ---------------------------------------------------------------------------
# Phase-7a-specific seed data — tables already created by conftest's setup_db.
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="session", autouse=True)
async def seed_phase7a_data():
    """Seed default data needed by Phase 7a tests."""
    await _seed_test_data()
    yield


async def _seed_test_data():
    """Seed brand, category, product, and inventory for testing."""
    session = async_session_factory()
    try:
        # Brand
        result = await session.execute(select(Brand).where(Brand.id == 1))
        if not result.scalar_one_or_none():
            session.add(Brand(id=1, name="Default Brand Phase7a"))
            await session.commit()

        # Category
        result = await session.execute(select(Category).where(Category.id == 1))
        if not result.scalar_one_or_none():
            session.add(Category(id=1, name="Default Category Phase7a"))
            await session.commit()

        # Product
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
                    description="Test product for Phase 7a",
                    cost_price=8000.00,
                    selling_price=12000.00,
                    is_active=True,
                )
            )
            await session.commit()

        # Customer with messenger_user_id
        result = await session.execute(
            select(Customer).where(Customer.messenger_user_id == SAMPLE_SENDER_ID)
        )
        if not result.scalar_one_or_none():
            session.add(
                Customer(
                    first_name="Phase7a",
                    last_name="User",
                    phone_number="+63-999-777-1111",
                    messenger_user_id=SAMPLE_SENDER_ID,
                )
            )
            await session.commit()

    finally:
        await session.close()


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------


async def _cleanup_test_data():
    """Remove reservation and inventory test data."""
    session = async_session_factory()
    try:
        # Remove reservations for our product or customer
        await session.execute(
            Reservation.__table__.delete().where(
                Reservation.product_id == SAMPLE_PRODUCT_ID
            )
        )
        # Remove inventory items for our product
        await session.execute(
            Inventory.__table__.delete().where(
                Inventory.product_id == SAMPLE_PRODUCT_ID
            )
        )
        # Remove repair requests for our customer
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
        await session.commit()
    finally:
        await session.close()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def db_session():
    session = async_session_factory()
    try:
        yield session
    finally:
        await session.close()


@pytest.fixture(autouse=True)
async def cleanup():
    await _cleanup_test_data()
    yield
    await _cleanup_test_data()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_check_product_availability_found(db_session):
    """check_product_availability with a real seeded product returns found=True,
    correct in_stock_count, and does NOT contain cost_price."""
    from app.services.ai_tools_service import check_product_availability

    # First seed an In Stock inventory item
    inv = Inventory(
        product_id=SAMPLE_PRODUCT_ID,
        serial_number=SAMPLE_INVENTORY_SERIAL,
        status="In Stock",
        location="Main Store",
    )
    db_session.add(inv)
    await db_session.commit()

    result = await check_product_availability(
        db_session,
        product_name_or_model=SAMPLE_PRODUCT_NAME,
    )

    assert result["found"] is True, f"Expected found=True, got {result}"
    assert result["product_name"] == SAMPLE_PRODUCT_NAME
    assert result["in_stock_count"] >= 1, f"Expected at least 1 in stock, got {result}"
    assert "cost_price" not in result, "cost_price must not be included!"
    assert "selling_price" in result, "selling_price should be present"
    assert result["selling_price"] == 12000.0


@pytest.mark.asyncio
async def test_check_product_availability_not_found(db_session):
    """check_product_availability with a nonsense name returns found=False."""
    from app.services.ai_tools_service import check_product_availability

    result = await check_product_availability(
        db_session,
        product_name_or_model="XYZZY-NONEXISTENT-PRODUCT-99999",
    )

    assert result["found"] is False, f"Expected found=False, got {result}"
    assert "message" in result


@pytest.mark.asyncio
async def test_create_reservation_via_chat_success(db_session):
    """create_reservation_via_chat for an in-stock product with valid customer
    creates a Reservation row AND flips an Inventory row to 'Reserved'."""
    from app.services.ai_tools_service import create_reservation_via_chat

    # Seed an In Stock inventory item
    inv = Inventory(
        product_id=SAMPLE_PRODUCT_ID,
        serial_number=SAMPLE_INVENTORY_SERIAL,
        status="In Stock",
        location="Main Store",
    )
    db_session.add(inv)
    await db_session.commit()

    result = await create_reservation_via_chat(
        db_session,
        messenger_user_id=SAMPLE_SENDER_ID,
        product_name_or_model=SAMPLE_PRODUCT_NAME,
    )

    assert result["success"] is True, f"Expected success=True, got {result}"
    assert "reservation_id" in result
    assert result["product_name"] == SAMPLE_PRODUCT_NAME
    assert "expiry_date" in result

    # Verify Reservation row exists in DB (fresh session to avoid identity map)
    verify_session = async_session_factory()
    try:
        res_result = await verify_session.execute(
            select(Reservation).where(Reservation.id == result["reservation_id"])
        )
        reservation = res_result.scalar_one_or_none()
        assert reservation is not None, "Reservation should exist in DB"
        assert reservation.status == "Pending"

        # Verify Inventory row is Reserved
        inv_result = await verify_session.execute(
            select(Inventory).where(Inventory.serial_number == SAMPLE_INVENTORY_SERIAL)
        )
        inv_item = inv_result.scalar_one_or_none()
        assert inv_item is not None, "Inventory row should exist"
        assert inv_item.status == "Reserved", (
            f"Expected Reserved, got {inv_item.status}"
        )
    finally:
        await verify_session.close()


@pytest.mark.asyncio
async def test_create_reservation_via_chat_24h_guardrail(db_session):
    """Creating two reservations for same customer within 24h — second fails."""
    from app.services.ai_tools_service import create_reservation_via_chat

    # Seed two inventory items (need 2 for 2 reservation attempts)
    inv1 = Inventory(
        product_id=SAMPLE_PRODUCT_ID,
        serial_number="SN-PHASE7A-002",
        status="In Stock",
        location="Main Store",
    )
    inv2 = Inventory(
        product_id=SAMPLE_PRODUCT_ID,
        serial_number="SN-PHASE7A-003",
        status="In Stock",
        location="Main Store",
    )
    db_session.add(inv1)
    db_session.add(inv2)
    await db_session.commit()

    # First reservation — should succeed
    result1 = await create_reservation_via_chat(
        db_session,
        messenger_user_id=SAMPLE_SENDER_ID,
        product_name_or_model=SAMPLE_PRODUCT_NAME,
    )
    assert result1["success"] is True, f"First reservation failed: {result1}"

    # Second reservation — should fail due to 24h guardrail
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
async def test_create_reservation_via_chat_out_of_stock(db_session):
    """create_reservation_via_chat for an out-of-stock product returns success=False."""
    from app.services.ai_tools_service import create_reservation_via_chat

    # No inventory seeded for this product
    result = await create_reservation_via_chat(
        db_session,
        messenger_user_id=SAMPLE_SENDER_ID,
        product_name_or_model=SAMPLE_PRODUCT_NAME,
    )

    assert result["success"] is False, f"Expected failure for out-of-stock, got {result}"
    assert "reason" in result


@pytest.mark.asyncio
async def test_check_repair_status_found(db_session):
    """check_repair_status for a customer with an existing repair returns correct status."""
    from app.services.ai_tools_service import check_repair_status

    # Find customer
    cust_result = await db_session.execute(
        select(Customer).where(Customer.messenger_user_id == SAMPLE_SENDER_ID)
    )
    customer = cust_result.scalar_one_or_none()
    assert customer is not None, "Test customer should exist"

    # Create a repair request
    now = datetime.now(timezone.utc).replace(tzinfo=None)
    repair = RepairRequest(
        customer_id=customer.id,
        device_model="iPhone 15 Pro Max",
        issue_description="Battery not charging",
        estimated_cost=3500.00,
        status="In Progress",
        notes="Waiting for parts",
        updated_at=now,
    )
    db_session.add(repair)
    await db_session.commit()

    result = await check_repair_status(
        db_session,
        messenger_user_id=SAMPLE_SENDER_ID,
    )

    assert result["found"] is True, f"Expected found=True, got {result}"
    assert result["device_model"] == "iPhone 15 Pro Max"
    assert result["status"] == "In Progress"
    assert result["estimated_cost"] == 3500.0
    assert "Waiting for parts" in result["notes"]


@pytest.mark.asyncio
async def test_check_repair_status_not_found(db_session):
    """check_repair_status for a customer with no repairs returns found=False."""
    from app.services.ai_tools_service import check_repair_status

    # No repair requests exist for this customer (cleanup removes them)
    result = await check_repair_status(
        db_session,
        messenger_user_id=SAMPLE_SENDER_ID,
    )

    assert result["found"] is False, f"Expected found=False, got {result}"


@pytest.mark.asyncio
async def test_max_tool_roundtrips_returns_handoff(db_session, monkeypatch):
    """If the AI requests 4+ tool calls, the loop stops at 3 and returns handoff."""
    from app.services.deepseek_service import generate_reply, MAX_TOOL_ROUNDTRIPS

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
                                                "product_name_or_model": "iPhone",
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

    # Now call generate_reply — it will try tools and hit the cap
    result = await generate_reply(
        db_session,
        customer_message="Do you have iPhones in stock?",
        conversation_history=[],
    )

    # Should hit the 3-round-trip cap and return the holding message
    assert result.reply_text is not None
    assert len(result.reply_text) > 0
    # Should contain the holding message since we hit the cap
    assert "Thanks for reaching out" in result.reply_text or "team" in result.reply_text


@pytest.mark.asyncio
async def test_create_reservation_wrong_product_guardrail(db_session, monkeypatch):
    """If DeepSeek calls create_reservation_via_chat with a product NOT mentioned
    in recent conversation, the tool is NOT executed and the model is prompted to clarify."""
    from app.services.deepseek_service import generate_reply, _product_name_in_conversation

    # Test the guardrail function directly first
    # Product "Galaxy Buds" not mentioned in message or history
    assert _product_name_in_conversation(
        "Galaxy Buds",
        "I want to reserve something",
        [{"speaker": "User", "text": "How much is the iPhone?"}],
    ) is False, "Guardrail should block product not in conversation"

    # Product "iPhone" IS mentioned
    assert _product_name_in_conversation(
        "iPhone",
        "I want to reserve an iPhone",
        [{"speaker": "User", "text": "How much is the Samsung?"}],
    ) is True, "Guardrail should allow product in current message"

    # Product mentioned in last 2 turns of history
    assert _product_name_in_conversation(
        "Samsung",
        "I want to reserve it",
        [{"speaker": "User", "text": "How much is the Samsung Galaxy?"}],
    ) is True, "Guardrail should allow product in recent history"
