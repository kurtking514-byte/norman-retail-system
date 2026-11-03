"""The backend's own address should lead people to the admin dashboard."""

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-home-redirect")

import httpx  # noqa: E402
from httpx import ASGITransport  # noqa: E402

from app.main import app  # noqa: E402


async def test_home_redirects_to_dashboard():
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        res = await client.get("/")
    assert res.status_code == 307
    assert res.headers["location"].startswith("https://")
