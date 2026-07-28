from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_admin
from app.models.product import Product
from app.schemas.product import (
    ProductAdminResponse,
    ProductCreate,
    ProductPublicResponse,
    ProductUpdate,
)

router = APIRouter(tags=["Products"])


def _build_error(code: str, message: str) -> dict:
    return {
        "success": False,
        "error": {
            "code": code,
            "message": message,
            "details": [],
        },
    }


@router.get("", response_model=list[ProductAdminResponse])
async def list_products_admin(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    brand_id: int | None = Query(None),
    category_id: int | None = Query(None),
    q: str | None = Query(None),
    admin: dict = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Product)
    if brand_id is not None:
        stmt = stmt.where(Product.brand_id == brand_id)
    if category_id is not None:
        stmt = stmt.where(Product.category_id == category_id)
    if q:
        stmt = stmt.where(
            Product.name.ilike(f"%{q}%") | Product.model_number.ilike(f"%{q}%")
        )
    stmt = stmt.offset(skip).limit(limit)
    result = await db.execute(stmt)
    products = result.scalars().all()
    return [ProductAdminResponse.model_validate(p) for p in products]


@router.post("", response_model=ProductAdminResponse, status_code=status.HTTP_201_CREATED)
async def create_product(
    body: ProductCreate,
    admin: dict = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    if body.selling_price <= body.cost_price:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=_build_error(
                "VALIDATION_ERROR",
                "selling_price must be greater than cost_price.",
            ),
        )

    # Check model_number uniqueness
    existing = await db.execute(
        select(Product).where(Product.model_number == body.model_number)
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_build_error(
                "DUPLICATE_MODEL_NUMBER",
                f"A product with model_number '{body.model_number}' already exists.",
            ),
        )

    product = Product(**body.model_dump())
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return ProductAdminResponse.model_validate(product)


@router.put("/{product_id}", response_model=ProductAdminResponse)
async def update_product(
    product_id: int,
    body: ProductUpdate,
    admin: dict = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_build_error("NOT_FOUND", f"Product with id {product_id} not found."),
        )

    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(product, key, value)
    await db.commit()
    await db.refresh(product)
    return ProductAdminResponse.model_validate(product)


@router.delete("/{product_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_product(
    product_id: int,
    admin: dict = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(select(Product).where(Product.id == product_id))
    product = result.scalar_one_or_none()
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_build_error("NOT_FOUND", f"Product with id {product_id} not found."),
        )
    product.is_active = False
    await db.commit()
    return None


@router.get("/public", response_model=list[ProductPublicResponse])
async def list_products_public(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    brand_id: int | None = Query(None),
    category_id: int | None = Query(None),
    q: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Product).where(Product.is_active == True)
    if brand_id is not None:
        stmt = stmt.where(Product.brand_id == brand_id)
    if category_id is not None:
        stmt = stmt.where(Product.category_id == category_id)
    if q:
        stmt = stmt.where(
            Product.name.ilike(f"%{q}%") | Product.model_number.ilike(f"%{q}%")
        )
    stmt = stmt.offset(skip).limit(limit)
    result = await db.execute(stmt)
    products = result.scalars().all()
    # Build response manually — never leak cost_price
    return [
        ProductPublicResponse(
            id=p.id,
            brand_id=p.brand_id,
            category_id=p.category_id,
            name=p.name,
            model_number=p.model_number,
            description=p.description,
            warranty_months=p.warranty_months,
            specifications=p.specifications,
            is_active=p.is_active,
            selling_price=float(p.selling_price),
            created_at=p.created_at,
        )
        for p in products
    ]


