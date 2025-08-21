import os
from sqlalchemy import create_engine, Column, Integer, String, Float, ForeignKey
from sqlalchemy.orm import sessionmaker, declarative_base, relationship

# --- تعديل: اقرأ رابط قاعدة البيانات من متغيرات البيئة ---
DATABASE_URL = os.getenv("DATABASE_URL")

# إذا كنت تختبر محلياً، يمكنك استخدام رابط SQLite كبديل
if DATABASE_URL is None:
    DATABASE_URL = "sqlite:///./store.db"

engine = create_engine(DATABASE_URL)

# باقي الملف يبقى كما هو...
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

# (نماذج الجداول Product, ProductOption, Order تبقى كما هي)
class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    options = relationship("ProductOption", back_populates="product")

class ProductOption(Base):
    __tablename__ = "product_options"
    id = Column(Integer, primary_key=True, index=True)
    option = Column(String)
    price = Column(Float)
    product_id = Column(Integer, ForeignKey("products.id"))
    product = relationship("Product", back_populates="options")

class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer)
    username = Column(String)
    product_name = Column(String)
    option = Column(String)
    price = Column(Float)
    status = Column(String, default="pending")

def create_db():
    Base.metadata.create_all(bind=engine)

if __name__ == "__main__":
    create_db()
    print("Database and tables created successfully.")
