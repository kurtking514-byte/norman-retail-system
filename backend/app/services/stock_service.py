"""
Helpers for "how many units of this product are in the store".

Stock is stored as one ``inventory`` row per unit. These helpers count
"In Stock" units and move the count to a target by adding untracked units or
removing them. Units with a serial number are never removed automatically —
staff should mark those Sold instead.
"""

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Inventory


async def in_stock_counts(db: AsyncSession, product_ids: list[int] | None = None) -> dict[int, int]:
    """In-stock unit count per product id (products with none are omitted)."""
    stmt = (
        select(Inventory.product_id, func.count())
        .where(Inventory.status == "In Stock")
        .group_by(Inventory.product_id)
    )
    if product_ids is not None:
        if not product_ids:
            return {}
        stmt = stmt.where(Inventory.product_id.in_(product_ids))
    return dict((await db.execute(stmt)).all())


async def set_in_stock(db: AsyncSession, product_id: int, current: int, target: int) -> tuple[int, int, str | None]:
    """Add or remove untracked "In Stock" units so the count becomes ``target``.

    Does not commit. Returns ``(added, removed, warning)``.
    """
    diff = target - current
    if diff > 0:
        db.add_all(Inventory(product_id=product_id, status="In Stock") for _ in range(diff))
        return diff, 0, None
    if diff == 0:
        return 0, 0, None

    result = await db.execute(
        select(Inventory)
        .where(
            Inventory.product_id == product_id,
            Inventory.status == "In Stock",
            Inventory.serial_number.is_(None),
        )
        .order_by(Inventory.id.desc())
        .limit(-diff)
    )
    units = result.scalars().all()
    for unit in units:
        await db.delete(unit)
    warning = None
    if len(units) < -diff:
        warning = (
            f"Only {len(units)} unit(s) could be removed — the rest have serial numbers. "
            "Mark them Sold in Inventory instead."
        )
    return 0, len(units), warning
