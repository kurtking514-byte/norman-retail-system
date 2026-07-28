from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict


class ProductBase(BaseModel):
    name: str
    model_number: str
    description: Optional[str] = None
    warranty_months: Optional[int] = 12
    specifications: Optional[dict[str, Any]] = None
    is_active: Optional[bool] = True


class ProductCreate(ProductBase):
    brand_id: int
    category_id: int
    cost_price: float
    selling_price: float


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


class ProductAdminResponse(ProductBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    brand_id: int
    category_id: int
    cost_price: float
    selling_price: float
    created_at: datetime


class ProductPublicResponse(ProductBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    brand_id: int
    category_id: int
    selling_price: float
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
