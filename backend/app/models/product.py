import datetime

from sqlalchemy import Boolean, Column, DateTime, DECIMAL, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import relationship

from app.models.base import Base


class Brand(Base):
    __tablename__ = "brands"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False)

    products = relationship("Product", back_populates="brand")


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(100), unique=True, nullable=False)

    products = relationship("Product", back_populates="category")


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, autoincrement=True)
    brand_id = Column(Integer, ForeignKey("brands.id"), nullable=False)
    category_id = Column(Integer, ForeignKey("categories.id"), nullable=False)
    name = Column(String(255), nullable=False)
    model_number = Column(String(100), unique=True, nullable=False, index=True)
    description = Column(Text, nullable=True)
    cost_price = Column(DECIMAL(10, 2), nullable=False)
    selling_price = Column(DECIMAL(10, 2), nullable=False)
    warranty_months = Column(Integer, default=12)
    specifications = Column(JSON, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.datetime.now)

    brand = relationship("Brand", back_populates="products")
    category = relationship("Category", back_populates="products")
    inventory_items = relationship("Inventory", back_populates="product")
    discounts = relationship("Discount", back_populates="product")
    installments = relationship("Installment", back_populates="product")
    reservations = relationship("Reservation", back_populates="product")


class Inventory(Base):
    __tablename__ = "inventory"

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    serial_number = Column(String(100), unique=True, nullable=True, index=True)
    # Status allowed values: In Stock, Sold, Reserved, In Repair
    status = Column(String(50), default="In Stock", index=True)
    location = Column(String(100), default="Main Store")
    date_added = Column(DateTime, default=datetime.datetime.now)

    product = relationship("Product", back_populates="inventory_items")


class Discount(Base):
    __tablename__ = "discounts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    discount_percentage = Column(DECIMAL(5, 2), default=0.0)
    fixed_discount = Column(DECIMAL(10, 2), default=0.0)
    start_date = Column(DateTime)
    end_date = Column(DateTime)
    active = Column(Boolean, default=True)

    product = relationship("Product", back_populates="discounts")


class Installment(Base):
    __tablename__ = "installments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    # Partner allowed values: Home Credit, Skyro
    partner_name = Column(String(100))
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False)
    downpayment = Column(DECIMAL(10, 2), nullable=False)
    term_months = Column(Integer, nullable=False)
    monthly_amortization = Column(DECIMAL(10, 2), nullable=False)
    active = Column(Boolean, default=True)

    product = relationship("Product", back_populates="installments")
