from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, field_validator


def _blank_to_none(value):
    if isinstance(value, str):
        return value.strip() or None
    return value


class ProductBase(BaseModel):
    name: Optional[str] = None
    model_number: Optional[str] = None
    description: Optional[str] = None
    warranty_months: Optional[int] = 12
    specifications: Optional[dict[str, Any]] = None
    is_active: Optional[bool] = True

    _clean_text = field_validator("name", "model_number", mode="before")(_blank_to_none)


class ProductCreate(ProductBase):
    brand_id: Optional[int] = None
    category_id: Optional[int] = None
    cost_price: Optional[float] = None
    selling_price: Optional[float] = None


class ProductUpdate(BaseModel):
    name: Optional[str] = None
    model_number: Optional[str] = None
    description: Optional[str] = None
    warranty_months: Optional[int] = None
    specifications: Optional[dict[str, Any]] = None
    is_active: Optional[bool] = None
    brand_id: Optional[int] = None
    category_id: Optional[int] = None
    cost_price: Optional[float] = None
    selling_price: Optional[float] = None

    _clean_text = field_validator("name", "model_number", mode="before")(_blank_to_none)


class ProductAdminResponse(ProductBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    brand_id: Optional[int] = None
    category_id: Optional[int] = None
    cost_price: Optional[float] = None
    selling_price: Optional[float] = None
    created_at: datetime


class ProductPublicResponse(ProductBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    brand_id: Optional[int] = None
    category_id: Optional[int] = None
    selling_price: Optional[float] = None
    created_at: datetime


class InventoryItemCreate(BaseModel):
    product_id: int
    serial_number: Optional[str] = None
    location: str = "Main Store"


class InventoryItemResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    product_id: int
    serial_number: Optional[str] = None
    status: str
    location: str
    date_added: datetime


class InventoryStatusUpdate(BaseModel):
    status: str
