from sqlalchemy import create_engine, Column, Integer, String, Float, ForeignKey
from sqlalchemy.orm import sessionmaker, declarative_base, relationship

# إنشاء اتصال مع قاعدة بيانات SQLite
DATABASE_URL = "sqlite:///./store.db"
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

# إعداد جلسة للتعامل مع قاعدة البيانات
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# الفئة الأساسية التي سترث منها جميع نماذج الجداول
Base = declarative_base()

# تعريف جدول المنتجات
class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True)
    options = relationship("ProductOption", back_populates="product")

# تعريف جدول خيارات المنتج (المدة والسعر)
class ProductOption(Base):
    __tablename__ = "product_options"
    id = Column(Integer, primary_key=True, index=True)
    option = Column(String)
    price = Column(Float)
    product_id = Column(Integer, ForeignKey("products.id"))
    product = relationship("Product", back_populates="options")

# تعريف جدول الطلبات
class Order(Base):
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer)
    username = Column(String)
    product_name = Column(String)
    option = Column(String)
    price = Column(Float)
    status = Column(String, default="pending") # (pending, paid, delivered, canceled)

# دالة لإنشاء جميع الجداول في قاعدة البيانات
def create_db():
    Base.metadata.create_all(bind=engine)

# دالة للحصول على جلسة للتعامل مع قاعدة البيانات
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

# عند تشغيل هذا الملف لأول مرة، سيتم إنشاء قاعدة البيانات والجداول
if __name__ == "__main__":
    create_db()
    print("Database and tables created successfully.")
