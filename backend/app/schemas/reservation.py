from datetime import datetime
from typing import ClassVar, Optional

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class ReservationCreate(BaseModel):
    """Create a reservation.

    Customer identification is dual-mode: provide either an existing
    ``customer_id`` OR new-customer fields (``first_name``,
    ``last_name``, ``phone_number``), but not both and not neither.
    """

    # Existing customer
    customer_id: Optional[int] = None

    # New customer (inline creation)
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    phone_number: Optional[str] = None

    # Reservation fields
    product_id: int
    expiry_hours: int = 48
    notes: Optional[str] = None

    @model_validator(mode="after")
    def validate_customer_mode(self):
        has_customer_id = self.customer_id is not None
        has_new_customer = (
            self.first_name is not None
            or self.last_name is not None
            or self.phone_number is not None
        )

        if has_customer_id and has_new_customer:
            raise ValueError(
                "Provide either an existing customer_id OR new-customer fields "
                "(first_name, last_name, phone_number), not both."
            )
        if not has_customer_id and not has_new_customer:
            raise ValueError(
                "Provide either an existing customer_id OR new-customer fields "
                "(first_name, last_name, phone_number)."
            )
        if has_new_customer and not self.phone_number:
            raise ValueError(
                "phone_number is required when creating a new customer."
            )
        return self


class ReservationUpdate(BaseModel):
    status: Optional[str] = None
    notes: Optional[str] = None

    VALID_STATUSES: ClassVar[set[str]] = {"Pending", "Confirmed", "Claimed", "Cancelled"}

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in cls.VALID_STATUSES:
            raise ValueError(
                f"Invalid status '{v}'. "
                f"Allowed: {', '.join(sorted(cls.VALID_STATUSES))}."
            )
        return v


class ReservationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    customer_id: int
    product_id: int
    reservation_date: datetime
    expiry_date: datetime
    status: str
    notes: Optional[str] = None
