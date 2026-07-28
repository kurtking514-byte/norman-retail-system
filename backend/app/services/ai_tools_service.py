"""
Tool functions for Gemini function-calling in the chat interface.

Each function is designed to be registered as a Gemini tool declaration,
allowing the AI model to call real backend operations during a conversation
with a customer.

All functions are async and accept an ``AsyncSession`` as the first parameter
(for database access) plus keyword arguments matching the tool parameters
Gemini will provide.
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.models.product import Inventory, Product
from app.models.reservation import Reservation
from app.models.repair import RepairRequest
from app.api.v1.endpoints.reservations import (
    create_reservation_for_customer,
    _reserve_one_inventory,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Product lookup helper (shared between tools)
# ---------------------------------------------------------------------------


async def _find_product(
    db: AsyncSession,
    product_name_or_model: str,
) -> Product | None:
    """Search for a product by name or model_number (case-insensitive partial match).

    Returns the first matching ``Product`` or ``None`` if no match found.
    """
    term = f"%{product_name_or_model}%"
    result = await db.execute(
        select(Product).where(
            Product.is_active.is_(True),
            Product.name.ilike(term) | Product.model_number.ilike(term),
        ).limit(1)
    )
    return result.scalar_one_or_none()


# ---------------------------------------------------------------------------
# Tool 1: Check product availability
# ---------------------------------------------------------------------------


async def check_product_availability(
    db: AsyncSession,
    product_name_or_model: str,
) -> dict:
    """Check real-time stock availability for a product.

    Use this tool when a customer asks whether a specific product is in stock,
    how many units are available, or what the selling price is.

    **Never include cost_price** in the response.

    Args:
        db: Database session.
        product_name_or_model: Full or partial product name or model number
            (e.g. "iPhone 13", "S23 Ultra", "XG-100").

    Returns:
        A dict with availability information or an error message.
    """
    product = await _find_product(db, product_name_or_model)

    if product is None:
        return {
            "found": False,
            "message": f"No product found matching '{product_name_or_model}'. "
                       "Please ask the customer to check the product name or model number.",
        }

    # Count In Stock inventory
    count_result = await db.execute(
        select(func.count(Inventory.id)).where(
            Inventory.product_id == product.id,
            Inventory.status == "In Stock",
        )
    )
    in_stock_count = count_result.scalar() or 0

    return {
        "found": True,
        "product_name": product.name,
        "model_number": product.model_number,
        "selling_price": float(product.selling_price),
        "in_stock_count": in_stock_count,
    }


# ---------------------------------------------------------------------------
# Tool 2: Create a reservation via chat
# ---------------------------------------------------------------------------


async def create_reservation_via_chat(
    db: AsyncSession,
    messenger_user_id: str,
    product_name_or_model: str,
) -> dict:
    """Reserve/hold a product for a customer based on their Messenger user ID.

    Use this tool ONLY when a customer has explicitly and clearly asked to
    reserve, hold, or put aside a specific item — NOT just when they ask
    about its availability or price. Only one reservation per customer per
    24 hours is allowed.

    Args:
        db: Database session.
        messenger_user_id: The customer's Messenger sender ID (e.g. from
            ``sender.id`` in the webhook payload).
        product_name_or_model: The name or model number of the product the
            customer wants to reserve.

    Returns:
        A dict with success status and reservation details, or a failure
        reason.
    """
    # ---- Step 1: Look up the product ----------------------------------------
    product = await _find_product(db, product_name_or_model)
    if product is None:
        return {
            "success": False,
            "reason": f"I couldn't find a product matching '{product_name_or_model}'. "
                      "Could you please double-check the product name or model number?",
        }

    # ---- Step 2: Look up the customer by messenger_user_id -------------------
    result = await db.execute(
        select(Customer).where(Customer.messenger_user_id == messenger_user_id)
    )
    customer = result.scalar_one_or_none()
    if customer is None:
        return {
            "success": False,
            "reason": "I couldn't find your customer account. Please contact the "
                      "shop directly so we can help you with a reservation.",
        }

    # ---- Step 3: 24-hour rolling guardrail ----------------------------------
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    recent_result = await db.execute(
        select(func.count(Reservation.id)).where(
            Reservation.customer_id == customer.id,
            Reservation.status.in_(["Pending", "Confirmed"]),
            Reservation.reservation_date >= since,
        )
    )
    recent_count = recent_result.scalar() or 0
    if recent_count > 0:
        return {
            "success": False,
            "reason": "You already have a pending or confirmed reservation created "
                      "in the last 24 hours. For additional reservations, please "
                      "contact the shop directly so we can assist you personally.",
        }

    # ---- Step 4: Check inventory availability --------------------------------
    inv_item = await _reserve_one_inventory(db, product.id)
    if inv_item is None:
        return {
            "success": False,
            "reason": f"Sorry, '{product.name}' is currently out of stock and "
                      "cannot be reserved at this time.",
        }
    # Rollback the tentative reserve so we can use the shared function cleanly
    inv_item.status = "In Stock"

    # ---- Step 5: Create the reservation using shared core logic --------------
    try:
        reservation = await create_reservation_for_customer(
            db,
            product_id=product.id,
            customer=customer,
            product=product,
            expiry_hours=48,
            notes="Created via Messenger chat",
        )
    except Exception as exc:
        logger.exception("Failed to create reservation via chat: %s", exc)
        return {
            "success": False,
            "reason": "Sorry, something went wrong while creating your reservation. "
                      "Please try again or contact the shop directly.",
        }

    return {
        "success": True,
        "reservation_id": reservation.id,
        "product_name": product.name,
        "expiry_date": reservation.expiry_date.isoformat(),
    }


# ---------------------------------------------------------------------------
# Tool 3: Check repair status
# ---------------------------------------------------------------------------


async def check_repair_status(
    db: AsyncSession,
    messenger_user_id: str,
) -> dict:
    """Look up the status of a customer's most recent repair request.

    Use this tool when a customer asks about the status of their repair,
    when their phone will be ready, or any follow-up on a device they left
    for repair.

    Args:
        db: Database session.
        messenger_user_id: The customer's Messenger sender ID.

    Returns:
        A dict with repair details or a not-found message.
    """
    # ---- Look up the customer -----------------------------------------------
    result = await db.execute(
        select(Customer).where(Customer.messenger_user_id == messenger_user_id)
    )
    customer = result.scalar_one_or_none()

    if customer is None:
        return {
            "found": False,
            "message": "No repair requests found for this customer.",
        }

    # ---- Find most recent repair request ------------------------------------
    repair_result = await db.execute(
        select(RepairRequest)
        .where(RepairRequest.customer_id == customer.id)
        .order_by(RepairRequest.updated_at.desc())
        .limit(1)
    )
    repair = repair_result.scalar_one_or_none()

    if repair is None:
        return {
            "found": False,
            "message": "No repair requests found for this customer.",
        }

    return {
        "found": True,
        "device_model": repair.device_model,
        "status": repair.status,
        "estimated_cost": float(repair.estimated_cost) if repair.estimated_cost else 0.0,
        "notes": repair.notes or "",
    }
