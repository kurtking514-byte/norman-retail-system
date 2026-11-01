"""
Tests for admin login hardening.

Covers:
- Repeated wrong passwords from one IP are blocked with HTTP 429 and a
  Retry-After header, even when the right password is then used.
- The per-username limit blocks guessing spread across many IPs.
- Failures expire after the window; a successful login clears the IP count.
- Login tokens expire after ACCESS_TOKEN_EXPIRE_MINUTES.
- A malformed ADMIN_PASSWORD_HASH fails the login instead of crashing.
"""

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-login-security")
os.environ.setdefault("ADMIN_USERNAME", "admin")

import bcrypt  # noqa: E402

os.environ.setdefault(
    "ADMIN_PASSWORD_HASH",
    bcrypt.hashpw(b"changeme123", bcrypt.gensalt(12)).decode(),
)

from datetime import datetime, timezone  # noqa: E402

import httpx  # noqa: E402
import pytest  # noqa: E402
from httpx import ASGITransport  # noqa: E402
from jose import jwt  # noqa: E402

from app.main import app  # noqa: E402
from app.core.config import settings  # noqa: E402
from app.core.rate_limit import (  # noqa: E402
    MAX_FAILURES_PER_IP,
    MAX_FAILURES_PER_USERNAME,
    WINDOW_SECONDS,
    LoginRateLimiter,
)
from app.core.security import ALGORITHM, verify_password  # noqa: E402

LOGIN_URL = "/api/v1/auth/login"
GOOD = {"username": "admin", "password": "changeme123"}
BAD = {"username": "admin", "password": "wrong-password"}


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


def _from_ip(ip: str) -> dict:
    return {"X-Forwarded-For": ip}


async def test_ip_blocked_after_too_many_failures(client):
    for _ in range(MAX_FAILURES_PER_IP):
        resp = await client.post(LOGIN_URL, json=BAD, headers=_from_ip("1.1.1.1"))
        assert resp.status_code == 401

    resp = await client.post(LOGIN_URL, json=GOOD, headers=_from_ip("1.1.1.1"))
    assert resp.status_code == 429
    assert int(resp.headers["Retry-After"]) > 0
    assert "Too many failed login attempts" in resp.json()["error"]["message"]

    # A different IP can still log in
    resp = await client.post(LOGIN_URL, json=GOOD, headers=_from_ip("2.2.2.2"))
    assert resp.status_code == 200


async def test_username_blocked_across_many_ips(client):
    for i in range(MAX_FAILURES_PER_USERNAME):
        await client.post(LOGIN_URL, json=BAD, headers=_from_ip(f"10.0.0.{i}"))

    resp = await client.post(LOGIN_URL, json=GOOD, headers=_from_ip("10.0.1.1"))
    assert resp.status_code == 429


async def test_success_clears_ip_failures(client):
    for _ in range(MAX_FAILURES_PER_IP - 1):
        await client.post(LOGIN_URL, json=BAD, headers=_from_ip("3.3.3.3"))
    assert (await client.post(LOGIN_URL, json=GOOD, headers=_from_ip("3.3.3.3"))).status_code == 200

    for _ in range(MAX_FAILURES_PER_IP - 1):
        resp = await client.post(LOGIN_URL, json=BAD, headers=_from_ip("3.3.3.3"))
        assert resp.status_code == 401


def test_failures_expire_after_window():
    now = [1000.0]
    limiter = LoginRateLimiter(clock=lambda: now[0])
    for _ in range(MAX_FAILURES_PER_IP):
        limiter.record_failure("4.4.4.4", "admin")
    assert limiter.retry_after("4.4.4.4", "admin") > 0

    now[0] += WINDOW_SECONDS + 1
    assert limiter.retry_after("4.4.4.4", "admin") == 0


async def test_token_expires_after_configured_minutes(client):
    resp = await client.post(LOGIN_URL, json=GOOD)
    token = resp.json()["access_token"]
    payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[ALGORITHM])
    lifetime = payload["exp"] - datetime.now(timezone.utc).timestamp()
    expected = settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60
    assert expected - 60 < lifetime <= expected


async def test_expired_token_rejected(client):
    expired = jwt.encode(
        {"sub": "admin", "exp": 1}, settings.JWT_SECRET_KEY, algorithm=ALGORITHM
    )
    resp = await client.get(
        "/api/v1/settings/ai-replies", headers={"Authorization": f"Bearer {expired}"}
    )
    assert resp.status_code == 401


def test_malformed_password_hash_fails_closed():
    assert verify_password("anything", "") is False
    assert verify_password("anything", "not-a-bcrypt-hash") is False
