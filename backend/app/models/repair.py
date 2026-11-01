import datetime

from sqlalchemy import Column, DateTime, DECIMAL, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.models.base import Base
from app.core.clock import utcnow


class RepairRequest(Base):
    __tablename__ = "repair_requests"

    id = Column(Integer, primary_key=True, autoincrement=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    device_model = Column(String(255), nullable=False)
    # What is being fixed, picked from a list in the admin (e.g. "Screen replacement")
    repair_type = Column(String(100), nullable=True)
    issue_description = Column(Text, nullable=False)
    estimated_cost = Column(DECIMAL(10, 2), default=0.0)
    # Status allowed values: Pending, Diagnosis, In Progress, Ready for Pickup, Released, Cancelled
    status = Column(String(50), default="Pending", index=True)
    notes = Column(Text)
    created_at = Column(DateTime, default=utcnow, nullable=True)
    updated_at = Column(DateTime, default=utcnow)

    customer = relationship("Customer")
