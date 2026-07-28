"""
Phase 2 integration tests for Norman Cellphone Center API.

Covers authentication, product CRUD, inventory status validation,
and public endpoint data leakage prevention.

Uses a separate SQLite database file (test_norman_shop.db) that is
created at the start of the session and cleaned up after.
"""

import asyncio
import os

# ---------------------------------------------------------------------------
# Environment setup – must happen *before* any app imports so that
# pydantic-settings reads these values.  We set a JWT secret and admin
# credentials so that the test suite is self-contained and does not rely
# on a .env file existing on disk.
# ---------------------------------------------------------------------------
os.environ["JWT_SECRET_KEY"] = "test-secret-key-for-phase2-testing"
os.environ["ADMIN_USERNAME"] = "admin"

import bcrypt  # noqa: E402

HASHED_PW = bcrypt.hashpw(b"changeme123", bcrypt.gensalt(12)).decode()
os.environ["ADMIN_PASSWORD_HASH"] = HASHED_PW
# DATABASE_URL is set by conftest.py — no need to override here.

# Now it is safe to import the app – Settings() will pick up the env vars above.
import httpx  # noqa: E402
import pytest  # noqa: E402
from httpx import ASGITransport  # noqa: E402

from app.main import app  # noqa: E402
from app.core.database import async_session_factory  # noqa: E402
from app.models.product import Brand, Category  # noqa: E402

# ---------------------------------------------------------------------------
# Phase-2-specific seed data — tables already created by conftest's setup_db.
# ---------------------------------------------------------------------------


async def _seed_default_data():
    """Ensure brand_id=1 and category_id=1 exist so products can reference them."""
    session = async_session_factory()
    try:
        from sqlalchemy import select

        result = await session.execute(select(Brand).where(Brand.id == 1))
        if not result.scalar_one_or_none():
            session.add(Brand(id=1, name="Default Brand"))
        result = await session.execute(select(Category).where(Category.id == 1))
        if not result.scalar_one_or_none():
            session.add(Category(id=1, name="Default Category"))
        await session.commit()
    finally:
        await session.close()


@pytest.fixture(scope="session", autouse=True)
def seed_phase2_data():
    """Seed default data needed by Phase 2 tests."""
    asyncio.run(_seed_default_data())
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
async def admin_token(client: httpx.AsyncClient) -> str:
    """Log in as admin and return a valid JWT."""
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "changeme123"},
    )
    assert response.status_code == 200, f"Login failed: {response.text}"
    data = response.json()
    return data["access_token"]


@pytest.fixture
async def auth_headers(admin_token: str) -> dict:
    """Return Authorization headers for an authenticated admin."""
    return {"Authorization": f"Bearer {admin_token}"}


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_create_product_without_token_returns_401(client: httpx.AsyncClient):
    """POST /api/v1/products without a token → 401"""
    response = await client.post(
        "/api/v1/products",
        json={
            "name": "Broken Product",
            "model_number": "NOAUTH-001",
            "brand_id": 1,
            "category_id": 1,
            "cost_price": 100.0,
            "selling_price": 150.0,
        },
    )
    assert response.status_code == 401, f"Expected 401, got {response.status_code}: {response.text}"
    body = response.json()
    # The 401 error format from get_current_admin
    assert "success" in body
    assert body["success"] is False
    assert "error" in body


@pytest.mark.asyncio
async def test_login_valid_credentials_returns_jwt(client: httpx.AsyncClient):
    """POST /api/v1/auth/login with correct credentials → 200 + valid JWT"""
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "changeme123"},
    )
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    body = response.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"
    # A quick structural check – a JWT has two dots (three base64url segments)
    token = body["access_token"]
    assert token.count(".") == 2, f"'{token}' does not look like a JWT"


@pytest.mark.asyncio
async def test_create_product_selling_price_lte_cost_returns_422(
    client: httpx.AsyncClient,
    auth_headers: dict,
):
    """POST /api/v1/products with selling_price ≤ cost_price → 422"""
    response = await client.post(
        "/api/v1/products",
        json={
            "name": "Bad Pricing",
            "model_number": "PRICE-001",
            "brand_id": 1,
            "category_id": 1,
            "cost_price": 200.0,
            "selling_price": 150.0,  # < cost_price
        },
        headers=auth_headers,
    )
    assert response.status_code == 422, f"Expected 422, got {response.status_code}: {response.text}"
    body = response.json()
    assert body["success"] is False
    assert "selling_price" in str(body).lower() or "greater than" in str(body)


@pytest.mark.asyncio
async def test_create_product_duplicate_model_number_returns_409(
    client: httpx.AsyncClient,
    auth_headers: dict,
):
    """POST /api/v1/products with a duplicate model_number → 409"""
    model_number = "DUP-MODEL-001"

    # Clean up any leftover row from a previous run
    from app.core.database import async_session_factory
    import sqlalchemy as sa
    _s = async_session_factory()
    try:
        await _s.execute(sa.text("DELETE FROM products WHERE model_number = :mn"), {"mn": model_number})
        await _s.commit()
    finally:
        await _s.close()

    # First creation should succeed
    resp1 = await client.post(
        "/api/v1/products",
        json={
            "name": "Original",
            "model_number": model_number,
            "brand_id": 1,
            "category_id": 1,
            "cost_price": 100.0,
            "selling_price": 150.0,
        },
        headers=auth_headers,
    )
    assert resp1.status_code == 201, f"First insert failed: {resp1.text}"

    # Second creation with same model_number → 409
    resp2 = await client.post(
        "/api/v1/products",
        json={
            "name": "Duplicate",
            "model_number": model_number,
            "brand_id": 1,
            "category_id": 1,
            "cost_price": 110.0,
            "selling_price": 160.0,
        },
        headers=auth_headers,
    )
    assert resp2.status_code == 409, f"Expected 409, got {resp2.status_code}: {resp2.text}"
    body = resp2.json()
    assert body["success"] is False
    assert "DUPLICATE_MODEL_NUMBER" in str(body) or "already exists" in str(body)


@pytest.mark.asyncio
async def test_public_products_never_leak_cost_price(
    client: httpx.AsyncClient,
    auth_headers: dict,
):
    """GET /api/v1/products/public → cost_price must NOT appear anywhere in JSON keys."""
    # Clean up any leftover row from a previous run
    from app.core.database import async_session_factory
    import sqlalchemy as sa
    _s = async_session_factory()
    try:
        await _s.execute(sa.text("DELETE FROM products WHERE model_number = 'PUBLIC-001'"))
        await _s.commit()
    finally:
        await _s.close()

    # Arrange: insert a product first so there is data to return.
    resp = await client.post(
        "/api/v1/products",
        json={
            "name": "Public Test Phone",
            "model_number": "PUBLIC-001",
            "brand_id": 1,
            "category_id": 1,
            "cost_price": 300.0,
            "selling_price": 499.99,
        },
        headers=auth_headers,
    )
    assert resp.status_code == 201, f"Create failed: {resp.text}"

    # Act
    response = await client.get("/api/v1/products/public")
    assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"

    # Assert
    raw_json = response.text
    assert "cost_price" not in raw_json, (
        f"cost_price leaked in public endpoint response: {raw_json[:500]}"
    )
    # Also verify selling_price is present
    assert "selling_price" in raw_json, "selling_price should be present in public response"
    body = response.json()
    if body:
        assert "cost_price" not in body[0], "cost_price key found in response objects"
        assert "selling_price" in body[0], "selling_price key missing from response objects"


@pytest.mark.asyncio
async def test_update_inventory_status_invalid_returns_422(
    client: httpx.AsyncClient,
    auth_headers: dict,
):
    """PATCH /api/v1/inventory/{id}/status with an invalid status → 422"""
    # Clean up any leftover row from a previous run
    from app.core.database import async_session_factory
    import sqlalchemy as sa
    _s = async_session_factory()
    try:
        await _s.execute(sa.text("DELETE FROM products WHERE model_number = 'INV-STATUS-001'"))
        await _s.commit()
    finally:
        await _s.close()

    # Arrange: we need a product and an inventory item first.
    prod_resp = await client.post(
        "/api/v1/products",
        json={
            "name": "Inventory Test Item",
            "model_number": "INV-STATUS-001",
            "brand_id": 1,
            "category_id": 1,
            "cost_price": 50.0,
            "selling_price": 80.0,
        },
        headers=auth_headers,
    )
    assert prod_resp.status_code == 201, f"Product creation failed: {prod_resp.text}"
    product_id = prod_resp.json()["id"]

    inv_resp = await client.post(
        "/api/v1/inventory",
        json={
            "product_id": product_id,
            "serial_number": "SN-INV-STATUS",
            "location": "Test Shelf",
        },
        headers=auth_headers,
    )
    assert inv_resp.status_code == 201, f"Inventory creation failed: {inv_resp.text}"
    inventory_id = inv_resp.json()["id"]

    # Act – try to set an invalid status
    response = await client.patch(
        f"/api/v1/inventory/{inventory_id}/status",
        json={"status": "Lost"},  # "Lost" is not in the allowed set
        headers=auth_headers,
    )
    assert response.status_code == 422, (
        f"Expected 422 for invalid status, got {response.status_code}: {response.text}"
    )
    body = response.json()
    assert body["success"] is False
    # The error message should mention that 'Lost' is invalid
    assert "Lost" in str(body)
