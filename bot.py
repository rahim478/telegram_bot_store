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

    if message.from_user.id == config.ADMIN_ID:
        # قائمة الأدمن
        keyboard.add("📋 عرض كل الطلبات")
        keyboard.add("⚙️ إدارة الطلبات")
    else:
        # قائمة العميل
        for product in products.keys():
            keyboard.add(product)
        keyboard.add("🛒 طلباتي")

    await message.answer("🛒 Welcome! Please choose an option:", reply_markup=keyboard)

# ==========================
# Handle product selection (for clients)
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
        "status": "pending_payment"
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
        callback_data=f"cancel:{callback.from_user.id}:{product}:{option}:{price}"
    ))

    await callback.message.answer(
        f"🛒 Order placed!\n\n"
        f"📦 Product: {product} ({option}) - ${price}\n"
        f"💳 Please send payment to Binance ID: {config.BINANCE_ID}",
        reply_markup=keyboard
    )
    await callback.answer()

# ==========================
# Handle cancel order
# ==========================
@dp.callback_query_handler(lambda c: c.data.startswith("cancel:"))
async def handle_cancel(callback: types.CallbackQuery):
    _, user_id, product, option, price = callback.data.split(":")
    with open("orders.json", "r+") as f:
        orders = json.load(f)
        for order in orders:
            if (str(order["user_id"]) == user_id and order["product"] == product and
                order["option"] == option and order["price"] == price and order["status"] == "pending_payment"):
                order["status"] = "cancelled"
                break
        f.seek(0)
        json.dump(orders, f, indent=2)
        f.truncate()

    await callback.message.answer("❌ Your order has been cancelled.")
    await callback.answer()

# ==========================
# Handle payment confirmation
# ==========================
@dp.callback_query_handler(lambda c: c.data.startswith("paid:"))
async def handle_paid(callback: types.CallbackQuery):
    _, user_id, product, option, price = callback.data.split(":")
    username = callback.from_user.username or "NoUsername"
    mention = callback.from_user.get_mention()

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
        f"Username: {username}\n"
        f"Mention: {mention}\n"
        f"Product: {product} ({option}) - ${price}",
        reply_markup=keyboard
    )
    await callback.message.answer("✅ Thank you! Your payment will be verified by admin.")
    await callback.answer()
    
# ==========================
# Admin: Show all orders
# ==========================
@dp.message_handler(commands=['allorders'])
async def show_all_orders(message: types.Message):
    if message.from_user.id != config.ADMIN_ID:
        return

    with open("orders.json", "r") as f:
        try:
            orders = json.load(f)
        except json.JSONDecodeError:
            orders = []

    if not orders:
        await message.answer("📭 No orders yet.")
        return

    text = "📋 All Orders:\n\n"
    for i, order in enumerate(orders, 1):
        text += (
            f"🆔 Order #{i}\n"
            f"👤 User ID: {order['user_id']}\n"
            f"💬 Username: @{order['username'] if order['username'] else 'N/A'}\n"
            f"📦 Product: {order['product']} ({order['option']})\n"
            f"💲 Price: ${order['price']}\n"
            f"📌 Status: {order['status']}\n\n"
        )

    await message.answer(text)

# ==========================
# Admin confirm / reject payment
# ==========================
@dp.callback_query_handler(lambda c: c.data.startswith("confirm:") or c.data.startswith("reject:"))
async def handle_admin_decision(callback: types.CallbackQuery):
    action, user_id, product, option, price = callback.data.split(":")
    with open("orders.json", "r+") as f:
        orders = json.load(f)
        for order in orders:
            if (str(order["user_id"]) == user_id and order["product"] == product and
                order["option"] == option and order["price"] == price):
                if action == "confirm":
                    order["status"] = "confirmed"
                    await bot.send_message(user_id, f"✅ Your payment has been confirmed!\n📦 Product: {product} ({option})")
                else:
                    order["status"] = "rejected"
                    await bot.send_message(user_id, f"❌ Your payment was rejected.\n📦 Product: {product} ({option})")
                break
        f.seek(0)
        json.dump(orders, f, indent=2)
        f.truncate()

    await callback.message.answer("✅ Decision saved.")
    await callback.answer()

# ==========================
# Flask dummy port for Render
# ==========================
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running!"

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

# ==========================
# Run bot and Flask together
# ==========================
if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    asyncio.run(executor.start_polling(dp, skip_updates=True))
