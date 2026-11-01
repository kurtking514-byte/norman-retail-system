"""
Admin customer lookup, so staff can pick a customer by name or phone number
instead of typing a numeric ID.
"""

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints.conversations import customer_display_name
from app.core.database import get_db
from app.core.security import get_current_admin
from app.models.customer import Customer

router = APIRouter(tags=["Customers"])


class CustomerSummary(BaseModel):
    id: int
    name: str | None
    phone_number: str


@router.get("/customers", response_model=list[CustomerSummary])
async def search_customers(
    q: str = Query("", max_length=100),
    limit: int = Query(20, ge=1, le=100),
    admin: dict = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db),
):
    """Customers whose first, last or full name, or phone number, contains ``q``."""
    stmt = select(Customer)
    term = q.strip()
    if term:
        like = f"%{term}%"
        full_name = func.coalesce(Customer.first_name, "") + " " + func.coalesce(Customer.last_name, "")
        stmt = stmt.where(or_(
            full_name.ilike(like),
            Customer.last_name.ilike(like),
            Customer.phone_number.ilike(like),
        ))
    stmt = stmt.order_by(Customer.first_name, Customer.last_name).limit(limit)
    customers = (await db.execute(stmt)).scalars().all()
    return [
        CustomerSummary(id=c.id, name=customer_display_name(c), phone_number=c.phone_number)
        for c in customers
    ]
