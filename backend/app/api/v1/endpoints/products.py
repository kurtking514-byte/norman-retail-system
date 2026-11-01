from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.security import get_current_admin
from app.models.product import Product
from app.services import product_import_service as importer
from app.schemas.product import (
    ProductAdminResponse,
    ProductCreate,
    ProductPublicResponse,
    ProductUpdate,
)

router = APIRouter(tags=["Products"])

# Every product field is optional in the admin form; a product saved without a
# name still needs something to show in lists and to the chatbot.
UNTITLED_PRODUCT = "Untitled product"


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
    limit: int = Query(1000, ge=1, le=5000),
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


def _as_float(value) -> float | None:
    return None if value is None else float(value)


def _check_prices(cost: float | None, price: float | None) -> None:
    if cost is not None and price is not None and price <= cost:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=_build_error("VALIDATION_ERROR", "selling_price must be greater than cost_price."),
        )


async def _check_model_number_free(db: AsyncSession, model_number: str | None, product_id: int | None = None) -> None:
    if not model_number:
        return
    clash = (await db.execute(select(Product).where(Product.model_number == model_number))).scalar_one_or_none()
    if clash is not None and clash.id != product_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=_build_error(
                "DUPLICATE_MODEL_NUMBER",
                f"A product with model_number '{model_number}' already exists.",
            ),
        )


@router.post("", response_model=ProductAdminResponse, status_code=status.HTTP_201_CREATED)
async def create_product(
    body: ProductCreate,
    admin: dict = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    _check_prices(body.cost_price, body.selling_price)
    await _check_model_number_free(db, body.model_number)

    data = body.model_dump()
    data["name"] = data["name"] or UNTITLED_PRODUCT
    product = Product(**data)
    db.add(product)
    await db.commit()
    await db.refresh(product)
    return ProductAdminResponse.model_validate(product)


MAX_IMPORT_BYTES = 5 * 1024 * 1024


@router.get("/import/template")
async def download_import_template(admin: dict = Depends(get_current_admin)):
    """Excel template for bulk-importing phones, with example rows and instructions."""
    return Response(
        content=importer.build_template_xlsx(),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="phone-import-template.xlsx"'},
    )


@router.post("/import")
async def import_products(
    file: UploadFile = File(...),
    dry_run: bool = Query(True, description="Preview only; nothing is saved."),
    admin: dict = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Create/update phones and stock from an .xlsx or .csv spreadsheet.

    Always preview first (``dry_run=true``). With ``dry_run=false`` the import
    is applied only if every row is valid.
    """
    content = await file.read(MAX_IMPORT_BYTES + 1)
    if len(content) > MAX_IMPORT_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=_build_error("FILE_TOO_LARGE", "The file is larger than 5 MB. Split it into smaller files."),
        )
    try:
        results = importer.parse_spreadsheet(file.filename, content)
    except importer.ImportFileError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=_build_error("INVALID_FILE", str(exc)),
        )

    existing = await importer.plan_import(db, results)
    summary = importer.summarize(results)
    applied = False
    stock = {"stock_added": 0, "stock_removed": 0}
    if not dry_run:
        if summary["error"]:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=_build_error("ROWS_HAVE_ERRORS", "Fix the rows with errors before importing."),
            )
        stock = await importer.apply_import(db, results, existing)
        applied = True

    return {
        "applied": applied,
        "summary": {**summary, **stock},
        "rows": [
            {
                "row": r.row,
                "model_number": r.model_number,
                "name": r.name,
                "action": r.action,
                "errors": r.errors,
                "warnings": r.warnings,
                "stock_current": r.stock_current,
                "stock_target": r.stock_target,
            }
            for r in results
        ],
    }


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
    if "name" in update_data:
        update_data["name"] = update_data["name"] or UNTITLED_PRODUCT
    _check_prices(
        update_data.get("cost_price", _as_float(product.cost_price)),
        update_data.get("selling_price", _as_float(product.selling_price)),
    )
    await _check_model_number_free(db, update_data.get("model_number"), product.id)
    for key, value in update_data.items():
        setattr(product, key, value)
    await db.commit()
    await db.refresh(product)
    return ProductAdminResponse.model_validate(product)


class StockUpdate(BaseModel):
    in_stock: int = Field(ge=0, le=10000)


@router.put("/{product_id}/stock")
async def set_product_stock(
    product_id: int,
    body: StockUpdate,
    admin: dict = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Set how many units are in the store by adding/removing untracked units."""
    from app.services.stock_service import in_stock_counts, set_in_stock

    product = (await db.execute(select(Product).where(Product.id == product_id))).scalar_one_or_none()
    if product is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=_build_error("NOT_FOUND", f"Product with id {product_id} not found."),
        )
    current = (await in_stock_counts(db, [product_id])).get(product_id, 0)
    added, removed, warning = await set_in_stock(db, product_id, current, body.in_stock)
    await db.commit()
    return {
        "in_stock": current + added - removed,
        "added": added,
        "removed": removed,
        "warning": warning,
    }


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
            selling_price=_as_float(p.selling_price),
            created_at=p.created_at,
        )
        for p in products
    ]


