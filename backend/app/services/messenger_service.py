import hashlib

import hmac
import logging

from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.models.customer import Customer
from app.models.notification import ConversationLog, NotificationQueue

logger = logging.getLogger(__name__)


def verify_signature(
    raw_body: bytes,
    signature_header: str | None,
    app_secret: str,
) -> bool:
    """Verify the X-Hub-Signature-256 header against the raw request body.

    Computes HMAC-SHA256 of *raw_body* using *app_secret* and compares
    against the value after ``sha256=`` in *signature_header* using a
    constant-time comparison.

    Returns ``False`` if the header is missing, malformed, or doesn't match.
    Never raises.
    """
    if not signature_header:
        return False

    if not signature_header.startswith("sha256="):
        return False

    expected_signature = signature_header[len("sha256="):].strip()
    if not expected_signature:
        return False

    computed = hmac.new(
        app_secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()

    return hmac.compare_digest(computed, expected_signature)


async def get_or_create_customer(
    db: AsyncSession,
    messenger_user_id: str,
) -> Customer:
    """Look up a Customer by *messenger_user_id*; create one if none exists.

    Uses a lookup-then-create pattern (not ``merge()``).  If two concurrent
    requests race to insert the same ``messenger_user_id``, the second
    insert will hit the database ``UNIQUE`` constraint and raise
    ``IntegrityError``.  In that case the function falls back to a
    final lookup, guaranteeing exactly one row is returned.

    New customers get placeholder ``first_name="Messenger"``,
    ``last_name="User"``, and a unique ``phone_number`` of the form
    ``"pending-{messenger_user_id}"`` because Messenger doesn't provide
    phone numbers via the webhook.
    """
    result = await db.execute(
        select(Customer).where(Customer.messenger_user_id == messenger_user_id)
    )
    customer = result.scalar_one_or_none()

    if customer is not None:
        return customer

    customer = Customer(
        first_name="Messenger",
        last_name="User",
        phone_number=f"pending-{messenger_user_id}",
        messenger_user_id=messenger_user_id,
    )
    db.add(customer)
    try:
        await db.commit()
        await db.refresh(customer)
        logger.info("Created Customer with messenger_user_id=%s", messenger_user_id)
        return customer
    except IntegrityError:
        # Another concurrent request inserted this messenger_user_id first.
        # Roll back the failed insert and return the existing row.
        await db.rollback()
        result = await db.execute(
            select(Customer).where(Customer.messenger_user_id == messenger_user_id)
        )
        customer = result.scalar_one_or_none()
        if customer is None:
            # Shouldn't happen -- the IntegrityError means someone else inserted it --
            # but guard against the impossible case so we never return None.
            raise
        return customer


async def log_conversation(
    db: AsyncSession,
    messenger_user_id: str,
    speaker: str,
    message_text: str,
    payload: dict | None = None,
) -> ConversationLog:
    """Insert a row into ``conversation_logs`` and return it.

    Also emits an SSE event so connected dashboards receive the
    new message in real time.
    """
    log_entry = ConversationLog(
        messenger_user_id=messenger_user_id,
        speaker=speaker,
        message_text=message_text,
        payload=payload,
    )
    db.add(log_entry)
    await db.commit()
    await db.refresh(log_entry)

        # ---- Phase 12c: Emit SSE event for live updates -----------------------
    try:
        from app.services.sse_service import sse_manager

        await sse_manager.emit({
            "type": "new_message",
            "messenger_user_id": messenger_user_id,
            "speaker": speaker,
            "message": message_text,
            "timestamp": (
                log_entry.timestamp.isoformat()
                if log_entry.timestamp else ""
            ),
        })
    except Exception:
        logger.exception("Failed to emit SSE event for new message")

    return log_entry


async def fetch_conversation_history(
    db: AsyncSession,
    messenger_user_id: str,
    limit: int = 6,
) -> list[dict]:
    """Fetch the last *limit* ConversationLog rows for this user.

    Returns a list of dicts with keys ``speaker`` and ``text``, ordered
    chronologically (oldest first).
    """
    result = await db.execute(
        select(ConversationLog)
        .where(ConversationLog.messenger_user_id == messenger_user_id)
        .order_by(desc(ConversationLog.timestamp))
        .limit(limit)
    )
    rows = list(result.scalars().all())
    rows.reverse()  # oldest first

    return [
        {"speaker": row.speaker, "text": row.message_text}
        for row in rows
    ]


async def process_incoming_message(
    db: AsyncSession,
    entry: "MessagingEntry",
) -> None:
    """Orchestrate the processing of one messaging entry from Meta.

    Phase 4 behavior (unchanged):
        1. Extract ``sender.id`` as the ``messenger_user_id``.
        2. Call :func:`get_or_create_customer`.
        3. Extract text from ``entry.message``.
        4. Call :func:`log_conversation` with ``speaker="User"``.

    Phase 5 additions (AI reply):
        5. If ``settings.STAFF_HANDOFF_ENABLED`` is True, fetch conversation
           history and call ``gemini_service.generate_reply``.
        6. Log the bot's reply with ``speaker="Bot"``.
        7. Send the reply via ``send_api_service.send_message``.
        8. If ``needs_human_handoff`` is True, insert a row into
           ``notification_queue`` with ``channel="Dashboard"``,
           ``status="Pending"``.
    """
    messenger_user_id = entry.sender.get("id")
    if not messenger_user_id:
        logger.warning("Received MessagingEntry without a sender id – skipping")
        return

        # Ensure the customer exists (create if new)
    customer = await get_or_create_customer(db, messenger_user_id)

    # Extract text, handling non-text events gracefully
    if entry.message and isinstance(entry.message, dict):
        message_text = entry.message.get("text", "[non-text event]")
    else:
        message_text = "[non-text event]"

    # Log the incoming user message (Phase 4)
    await log_conversation(
        db,
        messenger_user_id=messenger_user_id,
        speaker="User",
        message_text=message_text,
        payload=entry.model_dump(exclude_none=True) if hasattr(entry, "model_dump") else None,
    )

        # ---- Phase 12b: Lazy idle-timeout auto-resume check -------------------
    # Before skipping for HUMAN_CONTROLLED, check if the thread has been
    # idle for 12+ hours and auto-resume it so the bot can reply.
    from app.services.thread_state_service import check_idle_timeout_auto_resume
    await check_idle_timeout_auto_resume(
        db, customer, source="process_incoming_message"
    )
    # After the check, re-read the state since it may have changed
    await db.refresh(customer)

    # ---- Phase 10: AI-pause guard -----------------------------------------------
    # If a staff member has manually taken over this conversation, skip the AI
    # reply entirely — store the incoming message but don't call DeepSeek.
    if customer.thread_state == "HUMAN_CONTROLLED":
        logger.info(
            "DEBUG process_incoming_message — thread_state=HUMAN_CONTROLLED for "
            "messenger_user_id=%s, skipping AI reply",
            messenger_user_id,
        )
        return

    # ---- Phase 5: AI reply ---------------------------------------------------
    # Skip AI generation for non-text events
    if message_text in ("[non-text event]",):
        logger.info("DEBUG process_incoming_message — RETURNING early because message is non-text event")
        return

    # If staff handoff / AI replies are disabled, stop here (Phase 4 behavior)
    if not settings.STAFF_HANDOFF_ENABLED:
        logger.info("DEBUG process_incoming_message — RETURNING early because STAFF_HANDOFF_ENABLED is False")
        return

    logger.info("DEBUG process_incoming_message — STAFF_HANDOFF_ENABLED is True, proceeding to AI reply phase")

    # Lazy imports to avoid circular dependencies at module level
    from app.services.deepseek_service import generate_reply
    from app.services.send_api_service import send_message

    try:
        logger.info("DEBUG process_incoming_message — fetching conversation history for user=%s", messenger_user_id)

        # Build conversation history from the last 6 messages
        conversation_history = await fetch_conversation_history(
            db, messenger_user_id, limit=6
        )
        logger.info("DEBUG process_incoming_message — history fetched, length=%s", len(conversation_history))

        # Generate reply via Gemini
        logger.info("DEBUG process_incoming_message — calling generate_reply()")
        result = await generate_reply(db, message_text, conversation_history)
        logger.info("DEBUG process_incoming_message — generate_reply returned: reply_text[:80]=%s, handoff=%s, reason=%s",
                     result.reply_text[:80] if result.reply_text else "None",
                     result.needs_human_handoff,
                     result.handoff_reason)

        # Log the bot's reply
        logger.info("DEBUG process_incoming_message — logging bot reply to conversation_logs")
        await log_conversation(
            db,
            messenger_user_id=messenger_user_id,
            speaker="Bot",
            message_text=result.reply_text,
        )

        # Send the reply via Messenger Send API
        logger.info("DEBUG process_incoming_message — calling send_message()")
        await send_message(messenger_user_id, result.reply_text)

        # If handoff is needed, create a notification queue entry
        if result.needs_human_handoff:
            logger.info("DEBUG process_incoming_message — handoff needed, creating notification_queue entry")
            handoff_payload = {
                "messenger_user_id": messenger_user_id,
                "reason": result.handoff_reason or "Unspecified",
                "customer_message": message_text,
            }
            nq = NotificationQueue(
                recipient_id=messenger_user_id,
                channel="Dashboard",
                payload=handoff_payload,
                status="Pending",
            )
            db.add(nq)
            await db.commit()
            logger.info(
                "DEBUG process_incoming_message — Created notification_queue entry for handoff: %s",
                handoff_payload,
            )
        else:
            logger.info("DEBUG process_incoming_message — no handoff needed, no notification created")

        logger.info("DEBUG process_incoming_message — COMPLETED successfully")

    except Exception as exc:
        logger.exception(
            "DEBUG process_incoming_message — CAUGHT exception: Error generating/sending AI reply for %s: %s",
            messenger_user_id,
            exc,
        )
        # The webhook handler will still return 200 — an AI failure should
        # never cause Meta to retry the webhook event.

