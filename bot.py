import json
import os
from aiogram import Bot, Dispatcher, executor, types

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

# Dummy port for Render free tier
PORT = int(os.environ.get("PORT", 8000))
print(f"Using port {PORT} (dummy, no actual server)")

# Start command
@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for product in products.keys():
        keyboard.add(product)
    await message.answer("🛒 Welcome! Please choose a product:", reply_markup=keyboard)

# Handle product selection
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

# Handle buy button
@dp.callback_query_handler(lambda c: c.data.startswith("buy:"))
async def handle_buy(callback: types.CallbackQuery):
    _, product, option, price = callback.data.split(":")
    order = {
        "user_id": callback.from_user.id,
        "username": callback.from_user.username or "None",
        "mention": f"@{callback.from_user.username}" if callback.from_user.username else "None",
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

# Handle payment confirmation
@dp.callback_query_handler(lambda c: c.data.startswith("paid:"))
async def handle_paid(callback: types.CallbackQuery):
    _, user_id, product, option, price = callback.data.split(":")
    await bot.send_message(
        config.ADMIN_ID,
        f"⚠️ Payment confirmation received!\n\n"
        f"User ID: {user_id}\n"
        f"Username: @{callback.from_user.username}\n"
        f"Product: {product} ({option}) - ${price}"
    )
    await callback.message.answer("✅ Thank you! Your payment will be verified.")
    await callback.answer()

# Handle order cancellation
@dp.callback_query_handler(lambda c: c.data.startswith("cancel:"))
async def handle_cancel(callback: types.CallbackQuery):
    _, user_id, product, option, price = callback.data.split(":")
    # Update orders.json
    with open("orders.json", "r+") as f:
        orders = json.load(f)
        for order in orders:
            if str(order["user_id"]) == user_id and order["product"] == product and order["option"] == option and order["price"] == price and order["status"] == "pending":
                order["status"] = "cancelled"
                break
        f.seek(0)
        f.truncate()
        json.dump(orders, f, indent=2)
    await callback.message.answer("❌ Your order has been cancelled.")
    await callback.answer()

if __name__ == "__main__":
    # Start polling (works with Render free tier)
    executor.start_polling(dp, skip_updates=True)
