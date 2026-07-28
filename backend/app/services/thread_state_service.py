"""
Service layer for managing thread state transitions.

Handles:
- Updating ``thread_state_updated_at`` whenever ``thread_state`` changes.
- Performing the lazy 12-hour idle-timeout auto-resume check.
- Managing the ``thread_state_pinned`` flag.
"""

import datetime
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer

logger = logging.getLogger(__name__)

_IDLE_TIMEOUT_HOURS = 12


async def update_thread_state(
    db: AsyncSession,
    customer: Customer,
    new_state: str,
    clear_pin: bool = False,
) -> None:
    """Set ``customer.thread_state`` and update ``thread_state_updated_at``.

    Also clears ``thread_state_pinned`` if ``clear_pin`` is True (used when
    staff manually toggles the thread state).

    Emits an SSE event so connected dashboards update in real time.
    """
    old_state = customer.thread_state
    customer.thread_state = new_state
    customer.thread_state_updated_at = datetime.datetime.now()
    if clear_pin:
        customer.thread_state_pinned = False
    db.add(customer)
    await db.commit()
    logger.info(
        "Thread state for messenger_user_id=%s set to %s (pinned=%s)",
        customer.messenger_user_id,
        new_state,
        customer.thread_state_pinned,
    )

    # ---- Phase 12c: Emit SSE event for thread-state change -----------------
    try:
        from app.services.sse_service import sse_manager

        await sse_manager.emit({
            "type": "thread_state_changed",
            "messenger_user_id": customer.messenger_user_id,
            "old_state": old_state,
            "new_state": new_state,
            "thread_state_pinned": customer.thread_state_pinned,
            "timestamp": (
                customer.thread_state_updated_at.isoformat()
                if customer.thread_state_updated_at else ""
            ),
        })
    except Exception:
        logger.exception("Failed to emit SSE event for thread-state change")


async def check_idle_timeout_auto_resume(
    db: AsyncSession,
    customer: Customer,
    source: str = "",
) -> bool:
    """Check if the thread should auto-resume from HUMAN_CONTROLLED to AI_CONTROLLED.

    Lazy check-on-access pattern (no background scheduler).

    Returns ``True`` if an auto-resume was performed, ``False`` otherwise.

    Conditions for auto-resume:
    1. Thread is HUMAN_CONTROLLED.
    2. ``thread_state_pinned`` is not True.
    3. ``thread_state_updated_at`` is not None.
    4. More than ``_IDLE_TIMEOUT_HOURS`` (12) hours have elapsed since the
       last thread state change.
    """
    if customer.thread_state != "HUMAN_CONTROLLED":
        return False

    if customer.thread_state_pinned:
        logger.info(
            "Auto-resume skipped for %s — thread_state_pinned is True",
            customer.messenger_user_id,
        )
        return False

    if customer.thread_state_updated_at is None:
        # No timestamp to compare against — skip
        return False

    elapsed = datetime.datetime.now() - customer.thread_state_updated_at
    if elapsed.total_seconds() < _IDLE_TIMEOUT_HOURS * 3600:
        return False

    # Perform the auto-resume
    old_ts = customer.thread_state_updated_at.isoformat()
    customer.thread_state = "AI_CONTROLLED"
    customer.thread_state_updated_at = datetime.datetime.now()
    # Do NOT clear thread_state_pinned (it's already False by this point)
    db.add(customer)
    await db.commit()

    logger.warning(
        "AUTO-RESUME: messenger_user_id=%s was HUMAN_CONTROLLED since %s "
        "(> %d hours idle). Resumed to AI_CONTROLLED. Source=%s",
        customer.messenger_user_id,
        old_ts,
        _IDLE_TIMEOUT_HOURS,
        source,
    )

    # ---- Phase 12c: Emit SSE event for auto-resume -------------------------
    try:
        from app.services.sse_service import sse_manager

        await sse_manager.emit({
            "type": "thread_state_changed",
            "messenger_user_id": customer.messenger_user_id,
            "old_state": "HUMAN_CONTROLLED",
            "new_state": "AI_CONTROLLED",
            "thread_state_pinned": False,
            "source": f"auto_resume_{source}",
            "timestamp": (
                customer.thread_state_updated_at.isoformat()
                if customer.thread_state_updated_at else ""
            ),
        })
    except Exception:
        logger.exception("Failed to emit SSE event for auto-resume")

    return True
