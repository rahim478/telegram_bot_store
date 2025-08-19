import json
import os
from aiogram import Bot, Dispatcher, types
from aiogram.utils.executor import start_webhook
from aiohttp import web
import config

# Bot initialization
bot = Bot(token=config.TOKEN)
dp = Dispatcher(bot)

WEBHOOK_HOST = f"https://{config.RENDER_URL}"  # رابط الخدمة على Render
WEBHOOK_PATH = f"/{config.TOKEN}"
WEBHOOK_URL = WEBHOOK_HOST + WEBHOOK_PATH

WEBAPP_HOST = "0.0.0.0"
WEBAPP_PORT = int(os.environ.get("PORT", 8000))

# Load products
with open("products.json", "r") as f:
    products = json.load(f)

# Ensure orders.json exists
if not os.path.exists("orders.json"):
    with open("orders.json", "w") as f:
        json.dump([], f)

# ===== Handlers =====
@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)
    for product in products.keys():
        keyboard.add(product)
    await message.answer("🛒 Welcome! Please choose a product:", reply_markup=keyboard)

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
    with open("orders.json", "r+") as f:
        orders = json.load(f)
        orders.append(order)
        f.seek(0)
        json.dump(orders, f, indent=2)

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

@dp.callback_query_handler(lambda c: c.data.startswith("paid:"))
async def handle_paid(callback: types.CallbackQuery):
    _, user_id, product, option, price = callback.data.split(":")
    with open("orders.json", "r+") as f:
        orders = json.load(f)
        for order in orders:
            if str(order["user_id"]) == user_id and order["product"] == product and order["option"] == option:
                order["status"] = "paid"
        f.seek(0)
        f.truncate()
        json.dump(orders, f, indent=2)

    await bot.send_message(
        config.ADMIN_ID,
        f"⚠️ Payment confirmation received!\n\n"
        f"User: @{callback.from_user.username} (ID: {user_id})\n"
        f"Product: {product} ({option}) - ${price}"
    )
    await callback.message.answer("✅ Thank you! Your payment will be verified.")
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data.startswith("cancel:"))
async def handle_cancel(callback: types.CallbackQuery):
    _, user_id, product, option = callback.data.split(":")
    with open("orders.json", "r+") as f:
        orders = json.load(f)
        orders = [o for o in orders if not (str(o["user_id"]) == user_id and o["product"] == product and o["option"] == option)]
        f.seek(0)
        f.truncate()
        json.dump(orders, f, indent=2)
    await callback.message.answer("❌ Your order has been cancelled.")
    await callback.answer()

# ===== Webhook setup =====
async def on_startup(app):
    await bot.set_webhook(WEBHOOK_URL)

async def on_shutdown(app):
    await bot.delete_webhook()

# دالة async لمعالجة التحديثات
async def handle_webhook(request):
    data = await request.json()
    update = types.Update(**data)
    await dp.process_update(update)
    return web.Response(text="OK")

app = web.Application()
app.router.add_post(WEBHOOK_PATH, handle_webhook)

if __name__ == "__main__":
    web.run_app(app, host=WEBAPP_HOST, port=WEBAPP_PORT)
