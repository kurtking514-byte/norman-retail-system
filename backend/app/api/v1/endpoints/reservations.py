"""
Admin-protected CRUD endpoints for product reservations.

Business logic:
- Reservations hold inventory — creating a reservation flips one ``In Stock``
  Inventory row to ``Reserved``.
- Claiming a reservation flips that row to ``Sold``.
- Cancelling a reservation flips it back to ``In Stock``.
- Stale (expired) reservations are auto-cancelled at the top of every
  ``GET /reservations`` call (instead of a background scheduler).
"""

import logging
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_admin
from app.models.customer import Customer
from app.models.product import Inventory, Product
from app.models.reservation import Reservation
from app.schemas.reservation import (
    ReservationCreate,
    ReservationResponse,
    ReservationUpdate,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Reservations"])


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
# Expiry helper
# ---------------------------------------------------------------------------


async def expire_stale_reservations(db: AsyncSession) -> int:
    """Find all expired ``Pending`` reservations and cancel them.

    For each expired reservation, release the held inventory back to
    ``In Stock``.

    Returns the number of reservations that were expired.
    """
    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(Reservation).where(
            Reservation.status == "Pending",
            Reservation.expiry_date < now,
        )
    )
    stale = list(result.scalars().all())

    for reservation in stale:
        reservation.status = "Cancelled"
        # Release held inventory back to In Stock
        inv_result = await db.execute(
            select(Inventory).where(
                Inventory.product_id == reservation.product_id,
                Inventory.status == "Reserved",
            ).limit(1)
        )
        inv_item = inv_result.scalar_one_or_none()
        if inv_item is not None:
            inv_item.status = "In Stock"

    if stale:
        await db.commit()

    for r in stale:
        await db.refresh(r)

    return len(stale)


# ---------------------------------------------------------------------------
# Inventory helpers
# ---------------------------------------------------------------------------


async def _reserve_one_inventory(
    db: AsyncSession,
    product_id: int,
) -> Inventory | None:
    """Find one ``In Stock`` inventory row for *product_id* and mark it ``Reserved``.

    Returns the updated ``Inventory`` row or ``None`` if none available.
    Caller is responsible for committing.
    """
    result = await db.execute(
        select(Inventory).where(
            Inventory.product_id == product_id,
            Inventory.status == "In Stock",
        ).limit(1)
    )
    item = result.scalar_one_or_none()
    if item is not None:
        item.status = "Reserved"
    return item


async def _release_one_inventory(
    db: AsyncSession,
    product_id: int,
) -> Inventory | None:
    """Find one ``Reserved`` inventory row for *product_id* and mark it ``In Stock``.

    Returns the updated ``Inventory`` row or ``None`` if none found.
    Caller is responsible for committing.
    """
    result = await db.execute(
        select(Inventory).where(
            Inventory.product_id == product_id,
            Inventory.status == "Reserved",
        ).limit(1)
    )
    item = result.scalar_one_or_none()
    if item is not None:
        item.status = "In Stock"
    return item


async def _sell_one_inventory(
    db: AsyncSession,
    product_id: int,
) -> Inventory | None:
    """Find one ``Reserved`` inventory row for *product_id* and mark it ``Sold``.

    Returns the updated ``Inventory`` row or ``None`` if none found.
    Caller is responsible for committing.
    """
    result = await db.execute(
        select(Inventory).where(
            Inventory.product_id == product_id,
            Inventory.status == "Reserved",
        ).limit(1)
    )
    item = result.scalar_one_or_none()
    if item is not None:
        item.status = "Sold"
    return item


# ---------------------------------------------------------------------------
# Shared core: create reservation + hold inventory (extracted for AI tools)
# ---------------------------------------------------------------------------


async def create_reservation_for_customer(
    db: AsyncSession,
    *,
    product_id: int,
    customer: Customer,
    product: Product,
    expiry_hours: int = 48,
    notes: str | None = None,
) -> Reservation:
    """Create a reservation and hold one inventory item.

    Caller MUST have already verified product exists and inventory is
    available (``_reserve_one_inventory`` returns ``None`` otherwise).

    This is the shared core used by both the REST endpoint and the
    AI tool-calling service.
    """
    now = datetime.now(timezone.utc)
    reservation = Reservation(
        customer_id=customer.id,
        product_id=product_id,
        reservation_date=now,
        expiry_date=now + timedelta(hours=expiry_hours),
        status="Pending",
        notes=notes,
    )
    db.add(reservation)
    await _reserve_one_inventory(db, product_id)
    await db.commit()
    await db.refresh(reservation)
    return reservation


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/reservations", response_model=list[ReservationResponse])
async def list_reservations(
    response: Response,
    status_filter: str | None = Query(None, alias="status"),
    customer_id: int | None = Query(None),
    product_id: int | None = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    admin: dict = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """List reservations, auto-expiring stale ones first.

    Stale ``Pending`` reservations whose ``expiry_date`` has passed are
    auto-cancelled and their inventory is released before the query runs.
    The count of expired reservations is returned in the
    ``X-Expired-Count`` response header.
    """
    expired_count = await expire_stale_reservations(db)
    response.headers["X-Expired-Count"] = str(expired_count)

    stmt = select(Reservation)
    if status_filter is not None:
        stmt = stmt.where(Reservation.status == status_filter)
    if customer_id is not None:
        stmt = stmt.where(Reservation.customer_id == customer_id)
    if product_id is not None:
        stmt = stmt.where(Reservation.product_id == product_id)
    stmt = stmt.offset(skip).limit(limit)

    result = await db.execute(stmt)
    reservations = result.scalars().all()
    return [ReservationResponse.model_validate(r) for r in reservations]


@router.post("/reservations", response_model=ReservationResponse, status_code=status.HTTP_201_CREATED)
async def create_reservation(
    body: ReservationCreate,
    admin: dict = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Create a new reservation.

    Accepts either an existing ``customer_id`` OR new-customer fields
    (``first_name``, ``last_name``, ``phone_number``), validated by
    the schema's ``@model_validator``.

    Business-rule checks:
    - Product must exist.
    - At least one ``In Stock`` inventory row must be available.
    """
    # ---- Check product exists -----------------------------------------------
    product_result = await db.execute(
        select(Product).where(Product.id == body.product_id)
    )
    product = product_result.scalar_one_or_none()
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_build_error(
                "NOT_FOUND",
                f"Product with id {body.product_id} not found.",
            ),
        )

    # ---- Check inventory availability ---------------------------------------
    inv_result = await db.execute(
        select(Inventory).where(
            Inventory.product_id == body.product_id,
            Inventory.status == "In Stock",
        ).limit(1)
    )
    available = inv_result.scalar_one_or_none()
    if available is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_build_error(
                "OUT_OF_STOCK",
                f"Product '{product.name}' (id={body.product_id}) has no "
                f"items currently In Stock. Cannot reserve.",
            ),
        )

    # ---- Resolve or create customer -----------------------------------------
    customer = await _resolve_customer(
        db,
        customer_id=body.customer_id,
        first_name=body.first_name,
        last_name=body.last_name,
        phone_number=body.phone_number,
    )

    # ---- Delegate to shared core --------------------------------------------
    reservation = await create_reservation_for_customer(
        db,
        product_id=body.product_id,
        customer=customer,
        product=product,
        expiry_hours=body.expiry_hours,
        notes=body.notes,
    )
    return ReservationResponse.model_validate(reservation)


@router.put("/reservations/{reservation_id}", response_model=ReservationResponse)
async def update_reservation(
    reservation_id: int,
    body: ReservationUpdate,
    admin: dict = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Update a reservation's status and/or notes.

    Special inventory handling by target status:

    - ``Confirmed``: just updates the status (staff confirmed with customer).
    - ``Claimed``: also flips the held Inventory row from ``Reserved`` to
      ``Sold``.  If no matching reserved inventory row is found, a warning
      is logged but the status change is **not** blocked — this is a
      data-integrity edge case.
    - ``Cancelled``: releases the held Inventory row back to ``In Stock``.
    """
    result = await db.execute(
        select(Reservation).where(Reservation.id == reservation_id)
    )
    reservation = result.scalar_one_or_none()
    if reservation is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_build_error(
                "NOT_FOUND",
                f"Reservation with id {reservation_id} not found.",
            ),
        )

    # Apply notes update regardless
    if body.notes is not None:
        reservation.notes = body.notes

    if body.status is not None:
        target_status = body.status

        if target_status == "Confirmed":
            reservation.status = target_status

        elif target_status == "Claimed":
            # Flip Reserved → Sold
            item = await _sell_one_inventory(db, reservation.product_id)
            if item is None:
                logger.warning(
                    "Reservation %d (product_id=%d) claimed but no Reserved "
                    "inventory row found. Status changed anyway.",
                    reservation_id,
                    reservation.product_id,
                )
            reservation.status = target_status

        elif target_status == "Cancelled":
            # Release Reserved → In Stock
            item = await _release_one_inventory(db, reservation.product_id)
            if item is None:
                logger.warning(
                    "Reservation %d (product_id=%d) cancelled but no Reserved "
                    "inventory row found to release.",
                    reservation_id,
                    reservation.product_id,
                )
            reservation.status = target_status

        else:
            # Pending — just update status
            reservation.status = target_status

    await db.commit()
    await db.refresh(reservation)
    return ReservationResponse.model_validate(reservation)
