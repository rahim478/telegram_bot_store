import os
import threading
import asyncio
from flask import Flask
from aiogram import Bot, Dispatcher, executor, types
from aiogram.dispatcher import FSMContext
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher.filters.state import State, StatesGroup

# --- استيراد من ملف قاعدة البيانات ---
# تأكد من أن ملف database.py موجود في نفس المجلد
from database import SessionLocal, Product, Order, Ticket, TicketMessage

# Import config
import config

# Initialize bot
bot = Bot(token=config.TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)

# --- الحصول على جلسة قاعدة البيانات ---
db_session = SessionLocal()

# ================= STATES =================
class SendProductState(StatesGroup):
    waiting_for_details = State()

class ReplyToTicketState(StatesGroup):
    waiting_for_reply = State()


# ================= START =================
@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    """
    Handles the /start command.
    Displays the main menu based on whether the user is an admin or a regular user.
    """
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True)

    if message.from_user.id == config.ADMIN_ID:
        keyboard.add("📋 View Orders")
        keyboard.add("🎫 View Open Tickets")
        keyboard.add("📦 Manage Products")
    else:
        # Fetch products from the database to display on the keyboard
        products = db_session.query(Product).all()
        for product in products:
            keyboard.add(product.name)
        keyboard.add("⚠️ Report a Problem")

    await message.answer("🛒 Welcome! Please choose an option:", reply_markup=keyboard)


# ================= CLIENT SIDE (PRODUCTS & ORDERS) =================
@dp.message_handler(lambda msg: db_session.query(Product).filter_by(name=msg.text).first() is not None and msg.from_user.id != config.ADMIN_ID)
async def product_selected(message: types.Message):
    """
    Triggered when a user selects a product from the main menu.
    Displays the available options and prices for the selected product.
    """
    product_name = message.text
    product = db_session.query(Product).filter_by(name=product_name).first()
    
    keyboard = types.InlineKeyboardMarkup()
    for option in product.options:
        keyboard.add(types.InlineKeyboardButton(
            text=f"{option.option} - ${option.price}",
            callback_data=f"buy:{product.name}:{option.option}:{option.price}"
        ))
    await message.answer(f"📦 {product.name}\nChoose duration/option:", reply_markup=keyboard)


@dp.callback_query_handler(lambda c: c.data.startswith("buy:"))
async def handle_buy(callback: types.CallbackQuery):
    """
    Handles the 'buy' callback when a user chooses a product option.
    Creates a new order in the database and prompts the user for payment.
    """
    _, product_name, option_text, price_str = callback.data.split(":")
    
    new_order = Order(
        user_id=callback.from_user.id,
        username=callback.from_user.username,
        product_name=product_name,
        option=option_text,
        price=float(price_str),
        status="pending"
    )
    db_session.add(new_order)
    db_session.commit()

    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton(
        text="✅ I have paid",
        callback_data=f"paid:{new_order.id}"
    ))
    await callback.message.answer(
        f"🛒 Order placed!\n\n"
        f"📦 Product: {product_name} ({option_text}) - ${price_str}\n"
        f"💳 Please send payment to Binance ID: {config.BINANCE_ID}",
        reply_markup=keyboard
    )
    await callback.answer()


@dp.callback_query_handler(lambda c: c.data.startswith("paid:"))
async def handle_paid(callback: types.CallbackQuery):
    """
    Handles the 'paid' callback.
    Notifies the admin that a user has claimed to have paid for an order.
    """
    _, order_id = callback.data.split(":")
    order = db_session.query(Order).filter_by(id=int(order_id)).first()

    if not order:
        await callback.message.answer("Order not found.")
        await callback.answer()
        return

    user_mention = f"@{callback.from_user.username}" if callback.from_user.username else "No username"

    keyboard = types.InlineKeyboardMarkup()
    keyboard.add(types.InlineKeyboardButton(text="✅ Confirm Payment", callback_data=f"confirm:{order_id}"))
    keyboard.add(types.InlineKeyboardButton(text="❌ Reject Payment", callback_data=f"reject:{order_id}"))

    await bot.send_message(
        config.ADMIN_ID,
        f"⚠️ Payment confirmation received!\n\n"
        f"Order ID: {order_id}\n"
        f"User: {callback.from_user.full_name} ({user_mention})\n"
        f"Product: {order.product_name} ({order.option}) - ${order.price}",
        reply_markup=keyboard
    )
    await callback.message.answer("✅ Thank you! Your payment will be verified by the admin shortly.")
    await callback.answer()


# ================= ADMIN SIDE (MANAGING ORDERS) =================
@dp.message_handler(lambda msg: msg.text == "📋 View Orders" and msg.from_user.id == config.ADMIN_ID)
async def show_orders(message: types.Message):
    """
    Admin command to view all orders from the database.
    """
    orders = db_session.query(Order).order_by(Order.id.desc()).all()

    if not orders:
        await message.answer("📭 No orders yet.")
        return

    for order in orders:
        await message.answer(
            f"🆔 Order ID: {order.id}\n"
            f"👤 User: @{order.username} (ID: {order.user_id})\n"
            f"📦 Product: {order.product_name} ({order.option})\n"
            f"💵 Price: ${order.price}\n"
            f"📌 Status: {order.status}"
        )


@dp.callback_query_handler(lambda c: c.data.startswith("confirm:") and c.from_user.id == config.ADMIN_ID)
async def confirm_payment(callback: types.CallbackQuery, state: FSMContext):
    """
    Admin callback to confirm a payment. Updates the order status to 'paid'
    and prompts the admin to send the product details.
    """
    _, order_id = callback.data.split(":")
    order = db_session.query(Order).filter_by(id=int(order_id)).first()

    if not order:
        await callback.message.answer("Order not found!")
        await callback.answer()
        return

    order.status = "paid"
    db_session.commit()
    
    await callback.message.edit_text(
        f"✅ Payment confirmed for user {order.user_id} (Order #{order_id}).\n\n"
        f"Please prepare the product details.",
        reply_markup=types.InlineKeyboardMarkup().add(
            types.InlineKeyboardButton(text="📤 Send Product", callback_data=f"sendproduct:{order.user_id}:{order_id}")
        )
    )
    await callback.answer()


@dp.callback_query_handler(lambda c: c.data.startswith("sendproduct:") and c.from_user.id == config.ADMIN_ID)
async def send_product(callback: types.CallbackQuery, state: FSMContext):
    """
    Initiates the process for the admin to send product details to the user.
    Enters the SendProductState.
    """
    _, user_id, order_id = callback.data.split(":")
    await callback.message.answer(f"✍️ Please type the product details to send to user {user_id} for Order #{order_id}:")
    await state.update_data(user_id=int(user_id), order_id=int(order_id))
    await SendProductState.waiting_for_details.set()
    await callback.answer()


@dp.message_handler(state=SendProductState.waiting_for_details, content_types=types.ContentTypes.TEXT)
async def process_product_details(message: types.Message, state: FSMContext):
    """
    Sends the product details entered by the admin to the user
    and updates the order status to 'delivered'.
    """
    details = message.text
    data = await state.get_data()
    user_id = data.get("user_id")
    order_id = data.get("order_id")

    order = db_session.query(Order).filter_by(id=order_id).first()
    if order:
        order.status = "delivered"
        db_session.commit()

    await bot.send_message(user_id, f"📦 Here is your product for Order #{order_id}:\n\n{details}")
    await message.answer(f"✅ Product sent to user {user_id}.")
    await state.finish()


@dp.callback_query_handler(lambda c: c.data.startswith("reject:") and c.from_user.id == config.ADMIN_ID)
async def reject_payment(callback: types.CallbackQuery):
    """
    Admin callback to reject a payment. Notifies the user.
    """
    _, order_id = callback.data.split(":")
    order = db_session.query(Order).filter_by(id=int(order_id)).first()

    if not order:
        await callback.message.answer("Order not found.")
        await callback.answer()
        return

    order.status = "rejected"
    db_session.commit()

    await callback.message.edit_text(f"❌ Payment for Order #{order_id} has been rejected.")
    await bot.send_message(
        order.user_id,
        f"⚠️ Your payment for {order.product_name} ({order.option}) has not been confirmed.\n"
        f"Please use the 'Report a Problem' button to contact the admin."
    )
    await callback.answer()

@dp.message_handler(lambda msg: msg.text == "📦 Manage Products" and msg.from_user.id == config.ADMIN_ID)
async def manage_products(message: types.Message):
    await message.answer("⚙️ Product management is under development.")

# ================== TICKETS SYSTEM ==================

@dp.message_handler(lambda msg: msg.text == "⚠️ Report a Problem")
async def report_problem(message: types.Message):
    """
    Allows a user to open a new support ticket.
    """
    open_ticket = db_session.query(Ticket).filter_by(user_id=message.from_user.id, is_open=True).first()

    if open_ticket:
        await message.answer("💬 You already have an open ticket. Please continue the conversation there.")
    else:
        new_ticket = Ticket(user_id=message.from_user.id, username=message.from_user.username)
        db_session.add(new_ticket)
        db_session.commit()
        await message.answer("✍️ Your ticket has been created. Please describe your problem now.")


@dp.message_handler(lambda msg: not msg.text.startswith('/') and msg.from_user.id != config.ADMIN_ID)
async def handle_user_message(message: types.Message):
    """
    Handles incoming messages from users who are not admins.
    If the user has an open ticket, the message is added to the ticket.
    """
    open_ticket = db_session.query(Ticket).filter_by(user_id=message.from_user.id, is_open=True).first()

    if open_ticket:
        new_message = TicketMessage(ticket_id=open_ticket.id, sender='user', text=message.text)
        db_session.add(new_message)
        db_session.commit()

        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("✍️ Reply", callback_data=f"reply:{open_ticket.id}"))
        keyboard.add(types.InlineKeyboardButton("❌ Close Ticket", callback_data=f"close:{open_ticket.id}"))

        await bot.send_message(
            config.ADMIN_ID,
            f"📩 New message in Ticket #{open_ticket.id} from @{open_ticket.username}:\n\n{message.text}",
            reply_markup=keyboard
        )
        await message.answer("✅ Your message has been sent to the admin.")


@dp.message_handler(lambda msg: msg.text == "🎫 View Open Tickets" and msg.from_user.id == config.ADMIN_ID)
async def view_open_tickets(message: types.Message):
    """
    Admin command to view all open support tickets.
    """
    open_tickets = db_session.query(Ticket).filter_by(is_open=True).all()
    if not open_tickets:
        await message.answer("📭 No open tickets at the moment.")
        return

    await message.answer("👇 Here are the currently open tickets:")
    for ticket in open_tickets:
        keyboard = types.InlineKeyboardMarkup()
        keyboard.add(types.InlineKeyboardButton("✍️ Reply", callback_data=f"reply:{ticket.id}"))
        keyboard.add(types.InlineKeyboardButton("❌ Close Ticket", callback_data=f"close:{ticket.id}"))
        await message.answer(f"**Ticket #{ticket.id}** - From: @{ticket.username}", reply_markup=keyboard, parse_mode="Markdown")


@dp.callback_query_handler(lambda c: c.data.startswith("reply:") and c.from_user.id == config.ADMIN_ID)
async def reply_to_ticket_callback(callback: types.CallbackQuery, state: FSMContext):
    """
    Initiates the reply process for an admin. Enters the ReplyToTicketState.
    """
    ticket_id = int(callback.data.split(":")[1])
    await state.update_data(ticket_id=ticket_id)
    await ReplyToTicketState.waiting_for_reply.set()
    await callback.message.answer(f"✍️ Please type your reply for Ticket #{ticket_id}:")
    await callback.answer()


@dp.message_handler(state=ReplyToTicketState.waiting_for_reply, user_id=config.ADMIN_ID)
async def process_admin_reply(message: types.Message, state: FSMContext):
    """
    Sends the admin's reply to the user and saves it to the database.
    """
    data = await state.get_data()
    ticket_id = data.get("ticket_id")
    ticket = db_session.query(Ticket).get(ticket_id)

    if ticket and ticket.is_open:
        admin_message = TicketMessage(ticket_id=ticket.id, sender='admin', text=message.text)
        db_session.add(admin_message)
        db_session.commit()

        await bot.send_message(ticket.user_id, f"💬 **Admin Reply:**\n{message.text}", parse_mode="Markdown")
        await message.answer(f"✅ Your reply has been sent for Ticket #{ticket.id}.")
    else:
        await message.answer("This ticket seems to be closed already.")
    
    await state.finish()


@dp.callback_query_handler(lambda c: c.data.startswith("close:") and c.from_user.id == config.ADMIN_ID)
async def close_ticket_callback(callback: types.CallbackQuery):
    """
    Admin callback to close a support ticket.
    """
    ticket_id = int(callback.data.split(":")[1])
    ticket = db_session.query(Ticket).get(ticket_id)

    if ticket:
        ticket.is_open = False
        db_session.commit()
        await bot.send_message(ticket.user_id, "✅ Your ticket has been closed by the admin.")
        await callback.message.edit_text(f"✅ Ticket #{ticket.id} has been closed.")
    await callback.answer()


# ================== FLASK & BOT RUNNER ==================
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is up and running!"

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    # Start Flask in a separate thread
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()
    
    # Start the Telegram bot
    executor.start_polling(dp, skip_updates=True)
