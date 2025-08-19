import json
import os
import threading
import asyncio
from flask import Flask
from aiogram import Bot, Dispatcher, executor, types
from aiogram.dispatcher import FSMContext
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher.filters.state import State, StatesGroup

# Import config
import config

# Initialize bot
bot = Bot(token=config.TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# Load products
with open("products.json", "r") as f:
    products = json.load(f)

# Ensure orders.json exists
if not os.path.exists("orders.json"):
    with open("orders.json", "w") as f:
        json.dump([], f)

# Ensure tickets.json exists
if not os.path.exists("tickets.json"):
    with open("tickets.json", "w") as f:
        json.dump({}, f)


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
        for product in products.keys():
            keyboard.add(product)
        keyboard.add("⚠️ Report a Problem")

    await message.answer("🛒 Welcome! Please choose an option:", reply_markup=keyboard)


# ================= CLIENT SIDE =================
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

    # Save order safely
    with open("orders.json", "r") as f:
        orders = json.load(f)

    orders.append(order)

    with open("orders.json", "w") as f:
        json.dump(orders, f, indent=2)

    # Send payment info
    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton(
        text="✅ I have paid",
        callback_data=f"paid:{callback.from_user.id}:{product}:{option}:{price}"
    ))
    await callback.message.answer(
        f"🛒 Order placed!\n\n"
        f"📦 Product: {product} ({option}) - ${price}\n"
        f"💳 Please send payment to Binance ID: {config.BINANCE_ID}",
        reply_markup=keyboard
    )
    await callback.answer()


# ==========================
# Handle payment confirmation
# ==========================
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


# ================= ADMIN SIDE =================
@dp.message_handler(lambda msg: msg.text == "📋 View Orders" and msg.from_user.id == config.ADMIN_ID)
async def show_orders(message: types.Message):
    with open("orders.json", "r") as f:
        orders = json.load(f)

    if not orders:
        await message.answer("📭 No orders yet.")
        return

    for order in orders:
        await message.answer(
            f"👤 User: {order['username']} (ID: {order['user_id']})\n"
            f"📦 Product: {order['product']} ({order['option']})\n"
            f"💵 Price: ${order['price']}\n"
            f"📌 Status: {order['status']}"
        )


@dp.message_handler(lambda msg: msg.text == "📦 Manage Products" and msg.from_user.id == config.ADMIN_ID)
async def manage_products(message: types.Message):
    await message.answer("⚙️ Product management is under development.")


# Confirm payment -> Send product
@dp.callback_query_handler(lambda c: c.data.startswith("confirm:") and c.from_user.id == config.ADMIN_ID)
async def confirm_payment(callback: types.CallbackQuery, state: FSMContext):
    _, user_id, product, option, price = callback.data.split(":")
    user_id = int(user_id)

    # Save order as paid
    with open("orders.json", "r") as f:
        orders = json.load(f)

    for order in orders:
        if order["user_id"] == user_id and order["product"] == product and order["option"] == option:
            order["status"] = "paid"

    with open("orders.json", "w") as f:
        json.dump(orders, f, indent=2)

    # Ask admin to send product
    await callback.message.answer(
        f"✅ Payment confirmed for user {user_id}\n\n"
        f"Please type the product details to send to the user.",
        reply_markup=types.InlineKeyboardMarkup().add(
            types.InlineKeyboardButton(
                text="📤 Send Product",
                callback_data=f"sendproduct:{user_id}"
            )
        )
    )
    await callback.answer()


@dp.callback_query_handler(lambda c: c.data.startswith("sendproduct:") and c.from_user.id == config.ADMIN_ID)
async def send_product(callback: types.CallbackQuery, state: FSMContext):
    _, user_id = callback.data.split(":")
    await callback.message.answer("✍️ Please type the product details:")
    await state.update_data(user_id=int(user_id))
    await SendProductState.waiting_for_details.set()
    await callback.answer()


@dp.message_handler(state=SendProductState.waiting_for_details, content_types=types.ContentTypes.TEXT)
async def process_product_details(message: types.Message, state: FSMContext):
    details = message.text
    data = await state.get_data()
    user_id = data.get("user_id")

    await bot.send_message(user_id, f"📦 Here is your product:\n\n{details}")
    await message.answer("✅ Product sent to the user.")
    await state.finish()


# ================== TICKETS SYSTEM ==================
def load_tickets():
    """Load tickets safely"""
    if not os.path.exists("tickets.json"):
        with open("tickets.json", "w") as f:
            json.dump({}, f)
        return {}

    try:
        with open("tickets.json", "r") as f:
            return json.load(f)
    except json.JSONDecodeError:
        with open("tickets.json", "w") as f:
            json.dump({}, f)
        return {}


def save_tickets(tickets):
    """Save tickets safely"""
    with open("tickets.json", "w") as f:
        json.dump(tickets, f, indent=2)


@dp.message_handler(lambda msg: msg.text == "⚠️ Report a Problem")
async def report_problem(message: types.Message):
    tickets = load_tickets()
    user_id = str(message.from_user.id)

    if user_id in tickets and tickets[user_id].get("open", False):
        await message.answer("⚠️ You already have an open ticket. Please describe your problem:")
    else:
        tickets[user_id] = {"open": True, "reply_to": None, "messages": []}
        save_tickets(tickets)
        await message.answer("✍️ Please describe your problem with the product:")


@dp.message_handler(lambda msg: True)
async def handle_messages(message: types.Message):
    tickets = load_tickets()
    user_id = str(message.from_user.id)

    # If client has open ticket
    if user_id in tickets and tickets[user_id].get("open", False) and message.from_user.id != config.ADMIN_ID:
        tickets[user_id]["messages"].append({"from": "user", "text": message.text})
        save_tickets(tickets)
        await bot.send_message(
            config.ADMIN_ID,
            f"📩 Message from {message.from_user.username} (ID: {message.from_user.id}):\n\n{message.text}",
            reply_markup=types.InlineKeyboardMarkup().add(
                types.InlineKeyboardButton("Reply", callback_data=f"reply:{user_id}")).add(
                types.InlineKeyboardButton("❌ Close Ticket", callback_data=f"close:{user_id}")
            )
        )
        return

    # If admin is replying to a ticket
    if message.from_user.id == config.ADMIN_ID:
        for uid, data in tickets.items():
            if data.get("open", False) and data.get("reply_to") == "waiting":
                tickets[uid]["messages"].append({"from": "admin", "text": message.text})
                await bot.send_message(int(uid), f"💬 Admin: {message.text}",
                                       reply_markup=types.InlineKeyboardMarkup().add(
                                           types.InlineKeyboardButton("❌ Close Ticket", callback_data=f"close:{uid}")
                                       ))
                tickets[uid]["reply_to"] = None
                save_tickets(tickets)
                break


@dp.callback_query_handler(lambda c: c.data.startswith("reply:"))
async def reply_ticket(callback: types.CallbackQuery):
    _, user_id = callback.data.split(":")
    tickets = load_tickets()
    if user_id in tickets and tickets[user_id].get("open", False):
        tickets[user_id]["reply_to"] = "waiting"
        save_tickets(tickets)
        await callback.message.answer(f"✍️ Please type your reply to user {user_id}:")
    await callback.answer()


@dp.callback_query_handler(lambda c: c.data.startswith("close:"))
async def close_ticket(callback: types.CallbackQuery):
    _, user_id = callback.data.split(":")
    tickets = load_tickets()
    if user_id in tickets:
        tickets[user_id]["open"] = False
        tickets[user_id]["reply_to"] = None
        save_tickets(tickets)
        await bot.send_message(int(user_id), "✅ Your ticket has been closed.")
        await callback.message.answer("✅ Ticket closed.")
    await callback.answer()


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
