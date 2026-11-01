"""
Tests for the global AI chatbot switch on the admin dashboard.

Covers:
- ``GET /api/v1/settings/ai-replies`` defaults to enabled and needs auth.
- ``PUT /api/v1/settings/ai-replies`` persists the switch.
- ``process_incoming_message`` logs the message but skips the AI reply
  while the switch is off, and replies again once it is back on.

The DeepSeek and Send API calls are mocked.
"""

import os

os.environ.setdefault("JWT_SECRET_KEY", "test-secret-key-ai-switch")
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
from app.core.config import settings  # noqa: E402
from app.core.database import async_session_factory  # noqa: E402
from app.models.business import Setting  # noqa: E402
from app.models.customer import Customer  # noqa: E402
from app.models.notification import ConversationLog  # noqa: E402
from app.schemas.ai_response import AIReplyResult  # noqa: E402
from app.schemas.messenger import MessagingEntry  # noqa: E402
from app.services.ai_settings_service import AI_REPLIES_KEY  # noqa: E402
from app.services.messenger_service import process_incoming_message  # noqa: E402

SENDER_ID = "messenger-user-ai-switch"
URL = "/api/v1/settings/ai-replies"


@pytest.fixture
async def client():
    transport = ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture(autouse=True)
async def cleanup():
    """Reset the switch and remove this file's test customer before each test."""
    session = async_session_factory()
    try:
        await session.execute(Setting.__table__.delete().where(Setting.key == AI_REPLIES_KEY))
        await session.execute(
            ConversationLog.__table__.delete().where(ConversationLog.messenger_user_id == SENDER_ID)
        )
        await session.execute(
            Customer.__table__.delete().where(Customer.messenger_user_id == SENDER_ID)
        )
        await session.commit()
    finally:
        await session.close()


@pytest.fixture
def ai_calls(monkeypatch):
    """Mock the AI reply and Send API; return a list recording AI calls."""
    calls = []

    async def _mock_generate_reply(db, message_text, history):
        calls.append(message_text)
        return AIReplyResult(reply_text="Mock AI reply", needs_human_handoff=False)

    async def _mock_send_message(recipient_id, message_text):
        return True

    monkeypatch.setattr("app.services.deepseek_service.generate_reply", _mock_generate_reply)
    monkeypatch.setattr("app.services.send_api_service.send_message", _mock_send_message)
    monkeypatch.setattr(settings, "STAFF_HANDOFF_ENABLED", True)
    return calls


async def _auth_headers(client) -> dict:
    resp = await client.post(
        "/api/v1/auth/login", json={"username": "admin", "password": "changeme123"}
    )
    assert resp.status_code == 200, resp.text
    return {"Authorization": f"Bearer {resp.json()['access_token']}"}


async def _receive(text: str) -> list[str]:
    """Process one incoming Messenger message and return logged speakers."""
    entry = MessagingEntry(
        sender={"id": SENDER_ID},
        recipient={"id": "page-1"},
        timestamp=1234567890,
        message={"mid": "mid.ai-switch", "text": text},
    )
    session = async_session_factory()
    try:
        await process_incoming_message(session, entry)
        result = await session.execute(
            select(ConversationLog.speaker)
            .where(ConversationLog.messenger_user_id == SENDER_ID)
            .order_by(ConversationLog.id)
        )
        return list(result.scalars().all())
    finally:
        await session.close()


async def test_ai_replies_requires_auth(client):
    resp = await client.get(URL)
    assert resp.status_code == 401


async def test_ai_replies_defaults_to_enabled(client):
    resp = await client.get(URL, headers=await _auth_headers(client))
    assert resp.status_code == 200
    assert resp.json() == {"enabled": True}


async def test_ai_replies_toggle_persists(client):
    headers = await _auth_headers(client)

    resp = await client.put(URL, json={"enabled": False}, headers=headers)
    assert resp.status_code == 200
    assert resp.json() == {"enabled": False}
    assert (await client.get(URL, headers=headers)).json() == {"enabled": False}

    resp = await client.put(URL, json={"enabled": True}, headers=headers)
    assert resp.json() == {"enabled": True}
    assert (await client.get(URL, headers=headers)).json() == {"enabled": True}


async def test_switch_off_skips_ai_reply_but_logs_message(client, ai_calls):
    headers = await _auth_headers(client)
    await client.put(URL, json={"enabled": False}, headers=headers)

    speakers = await _receive("Is the AI off?")
    assert speakers == ["User"]
    assert ai_calls == []

    await client.put(URL, json={"enabled": True}, headers=headers)

    speakers = await _receive("Is the AI back on?")
    assert speakers == ["User", "User", "Bot"]
    assert ai_calls == ["Is the AI back on?"]
