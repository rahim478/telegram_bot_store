from database import SessionLocal, Product, ProductOption
import json

db = SessionLocal()

# قراءة المنتجات من ملف JSON القديم
with open('products.json', 'r') as f:
    products_data = json.load(f)

for product_name, options in products_data.items():
    # التحقق مما إذا كان المنتج موجودًا بالفعل
    existing_product = db.query(Product).filter_by(name=product_name).first()
    if not existing_product:
        # إنشاء منتج جديد
        new_product = Product(name=product_name)
        db.add(new_product)
        db.commit()
        db.refresh(new_product)
        
        # إضافة خيارات المنتج
        for option_text, price_str in options.items():
            new_option = ProductOption(
                option=option_text,
                price=float(price_str),
                product_id=new_product.id
            )
            db.add(new_option)
        
        db.commit()
        print(f"Added product: {product_name}")
    else:
        print(f"Product already exists: {product_name}")

db.close()
print("Seeding complete.")
