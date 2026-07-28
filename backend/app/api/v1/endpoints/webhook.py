import json
import logging

from fastapi import APIRouter, Query, Request
from fastapi.responses import PlainTextResponse, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.database import async_session_factory
from app.schemas.messenger import WebhookPayload
from app.services.messenger_service import (
    process_incoming_message,
    verify_signature,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Webhook"])


# ---------------------------------------------------------------------------
# GET /webhook – Meta webhook verification handshake
# ---------------------------------------------------------------------------
@router.get("/webhook")
async def webhook_verify(
    mode: str = Query("", alias="hub.mode"),
    verify_token: str = Query("", alias="hub.verify_token"),
    challenge: str = Query("", alias="hub.challenge"),
):
    """Handle the Meta webhook verification handshake.

    Meta sends a GET request with ``hub.mode``, ``hub.verify_token``,
    and ``hub.challenge``.  If the tokens match we echo back the
    challenge as plain text; otherwise we return 403.
    """
    if mode == "subscribe" and verify_token == settings.MESSENGER_VERIFY_TOKEN:
        return PlainTextResponse(challenge)

    logger.warning(
        "Webhook verification failed: mode=%r verify_token=%r",
        mode,
        verify_token,
    )
    return Response(
        content=json.dumps({
            "success": False,
            "error": {
                "code": "VERIFICATION_FAILED",
                "message": "Invalid verify token or mode.",
                "details": [],
            },
        }),
        status_code=403,
        media_type="application/json",
    )


# ---------------------------------------------------------------------------
# POST /webhook – receive incoming Messenger events
# ---------------------------------------------------------------------------
@router.post("/webhook")
async def webhook_receive(request: Request):
    """Receive and process incoming Messenger events from Meta.

    This endpoint:
    1. Reads the **raw** request body for signature validation.
    2. Validates the ``X-Hub-Signature-256`` header unless
       ``META_APP_SECRET`` is empty (development/placeholder mode).
    3. Parses the JSON payload into :class:`WebhookPayload`.
    4. Processes each messaging entry via :func:`process_incoming_message`.
    5. Returns ``200 {"status": "EVENT_RECEIVED"}`` immediately.
    """
    raw_body = await request.body()

    # ---- Signature validation --------------------------------------------
    signature_header = request.headers.get("X-Hub-Signature-256")

    if settings.META_APP_SECRET:
        if not verify_signature(raw_body, signature_header, settings.META_APP_SECRET):
            logger.warning("Invalid signature on incoming webhook POST")
            return Response(
                content=json.dumps({
                    "success": False,
                    "error": {
                        "code": "INVALID_SIGNATURE",
                        "message": "X-Hub-Signature-256 does not match.",
                        "details": [],
                    },
                }),
                status_code=403,
                media_type="application/json",
            )
    else:
        logger.warning(
            "META_APP_SECRET is not configured — skipping signature validation. "
            "This is INSECURE and should only be used for local development."
        )

    # ---- Parse payload ---------------------------------------------------
    try:
        payload = WebhookPayload.model_validate(json.loads(raw_body))
    except Exception as exc:
        logger.error("Failed to parse webhook payload: %s", exc)
        return Response(
            content=json.dumps({"status": "EVENT_RECEIVED"}),
            status_code=200,
            media_type="application/json",
        )

    # ---- Process each entry ----------------------------------------------
    db = async_session_factory()
    try:
        for entry in payload.entry:
            for messaging in entry.messaging:
                try:
                    await process_incoming_message(db, messaging)
                except Exception as exc:
                    logger.exception(
                        "Error processing messaging entry: %s", exc
                    )
                    # Continue processing further entries – Meta wants a 200,
                    # and one bad message shouldn't block the rest.
    finally:
        await db.close()

    return Response(
        content=json.dumps({"status": "EVENT_RECEIVED"}),
        status_code=200,
        media_type="application/json",
    )


