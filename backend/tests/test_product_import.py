"""
Tests for bulk phone import from Excel/CSV.

Covers:
- The template downloads as a valid .xlsx that imports cleanly.
- Preview (dry run) reports create/update/unchanged/error and saves nothing.
- Applying creates brands, categories, products, specs and stock units.
- Re-importing updates by Model Number and adjusts stock up or down.
- Any invalid row blocks the whole import.
- Bad files (wrong type, missing columns) are rejected with a clear message.
"""

import io
import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-product-import")
os.environ.setdefault("ADMIN_USERNAME", "admin")

import bcrypt  # noqa: E402

os.environ.setdefault(
    "ADMIN_PASSWORD_HASH",
    bcrypt.hashpw(b"changeme123", bcrypt.gensalt(12)).decode(),
)

import httpx  # noqa: E402
import pytest  # noqa: E402
from httpx import ASGITransport  # noqa: E402
from openpyxl import load_workbook  # noqa: E402
from sqlalchemy import func, select  # noqa: E402

from app.main import app  # noqa: E402
from app.core.database import async_session_factory  # noqa: E402
from app.models.product import Brand, Category, Inventory, Product  # noqa: E402

URL = "/api/v1/products/import"
PREFIX = "IMPTEST-"
HEADER = "Brand,Category,Name,Model Number,Cost Price,Selling Price,Stock Qty,RAM,Storage,Weight\n"


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
            await s.execute(Brand.__table__.delete().where(Brand.name.like("ImpBrand%")))
            await s.execute(Category.__table__.delete().where(Category.name.like("ImpCat%")))
            await s.commit()

    await _clean()
    yield
    await _clean()


def _csv(*rows: str) -> dict:
    return {"file": ("phones.csv", (HEADER + "\n".join(rows) + "\n").encode(), "text/csv")}


async def _stock(model: str) -> int:
    async with async_session_factory() as s:
        return (
            await s.execute(
                select(func.count())
                .select_from(Inventory)
                .join(Product, Product.id == Inventory.product_id)
                .where(Product.model_number == model, Inventory.status == "In Stock")
            )
        ).scalar_one()


async def _product(model: str) -> Product | None:
    async with async_session_factory() as s:
        return (await s.execute(select(Product).where(Product.model_number == model))).scalar_one_or_none()


async def test_preview_saves_nothing(client):
    resp = await client.post(URL, files=_csv(f"ImpBrandA,ImpCatA,Phone A,{PREFIX}A,100,150,3,8GB,256GB,190g"))
    assert resp.status_code == 200
    body = resp.json()
    assert body["applied"] is False
    assert body["summary"]["create"] == 1
    assert body["rows"][0]["action"] == "create"
    assert any("New brand" in w for w in body["rows"][0]["warnings"])
    assert await _product(f"{PREFIX}A") is None


async def test_apply_creates_products_specs_and_stock(client):
    resp = await client.post(
        URL,
        params={"dry_run": "false"},
        files=_csv(
            f"ImpBrandA,ImpCatA,Phone A,{PREFIX}A,100,150,3,8GB,256GB,190g",
            f"ImpBrandA,ImpCatA,Phone B,{PREFIX}B,\"1,000\",₱1500,,,,",
        ),
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["applied"] is True
    assert resp.json()["summary"]["stock_added"] == 3

    a = await _product(f"{PREFIX}A")
    assert a.specifications == {"RAM": "8GB", "Storage": "256GB", "Weight": "190g"}
    assert float(a.selling_price) == 150
    assert await _stock(f"{PREFIX}A") == 3
    b = await _product(f"{PREFIX}B")
    assert float(b.cost_price) == 1000 and float(b.selling_price) == 1500
    assert await _stock(f"{PREFIX}B") == 0


async def test_reimport_updates_and_adjusts_stock(client):
    await client.post(URL, params={"dry_run": "false"},
                      files=_csv(f"ImpBrandA,ImpCatA,Phone A,{PREFIX}A,100,150,5,8GB,256GB,"))

    preview = await client.post(URL, files=_csv(f"ImpBrandA,ImpCatA,Phone A,{PREFIX}A,100,150,5,8GB,256GB,"))
    assert preview.json()["rows"][0]["action"] == "unchanged"

    resp = await client.post(URL, params={"dry_run": "false"},
                             files=_csv(f"ImpBrandA,ImpCatA,Phone A Plus,{PREFIX}A,100,175,2,8GB,256GB,"))
    row = resp.json()["rows"][0]
    assert row["action"] == "update"
    assert (row["stock_current"], row["stock_target"]) == (5, 2)
    assert resp.json()["summary"]["stock_removed"] == 3
    product = await _product(f"{PREFIX}A")
    assert product.name == "Phone A Plus" and float(product.selling_price) == 175
    assert await _stock(f"{PREFIX}A") == 2


async def test_invalid_rows_block_the_whole_import(client):
    resp = await client.post(
        URL,
        files=_csv(
            f"ImpBrandA,ImpCatA,Good,{PREFIX}A,100,150,1,,,",
            f"ImpBrandA,ImpCatA,,{PREFIX}B,abc,50,-1,,,",
            f"ImpBrandA,ImpCatA,Dupe,{PREFIX}A,100,150,1,,,",
        ),
    )
    rows = resp.json()["rows"]
    assert resp.json()["summary"]["error"] == 2
    assert "Name is required." in rows[1]["errors"]
    assert any("Cost Price must be a number" in e for e in rows[1]["errors"])
    assert any("can't be negative" in e for e in rows[1]["errors"])
    assert any("also appears on row 2" in e for e in rows[2]["errors"])

    applied = await client.post(URL, params={"dry_run": "false"}, files=_csv(
        f"ImpBrandA,ImpCatA,Good,{PREFIX}A,100,150,1,,,",
        f"ImpBrandA,ImpCatA,Cheap,{PREFIX}B,100,90,1,,,",
    ))
    assert applied.status_code == 422
    assert await _product(f"{PREFIX}A") is None


async def test_template_downloads_and_imports(client):
    resp = await client.get(f"{URL}/template")
    assert resp.status_code == 200
    wb = load_workbook(io.BytesIO(resp.content))
    assert wb.sheetnames == ["Phones", "Instructions"]
    ws = wb["Phones"]
    ws["D2"] = f"{PREFIX}T1"
    ws["D3"] = f"{PREFIX}T2"
    out = io.BytesIO()
    wb.save(out)

    files = {"file": ("filled.xlsx", out.getvalue(), "application/octet-stream")}
    imported = await client.post(URL, params={"dry_run": "false"}, files=files)
    assert imported.status_code == 200, imported.text
    assert imported.json()["summary"]["create"] == 2
    product = await _product(f"{PREFIX}T1")
    assert product.specifications["Chipset"] == "Exynos 1480"
    assert await _stock(f"{PREFIX}T1") == 4


async def test_bad_files_rejected(client):
    wrong_type = await client.post(URL, files={"file": ("phones.txt", b"hello", "text/plain")})
    assert wrong_type.status_code == 422
    assert "Excel (.xlsx) or CSV" in wrong_type.json()["error"]["message"]

    missing = await client.post(URL, files={"file": ("p.csv", b"Brand,Name\nX,Y\n", "text/csv")})
    assert missing.status_code == 422
    assert "Missing required column" in missing.json()["error"]["message"]


async def test_import_requires_login():
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        assert (await ac.get(f"{URL}/template")).status_code == 401
        assert (await ac.post(URL, files=_csv())).status_code == 401
