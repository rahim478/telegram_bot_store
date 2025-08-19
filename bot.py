import json
import os
from aiogram import Bot, Dispatcher, executor, types
from aiogram.types import ParseMode
import asyncio

# Import config
import config  # يحتوي على TOKEN, ADMIN_ID, BINANCE_ID

# Initialize bot
bot = Bot(token=config.TOKEN, parse_mode=ParseMode.HTML)
dp = Dispatcher(bot)

# Load products
with open("products.json", "r") as f:
    products = json.load(f)

# Ensure orders.json exists
if not os.path.exists("orders.json"):
    with open("orders.json", "w") as f:
        json.dump([], f, indent=2)

# Start command
@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for product in products.keys():
        keyboard.add(product)
    await message.answer("🛒 Welcome! Please choose a product:", reply_markup=keyboard)

# Show products
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

    # Payment and cancel buttons
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton(
        text="✅ I have paid",
        callback_data=f"paid:{callback.from_user.id}:{product}:{option}:{price}"
    ))
    keyboard.add(types.InlineKeyboardButton(
        text="❌ Cancel order",
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
    user_id = int(user_id)

    # Update order status
    with open("orders.json", "r+") as f:
        orders = json.load(f)
        for o in orders:
            if o["user_id"] == user_id and o["product"] == product and o["option"] == option:
                o["status"] = "paid"
        f.seek(0)
        f.truncate()
        json.dump(orders, f, indent=2)

    # Notify admin
    await bot.send_message(
        config.ADMIN_ID,
        f"⚠️ Payment confirmation received!\n\n"
        f"User: @{callback.from_user.username} ({callback.from_user.full_name})\n"
        f"User ID: {user_id}\n"
        f"Product: {product} ({option}) - ${price}"
    )
    await callback.message.answer("✅ Thank you! Your payment will be verified.")
    await callback.answer()

# Handle cancel order
@dp.callback_query_handler(lambda c: c.data.startswith("cancel:"))
async def handle_cancel(callback: types.CallbackQuery):
    _, user_id, product, option, price = callback.data.split(":")
    user_id = int(user_id)

    # Remove order
    with open("orders.json", "r+") as f:
        orders = json.load(f)
        orders = [o for o in orders if not (o["user_id"] == user_id and o["product"] == product and o["option"] == option)]
        f.seek(0)
        f.truncate()
        json.dump(orders, f, indent=2)

    await callback.message.answer("❌ Your order has been cancelled.")
    await callback.answer()

# Optional: show orders for admin
@dp.message_handler(commands=['orders'])
async def show_orders(message: types.Message):
    if message.from_user.id != config.ADMIN_ID:
        await message.reply("🚫 You are not authorized to view orders.")
        return
    with open("orders.json", "r") as f:
        orders = json.load(f)
    if not orders:
        await message.reply("📂 No orders yet.")
        return
    text = "📂 Orders:\n\n"
    for o in orders:
        text += f"User: @{o['username']} ({o['user_id']})\nProduct: {o['product']} ({o['option']}) - ${o['price']}\nStatus: {o['status']}\n\n"
    await message.reply(text)

# Optional: auto cancel unpaid orders after a timeout (e.g., 1 hour)
async def auto_cancel_unpaid():
    while True:
        await asyncio.sleep(3600)  # check every 1 hour
        with open("orders.json", "r+") as f:
            orders = json.load(f)
            changed = False
            for o in orders:
                if o["status"] == "pending":
                    o["status"] = "cancelled"
                    changed = True
            if changed:
                f.seek(0)
                f.truncate()
                json.dump(orders, f, indent=2)

if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.create_task(auto_cancel_unpaid())
    executor.start_polling(dp, skip_updates=True)
