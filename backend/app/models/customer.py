import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String

from app.models.base import Base


class Customer(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    first_name = Column(String(100))
    last_name = Column(String(100))
    phone_number = Column(String(100), unique=True, nullable=False)
    messenger_user_id = Column(String(100), unique=True, nullable=True, index=True)
    thread_state = Column(String(50), default="AI_CONTROLLED")
    thread_state_updated_at = Column(DateTime, nullable=True)
    thread_state_pinned = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.datetime.now)
