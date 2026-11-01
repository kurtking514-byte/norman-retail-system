"""
Tests for the Inventory page's brand/category lists, product editing and
quick stock setting.

Covers:
- ``GET/POST /brands`` and ``/categories`` with product counts and
  case-insensitive duplicate rejection.
- ``PUT /products/{id}`` rejects selling <= cost and duplicate model numbers.
- ``PUT /products/{id}/stock`` adds/removes untracked units and never removes
  serial-numbered ones.
- ``GET /inventory/summary`` returns in-stock counts per product.
"""

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-catalog-stock")
os.environ.setdefault("ADMIN_USERNAME", "admin")

import bcrypt  # noqa: E402

os.environ.setdefault(
    "ADMIN_PASSWORD_HASH",
    bcrypt.hashpw(b"changeme123", bcrypt.gensalt(12)).decode(),
)

import httpx  # noqa: E402
import pytest  # noqa: E402
from httpx import ASGITransport  # noqa: E402
from sqlalchemy import select  # noqa: E402

from app.main import app  # noqa: E402
from app.core.database import async_session_factory  # noqa: E402
from app.models.product import Brand, Category, Inventory, Product  # noqa: E402

PREFIX = "CATTEST-"


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        login = await ac.post(
            "/api/v1/auth/login", json={"username": "admin", "password": "changeme123"}
        )
        ac.headers["Authorization"] = f"Bearer {login.json()['access_token']}"
        yield ac


@pytest.fixture(autouse=True)
async def cleanup():
    async def _clean():
        async with async_session_factory() as s:
            ids = (await s.execute(select(Product.id).where(Product.model_number.like(f"{PREFIX}%")))).scalars().all()
            if ids:
                await s.execute(Inventory.__table__.delete().where(Inventory.product_id.in_(ids)))
                await s.execute(Product.__table__.delete().where(Product.id.in_(ids)))
            await s.execute(Brand.__table__.delete().where(Brand.name.like("CatBrand%")))
            await s.execute(Category.__table__.delete().where(Category.name.like("CatCat%")))
            await s.commit()

    await _clean()
    yield
    await _clean()


async def _make_product(client, model="A", cost=100, price=150) -> dict:
    brand = (await client.post("/api/v1/brands", json={"name": f"CatBrand{model}"})).json()
    category = (await client.post("/api/v1/categories", json={"name": f"CatCat{model}"})).json()
    resp = await client.post("/api/v1/products", json={
        "name": f"Phone {model}", "model_number": f"{PREFIX}{model}",
        "brand_id": brand["id"], "category_id": category["id"],
        "cost_price": cost, "selling_price": price,
    })
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_brands_and_categories_list_with_counts(client):
    product = await _make_product(client)
    brands = (await client.get("/api/v1/brands")).json()
    mine = next(b for b in brands if b["id"] == product["brand_id"])
    assert mine == {"id": product["brand_id"], "name": "CatBrandA", "product_count": 1}
    categories = (await client.get("/api/v1/categories")).json()
    assert any(c["name"] == "CatCatA" and c["product_count"] == 1 for c in categories)


async def test_duplicate_and_blank_names_rejected(client):
    assert (await client.post("/api/v1/brands", json={"name": "CatBrandX"})).status_code == 201
    dup = await client.post("/api/v1/brands", json={"name": "  catbrandx "})
    assert dup.status_code == 409
    assert "already exists" in dup.json()["error"]["message"]
    assert (await client.post("/api/v1/categories", json={"name": "   "})).status_code == 422


async def test_update_validates_price_and_model_number(client):
    a = await _make_product(client, "A")
    await _make_product(client, "B")

    cheap = await client.put(f"/api/v1/products/{a['id']}", json={"selling_price": 90})
    assert cheap.status_code == 422

    clash = await client.put(f"/api/v1/products/{a['id']}", json={"model_number": f"{PREFIX}B"})
    assert clash.status_code == 409

    ok = await client.put(f"/api/v1/products/{a['id']}", json={
        "name": "Phone A2", "selling_price": 175, "specifications": {"RAM": "8GB"},
    })
    assert ok.status_code == 200
    assert ok.json()["name"] == "Phone A2"
    assert ok.json()["specifications"] == {"RAM": "8GB"}


async def test_set_stock_up_down_and_keeps_serialized_units(client):
    a = await _make_product(client)
    url = f"/api/v1/products/{a['id']}/stock"

    up = (await client.put(url, json={"in_stock": 4})).json()
    assert (up["in_stock"], up["added"], up["removed"]) == (4, 4, 0)

    await client.post("/api/v1/inventory", json={"product_id": a["id"], "serial_number": f"{PREFIX}SN1"})
    summary = (await client.get("/api/v1/inventory/summary")).json()
    assert summary[str(a["id"])] == 5

    down = (await client.put(url, json={"in_stock": 0})).json()
    assert (down["in_stock"], down["removed"]) == (1, 4)
    assert "serial numbers" in down["warning"]

    assert (await client.put(url, json={"in_stock": -1})).status_code == 422
    assert (await client.put("/api/v1/products/999999/stock", json={"in_stock": 1})).status_code == 404
