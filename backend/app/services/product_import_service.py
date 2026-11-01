"""
Bulk product import from an Excel (.xlsx) or CSV spreadsheet.

One row per phone model, matched on ``Model Number``:
- new model numbers create a product, existing ones are updated;
- brands and categories are created by name if they don't exist yet;
- spec columns (and any extra column you add) go into ``specifications``;
- ``Stock Qty`` is the number of units in the store right now — the import
  adds or removes "In Stock" units to match. Leave it blank to keep stock as is.

Every import runs as a preview first. Nothing is saved unless every row is
valid, so a file never half-applies.
"""

import csv
import io
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.product import Brand, Category, Product
from app.services.stock_service import in_stock_counts, set_in_stock

MAX_ROWS = 5000

# Spreadsheet header -> internal field. Headers are matched case-insensitively.
CORE_COLUMNS = {
    "brand": "brand",
    "category": "category",
    "name": "name",
    "model number": "model_number",
    "cost price": "cost_price",
    "selling price": "selling_price",
    "stock qty": "stock_qty",
    "warranty (months)": "warranty_months",
    "description": "description",
    "active": "is_active",
}
REQUIRED = ["brand", "category", "name", "model_number", "cost_price", "selling_price"]
SPEC_COLUMNS = ["RAM", "Storage", "Screen", "Battery", "Main Camera", "Chipset", "Colors"]

TEMPLATE_HEADERS = [
    "Brand", "Category", "Name", "Model Number", "Cost Price", "Selling Price",
    "Stock Qty", "Warranty (months)", "Description", *SPEC_COLUMNS, "Active",
]
TEMPLATE_EXAMPLES = [
    ["Samsung", "Smartphones", "Galaxy A55 5G 8/256GB", "SM-A556E-256", 18500, 22990,
     4, 12, "Awesome Navy", "8GB", "256GB", '6.6" Super AMOLED 120Hz', "5000mAh",
     "50MP", "Exynos 1480", "Navy, Lilac, Iceblue", "Y"],
    ["Apple", "Smartphones", "iPhone 15 128GB", "MTP03ZP/A", 44000, 49990,
     2, 12, "", "6GB", "128GB", '6.1" Super Retina XDR', "3349mAh",
     "48MP", "A16 Bionic", "Black, Blue, Pink", "Y"],
]
INSTRUCTIONS = [
    "How to fill in the Phones sheet",
    "",
    "One row per phone model. Columns marked * are required.",
    "Model Number* is the unique key: re-uploading a file updates phones with the same model number.",
    "Brand* and Category* are created automatically if they don't exist yet.",
    "Cost Price* and Selling Price* are numbers in pesos (no ₱ sign needed). Selling must be higher than cost.",
    "Stock Qty = units in the store right now. Leave blank to keep the current stock.",
    "Warranty (months) defaults to 12.",
    "RAM, Storage, Screen, Battery, Main Camera, Chipset, Colors are specs shown to staff and the chatbot.",
    "You can add more spec columns (e.g. 'Weight', 'OS') — any extra column is saved as a spec.",
    "Active: Y (default) or N to hide the phone from customers.",
    "Delete the two example rows before uploading your own data.",
]


class ImportFileError(ValueError):
    """The file itself can't be read (wrong type, missing columns, too big)."""


@dataclass
class RowResult:
    row: int
    model_number: str = ""
    name: str = ""
    action: str = "error"  # create | update | unchanged | error
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    stock_current: int | None = None
    stock_target: int | None = None
    data: dict = field(default_factory=dict, repr=False)


# ---------------------------------------------------------------------------
# Template
# ---------------------------------------------------------------------------


def build_template_xlsx() -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    wb = Workbook()
    ws = wb.active
    ws.title = "Phones"
    ws.append([f"{h}*" if CORE_COLUMNS.get(h.lower()) in REQUIRED else h for h in TEMPLATE_HEADERS])
    for row in TEMPLATE_EXAMPLES:
        ws.append(row)
    header_fill = PatternFill("solid", fgColor="1E293B")
    for cell in ws[1]:
        cell.font = Font(bold=True, color="FFFFFF")
        cell.fill = header_fill
    for col in ws.columns:
        width = max(len(str(c.value or "")) for c in col) + 2
        ws.column_dimensions[col[0].column_letter].width = min(max(width, 10), 40)
    ws.freeze_panes = "A2"

    info = wb.create_sheet("Instructions")
    for line in INSTRUCTIONS:
        info.append([line])
    info["A1"].font = Font(bold=True, size=13)
    info.column_dimensions["A"].width = 110

    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------


def _read_rows(filename: str, content: bytes) -> list[list]:
    name = (filename or "").lower()
    if name.endswith(".xlsx"):
        from openpyxl import load_workbook

        try:
            wb = load_workbook(io.BytesIO(content), read_only=True, data_only=True)
        except Exception as exc:
            raise ImportFileError("Couldn't open the Excel file. Save it as .xlsx and try again.") from exc
        ws = wb["Phones"] if "Phones" in wb.sheetnames else wb.worksheets[0]
        return [list(r) for r in ws.iter_rows(values_only=True)]
    if name.endswith(".csv"):
        text = content.decode("utf-8-sig", errors="replace")
        return [row for row in csv.reader(io.StringIO(text))]
    raise ImportFileError("Upload an Excel (.xlsx) or CSV (.csv) file.")


def _clean(value) -> str:
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip()


def _number(value: str, label: str, errors: list[str], integer: bool = False):
    text = value.replace("₱", "").replace(",", "").replace("PHP", "").strip()
    try:
        number = float(text)
    except ValueError:
        errors.append(f"{label} must be a number (got '{value}').")
        return None
    if number < 0:
        errors.append(f"{label} can't be negative.")
        return None
    if integer:
        if not number.is_integer():
            errors.append(f"{label} must be a whole number.")
            return None
        return int(number)
    return round(number, 2)


def parse_spreadsheet(filename: str, content: bytes) -> list[RowResult]:
    rows = _read_rows(filename, content)
    # Skip leading blank rows to find the header
    while rows and not any(_clean(c) for c in rows[0]):
        rows.pop(0)
    if not rows:
        raise ImportFileError("The file is empty.")

    headers = [_clean(h).rstrip("*").strip() for h in rows[0]]
    columns: dict[int, str] = {}
    spec_columns: dict[int, str] = {}
    for i, header in enumerate(headers):
        if not header:
            continue
        key = CORE_COLUMNS.get(header.lower())
        if key:
            columns[i] = key
        else:
            spec_columns[i] = header
    missing = [k for k in REQUIRED if k not in columns.values()]
    if missing:
        labels = [h for h in TEMPLATE_HEADERS if CORE_COLUMNS.get(h.lower()) in missing]
        raise ImportFileError(
            f"Missing required column(s): {', '.join(labels)}. Download the template to see the expected columns."
        )

    data_rows = [(n, r) for n, r in enumerate(rows[1:], start=2) if any(_clean(c) for c in r)]
    if len(data_rows) > MAX_ROWS:
        raise ImportFileError(f"Too many rows ({len(data_rows)}). Split the file into parts of {MAX_ROWS} rows or fewer.")
    if not data_rows:
        raise ImportFileError("No phones found below the header row.")

    results: list[RowResult] = []
    seen: dict[str, int] = {}
    for row_number, raw in data_rows:
        cells = {key: _clean(raw[i]) if i < len(raw) else "" for i, key in columns.items()}
        result = RowResult(row=row_number, model_number=cells.get("model_number", ""), name=cells.get("name", ""))
        errors = result.errors

        for key in REQUIRED:
            if not cells.get(key):
                label = next(h for h in TEMPLATE_HEADERS if CORE_COLUMNS.get(h.lower()) == key)
                errors.append(f"{label} is required.")

        cost = _number(cells["cost_price"], "Cost Price", errors) if cells.get("cost_price") else None
        price = _number(cells["selling_price"], "Selling Price", errors) if cells.get("selling_price") else None
        if cost is not None and price is not None and price <= cost:
            errors.append("Selling Price must be higher than Cost Price.")

        stock = None
        if cells.get("stock_qty"):
            stock = _number(cells["stock_qty"], "Stock Qty", errors, integer=True)
        warranty = 12
        if cells.get("warranty_months"):
            warranty = _number(cells["warranty_months"], "Warranty (months)", errors, integer=True)

        active = cells.get("is_active", "").lower()
        if active and active not in ("y", "yes", "true", "1", "n", "no", "false", "0"):
            errors.append("Active must be Y or N.")
        is_active = active not in ("n", "no", "false", "0")

        model = result.model_number
        if model:
            if model.lower() in seen:
                errors.append(f"Model Number '{model}' also appears on row {seen[model.lower()]}.")
            else:
                seen[model.lower()] = row_number

        specs = {}
        for i, label in spec_columns.items():
            value = _clean(raw[i]) if i < len(raw) else ""
            if value:
                specs[label] = value

        result.stock_target = stock
        result.data = {
            "brand": cells.get("brand", ""),
            "category": cells.get("category", ""),
            "name": result.name,
            "model_number": model,
            "cost_price": cost,
            "selling_price": price,
            "warranty_months": warranty,
            "description": cells.get("description") or None,
            "specifications": specs or None,
            "is_active": is_active,
        }
        results.append(result)
    return results


# ---------------------------------------------------------------------------
# Plan + apply
# ---------------------------------------------------------------------------


async def plan_import(db: AsyncSession, results: list[RowResult]) -> dict[str, Product]:
    """Decide create/update/unchanged for each valid row. Returns existing products by model number."""
    models = [r.model_number for r in results if r.model_number]
    existing: dict[str, Product] = {}
    for start in range(0, len(models), 500):
        chunk = models[start:start + 500]
        res = await db.execute(select(Product).where(Product.model_number.in_(chunk)))
        for p in res.scalars():
            existing[p.model_number] = p
    stock = await in_stock_counts(db, [p.id for p in existing.values()])

    brands = {b.name.lower() for b in (await db.execute(select(Brand))).scalars()}
    categories = {c.name.lower() for c in (await db.execute(select(Category))).scalars()}

    for r in results:
        if r.errors:
            r.action = "error"
            continue
        product = existing.get(r.model_number)
        if r.data["brand"].lower() not in brands:
            r.warnings.append(f"New brand '{r.data['brand']}' will be created.")
        if r.data["category"].lower() not in categories:
            r.warnings.append(f"New category '{r.data['category']}' will be created.")
        if product is None:
            r.action = "create"
            r.stock_current = 0
            continue
        r.stock_current = stock.get(product.id, 0)
        changed = (
            product.name != r.data["name"]
            or _float(product.cost_price) != r.data["cost_price"]
            or _float(product.selling_price) != r.data["selling_price"]
            or product.warranty_months != r.data["warranty_months"]
            or (product.description or None) != r.data["description"]
            or (product.specifications or None) != r.data["specifications"]
            or bool(product.is_active) != r.data["is_active"]
            or (r.stock_target is not None and r.stock_target != r.stock_current)
        )
        r.action = "update" if changed else "unchanged"
    return existing


def _float(value) -> float | None:
    return None if value is None else float(value)


async def _get_or_create(db: AsyncSession, model, name: str, cache: dict):
    key = name.lower()
    if key in cache:
        return cache[key]
    res = await db.execute(select(model).where(func.lower(model.name) == key))
    obj = res.scalar_one_or_none()
    if obj is None:
        obj = model(name=name)
        db.add(obj)
        await db.flush()
    cache[key] = obj
    return obj


async def apply_import(db: AsyncSession, results: list[RowResult], existing: dict[str, Product]) -> dict:
    brands: dict = {}
    categories: dict = {}
    added = removed = 0
    for r in results:
        if r.action == "unchanged":
            continue
        brand = await _get_or_create(db, Brand, r.data["brand"], brands)
        category = await _get_or_create(db, Category, r.data["category"], categories)
        fields = {k: v for k, v in r.data.items() if k not in ("brand", "category")}
        product = existing.get(r.model_number)
        if product is None:
            product = Product(brand_id=brand.id, category_id=category.id, **fields)
            db.add(product)
            await db.flush()
        else:
            product.brand_id = brand.id
            product.category_id = category.id
            for key, value in fields.items():
                setattr(product, key, value)

        if r.stock_target is None:
            continue
        stock_added, stock_removed, warning = await set_in_stock(
            db, product.id, r.stock_current or 0, r.stock_target
        )
        added += stock_added
        removed += stock_removed
        if warning:
            r.warnings.append(warning)
    await db.commit()
    return {"stock_added": added, "stock_removed": removed}


def summarize(results: list[RowResult]) -> dict:
    counts = {"create": 0, "update": 0, "unchanged": 0, "error": 0}
    for r in results:
        counts[r.action] += 1
    return {"rows": len(results), **counts}
