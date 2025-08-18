import json
import os
import asyncio
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, executor, types

# Import config
import config  # يجب أن يحتوي على TOKEN, ADMIN_ID, BINANCE_ID

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

# ===== Start Command =====
@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for product in products.keys():
        keyboard.add(product)
    await message.answer("🛒 Welcome! Please choose a product:", reply_markup=keyboard)

# ===== Product Selection =====
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

# ===== Buy Button =====
@dp.callback_query_handler(lambda c: c.data.startswith("buy:"))
async def handle_buy(callback: types.CallbackQuery):
    _, product, option, price = callback.data.split(":")
    user_id = callback.from_user.id
    username = callback.from_user.username or "N/A"
    full_name = callback.from_user.full_name

    order = {
        "user_id": user_id,
        "username": username,
        "full_name": full_name,
        "product": product,
        "option": option,
        "price": price,
        "status": "pending",
        "time": datetime.now().isoformat()
    }

    # Save order
    with open("orders.json", "r+") as f:
        orders = json.load(f)
        orders.append(order)
        f.seek(0)
        json.dump(orders, f, indent=2)

    # Payment keyboard
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton(
        text="✅ I have paid",
        callback_data=f"paid:{user_id}:{product}:{option}:{price}"
    ))
    keyboard.add(types.InlineKeyboardButton(
        text="❌ Cancel Order",
        callback_data=f"cancel:{user_id}:{product}:{option}:{price}"
    ))

    await callback.message.answer(
        f"🛒 Order placed!\n\n"
        f"📦 Product: {product} ({option}) - ${price}\n"
        f"💳 Please send payment to Binance ID: {config.BINANCE_ID}",
        reply_markup=keyboard
    )
    await callback.answer()

# ===== Payment Confirmation =====
@dp.callback_query_handler(lambda c: c.data.startswith("paid:"))
async def handle_paid(callback: types.CallbackQuery):
    _, user_id, product, option, price = callback.data.split(":")
    await bot.send_message(
        config.ADMIN_ID,
        f"⚠️ Payment confirmation received!\n\n"
        f"User ID: {user_id}\n"
        f"Username: @{callback.from_user.username or 'N/A'}\n"
        f"Full Name: {callback.from_user.full_name}\n"
        f"Product: {product} ({option}) - ${price}"
    )
    # Update order status
    with open("orders.json", "r+") as f:
        orders = json.load(f)
        for o in orders:
            if o["user_id"] == int(user_id) and o["product"] == product and o["option"] == option and o["price"] == price:
                o["status"] = "paid"
        f.seek(0)
        f.truncate()
        json.dump(orders, f, indent=2)

    await callback.message.answer("✅ Thank you! Your payment will be verified.")
    await callback.answer()

# ===== Cancel Order =====
@dp.callback_query_handler(lambda c: c.data.startswith("cancel:"))
async def handle_cancel(callback: types.CallbackQuery):
    _, user_id, product, option, price = callback.data.split(":")
    user_id = int(user_id)

    with open("orders.json", "r+") as f:
        orders = json.load(f)
        orders = [o for o in orders if not (
            o["user_id"] == user_id and o["product"] == product and o["option"] == option and o["price"] == price and o["status"] == "pending"
        )]
        f.seek(0)
        f.truncate()
        json.dump(orders, f, indent=2)

    await callback.message.answer("❌ Your order has been cancelled.")
    await bot.send_message(config.ADMIN_ID,
                           f"⚠️ Order cancelled by user.\nUser ID: {user_id}\nProduct: {product} ({option}) - ${price}")
    await callback.answer()

# ===== Show Orders for User =====
@dp.message_handler(commands=['myorders'])
async def my_orders(message: types.Message):
    with open("orders.json", "r") as f:
        orders = json.load(f)
    user_orders = [o for o in orders if o["user_id"] == message.from_user.id]
    if not user_orders:
        await message.answer("📦 You have no orders.")
        return
    msg = "📦 Your Orders:\n"
    for o in user_orders:
        msg += f"- {o['product']} ({o['option']}) - ${o['price']} | Status: {o['status']}\n"
    await message.answer(msg)

# ===== Show All Orders for Admin =====
@dp.message_handler(lambda m: m.from_user.id == config.ADMIN_ID, commands=['allorders'])
async def all_orders(message: types.Message):
    with open("orders.json", "r") as f:
        orders = json.load(f)
    if not orders:
        await message.answer("📦 No orders yet.")
        return
    msg = "📦 All Orders:\n"
    for o in orders:
        msg += f"- {o['product']} ({o['option']}) - ${o['price']} | User: @{o['username']} | Full Name: {o['full_name']} | Status: {o['status']}\n"
    await message.answer(msg)

# ===== Background Task: Reminder for Pending Orders =====
async def check_pending_orders():
    while True:
        if os.path.exists("orders.json"):
            with open("orders.json", "r+") as f:
                orders = json.load(f)
                changed = False
                for order in orders:
                    if order["status"] == "pending":
                        order_time = datetime.fromisoformat(order.get("time"))
                        if datetime.now() - order_time > timedelta(minutes=30):
                            try:
                                await bot.send_message(order["user_id"],
                                    f"⏰ Reminder: Your order for {order['product']} ({order['option']}) is still pending payment.")
                            except:
                                pass
                            changed = True
                if changed:
                    f.seek(0)
                    f.truncate()
                    json.dump(orders, f, indent=2)
        await asyncio.sleep(300)  # Check every 5 minutes

# ===== Run Bot =====
if __name__ == "__main__":
    loop = asyncio.get_event_loop()
    loop.create_task(check_pending_orders())
    executor.start_polling(dp, skip_updates=True)
