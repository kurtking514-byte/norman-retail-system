"""
Meta Messenger Send API wrapper.

Sends messages back to customers via Meta's ``/me/messages`` endpoint.
Supports a safe dev mode — if ``MESSENGER_PAGE_ACCESS_TOKEN`` is empty,
the actual HTTP call is skipped and the message is logged instead.
"""

import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)

# Meta Graph API base URL — v21.0 is used here.  If this version is
# deprecated by the time this code is deployed, update to the current
# stable version (e.g. v22.0 or whatever is latest).
GRAPH_API_BASE = "https://graph.facebook.com/v21.0"


async def send_message(recipient_id: str, message_text: str) -> bool:
    """Send a text message to a Messenger user via the Send API.

    Parameters
    ----------
    recipient_id:
        The ``id`` field of the recipient's sender object (the PSID).
    message_text:
        The plain-text message to send.

    Returns
    -------
    bool
        ``True`` if the message was sent (or skipped in dev mode),
        ``False`` on error.
    """
    page_token = settings.MESSENGER_PAGE_ACCESS_TOKEN

    # ---- Dev mode: skip actual HTTP call if no real token --------------------
    if not page_token:
        logger.warning(
            "[DEV MODE] Would send to %s: %s",
            recipient_id,
            message_text,
        )
        return True

    url = f"{GRAPH_API_BASE}/me/messages"
    params = {"access_token": page_token}
    payload = {
        "recipient": {"id": recipient_id},
        "message": {"text": message_text},
    }

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(url, params=params, json=payload)
            response.raise_for_status()
            logger.info(
                "Sent message to %s (status=%s)",
                recipient_id,
                response.status_code,
            )
            return True
    except httpx.HTTPStatusError as exc:
        logger.error(
            "Send API HTTP error sending to %s: %s — %s",
            recipient_id,
            exc.response.status_code,
            exc.response.text,
        )
        return False
    except httpx.RequestError as exc:
        logger.error(
            "Send API request error sending to %s: %s",
            recipient_id,
            exc,
        )
        return False
    except Exception as exc:
        logger.exception(
            "Unexpected error sending message to %s: %s",
            recipient_id,
            exc,
        )
        return False
