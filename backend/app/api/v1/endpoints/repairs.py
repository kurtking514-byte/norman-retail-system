"""
Admin-protected CRUD endpoints for repair requests.

Business logic:
- Repair requests are not tied to product inventory — they track device
  repairs independently.
- Records move through a defined status lifecycle: Pending → Diagnosis →
  In Progress → Ready for Pickup → Released (or Cancelled at any point).
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_admin
from app.models.customer import Customer
from app.models.repair import RepairRequest
from app.schemas.repair import (
    RepairRequestCreate,
    RepairRequestResponse,
    RepairRequestUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Repairs"])


def _build_error(code: str, message: str) -> dict:
    return {
        "success": False,
        "error": {
            "code": code,
            "message": message,
            "details": [],
        },
    }


# ---------------------------------------------------------------------------
# Customer resolution helper
# ---------------------------------------------------------------------------


async def _resolve_customer(
    db: AsyncSession,
    *,
    customer_id: int | None = None,
    first_name: str | None = None,
    last_name: str | None = None,
    phone_number: str | None = None,
) -> Customer:
    """Return an existing Customer or create a new one.

    *customer_id* and the new-customer fields (*first_name*, *last_name*,
    *phone_number*) are mutually exclusive — callers must validate that
    exactly one mode is used before calling this function.

    Raises ``HTTPException(409)`` if *phone_number* already belongs to a
    different customer.
    """
    if customer_id is not None:
        result = await db.execute(select(Customer).where(Customer.id == customer_id))
        customer = result.scalar_one_or_none()
        if customer is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=_build_error(
                    "NOT_FOUND",
                    f"Customer with id {customer_id} not found.",
                ),
            )
        return customer

    # Inline new-customer creation
    if phone_number:
        result = await db.execute(
            select(Customer).where(Customer.phone_number == phone_number)
        )
        existing = result.scalar_one_or_none()
        if existing is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=_build_error(
                    "DUPLICATE_PHONE_NUMBER",
                    f"A customer with phone number '{phone_number}' already exists "
                    f"(id={existing.id}). Use that customer_id instead.",
                ),
            )

    customer = Customer(
        first_name=first_name,
        last_name=last_name,
        phone_number=phone_number or f"walkin-{datetime.now(timezone.utc).timestamp()}",
    )
    db.add(customer)
    await db.commit()
    await db.refresh(customer)
    return customer


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/repairs", response_model=list[RepairRequestResponse])
async def list_repairs(
    status_filter: str | None = Query(None, alias="status"),
    customer_id: int | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    admin: dict = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """List repair requests, filterable by status and/or customer_id."""
    stmt = select(RepairRequest)
    if status_filter is not None:
        stmt = stmt.where(RepairRequest.status == status_filter)
    if customer_id is not None:
        stmt = stmt.where(RepairRequest.customer_id == customer_id)
    stmt = stmt.offset(skip).limit(limit)

    result = await db.execute(stmt)
    repairs = result.scalars().all()
    return [RepairRequestResponse.model_validate(r) for r in repairs]


@router.post("/repairs", response_model=RepairRequestResponse, status_code=status.HTTP_201_CREATED)
async def create_repair(
    body: RepairRequestCreate,
    admin: dict = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Create a new repair request.

    Accepts either an existing ``customer_id`` OR new-customer fields
    (``first_name``, ``last_name``, ``phone_number``), validated by
    the schema's ``@model_validator``.
    """
    # Resolve or create customer
    customer = await _resolve_customer(
        db,
        customer_id=body.customer_id,
        first_name=body.first_name,
        last_name=body.last_name,
        phone_number=body.phone_number,
    )

    now = datetime.now(timezone.utc).replace(tzinfo=None)
    repair = RepairRequest(
        customer_id=customer.id,
        device_model=body.device_model,
        issue_description=body.issue_description,
        estimated_cost=body.estimated_cost,
        status="Pending",
        notes=body.notes,
        updated_at=now,
    )
    db.add(repair)
    await db.commit()
    await db.refresh(repair)
    return RepairRequestResponse.model_validate(repair)


@router.put("/repairs/{repair_id}", response_model=RepairRequestResponse)
async def update_repair(
    repair_id: int,
    body: RepairRequestUpdate,
    admin: dict = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update a repair request's status, estimated_cost, and/or notes.

    ``status`` is validated against the allowed set: Pending, Diagnosis,
    In Progress, Ready for Pickup, Released, Cancelled.

    ``updated_at`` is always set to now on any change.
    """
    result = await db.execute(
        select(RepairRequest).where(RepairRequest.id == repair_id)
    )
    repair = result.scalar_one_or_none()
    if repair is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_build_error(
                "NOT_FOUND",
                f"Repair request with id {repair_id} not found.",
            ),
        )

    if body.status is not None:
        repair.status = body.status
    if body.estimated_cost is not None:
        repair.estimated_cost = body.estimated_cost
    if body.notes is not None:
        repair.notes = body.notes

    repair.updated_at = datetime.now(timezone.utc).replace(tzinfo=None)
    await db.commit()
    await db.refresh(repair)
    return RepairRequestResponse.model_validate(repair)
