"""
Notification queue endpoints for the staff Live Chat dashboard.

Provides:
- ``GET /notifications`` — list notification queue entries, filterable by
  status. Default: shows only ``Pending`` items (the actionable queue).
- ``PATCH /notifications/{id}`` — update the status of a notification
  (e.g. mark a handoff as "Resolved").
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_admin
from app.models.notification import NotificationQueue
from app.schemas.conversation import (
    NotificationResponse,
    NotificationUpdateRequest,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Notifications"])


# ---------------------------------------------------------------------------
# GET /notifications — list notification queue entries
# ---------------------------------------------------------------------------


@router.get("/notifications", response_model=list[NotificationResponse])
async def list_notifications(
    status: str | None = Query(
        None,
        description="Filter by status. Defaults to 'Pending' if omitted.",
    ),
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_admin),
):
    """Return notification queue entries, ordered most recent first.

    If ``status`` is not provided, only ``Pending`` items are returned
    (the default actionable queue).
    """
    filter_status = status if status is not None else "Pending"

    stmt = (
        select(NotificationQueue)
        .where(NotificationQueue.status == filter_status)
        .order_by(desc(NotificationQueue.created_at))
    )
    result = await db.execute(stmt)
    rows = result.scalars().all()

    return [
        NotificationResponse(
            id=row.id,
            recipient_id=row.recipient_id,
            channel=row.channel,
            payload=row.payload,
            status=row.status,
            created_at=row.created_at.isoformat() if row.created_at else "",
        )
        for row in rows
    ]


# ---------------------------------------------------------------------------
# PATCH /notifications/{id} — update notification status
# ---------------------------------------------------------------------------


@router.patch(
    "/notifications/{notification_id}",
    response_model=NotificationResponse,
)
async def update_notification_status(
    notification_id: int,
    body: NotificationUpdateRequest,
    db: AsyncSession = Depends(get_db),
    _: str = Depends(get_current_admin),
):
    """Update the status of a notification queue item.

    Typical use: staff marks a pending handoff as ``Resolved`` once
    they have handled it manually.
    """
    result = await db.execute(
        select(NotificationQueue).where(NotificationQueue.id == notification_id)
    )
    nq = result.scalar_one_or_none()

    if nq is None:
        raise HTTPException(
            status_code=404,
            detail={
                "success": False,
                "error": {
                    "code": "NOT_FOUND",
                    "message": (
                        f"Notification with id '{notification_id}' not found."
                    ),
                    "details": [],
                },
            },
        )

    nq.status = body.status
    await db.commit()
    await db.refresh(nq)

    return NotificationResponse(
        id=nq.id,
        recipient_id=nq.recipient_id,
        channel=nq.channel,
        payload=nq.payload,
        status=nq.status,
        created_at=nq.created_at.isoformat() if nq.created_at else "",
    )
