from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_admin
from app.models.product import Inventory, Product
from app.schemas.product import (
    InventoryItemCreate,
    InventoryItemResponse,
    InventoryStatusUpdate,
)

router = APIRouter(tags=["Inventory"])

VALID_STATUSES = {"In Stock", "Sold", "Reserved", "In Repair"}


def _build_error(code: str, message: str) -> dict:
    return {
        "success": False,
        "error": {
            "code": code,
            "message": message,
            "details": [],
        },
    }


@router.get("", response_model=list[InventoryItemResponse])
async def list_inventory(
    product_id: int | None = Query(None),
    status: str | None = Query(None),
    admin: dict = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Inventory)
    if product_id is not None:
        stmt = stmt.where(Inventory.product_id == product_id)
    if status is not None:
        stmt = stmt.where(Inventory.status == status)
    result = await db.execute(stmt)
    items = result.scalars().all()
    return [InventoryItemResponse.model_validate(item) for item in items]


@router.post("", response_model=InventoryItemResponse, status_code=status.HTTP_201_CREATED)
async def create_inventory_item(
    body: InventoryItemCreate,
    admin: dict = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    # Verify product exists
    product_result = await db.execute(
        select(Product).where(Product.id == body.product_id)
    )
    if product_result.scalar_one_or_none() is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_build_error(
                "NOT_FOUND",
                f"Product with id {body.product_id} not found.",
            ),
        )

    item = Inventory(**body.model_dump())
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return InventoryItemResponse.model_validate(item)


@router.patch("/{item_id}/status", response_model=InventoryItemResponse)
async def update_inventory_status(
    item_id: int,
    body: InventoryStatusUpdate,
    admin: dict = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    if body.status not in VALID_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=_build_error(
                "VALIDATION_ERROR",
                f"Invalid status '{body.status}'. Allowed values: {', '.join(sorted(VALID_STATUSES))}.",
            ),
        )

    result = await db.execute(select(Inventory).where(Inventory.id == item_id))
    item = result.scalar_one_or_none()
    if item is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_build_error(
                "NOT_FOUND",
                f"Inventory item with id {item_id} not found.",
            ),
        )

    item.status = body.status
    await db.commit()
    await db.refresh(item)
    return InventoryItemResponse.model_validate(item)

