import json
import os
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


# ================= STATES =================
class SendProductState(StatesGroup):
    waiting_for_details = State()

class ReportProblemState(StatesGroup):
    waiting_for_report = State()

class ReplyProblemState(StatesGroup):
    waiting_for_reply = State()


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
        f"Product: {product} ({option}) - ${price}",
        reply_markup=types.InlineKeyboardMarkup().add(
            types.InlineKeyboardButton(
                text="✅ Confirm Payment",
                callback_data=f"confirm:{user_id}:{product}:{option}:{price}"
            )
        )
    )
    await callback.message.answer("✅ Thank you! Your payment will be verified.")
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
    with open("orders.json", "r+") as f:
        orders = json.load(f)
        for order in orders:
            if order["user_id"] == user_id and order["product"] == product and order["option"] == option:
                order["status"] = "paid"
        f.seek(0)
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


# ================= REPORT PROBLEM (CLIENT) =================
@dp.message_handler(lambda msg: msg.text == "⚠️ Report a Problem")
async def report_problem(message: types.Message, state: FSMContext):
    await message.answer("✍️ Please describe the problem with your product:")
    await ReportProblemState.waiting_for_report.set()


@dp.message_handler(state=ReportProblemState.waiting_for_report, content_types=types.ContentTypes.TEXT)
async def process_report_problem(message: types.Message, state: FSMContext):
    report_text = message.text
    await bot.send_message(
        config.ADMIN_ID,
        f"⚠️ Problem Report Received!\n\n"
        f"👤 User: {message.from_user.username} (ID: {message.from_user.id})\n"
        f"📝 Report: {report_text}",
        reply_markup=types.InlineKeyboardMarkup().add(
            types.InlineKeyboardButton(
                text="💬 Reply",
                callback_data=f"reply:{message.from_user.id}"
            )
        )
    )
    await message.answer("✅ Thank you! Your problem has been reported to the admin.")
    await state.finish()


# ================= ADMIN REPLY TO PROBLEM =================
@dp.callback_query_handler(lambda c: c.data.startswith("reply:") and c.from_user.id == config.ADMIN_ID)
async def start_reply(callback: types.CallbackQuery, state: FSMContext):
    _, user_id = callback.data.split(":")
    await callback.message.answer("✍️ Please type your reply to the user:")
    await state.update_data(reply_user_id=int(user_id))
    await ReplyProblemState.waiting_for_reply.set()
    await callback.answer()


@dp.message_handler(state=ReplyProblemState.waiting_for_reply, content_types=types.ContentTypes.TEXT)
async def process_admin_reply(message: types.Message, state: FSMContext):
    reply_text = message.text
    data = await state.get_data()
    user_id = data.get("reply_user_id")

    await bot.send_message(user_id, f"💬 Admin replied to your problem:\n\n{reply_text}")
    await message.answer("✅ Your reply has been sent to the user.")
    await state.finish()


# ================= RUN =================
if __name__ == "__main__":
    executor.start_polling(dp, skip_updates=True)
