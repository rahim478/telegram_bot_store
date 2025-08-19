import json
import os
import asyncio
from aiogram import Bot, Dispatcher, types, executor
from flask import Flask
import threading

# Import config
import config

# Initialize bot
bot = Bot(token=config.TOKEN, parse_mode="HTML")
dp = Dispatcher(bot)

# Load products
with open("products.json", "r") as f:
    products = json.load(f)

# Ensure orders.json exists
if not os.path.exists("orders.json"):
    with open("orders.json", "w") as f:
        json.dump([], f)

# -------------------------
# Start command
# -------------------------
@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    if str(message.from_user.id) == str(config.ADMIN_ID):
        keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
        keyboard.add("📋 View Orders", "🛠 Manage Products")
        await message.answer("⚙️ Admin Panel:", reply_markup=keyboard)
    else:
        keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
        for product in products.keys():
            keyboard.add(product)
        await message.answer("🛒 Welcome! Please choose a product:", reply_markup=keyboard)

# -------------------------
# Handle product selection (client only)
# -------------------------
@dp.message_handler(lambda msg: msg.text in products.keys())
async def product_selected(message: types.Message):
    product = message.text
    keyboard = types.InlineKeyboardMarkup()
    for option, price in products[product].items():
        keyboard.add(types.InlineKeyboardButton(
            text=f"{option} - ${price}",
            callback_data=f"buy:{product}:{option}:{price}"
        ))
    await message.answer(f"📦 {product}\nChoose duration/option:", reply_markup=keyboard)

# -------------------------
# Handle buy button
# -------------------------
@dp.callback_query_handler(lambda c: c.data.startswith("buy:"))
async def handle_buy(callback: types.CallbackQuery):
    _, product, option, price = callback.data.split(":")
    order = {
        "user_id": callback.from_user.id,
        "username": callback.from_user.username,
        "product": product,
        "option": option,
        "price": price,
        "status": "pending"
    }

    # Save order
    with open("orders.json", "r+") as f:
        try:
            orders = json.load(f)
        except json.JSONDecodeError:
            orders = []
        orders.append(order)
        f.seek(0)
        json.dump(orders, f, indent=2)
        f.truncate()

    # Send payment info
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton(
        text="✅ I have paid",
        callback_data=f"paid:{callback.from_user.id}:{product}:{option}:{price}"
    ),
    types.InlineKeyboardButton(
        text="❌ Cancel Order",
        callback_data=f"cancel:{callback.from_user.id}:{product}:{option}:{price}"
    ))
    await callback.message.answer(
        f"🛒 Order placed!\n\n"
        f"📦 Product: {product} ({option}) - ${price}\n"
        f"💳 Please send payment to Binance ID: {config.BINANCE_ID}",
        reply_markup=keyboard
    )
    await callback.answer()

# -------------------------
# Handle cancel order
# -------------------------
@dp.callback_query_handler(lambda c: c.data.startswith("cancel:"))
async def handle_cancel(callback: types.CallbackQuery):
    _, user_id, product, option, price = callback.data.split(":")
    with open("orders.json", "r+") as f:
        orders = json.load(f)
        for order in orders:
            if str(order["user_id"]) == str(user_id) and order["product"] == product and order["status"] == "pending":
                order["status"] = "cancelled"
        f.seek(0)
        json.dump(orders, f, indent=2)
        f.truncate()
    await callback.message.answer("❌ Your order has been cancelled.")
    await callback.answer()

# -------------------------
# Handle payment confirmation (client)
# -------------------------
@dp.callback_query_handler(lambda c: c.data.startswith("paid:"))
async def handle_paid(callback: types.CallbackQuery):
    _, user_id, product, option, price = callback.data.split(":")
    user_mention = f"@{callback.from_user.username}" if callback.from_user.username else "No username"

    # إشعار الأدمن مع أزرار تأكيد / رفض
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton(
        text="✅ Confirm Payment",
        callback_data=f"confirm:{user_id}:{product}:{option}:{price}"
    ))
    keyboard.add(types.InlineKeyboardButton(
        text="❌ Reject Payment",
        callback_data=f"reject:{user_id}:{product}:{option}:{price}"
    ))

    await bot.send_message(
        config.ADMIN_ID,
        f"⚠️ Payment confirmation received!\n\n"
        f"User ID: {user_id}\n"
        f"Name: {callback.from_user.full_name}\n"
        f"Telegram: {user_mention}\n"
        f"Product: {product} ({option}) - ${price}",
        reply_markup=keyboard
    )
    await callback.message.answer("✅ Thank you! Your payment will be verified by admin.")
    await callback.answer()

# -------------------------
# Admin confirms payment -> ask to enter product
# -------------------------
@dp.callback_query_handler(lambda c: c.data.startswith("confirm:"))
async def confirm_payment(callback: types.CallbackQuery):
    _, user_id, product, option, price = callback.data.split(":")
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(
        types.InlineKeyboardButton(
            text="📤 Send Product",
            callback_data=f"sendproduct:{user_id}:{product}:{option}:{price}"
        )
    )
    await callback.message.answer(
        f"✅ Payment confirmed for <b>{product} ({option}) - ${price}</b>.\n\n"
        f"Now please send the product to the client:",
        reply_markup=keyboard
    )
    await callback.answer()

# -------------------------
# Admin clicks send product -> ask input
# -------------------------
@dp.callback_query_handler(lambda c: c.data.startswith("sendproduct:"))
async def ask_product_input(callback: types.CallbackQuery):
    _, user_id, product, option, price = callback.data.split(":")
    await callback.message.answer(
        f"✍️ Please type the product details to send to user <b>{user_id}</b>."
    )
    dp.register_message_handler(
        lambda msg: process_product_input(msg, user_id, product, option, price),
        content_types=types.ContentTypes.TEXT,
        once=True
    )
    await callback.answer()

async def process_product_input(message: types.Message, user_id, product, option, price):
    product_text = message.text
    try:
        await bot.send_message(
            user_id,
            f"🎁 Your product is ready!\n\n"
            f"📦 {product} ({option}) - ${price}\n\n"
            f"{product_text}"
        )
        await message.answer("✅ Product sent to client.")
    except Exception as e:
        await message.answer(f"⚠️ Failed to send product: {e}")

# -------------------------
# Admin panel actions
# -------------------------
@dp.message_handler(lambda msg: msg.text == "📋 View Orders")
async def view_orders(message: types.Message):
    with open("orders.json", "r") as f:
        try:
            orders = json.load(f)
        except json.JSONDecodeError:
            orders = []
    if not orders:
        await message.answer("📭 No orders found.")
        return
    text = "📋 All Orders:\n\n"
    for order in orders:
        text += (f"👤 User: {order['username']} (ID: {order['user_id']})\n"
                 f"📦 Product: {order['product']} ({order['option']})\n"
                 f"💲 Price: ${order['price']}\n"
                 f"📌 Status: {order['status']}\n\n")
    await message.answer(text)

@dp.message_handler(lambda msg: msg.text == "🛠 Manage Products")
async def manage_products(message: types.Message):
    text = "🛠 Product List:\n\n"
    for product, options in products.items():
        text += f"📦 {product}\n"
        for option, price in options.items():
            text += f" - {option}: ${price}\n"
        text += "\n"
    await message.answer(text)

# -------------------------
# Flask dummy port for Render
# -------------------------
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running!"

def run_flask():
    port = int(os.environ.get("PORT", 5000))  # Render sets PORT automatically
    app.run(host="0.0.0.0", port=port)

# -------------------------
# Run bot and Flask together
# -------------------------
if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    asyncio.run(executor.start_polling(dp, skip_updates=True))
