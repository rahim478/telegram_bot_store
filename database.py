import os
from sqlalchemy import create_engine, Column, Integer, String, Float, ForeignKey, Boolean, DateTime
from sqlalchemy.orm import sessionmaker, declarative_base, relationship
from sqlalchemy.sql import func

# --- إعداد الاتصال بقاعدة البيانات ---
# يقرأ الرابط من متغيرات البيئة (مثالي لـ Railway)
# وإذا لم يجده، يستخدم ملف SQLite محلي للاختبار
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    DATABASE_URL = "sqlite:///./store.db"

engine = create_engine(DATABASE_URL)

# --- إعداد جلسة قاعدة البيانات ---
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# --- تعريف الجداول (النماذج) ---

class User(Base):
    """جدول لتخزين معلومات المستخدمين ولغتهم المفضلة."""
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, unique=True, nullable=False, index=True)
    username = Column(String)
    language = Column(String, default=None)  # 'en' or 'ar'

class Product(Base):
    """جدول لتخزين المنتجات الرئيسية."""
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    options = relationship("ProductOption", back_populates="product", cascade="all, delete-orphan")

class ProductOption(Base):
    """جدول لتخزين خيارات وأسعار كل منتج."""
    __tablename__ = "product_options"
    id = Column(Integer, primary_key=True, index=True)
    option = Column(String)
    price = Column(Float)
    product_id = Column(Integer, ForeignKey("products.id"))
    product = relationship("Product", back_populates="options")

class Order(Base):
    """جدول لتخزين طلبات المستخدمين."""
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, nullable=False)
    username = Column(String)
    product_name = Column(String)
    option = Column(String)
    price = Column(Float)
    status = Column(String, default="pending")  # (pending, paid, delivered, rejected)

class Ticket(Base):
    """جدول لتخزين تذاكر الدعم الفني."""
    __tablename__ = "tickets"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.user_id"), nullable=False)
    is_open = Column(Boolean, default=True)
    messages = relationship("TicketMessage", back_populates="ticket", cascade="all, delete-orphan")
    user = relationship("User")

class TicketMessage(Base):
    """جدول لتخزين الرسائل داخل كل تذكرة."""
    __tablename__ = "ticket_messages"
    id = Column(Integer, primary_key=True, index=True)
    ticket_id = Column(Integer, ForeignKey("tickets.id"), nullable=False)
    sender = Column(String)  # 'user' or 'admin'
    text = Column(String, nullable=False)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    ticket = relationship("Ticket", back_populates="messages")


def create_db():
    """دالة لإنشاء جميع الجداول المحددة أعلاه في قاعدة البيانات."""
    Base.metadata.create_all(bind=engine)


# هذا الجزء يسمح بتشغيل الملف مباشرة لإنشاء الجداول
if __name__ == "__main__":
    create_db()
    print("Database tables created successfully.")
