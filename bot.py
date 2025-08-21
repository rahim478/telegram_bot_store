import os
import threading
import asyncio
from flask import Flask
from aiogram import Bot, Dispatcher, executor, types
from aiogram.dispatcher import FSMContext
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher.filters.state import State, StatesGroup

# --- تعديل: استيراد من ملف قاعدة البيانات ---
from database import SessionLocal, Product, ProductOption, Order

# Import config
import config

# Initialize bot
bot = Bot(token=config.TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# --- تعديل: الحصول على جلسة قاعدة البيانات ---
db_session = SessionLocal()

# ================= STATES =================
class SendProductState(StatesGroup):
    waiting_for_details = State()


# ================= START =================
@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)

    if message.from_user.id == config.ADMIN_ID:
        keyboard.add("📋 View Orders")
        keyboard.add("📦 Manage Products")
    else:
        # --- تعديل: جلب المنتجات من قاعدة البيانات ---
        products = db_session.query(Product).all()
        for product in products:
            keyboard.add(product.name)
        keyboard.add("⚠️ Report a Problem")

    await message.answer("🛒 Welcome! Please choose an option:", reply_markup=keyboard)


# ================= CLIENT SIDE =================
# --- تعديل: التعامل مع اختيار المنتج من قاعدة البيانات ---
@dp.message_handler(lambda msg: db_session.query(Product).filter_by(name=msg.text).first() is not None)
async def product_selected(message: types.Message):
    product_name = message.text
    product = db_session.query(Product).filter_by(name=product_name).first()
    
    keyboard = types.InlineKeyboardMarkup()
    for option in product.options:
        keyboard.add(types.InlineKeyboardButton(
            text=f"{option.option} - ${option.price}",
            callback_data=f"buy:{product.name}:{option.option}:{option.price}"
        ))
    await message.answer(f"📦 {product.name}\nChoose duration/option:", reply_markup=keyboard)


# Handle buy button
@dp.callback_query_handler(lambda c: c.data.startswith("buy:"))
async def handle_buy(callback: types.CallbackQuery):
    _, product_name, option_text, price_str = callback.data.split(":")
    
    # --- تعديل: إنشاء طلب جديد في قاعدة البيانات ---
    new_order = Order(
        user_id=callback.from_user.id,
        username=callback.from_user.username,
        product_name=product_name,
        option=option_text,
        price=float(price_str),
        status="pending"
    )
    db_session.add(new_order)
    db_session.commit()

    # Send payment info
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton(
        text="✅ I have paid",
        callback_data=f"paid:{new_order.id}" # إرسال ID الطلب لسهولة التعرف عليه
    ))
    await callback.message.answer(
        f"🛒 Order placed!\n\n"
        f"📦 Product: {product_name} ({option_text}) - ${price_str}\n"
        f"💳 Please send payment to Binance ID: {config.BINANCE_ID}",
        reply_markup=keyboard
    )
    await callback.answer()

# ==========================
# Handle payment confirmation
# ==========================
@dp.callback_query_handler(lambda c: c.data.startswith("paid:"))
async def handle_paid(callback: types.CallbackQuery):
    _, order_id = callback.data.split(":")
    order = db_session.query(Order).filter_by(id=int(order_id)).first()

    if not order:
        await callback.message.answer("Order not found.")
        await callback.answer()
        return

    user_mention = f"@{callback.from_user.username}" if callback.from_user.username else "No username"

    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton(
        text="✅ Confirm Payment",
        callback_data=f"confirm:{order_id}"
    ))
    keyboard.add(types.InlineKeyboardButton(
        text="❌ Reject Payment",
        callback_data=f"reject:{order_id}"
    ))

    await bot.send_message(
        config.ADMIN_ID,
        f"⚠️ Payment confirmation received!\n\n"
        f"Order ID: {order_id}\n"
        f"User ID: {order.user_id}\n"
        f"Name: {callback.from_user.full_name}\n"
        f"Telegram: {user_mention}\n"
        f"Product: {order.product_name} ({order.option}) - ${order.price}",
        reply_markup=keyboard
    )
    await callback.message.answer("✅ Thank you! Your payment will be verified by admin.")
    await callback.answer()


# ================= ADMIN SIDE =================
@dp.message_handler(lambda msg: msg.text == "📋 View Orders" and msg.from_user.id == config.ADMIN_ID)
async def show_orders(message: types.Message):
    # --- تعديل: جلب الطلبات من قاعدة البيانات ---
    orders = db_session.query(Order).order_by(Order.id.desc()).all()

    if not orders:
        await message.answer("📭 No orders yet.")
        return

    for order in orders:
        await message.answer(
            f"🆔 Order ID: {order.id}\n"
            f"👤 User: {order.username} (ID: {order.user_id})\n"
            f"📦 Product: {order.product_name} ({order.option})\n"
            f"💵 Price: ${order.price}\n"
            f"📌 Status: {order.status}"
        )


@dp.message_handler(lambda msg: msg.text == "📦 Manage Products" and msg.from_user.id == config.ADMIN_ID)
async def manage_products(message: types.Message):
    await message.answer("⚙️ Product management is under development.")


# Confirm payment -> Send product
@dp.callback_query_handler(lambda c: c.data.startswith("confirm:") and c.from_user.id == config.ADMIN_ID)
async def confirm_payment(callback: types.CallbackQuery, state: FSMContext):
    _, order_id = callback.data.split(":")
    order = db_session.query(Order).filter_by(id=int(order_id)).first()

    if not order:
        await callback.message.answer("Order not found!")
        await callback.answer()
        return

    # --- تعديل: تحديث حالة الطلب في قاعدة البيانات ---
    order.status = "paid"
    db_session.commit()
    
    user_id = order.user_id

    # Ask admin to send product
    await callback.message.answer(
        f"✅ Payment confirmed for user {user_id}\n\n"
        f"Please type the product details to send to the user.",
        reply_markup=types.InlineKeyboardMarkup().add(
            types.InlineKeyboardButton(
                text="📤 Send Product",
                callback_data=f"sendproduct:{user_id}:{order_id}"
            )
        )
    )
    await callback.answer()


@dp.callback_query_handler(lambda c: c.data.startswith("sendproduct:") and c.from_user.id == config.ADMIN_ID)
async def send_product(callback: types.CallbackQuery, state: FSMContext):
    _, user_id, order_id = callback.data.split(":")
    await callback.message.answer("✍️ Please type the product details:")
    await state.update_data(user_id=int(user_id), order_id=int(order_id))
    await SendProductState.waiting_for_details.set()
    await callback.answer()


@dp.message_handler(state=SendProductState.waiting_for_details, content_types=types.ContentTypes.TEXT)
async def process_product_details(message: types.Message, state: FSMContext):
    details = message.text
    data = await state.get_data()
    user_id = data.get("user_id")
    order_id = data.get("order_id")

    # --- تعديل: تحديث حالة الطلب إلى "delivered" ---
    order = db_session.query(Order).filter_by(id=order_id).first()
    if order:
        order.status = "delivered"
        db_session.commit()

    await bot.send_message(user_id, f"📦 Here is your product:\n\n{details}")
    await message.answer("✅ Product sent to the user.")
    await state.finish()

# ... (باقي الكود الخاص بنظام التذاكر و Flask يبقى كما هو) ...

# -------------------------
# Flask dummy port for Render
# -------------------------
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running!"

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

# -------------------------
# Run bot and Flask together
# -------------------------
if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    executor.start_polling(dp, skip_updates=True)
