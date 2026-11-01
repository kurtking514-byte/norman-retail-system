from datetime import datetime
from typing import ClassVar, Optional

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class RepairRequestCreate(BaseModel):
    """Create a repair request.

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

    # Repair fields
    device_model: str
    repair_type: Optional[str] = None
    issue_description: str = ""
    estimated_cost: float = 0.0
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
        if not (self.repair_type or "").strip() and not self.issue_description.strip():
            raise ValueError("Choose what needs fixing or describe the issue.")
        return self


class RepairRequestUpdate(BaseModel):
    status: Optional[str] = None
    repair_type: Optional[str] = None
    estimated_cost: Optional[float] = None
    notes: Optional[str] = None

    VALID_STATUSES: ClassVar[set[str]] = {
        "Pending", "Diagnosis", "In Progress",
        "Ready for Pickup", "Released", "Cancelled",
    }

    @field_validator("status")
    @classmethod
    def validate_status(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and v not in cls.VALID_STATUSES:
            raise ValueError(
                f"Invalid status '{v}'. "
                f"Allowed: {', '.join(sorted(cls.VALID_STATUSES))}."
            )
        return v


class RepairRequestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    customer_id: int
    customer_name: Optional[str] = None
    customer_phone: Optional[str] = None
    device_model: str
    repair_type: Optional[str] = None
    issue_description: str
    estimated_cost: float
    status: str
    notes: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: datetime
