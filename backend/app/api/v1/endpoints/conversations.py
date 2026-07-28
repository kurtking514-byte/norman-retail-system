"""
Conversation endpoints for the staff Live Chat dashboard.

Provides:
- ``GET /conversations`` — list all distinct customer threads (one per
  ``messenger_user_id``), ordered by most recent message first.
- ``GET /conversations/{messenger_user_id}`` — fetch full message history
  for a specific customer (chronological order).
- ``POST /conversations/{messenger_user_id}/reply`` — send a manual staff
  reply to a customer via Messenger.
- ``PATCH /conversations/{messenger_user_id}/thread-state`` — toggle AI
  control state for a conversation thread.
"""

import datetime
import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, field_validator
from sqlalchemy import func, select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_admin
from app.models.customer import Customer
from app.models.notification import ConversationLog, NotificationQueue
from app.schemas.conversation import (
    ConversationMessage,
    ConversationThreadSummary,
    SendReplyRequest,
)
from app.services.send_api_service import send_message

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Conversations"])


# ---------------------------------------------------------------------------
# GET /conversations — list distinct customer threads
# ---------------------------------------------------------------------------


@router.get("/conversations", response_model=list[ConversationThreadSummary])
async def list_conversations(
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_admin),
):
    """Return one thread summary per distinct ``messenger_user_id``.

    Ordered by the most recent message first.  ``unread_handoff`` is set
    to ``True`` if there's a ``Pending`` notification_queue entry for
    this ``messenger_user_id`` (matched via the payload's
    ``messenger_user_id`` field).
    """
    # ---- Fetch all conversation_logs grouped by messenger_user_id ----------
    subq = (
        select(
            ConversationLog.messenger_user_id,
            func.max(ConversationLog.timestamp).label("max_ts"),
        )
        .group_by(ConversationLog.messenger_user_id)
        .subquery()
    )

    # Join with the full log table to get the last message's details
    stmt = (
        select(ConversationLog)
        .join(
            subq,
            (ConversationLog.messenger_user_id == subq.c.messenger_user_id)
            & (ConversationLog.timestamp == subq.c.max_ts),
        )
        .order_by(desc(ConversationLog.timestamp))
    )

    result = await db.execute(stmt)
    last_messages = result.scalars().all()

    # ---- Fetch all messenger_user_ids that have a Pending notification ----
    handoff_result = await db.execute(
        select(NotificationQueue).where(NotificationQueue.status == "Pending")
    )
    pending_handoffs = handoff_results = handoff_result.scalars().all()  # type: ignore[assignment]

    # Build a set of messenger_user_ids that have a pending handoff
    pending_ids: set[str] = set()
    for nq in pending_handoffs:
        if nq.payload and isinstance(nq.payload, dict):
            uid = nq.payload.get("messenger_user_id")
            if uid and isinstance(uid, str):
                pending_ids.add(uid)

    # ---- Build summaries --------------------------------------------------
    summaries: list[ConversationThreadSummary] = []
    for log in last_messages:
        # Try to look up the customer name
        customer_name: str | None = None
        customer_id: int | None = None
        cust_result = await db.execute(
            select(Customer).where(
                Customer.messenger_user_id == log.messenger_user_id
            )
        )
        customer = cust_result.scalar_one_or_none()
        if customer:
            customer_id = customer.id
            customer_name = (
                f"{customer.first_name or ''} {customer.last_name or ''}".strip()
                or None
            )

        # ---- Phase 12b: Lazy auto-resume check on read --------------------
        from app.services.thread_state_service import check_idle_timeout_auto_resume
        if customer:
            await check_idle_timeout_auto_resume(
                db, customer, source="list_conversations"
            )
            await db.refresh(customer)

        summaries.append(
            ConversationThreadSummary(
                messenger_user_id=log.messenger_user_id,
                customer_id=customer_id,
                customer_name=customer_name,
                last_message_text=log.message_text,
                last_message_timestamp=(
                    log.timestamp.isoformat() if log.timestamp else None
                ),
                unread_handoff=(log.messenger_user_id in pending_ids),
                thread_state=(customer.thread_state if customer else "AI_CONTROLLED"),
                thread_state_pinned=(customer.thread_state_pinned if customer else False),
            )
        )

    return summaries


# ---------------------------------------------------------------------------
# GET /conversations/stream — SSE endpoint for live updates
# ---------------------------------------------------------------------------


import asyncio
import json

from fastapi import Query
from fastapi.responses import StreamingResponse

# SSE clients (EventSource) cannot set custom HTTP headers, so we accept
# the JWT token as a query parameter and validate it directly.
from jose import JWTError as _JWTError
from jose import jwt as _jwt

from app.core.config import settings as _settings


@router.get("/conversations/stream")
async def stream_conversations(
    token: str | None = Query(None),
):
    """SSE endpoint that streams conversation events (new messages,
    thread-state changes) to connected dashboards in real time.

    Because ``EventSource`` cannot set the ``Authorization`` header,
    the JWT token is passed as a ``?token=...`` query parameter and
    validated directly.

    The client connects via ``EventSource`` and receives events like::

        event: connected
        data: {}

        event: message
        data: {"type": "new_message", "messenger_user_id": "...",
               "speaker": "User", "message": "...", "timestamp": "..."}

        event: message
        data: {"type": "thread_state_changed", "messenger_user_id": "...",
               "old_state": "AI_CONTROLLED", "new_state": "HUMAN_CONTROLLED",
               "thread_state_pinned": false, "timestamp": "..."}
    """
    # ---- Validate JWT token from query param directly ------------------
    if not token:
        return StreamingResponse(
            iter([json.dumps({"error": "Missing token"})]),
            status_code=401,
            media_type="application/json",
        )

    try:
        payload = _jwt.decode(
            token,
            _settings.JWT_SECRET_KEY,
            algorithms=["HS256"],
        )
        if payload.get("sub") is None:
            return StreamingResponse(
                iter([json.dumps({"error": "Invalid token payload"})]),
                status_code=401,
                media_type="application/json",
            )
    except _JWTError:
        return StreamingResponse(
            iter([json.dumps({"error": "Invalid or expired token"})]),
            status_code=401,
            media_type="application/json",
        )

    from app.services.sse_service import sse_manager

    queue: asyncio.Queue = await sse_manager.subscribe()

    async def event_generator():
        try:
            # Send an initial heartbeat to confirm connection
            yield "event: connected\ndata: {}\n\n"
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=30.0)
                    yield f"event: message\ndata: {json.dumps(event)}\n\n"
                except asyncio.TimeoutError:
                    # Send a keepalive comment to prevent proxies from
                    # closing the connection
                    yield ": keepalive\n\n"
        except asyncio.CancelledError:
            pass
        finally:
            await sse_manager.unsubscribe(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# GET /conversations/{messenger_user_id} — full message history
# ---------------------------------------------------------------------------


@router.get(
    "/conversations/{messenger_user_id}",
    response_model=list[ConversationMessage],
)
async def get_conversation_messages(
    messenger_user_id: str,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_admin),
):
    """Return all messages for a specific customer thread (oldest first)."""
    # ---- Phase 12b: Lazy auto-resume check on read --------------------
    cust_result = await db.execute(
        select(Customer).where(Customer.messenger_user_id == messenger_user_id)
    )
    customer = cust_result.scalar_one_or_none()
    if customer:
        from app.services.thread_state_service import check_idle_timeout_auto_resume
        await check_idle_timeout_auto_resume(
            db, customer, source="get_conversation_messages"
        )
        await db.refresh(customer)

    stmt = (
        select(ConversationLog)
        .where(ConversationLog.messenger_user_id == messenger_user_id)
        .order_by(ConversationLog.timestamp)
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()

    if not rows:
        raise HTTPException(
            status_code=404,
            detail={
                "success": False,
                "error": {
                    "code": "NOT_FOUND",
                    "message": (
                        f"No conversation found for messenger_user_id "
                        f"'{messenger_user_id}'."
                    ),
                    "details": [],
                },
            },
        )

    return [
        ConversationMessage(
            id=row.id,
            speaker=row.speaker,
            message_text=row.message_text,
            timestamp=row.timestamp.isoformat() if row.timestamp else "",
        )
        for row in rows
    ]


# ---------------------------------------------------------------------------
# POST /conversations/{messenger_user_id}/reply — staff sends a message
# ---------------------------------------------------------------------------


@router.post(
    "/conversations/{messenger_user_id}/reply",
    response_model=ConversationMessage,
    status_code=201,
)
async def send_staff_reply(
    messenger_user_id: str,
    body: SendReplyRequest,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_admin),
):
    """Send a manual staff reply to a customer.

    1. Log the outgoing message to ``conversation_logs`` with
       ``speaker="Staff"``.
    2. Send the message via the Messenger Send API.
    3. Return the newly created log entry.
    """
    # Log the staff message (uses log_conversation from messenger_service
    # so that SSE events are emitted for live updates)
    from app.services.messenger_service import log_conversation as _log_conversation
    log_entry = await _log_conversation(
        db,
        messenger_user_id=messenger_user_id,
        speaker="Staff",
        message_text=body.message_text,
    )

    logger.info(
        "Staff replied to %s: %s",
        messenger_user_id,
        body.message_text,
    )

    # Send via Messenger (dev-mode logs "would send" if token is unset)
    try:
        await send_message(messenger_user_id, body.message_text)
    except Exception as exc:
        logger.exception(
            "Failed to send staff reply via Messenger for %s: %s",
            messenger_user_id,
            exc,
        )
        # We still return the logged message even if the Send API call fails.
        # The message is saved; the staff can retry.

    # ---- Phase 12a: Auto-pause AI when staff sends a manual reply ----------
    # If the conversation is currently AI-controlled, pause it so the bot
    # doesn't talk over the staff member who just replied.
    # No-op if already HUMAN_CONTROLLED — avoids a redundant write.
    result = await db.execute(
        select(Customer).where(Customer.messenger_user_id == messenger_user_id)
    )
    customer = result.scalar_one_or_none()
    if customer and customer.thread_state == "AI_CONTROLLED":
        from app.services.thread_state_service import update_thread_state
        await update_thread_state(db, customer, "HUMAN_CONTROLLED")
        logger.info(
            "Auto-paused AI for %s after staff reply",
            messenger_user_id,
        )

    return ConversationMessage(
        id=log_entry.id,
        speaker=log_entry.speaker,
        message_text=log_entry.message_text,
        timestamp=(
            log_entry.timestamp.isoformat() if log_entry.timestamp else ""
        ),
    )


# ---------------------------------------------------------------------------
# PATCH /conversations/{messenger_user_id}/thread-state — toggle AI control
# ---------------------------------------------------------------------------


class ThreadStateUpdateRequest(BaseModel):
    """Payload for updating a conversation's thread state."""

    thread_state: str

    @field_validator("thread_state")
    @classmethod
    def validate_thread_state(cls, v: str) -> str:
        allowed = {"AI_CONTROLLED", "HUMAN_CONTROLLED"}
        if v not in allowed:
            raise ValueError(
                f"Invalid thread_state '{v}'. Must be one of: {', '.join(sorted(allowed))}"
            )
        return v


class ThreadStatePinRequest(BaseModel):
    """Payload for pinning/unpinning a conversation's thread state."""

    thread_state_pinned: bool


class ThreadStateResponse(BaseModel):
    """Response after updating thread state."""

    messenger_user_id: str
    customer_id: int
    customer_name: str | None
    thread_state: str
    thread_state_pinned: bool = False

    model_config = {"from_attributes": True}


@router.patch(
    "/conversations/{messenger_user_id}/thread-state",
    response_model=ThreadStateResponse,
)
async def update_thread_state(
    messenger_user_id: str,
    body: ThreadStateUpdateRequest,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_admin),
):
    """Toggle the AI control state for a conversation thread.

    ``AI_CONTROLLED`` — the bot will auto-reply to incoming messages.
    ``HUMAN_CONTROLLED`` — the bot will NOT auto-reply; staff has taken over.
    """
    result = await db.execute(
        select(Customer).where(Customer.messenger_user_id == messenger_user_id)
    )
    customer = result.scalar_one_or_none()
    if customer is None:
        raise HTTPException(
            status_code=404,
            detail={
                "success": False,
                "error": {
                    "code": "NOT_FOUND",
                    "message": (
                        f"No customer found for messenger_user_id "
                        f"'{messenger_user_id}'."
                    ),
                    "details": [],
                },
            },
        )

    from app.services.thread_state_service import update_thread_state
    await update_thread_state(db, customer, body.thread_state, clear_pin=True)

    customer_name = (
        f"{customer.first_name or ''} {customer.last_name or ''}".strip()
        or None
    )

    logger.info(
        "Thread state for %s updated to %s (pinned cleared)",
        messenger_user_id,
        body.thread_state,
    )

    return ThreadStateResponse(
        messenger_user_id=customer.messenger_user_id,
        customer_id=customer.id,
        customer_name=customer_name,
        thread_state=customer.thread_state,
        thread_state_pinned=customer.thread_state_pinned,
    )


# ---------------------------------------------------------------------------
# PATCH /conversations/{messenger_user_id}/thread-state/pin — pin/unpin
# ---------------------------------------------------------------------------


@router.patch(
    "/conversations/{messenger_user_id}/thread-state/pin",
    response_model=ThreadStateResponse,
)
async def update_thread_state_pin(
    messenger_user_id: str,
    body: ThreadStatePinRequest,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_admin),
):
    """Set or clear the ``thread_state_pinned`` flag for a conversation.

    When pinned (``true``), the 12-hour idle-timeout auto-resume is skipped
    for this thread, even if it's been ``HUMAN_CONTROLLED`` for a long time.
    """
    result = await db.execute(
        select(Customer).where(Customer.messenger_user_id == messenger_user_id)
    )
    customer = result.scalar_one_or_none()
    if customer is None:
        raise HTTPException(
            status_code=404,
            detail={
                "success": False,
                "error": {
                    "code": "NOT_FOUND",
                    "message": (
                        f"No customer found for messenger_user_id "
                        f"'{messenger_user_id}'."
                    ),
                    "details": [],
                },
            },
        )

    customer.thread_state_pinned = body.thread_state_pinned
    db.add(customer)
    await db.commit()
    await db.refresh(customer)

    customer_name = (
        f"{customer.first_name or ''} {customer.last_name or ''}".strip()
        or None
    )

    logger.info(
        "Thread state pin for %s set to %s",
        messenger_user_id,
        body.thread_state_pinned,
    )

    return ThreadStateResponse(
        messenger_user_id=customer.messenger_user_id,
        customer_id=customer.id,
        customer_name=customer_name,
        thread_state=customer.thread_state,
        thread_state_pinned=customer.thread_state_pinned,
    )
