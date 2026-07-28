"""
Phase 6 integration tests for Reservations & Repair Request endpoints.

Covers:
- Auth protection (401 without token)
- OUT_OF_STOCK validation
- Successful reservation creation with inventory hold
- Dual-customer-mode validation (both/neither → 422)
- Status transitions: Cancelled → release, Claimed → Sold
- Auto-expiry on GET
- Repair CRUD and invalid status validation
"""

import json
import os

# ---------------------------------------------------------------------------
# Environment setup – must happen *before* any app imports
# ---------------------------------------------------------------------------
os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-for-phase6-testing")
os.environ.setdefault("ADMIN_USERNAME", "admin")

import bcrypt  # noqa: E402

HASHED_PW = bcrypt.hashpw(b"changeme123", bcrypt.gensalt(12)).decode()
os.environ.setdefault("ADMIN_PASSWORD_HASH", HASHED_PW)
# DATABASE_URL is set by conftest.py — no need to override here.
os.environ.setdefault("META_APP_SECRET", "")

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
from app.models.product import Brand, Category, Product, Inventory  # noqa: E402
from app.models.reservation import Reservation  # noqa: E402
from app.models.repair import RepairRequest  # noqa: E402

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

TEST_PHONE = "+63-999-888-7777"
TEST_PRODUCT_ID = 1000  # Will be created in seed
TEST_INVENTORY_SERIAL = "SN-PHASE6-001"
AUTH_HEADER = None  # Set in fixture


async def _get_token(client: httpx.AsyncClient) -> str:
    """Log in as admin and return the Bearer token."""
    resp = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "changeme123"},
    )
    assert resp.status_code == 200, f"Login failed: {resp.text}"
    return resp.json()["access_token"]


async def _seed_test_data():
    """Seed a brand, category, product, and one inventory row."""
    session = async_session_factory()
    try:
        # Brand
        result = await session.execute(select(Brand).where(Brand.id == 1))
        if not result.scalar_one_or_none():
            session.add(Brand(id=1, name="Default Brand Phase6"))
            await session.commit()

        # Category
        result = await session.execute(select(Category).where(Category.id == 1))
        if not result.scalar_one_or_none():
            session.add(Category(id=1, name="Default Category Phase6"))
            await session.commit()

        # Product
        result = await session.execute(
            select(Product).where(Product.model_number == "PHASE6-TEST-100")
        )
        product = result.scalar_one_or_none()
        if product is None:
            product = Product(
                id=TEST_PRODUCT_ID,
                brand_id=1,
                category_id=1,
                name="Phase 6 Test Phone",
                model_number="PHASE6-TEST-100",
                description="Test product for Phase 6",
                cost_price=10000.00,
                selling_price=15000.00,
                is_active=True,
            )
            session.add(product)
            await session.commit()
            await session.refresh(product)

        # Inventory – one In Stock row
        result = await session.execute(
            select(Inventory).where(
                Inventory.serial_number == TEST_INVENTORY_SERIAL
            )
        )
        if not result.scalar_one_or_none():
            inv = Inventory(
                product_id=product.id,
                serial_number=TEST_INVENTORY_SERIAL,
                status="In Stock",
                location="Main Store",
            )
            session.add(inv)
            await session.commit()

    finally:
        await session.close()


async def _cleanup_test_data():
    """Remove all test-specific rows."""
    session = async_session_factory()
    try:
        await session.execute(
            Reservation.__table__.delete().where(
                Reservation.product_id == TEST_PRODUCT_ID
            )
        )
        await session.execute(
            RepairRequest.__table__.delete().where(
                RepairRequest.customer_id.in_(
                    select(Customer.id).where(Customer.phone_number == TEST_PHONE)
                )
            )
        )
        await session.execute(
            Customer.__table__.delete().where(
                Customer.phone_number == TEST_PHONE
            )
        )
        await session.execute(
            Inventory.__table__.delete().where(
                Inventory.serial_number == TEST_INVENTORY_SERIAL
            )
        )
        await session.commit()
    finally:
        await session.close()


# ---------------------------------------------------------------------------
# Phase-6-specific seed data — tables already created by conftest's setup_db.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="session", autouse=True)
def seed_phase6_data():
    """Seed default data needed by Phase 6 tests."""
    asyncio.run(_seed_test_data())
    yield


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def db_session():
    session = async_session_factory()
    try:
        yield session
    finally:
        await session.close()


@pytest.fixture(autouse=True)
async def cleanup_test_data():
    await _cleanup_test_data()
    yield
    await _cleanup_test_data()


@pytest.fixture
async def auth_token(client):
    return await _get_token(client)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_reservation_out_of_stock(client, auth_token, db_session):
    """POST /reservations for a product with no In Stock inventory → 409 OUT_OF_STOCK."""
    # First, ensure there's no In Stock inventory for the product
    # (cleanup removes ours, but there may be seeded data from other phases).
    # Mark any existing In Stock rows for this product as Sold first.
    await db_session.execute(
        Inventory.__table__.update()
        .where(Inventory.product_id == TEST_PRODUCT_ID)
        .where(Inventory.status == "In Stock")
        .values(status="Sold")
    )
    await db_session.commit()

    # Re-seed cleanup will clean this up
    resp = await client.post(
        "/api/v1/reservations",
        json={
            "first_name": "Jane",
            "last_name": "Doe",
            "phone_number": TEST_PHONE,
            "product_id": TEST_PRODUCT_ID,
            "expiry_hours": 48,
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert resp.status_code == 409, f"Expected 409, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["error"]["code"] == "OUT_OF_STOCK", f"Wrong code: {body}"


@pytest.mark.asyncio
async def test_create_reservation_success(client, auth_token, db_session):
    """POST /reservations for an in-stock product → 201, inventory becomes Reserved."""
    # Use a fresh session to seed inventory (avoids identity-map caching)
    seed_session = async_session_factory()
    try:
        inv = Inventory(
            product_id=TEST_PRODUCT_ID,
            serial_number=TEST_INVENTORY_SERIAL,
            status="In Stock",
            location="Main Store",
        )
        seed_session.add(inv)
        await seed_session.commit()
    finally:
        await seed_session.close()

    resp = await client.post(
        "/api/v1/reservations",
        json={
            "first_name": "John",
            "last_name": "Smith",
            "phone_number": TEST_PHONE,
            "product_id": TEST_PRODUCT_ID,
            "expiry_hours": 48,
            "notes": "Test reservation",
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert resp.status_code == 201, f"Expected 201, got {resp.status_code}: {resp.text}"
    body = resp.json()
    assert body["status"] == "Pending"
    assert body["product_id"] == TEST_PRODUCT_ID
    assert body["notes"] == "Test reservation"

    # Verify inventory is Reserved (use a fresh session to avoid stale identity map)
    verify_session = async_session_factory()
    try:
        result = await verify_session.execute(
            select(Inventory).where(Inventory.serial_number == TEST_INVENTORY_SERIAL)
        )
        inv_item = result.scalar_one_or_none()
        assert inv_item is not None, "Inventory row not found"
        assert inv_item.status == "Reserved", (
            f"Expected Reserved, got {inv_item.status}"
        )
    finally:
        await verify_session.close()


@pytest.mark.asyncio
async def test_create_reservation_both_customer_modes_422(client, auth_token):
    """POST /reservations with BOTH customer_id and new-customer fields → 422."""
    resp = await client.post(
        "/api/v1/reservations",
        json={
            "customer_id": 1,
            "first_name": "John",
            "last_name": "Doe",
            "phone_number": TEST_PHONE,
            "product_id": TEST_PRODUCT_ID,
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"


@pytest.mark.asyncio
async def test_create_reservation_neither_customer_mode_422(client, auth_token):
    """POST /reservations with NEITHER customer_id nor new-customer fields → 422."""
    resp = await client.post(
        "/api/v1/reservations",
        json={
            "product_id": TEST_PRODUCT_ID,
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"


@pytest.mark.asyncio
async def test_cancel_reservation_releases_inventory(client, auth_token, db_session):
    """PUT /reservations/{id} to Cancelled → inventory reverts to In Stock."""
    # Use a fresh session to seed inventory (avoids identity-map caching)
    seed_session = async_session_factory()
    try:
        inv = Inventory(
            product_id=TEST_PRODUCT_ID,
            serial_number=TEST_INVENTORY_SERIAL,
            status="In Stock",
            location="Main Store",
        )
        seed_session.add(inv)
        await seed_session.commit()
    finally:
        await seed_session.close()

    # Create reservation
    resp = await client.post(
        "/api/v1/reservations",
        json={
            "first_name": "Cancel",
            "last_name": "Test",
            "phone_number": TEST_PHONE,
            "product_id": TEST_PRODUCT_ID,
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert resp.status_code == 201, f"Create failed: {resp.text}"
    reservation_id = resp.json()["id"]

    # Verify inventory is Reserved (fresh session)
    verify_session = async_session_factory()
    try:
        result = await verify_session.execute(
            select(Inventory).where(Inventory.serial_number == TEST_INVENTORY_SERIAL)
        )
        assert result.scalar_one().status == "Reserved"
    finally:
        await verify_session.close()

    # Cancel
    resp = await client.put(
        f"/api/v1/reservations/{reservation_id}",
        json={"status": "Cancelled"},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert resp.status_code == 200, f"Cancel failed: {resp.text}"
    assert resp.json()["status"] == "Cancelled"

    # Verify inventory is In Stock again (fresh session)
    verify_session = async_session_factory()
    try:
        result = await verify_session.execute(
            select(Inventory).where(Inventory.serial_number == TEST_INVENTORY_SERIAL)
        )
        assert result.scalar_one().status == "In Stock"
    finally:
        await verify_session.close()


@pytest.mark.asyncio
async def test_claim_reservation_sells_inventory(client, auth_token, db_session):
    """PUT /reservations/{id} to Claimed → inventory becomes Sold."""
    # Seed inventory and create a reservation
    inv = Inventory(
        product_id=TEST_PRODUCT_ID,
        serial_number=TEST_INVENTORY_SERIAL,
        status="In Stock",
        location="Main Store",
    )
    db_session.add(inv)
    await db_session.commit()

    # Create reservation
    resp = await client.post(
        "/api/v1/reservations",
        json={
            "first_name": "Claim",
            "last_name": "Test",
            "phone_number": TEST_PHONE,
            "product_id": TEST_PRODUCT_ID,
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert resp.status_code == 201, f"Create failed: {resp.text}"
    reservation_id = resp.json()["id"]

    # Claim it
    resp = await client.put(
        f"/api/v1/reservations/{reservation_id}",
        json={"status": "Claimed"},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert resp.status_code == 200, f"Claim failed: {resp.text}"
    assert resp.json()["status"] == "Claimed"

    # Verify inventory is Sold
    await db_session.refresh(inv)
    assert inv.status == "Sold", f"Expected Sold, got {inv.status}"


@pytest.mark.asyncio
async def test_expired_reservation_auto_cancels(client, auth_token, db_session):
    """Create reservation with expiry_hours=-1 → GET auto-cancels, inventory released."""
    # Seed inventory
    inv = Inventory(
        product_id=TEST_PRODUCT_ID,
        serial_number=TEST_INVENTORY_SERIAL,
        status="In Stock",
        location="Main Store",
    )
    db_session.add(inv)
    await db_session.commit()

    # Manually create an already-expired reservation (expiry in the past)
    from datetime import datetime, timedelta, timezone

    # First, create a customer
    cust = Customer(
        first_name="Expiry",
        last_name="Test",
        phone_number=TEST_PHONE,
    )
    db_session.add(cust)
    await db_session.commit()
    await db_session.refresh(cust)

    now = datetime.now(timezone.utc)
    expired_reservation = Reservation(
        customer_id=cust.id,
        product_id=TEST_PRODUCT_ID,
        reservation_date=now - timedelta(hours=1),
        expiry_date=now - timedelta(hours=1),  # Already expired
        status="Pending",
    )
    db_session.add(expired_reservation)

    # Also reserve the inventory manually
    inv.status = "Reserved"
    await db_session.commit()
    await db_session.refresh(expired_reservation)
    res_id = expired_reservation.id

    # GET /reservations should auto-cancel it
    resp = await client.get(
        "/api/v1/reservations",
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert resp.status_code == 200, f"List failed: {resp.text}"

    # Verify the X-Expired-Count header
    assert "X-Expired-Count" in resp.headers
    assert int(resp.headers["X-Expired-Count"]) >= 1

    # Verify the reservation is cancelled
    await db_session.refresh(expired_reservation)
    assert expired_reservation.status == "Cancelled", (
        f"Expected Cancelled, got {expired_reservation.status}"
    )

    # Verify inventory is back to In Stock
    await db_session.refresh(inv)
    assert inv.status == "In Stock", f"Expected In Stock, got {inv.status}"


@pytest.mark.asyncio
async def test_repair_create_and_invalid_status(client, auth_token, db_session):
    """POST /repairs creates successfully, PUT with invalid status → 422."""
    # Create repair
    resp = await client.post(
        "/api/v1/repairs",
        json={
            "first_name": "Repair",
            "last_name": "Customer",
            "phone_number": TEST_PHONE,
            "device_model": "iPhone 15 Pro",
            "issue_description": "Broken screen",
            "estimated_cost": 5000.00,
            "notes": "Urgent",
        },
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert resp.status_code == 201, f"Create failed: {resp.text}"
    body = resp.json()
    assert body["status"] == "Pending"
    assert body["device_model"] == "iPhone 15 Pro"
    assert body["estimated_cost"] == 5000.0
    repair_id = body["id"]

    # Update with invalid status
    resp = await client.put(
        f"/api/v1/repairs/{repair_id}",
        json={"status": "BogusStatus"},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert resp.status_code == 422, f"Expected 422, got {resp.status_code}: {resp.text}"

    # Update with valid status
    resp = await client.put(
        f"/api/v1/repairs/{repair_id}",
        json={"status": "In Progress"},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert resp.status_code == 200, f"Update failed: {resp.text}"
    assert resp.json()["status"] == "In Progress"


@pytest.mark.asyncio
async def test_reservations_requires_auth(client, db_session):
    """POST /reservations without auth → 401."""
    resp = await client.post(
        "/api/v1/reservations",
        json={
            "first_name": "No",
            "last_name": "Auth",
            "phone_number": TEST_PHONE,
            "product_id": TEST_PRODUCT_ID,
        },
    )
    assert resp.status_code == 401, f"Expected 401, got {resp.status_code}: {resp.text}"


@pytest.mark.asyncio
async def test_repairs_requires_auth(client, db_session):
    """POST /repairs without auth → 401."""
    resp = await client.post(
        "/api/v1/repairs",
        json={
            "first_name": "No",
            "last_name": "Auth",
            "phone_number": TEST_PHONE,
            "device_model": "Test",
            "issue_description": "Test issue",
        },
    )
    assert resp.status_code == 401, f"Expected 401, got {resp.status_code}: {resp.text}"
