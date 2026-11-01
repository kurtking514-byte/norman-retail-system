"""
Tests for the repair type picked from the Repairs page dropdown.

Covers:
- ``POST /repairs`` stores ``repair_type`` and accepts it without a description.
- A repair needs either a type or a description.
- ``PUT /repairs/{id}`` can change the type.
"""

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-repair-type")
os.environ.setdefault("ADMIN_USERNAME", "admin")

import bcrypt  # noqa: E402

os.environ.setdefault(
    "ADMIN_PASSWORD_HASH",
    bcrypt.hashpw(b"changeme123", bcrypt.gensalt(12)).decode(),
)

import httpx  # noqa: E402
import pytest  # noqa: E402
from httpx import ASGITransport  # noqa: E402

from app.main import app  # noqa: E402

NEW_CUSTOMER = {"first_name": "Repair", "last_name": "Type", "phone_number": "+63-917-555-0199"}


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        login = await ac.post(
            "/api/v1/auth/login", json={"username": "admin", "password": "changeme123"}
        )
        ac.headers["Authorization"] = f"Bearer {login.json()['access_token']}"
        yield ac


async def test_repair_type_saved_without_description(client):
    resp = await client.post("/api/v1/repairs", json={
        **NEW_CUSTOMER, "device_model": "Galaxy A55", "repair_type": " Screen replacement ",
    })
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["repair_type"] == "Screen replacement"
    assert body["issue_description"] == ""

    changed = await client.put(f"/api/v1/repairs/{body['id']}", json={"repair_type": "Battery replacement"})
    assert changed.json()["repair_type"] == "Battery replacement"


async def test_repair_needs_type_or_description(client):
    resp = await client.post("/api/v1/repairs", json={**NEW_CUSTOMER, "device_model": "Galaxy A55"})
    assert resp.status_code == 422
