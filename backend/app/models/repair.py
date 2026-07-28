import datetime

from sqlalchemy import Column, DateTime, DECIMAL, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.models.base import Base


class RepairRequest(Base):
    __tablename__ = "repair_requests"

    id = Column(Integer, primary_key=True, autoincrement=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    device_model = Column(String(255), nullable=False)
    issue_description = Column(Text, nullable=False)
    estimated_cost = Column(DECIMAL(10, 2), default=0.0)
    # Status allowed values: Pending, Diagnosis, In Progress, Ready for Pickup, Released, Cancelled
    status = Column(String(50), default="Pending", index=True)
    notes = Column(Text)
    updated_at = Column(DateTime, default=datetime.datetime.now)

    customer = relationship("Customer")
