import json
import os
import asyncio
from aiogram import Bot, Dispatcher, types, executor
from flask import Flask
import threading

# Import config
import config

# Initialize bot
bot = Bot(token=config.TOKEN)
dp = Dispatcher(bot)

# Load products
with open("products.json", "r") as f:
    products = json.load(f)

# Ensure orders.json exists
if not os.path.exists("orders.json"):
    with open("orders.json", "w") as f:
        json.dump([], f)

# ==========================
# Start command
# ==========================
@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for product in products.keys():
        keyboard.add(product)
    keyboard.add("/myorders")  # زر لعرض الطلبات للعميل
    keyboard.add("/help")      # زر help
    await message.answer("🛒 Welcome! Please choose a product:", reply_markup=keyboard)

# ==========================
# Show orders for customer or admin
# ==========================
@dp.message_handler(commands=['myorders'])
async def show_orders(message: types.Message):
    user_id = message.from_user.id
    with open("orders.json", "r") as f:
        orders = json.load(f)
    user_orders = [o for o in orders if o["user_id"] == user_id]
    if not user_orders:
        await message.answer("📂 You have no orders yet.")
        return
    msg = "📂 Your Orders:\n\n"
    for o in user_orders:
        msg += f"{o['product']} ({o['option']}) - ${o['price']} - Status: {o['status']}\n"
    await message.answer(msg)

# ==========================
# Show all orders (admin only)
# ==========================
@dp.message_handler(commands=['allorders'])
async def show_all_orders(message: types.Message):
    if message.from_user.id != config.ADMIN_ID:
        await message.answer("❌ You are not authorized to view all orders.")
        return
    with open("orders.json", "r") as f:
        orders = json.load(f)
    if not orders:
        await message.answer("📂 No orders yet.")
        return
    msg = "📂 All Orders:\n\n"
    for o in orders:
        username = o.get("username") or "NoUsername"
        msg += f"User ID: {o['user_id']} | Username: {username} | {o['product']} ({o['option']}) - ${o['price']} - Status: {o['status']}\n"
    await message.answer(msg)

# ==========================
# Help command
# ==========================
@dp.message_handler(commands=['help'])
async def show_help(message: types.Message):
    msg = (
        "🆘 Help - Available Commands:\n\n"
        "/start - Show available products\n"
        "/myorders - Show your orders\n"
        "/help - Show this help message\n"
    )
    if message.from_user.id == config.ADMIN_ID:
        msg += "/allorders - Show all orders (admin only)\n"
    await message.answer(msg)

# ==========================
# Handle product selection
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
# Handle buy button
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
        orders = json.load(f)
        orders.append(order)
        f.seek(0)
        json.dump(orders, f, indent=2)

    # Send payment info with Cancel button
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton(
        text="✅ I have paid",
        callback_data=f"paid:{callback.from_user.id}:{product}:{option}:{price}"
    ))
    keyboard.add(types.InlineKeyboardButton(
        text="❌ Cancel Order",
        callback_data=f"cancel:{callback.from_user.id}:{product}:{option}:{price}"
    ))
    msg = await callback.message.answer(
        f"🛒 Order placed!\n\n"
        f"📦 Product: {product} ({option}) - ${price}\n"
        f"💳 Please send payment to Binance ID: {config.BINANCE_ID}",
        reply_markup=keyboard
    )

    # Auto-reminder if payment not done after 30 minutes
    async def payment_reminder():
        await asyncio.sleep(1800)  # 30 minutes
        with open("orders.json", "r") as f:
            orders = json.load(f)
        for o in orders:
            if o["user_id"] == callback.from_user.id and o["product"] == product and o["option"] == option and o["status"] == "pending":
                await bot.send_message(callback.from_user.id, f"⏰ Reminder: You have not paid for {product} ({option}). Please complete the payment or cancel the order.")
    asyncio.create_task(payment_reminder())

    await callback.answer()

# ==========================
# Handle payment confirmation
# ==========================
@dp.callback_query_handler(lambda c: c.data.startswith("paid:"))
async def handle_paid(callback: types.CallbackQuery):
    _, user_id, product, option, price = callback.data.split(":")
    username = callback.from_user.username or "NoUsername"
    mention = callback.from_user.get_mention()
    
    # Update order status
    with open("orders.json", "r+") as f:
        orders = json.load(f)
        for o in orders:
            if o["user_id"] == int(user_id) and o["product"] == product and o["option"] == option:
                o["status"] = "paid"
        f.seek(0)
        json.dump(orders, f, indent=2)
    
    await bot.send_message(
        config.ADMIN_ID,
        f"⚠️ Payment confirmation received!\n\n"
        f"User ID: {user_id}\n"
        f"Username: {username}\n"
        f"Mention: {mention}\n"
        f"Product: {product} ({option}) - ${price}"
    )
    await callback.message.answer("✅ Thank you! Your payment will be verified.")
    await callback.answer()

# ==========================
# Handle cancel order
# ==========================
@dp.callback_query_handler(lambda c: c.data.startswith("cancel:"))
async def handle_cancel(callback: types.CallbackQuery):
    _, user_id, product, option, price = callback.data.split(":")
    with open("orders.json", "r+") as f:
        orders = json.load(f)
        for o in orders:
            if o["user_id"] == int(user_id) and o["product"] == product and o["option"] == option and o["status"] == "pending":
                o["status"] = "cancelled"
        f.seek(0)
        json.dump(orders, f, indent=2)
    await callback.message.answer(f"❌ Your order for {product} ({option}) has been cancelled.")
    await callback.answer()

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
