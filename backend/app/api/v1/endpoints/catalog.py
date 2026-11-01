"""
Brands and categories for the admin Inventory page.

Provides:
- ``GET /brands`` / ``GET /categories`` — all names, alphabetical, with how
  many active products use each.
- ``POST /brands`` / ``POST /categories`` — add a new name (case-insensitive
  duplicates are rejected).
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_admin
from app.models.product import Brand, Category, Product

router = APIRouter(tags=["Catalog"])


class NameCreate(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def _not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Name is required.")
        if len(value) > 100:
            raise ValueError("Name must be 100 characters or fewer.")
        return value


class NameResponse(BaseModel):
    id: int
    name: str
    product_count: int = 0


async def _list(db: AsyncSession, model, fk) -> list[NameResponse]:
    counts = dict(
        (
            await db.execute(
                select(fk, func.count()).where(Product.is_active.is_(True)).group_by(fk)
            )
        ).all()
    )
    rows = (await db.execute(select(model).order_by(func.lower(model.name)))).scalars().all()
    return [NameResponse(id=r.id, name=r.name, product_count=counts.get(r.id, 0)) for r in rows]


async def _create(db: AsyncSession, model, label: str, body: NameCreate) -> NameResponse:
    existing = await db.execute(select(model).where(func.lower(model.name) == body.name.lower()))
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "success": False,
                "error": {
                    "code": "DUPLICATE_NAME",
                    "message": f"{label} '{body.name}' already exists.",
                    "details": [],
                },
            },
        )
    row = model(name=body.name)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return NameResponse(id=row.id, name=row.name)


@router.get("/brands", response_model=list[NameResponse])
async def list_brands(db: AsyncSession = Depends(get_db), _: dict = Depends(get_current_admin)):
    return await _list(db, Brand, Product.brand_id)


@router.post("/brands", response_model=NameResponse, status_code=status.HTTP_201_CREATED)
async def create_brand(body: NameCreate, db: AsyncSession = Depends(get_db), _: dict = Depends(get_current_admin)):
    return await _create(db, Brand, "Brand", body)


@router.get("/categories", response_model=list[NameResponse])
async def list_categories(db: AsyncSession = Depends(get_db), _: dict = Depends(get_current_admin)):
    return await _list(db, Category, Product.category_id)


@router.post("/categories", response_model=NameResponse, status_code=status.HTTP_201_CREATED)
async def create_category(body: NameCreate, db: AsyncSession = Depends(get_db), _: dict = Depends(get_current_admin)):
    return await _create(db, Category, "Category", body)
