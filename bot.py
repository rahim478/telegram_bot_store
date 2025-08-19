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

# ==========================
# START COMMAND
# ==========================
@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    if message.from_user.id == config.ADMIN_ID:
        keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
        keyboard.add("All Orders", "Manage Products")
        await message.answer("🔑 Welcome Admin! Choose an option:", reply_markup=keyboard)
    else:
        keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
        for product in products.keys():
            keyboard.add(product)
        await message.answer("🛒 Welcome! Please choose a product:", reply_markup=keyboard)

# ==========================
# CLIENT: PRODUCT SELECTION
# ==========================
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

# ==========================
# CLIENT: HANDLE BUY
# ==========================
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
    ))
    keyboard.add(types.InlineKeyboardButton(
        text="❌ Cancel Order",
        callback_data=f"cancel:{callback.from_user.id}:{product}:{option}"
    ))
    await callback.message.answer(
        f"🛒 Order placed!\n\n"
        f"📦 Product: {product} ({option}) - ${price}\n"
        f"💳 Please send payment to Binance ID: {config.BINANCE_ID}",
        reply_markup=keyboard
    )
    await callback.answer()

# ==========================
# CLIENT: CANCEL ORDER
# ==========================
@dp.callback_query_handler(lambda c: c.data.startswith("cancel:"))
async def handle_cancel(callback: types.CallbackQuery):
    _, user_id, product, option = callback.data.split(":")
    with open("orders.json", "r+") as f:
        try:
            orders = json.load(f)
        except json.JSONDecodeError:
            orders = []
        for o in orders:
            if o["user_id"] == int(user_id) and o["product"] == product and o["option"] == option and o["status"] == "pending":
                o["status"] = "cancelled"
        f.seek(0)
        json.dump(orders, f, indent=2)
        f.truncate()
    await callback.message.answer("❌ Your order has been cancelled.")
    await callback.answer()

# ==========================
# CLIENT: CONFIRM PAYMENT
# ==========================
@dp.callback_query_handler(lambda c: c.data.startswith("paid:"))
async def handle_paid(callback: types.CallbackQuery):
    _, user_id, product, option, price = callback.data.split(":")
    user_mention = f"@{callback.from_user.username}" if callback.from_user.username else "No username"

    order_info = (
        f"⚠️ Payment confirmation received!\n\n"
        f"User ID: {user_id}\n"
        f"Name: {callback.from_user.full_name}\n"
        f"Telegram: {user_mention}\n"
        f"Product: {product} ({option}) - ${price}",
    )

    # Send to admin with confirm button
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton(
        text="✅ Confirm Payment",
        callback_data=f"confirm:{user_id}:{product}:{option}:{price}"
    ))
    await bot.send_message(config.ADMIN_ID, order_info, reply_markup=keyboard)

    await callback.message.answer("✅ Thank you! Your payment will be verified.")
    await callback.answer()

# ==========================
# ADMIN: CONFIRM PAYMENT
# ==========================
@dp.callback_query_handler(lambda c: c.data.startswith("confirm:"))
async def handle_confirm(callback: types.CallbackQuery):
    _, user_id, product, option, price = callback.data.split(":")
    # ask admin to send product
    await bot.send_message(
        callback.from_user.id,
        f"💾 Please send the product details to deliver to <b>User {user_id}</b>\n"
        f"Product: {product} ({option}) - ${price}\n\n"
        f"Type your message and it will be sent to the client.",
        reply_markup=types.ForceReply(selective=True)
    )
    # store context
    dp.current_order = {"user_id": int(user_id)}

# ==========================
# ADMIN: SEND PRODUCT
# ==========================
@dp.message_handler(lambda msg: msg.reply_to_message and "Please send the product details" in msg.reply_to_message.text, user_id=config.ADMIN_ID)
async def send_product(message: types.Message):
    order = getattr(dp, "current_order", None)
    if order:
        user_id = order["user_id"]
        await bot.send_message(user_id, f"📦 Here is your product:\n\n{message.text}")
        await message.answer("✅ Product delivered to client.")
        # update order status
        with open("orders.json", "r+") as f:
            try:
                orders = json.load(f)
            except json.JSONDecodeError:
                orders = []
            for o in orders:
                if o["user_id"] == user_id and o["status"] == "pending":
                    o["status"] = "completed"
            f.seek(0)
            json.dump(orders, f, indent=2)
            f.truncate()

# ==========================
# ADMIN: SHOW ALL ORDERS
# ==========================
@dp.message_handler(lambda msg: msg.text == "All Orders" and msg.from_user.id == config.ADMIN_ID)
async def show_orders(message: types.Message):
    with open("orders.json", "r") as f:
        try:
            orders = json.load(f)
        except json.JSONDecodeError:
            orders = []
    if not orders:
        await message.answer("📭 No orders found.")
    else:
        text = "📋 <b>All Orders:</b>\n\n"
        for o in orders:
            text += (
                f"👤 User: {o['username']} (ID: {o['user_id']})\n"
                f"📦 Product: {o['product']} ({o['option']})\n"
                f"💵 Price: ${o['price']}\n"
                f"📌 Status: {o['status']}\n\n"
            )
        await message.answer(text)

# ==========================
# ADMIN: MANAGE PRODUCTS
# ==========================
@dp.message_handler(lambda msg: msg.text == "Manage Products" and msg.from_user.id == config.ADMIN_ID)
async def manage_products(message: types.Message):
    text = "🛠 <b>Manage Products</b>\n\n(Current products loaded from products.json)"
    await message.answer(text)

# ==========================
# Flask dummy port for Render
# ==========================
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running!"

def run_flask():
    port = int(os.environ.get("PORT", 5000))  # Render sets PORT automatically
    app.run(host="0.0.0.0", port=port)

# ==========================
# Run bot and Flask together
# ==========================
if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    asyncio.run(executor.start_polling(dp, skip_updates=True))
