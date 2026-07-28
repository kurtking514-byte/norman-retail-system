import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from app.models.base import Base


class Reservation(Base):
    __tablename__ = "reservations"

    id = Column(Integer, primary_key=True, autoincrement=True)
    customer_id = Column(Integer, ForeignKey("customers.id"), nullable=False)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    reservation_date = Column(DateTime, default=datetime.datetime.now)
    expiry_date = Column(DateTime, nullable=False)
    # Status allowed values: Pending, Confirmed, Claimed, Cancelled
    status = Column(String(50), default="Pending", index=True)
    notes = Column(Text)

    customer = relationship("Customer")
    product = relationship("Product")
