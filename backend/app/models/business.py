import datetime

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text

from app.models.base import Base


class FAQ(Base):
    __tablename__ = "faqs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    category = Column(String(100), index=True)


class Promotion(Base):
    __tablename__ = "promotions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    description = Column(Text)
    start_date = Column(DateTime)
    end_date = Column(DateTime)
    active = Column(Boolean, default=True)


class Setting(Base):
    __tablename__ = "settings"

    key = Column(String(100), primary_key=True, unique=True)
    value = Column(Text, nullable=False)
    description = Column(Text)
