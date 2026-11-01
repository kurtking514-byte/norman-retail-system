"""
Tests for showing real customer names in Live Chat.

Covers:
- New Messenger customers get their Facebook first/last name when the
  User Profile API returns it.
- Existing placeholder customers are filled in on their next message.
- When Facebook doesn't share the name, the conversation list shows
  "Messenger User ···<last 4 of PSID>" so customers stay distinguishable.
"""

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-names")
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
from app.core.database import async_session_factory  # noqa: E402
from app.models.customer import Customer  # noqa: E402
from app.models.notification import ConversationLog  # noqa: E402
from app.services.messenger_service import get_or_create_customer, log_conversation  # noqa: E402

PSID_NAMED = "names-test-psid-1111"
PSID_HIDDEN = "names-test-psid-2222"


@pytest.fixture(autouse=True)
async def cleanup():
    session = async_session_factory()
    try:
        ids = [PSID_NAMED, PSID_HIDDEN]
        await session.execute(
            ConversationLog.__table__.delete().where(ConversationLog.messenger_user_id.in_(ids))
        )
        await session.execute(Customer.__table__.delete().where(Customer.messenger_user_id.in_(ids)))
        await session.commit()
    finally:
        await session.close()


@pytest.fixture
def profiles(monkeypatch):
    """Mock the User Profile API with a dict of PSID -> profile (missing = refused)."""
    known = {}

    async def _mock_get_user_profile(psid):
        return known.get(psid)

    monkeypatch.setattr("app.services.send_api_service.get_user_profile", _mock_get_user_profile)
    return known


async def test_new_customer_gets_facebook_name(profiles):
    profiles[PSID_NAMED] = {"first_name": "Maria", "last_name": "Santos"}
    async with async_session_factory() as session:
        customer = await get_or_create_customer(session, PSID_NAMED)
        assert (customer.first_name, customer.last_name) == ("Maria", "Santos")


async def test_placeholder_customer_filled_on_next_message(profiles):
    async with async_session_factory() as session:
        customer = await get_or_create_customer(session, PSID_NAMED)
        assert (customer.first_name, customer.last_name) == ("Messenger", "User")

    profiles[PSID_NAMED] = {"first_name": "Juan", "last_name": "Dela Cruz"}
    async with async_session_factory() as session:
        customer = await get_or_create_customer(session, PSID_NAMED)
        assert (customer.first_name, customer.last_name) == ("Juan", "Dela Cruz")


async def test_hidden_name_shows_distinguishable_label(profiles):
    async with async_session_factory() as session:
        await get_or_create_customer(session, PSID_HIDDEN)
        await log_conversation(session, PSID_HIDDEN, "User", "hello")

    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        login = await client.post(
            "/api/v1/auth/login", json={"username": "admin", "password": "changeme123"}
        )
        headers = {"Authorization": f"Bearer {login.json()['access_token']}"}
        resp = await client.get("/api/v1/conversations", headers=headers)

    names = {c["messenger_user_id"]: c["customer_name"] for c in resp.json()}
    assert names[PSID_HIDDEN] == "Messenger User ···2222"
