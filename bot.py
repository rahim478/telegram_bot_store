import os
import threading
import asyncio
import json
from flask import Flask
from aiogram import Bot, Dispatcher, executor, types
from aiogram.dispatcher import FSMContext
from aiogram.contrib.fsm_storage.memory import MemoryStorage
from aiogram.dispatcher.filters.state import State, StatesGroup

# --- استيراد النماذج من ملف قاعدة البيانات ---
from database import SessionLocal, Product, Order, Ticket, TicketMessage, User
import config

# --- إعداد نظام الترجمة ---
LANGUAGES = {}
def load_translations():
    """تحميل ملفات الترجمة JSON عند بدء التشغيل."""
    for lang_code in ['en', 'ar']:
        # تأكد من وجود الملفات قبل محاولة فتحها
        if os.path.exists(f'{lang_code}.json'):
            with open(f'{lang_code}.json', 'r', encoding='utf-8') as f:
                LANGUAGES[lang_code] = json.load(f)
        else:
            print(f"WARNING: Translation file '{lang_code}.json' not found.")
            LANGUAGES[lang_code] = {}

def _(text_key, lang='en', **kwargs):
    """دالة لجلب النص المترجم. إذا لم تكن اللغة موجودة، تستخدم الإنجليزية كافتراضي."""
    # Fallback to English if language is not set or not found
    lang = lang if lang in LANGUAGES else 'en'
    return LANGUAGES.get(lang, {}).get(text_key, f"<{text_key}>").format(**kwargs)

# --- تهيئة البوت وقاعدة البيانات ---
bot = Bot(token=config.TOKEN)
storage = MemoryStorage()
dp = Dispatcher(bot, storage=storage)
db_session = SessionLocal()

# ================= STATES =================
class SendProductState(StatesGroup):
    waiting_for_details = State()

class ReplyToTicketState(StatesGroup):
    waiting_for_reply = State()

# --- دوال مساعدة ---
def get_or_create_user(user_id, username):
    """جلب مستخدم من قاعدة البيانات أو إنشائه إذا لم يكن موجودًا."""
    user = db_session.query(User).filter_by(user_id=user_id).first()
    if not user:
        user = User(user_id=user_id, username=username, language=None)
        db_session.add(user)
        db_session.commit()
        db_session.refresh(user)
    return user

# ================= START & LANGUAGE SELECTION =================
@dp.message_handler(commands=['start'])
async def start(message: types.Message):
    """التعامل مع أمر /start، وطلب اختيار اللغة إذا كانت غير محددة."""
    user = get_or_create_user(message.from_user.id, message.from_user.username)
    
    if user.language is None:
        keyboard = types.InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            types.InlineKeyboardButton("English 🇬🇧", callback_data="setlang:en"),
            types.InlineKeyboardButton("العربية 🇸🇦", callback_data="setlang:ar")
        )
        # رسالة الترحيب تعرض دائمًا باللغتين
        await message.answer("🛒 Welcome! Please choose a language:\n\n🛒 أهلاً بك! الرجاء اختيار اللغة:", reply_markup=keyboard)
    else:
        await show_main_menu(message)

@dp.callback_query_handler(lambda c: c.data.startswith("setlang:"))
async def set_language(callback: types.CallbackQuery):
    """حفظ اللغة التي اختارها المستخدم وعرض القائمة الرئيسية."""
    lang_code = callback.data.split(":")[1]
    user = get_or_create_user(callback.from_user.id, callback.from_user.username)
    user.language = lang_code
    db_session.commit()
    
    await callback.message.delete()
    await show_main_menu(callback.message)

async def show_main_menu(message: types.Message):
    """عرض القائمة الرئيسية باللغة المناسبة."""
    user = get_or_create_user(message.from_user.id, message.from_user.username)
    lang = user.language
    
    keyboard = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)

    if message.from_user.id == config.ADMIN_ID:
        keyboard.add(_("view_orders", lang), _("view_tickets", lang))
        keyboard.add(_("manage_products", lang))
    else:
        products = db_session.query(Product).all()
        for product in products:
            keyboard.add(product.name)
        keyboard.add(_("report_problem", lang))
    
    keyboard.add(_("select_language_button", lang))
    await message.answer(_("welcome_back", lang), reply_markup=keyboard)

@dp.message_handler(lambda msg: msg.text in [_("select_language_button", lang) for lang in LANGUAGES.keys()])
async def change_language_prompt(message: types.Message):
    """السماح للمستخدم بتغيير لغته."""
    user = get_or_create_user(message.from_user.id, message.from_user.username)
    user.language = None
    db_session.commit()
    await start(message)

# ================= CLIENT SIDE (PRODUCTS & ORDERS) =================
@dp.message_handler(lambda msg: db_session.query(Product).filter_by(name=msg.text).first() is not None and msg.from_user.id != config.ADMIN_ID)
async def product_selected(message: types.Message):
    user = get_or_create_user(message.from_user.id, message.from_user.username)
    product = db_session.query(Product).filter_by(name=message.text).first()
    
    keyboard = types.InlineKeyboardMarkup()
    for option in product.options:
        keyboard.add(types.InlineKeyboardButton(
            text=f"{option.option} - ${option.price}",
            callback_data=f"buy:{product.name}:{option.option}:{option.price}"
        ))
    await message.answer(f"📦 {product.name}\n{_('choose_option', user.language)}", reply_markup=keyboard)

@dp.callback_query_handler(lambda c: c.data.startswith("buy:"))
async def handle_buy(callback: types.CallbackQuery):
    user = get_or_create_user(callback.from_user.id, callback.from_user.username)
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

    paid_button_text = "I have paid" if user.language == 'en' else "لقد دفعت"
    keyboard = types.InlineKeyboardMarkup().add(types.InlineKeyboardButton(f"✅ {paid_button_text}", callback_data=f"paid:{new_order.id}"))

    await callback.message.answer(
        f"{_('order_placed', user.language)}\n\n"
        f"{_('payment_prompt', user.language, product_name=product_name, option_text=option_text, price_str=price_str, binance_id=config.BINANCE_ID)}",
        reply_markup=keyboard
    )
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data.startswith("paid:"))
async def handle_paid(callback: types.CallbackQuery):
    user = get_or_create_user(callback.from_user.id, callback.from_user.username)
    order_id = int(callback.data.split(":")[1])
    order = db_session.query(Order).get(order_id)

    if not order:
        await callback.message.answer("Order not found.")
        await callback.answer()
        return

    # إشعار المدير يبقى بالإنجليزية لسهولة المتابعة
    keyboard = types.InlineKeyboardMarkup(row_width=2)
    keyboard.add(
        types.InlineKeyboardButton(text="✅ Confirm Payment", callback_data=f"confirm:{order.id}"),
        types.InlineKeyboardButton(text="❌ Reject Payment", callback_data=f"reject:{order.id}")
    )
    await bot.send_message(
        config.ADMIN_ID,
        f"⚠️ Payment confirmation received!\n\n"
        f"Order ID: {order.id}\n"
        f"User: @{order.username} (ID: {order.user_id})\n"
        f"Product: {order.product_name} ({order.option}) - ${order.price}",
        reply_markup=keyboard
    )
    
    await callback.message.answer(_("payment_confirmation", user.language))
    await callback.answer()

# ================= ADMIN SIDE (MANAGING ORDERS) =================
@dp.message_handler(lambda msg: msg.text in [_("view_orders", lang) for lang in LANGUAGES.keys()] and msg.from_user.id == config.ADMIN_ID)
async def show_orders(message: types.Message):
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
async def confirm_payment(callback: types.CallbackQuery):
    order_id = int(callback.data.split(":")[1])
    order = db_session.query(Order).get(order_id)
    if not order:
        await callback.answer("Order not found!")
        return
    
    order.status = "paid"
    db_session.commit()
    
    await callback.message.edit_text(
        f"✅ Payment confirmed for Order #{order.id}.\n"
        f"User: @{order.username}\n\n"
        f"Please prepare the product details.",
        reply_markup=types.InlineKeyboardMarkup().add(
            types.InlineKeyboardButton(text="📤 Send Product", callback_data=f"sendproduct:{order.id}")
        )
    )
    await callback.answer()

@dp.callback_query_handler(lambda c: c.data.startswith("sendproduct:") and c.from_user.id == config.ADMIN_ID)
async def send_product(callback: types.CallbackQuery, state: FSMContext):
    order_id = int(callback.data.split(":")[1])
    order = db_session.query(Order).get(order_id)
    if not order:
        await callback.answer("Order not found!")
        return

    await callback.message.answer(f"✍️ Please type the product details to send for Order #{order.id}:")
    await state.update_data(order_id=order.id)
    await SendProductState.waiting_for_details.set()
    await callback.answer()

@dp.message_handler(state=SendProductState.waiting_for_details, content_types=types.ContentTypes.TEXT, user_id=config.ADMIN_ID)
async def process_product_details(message: types.Message, state: FSMContext):
    data = await state.get_data()
    order_id = data.get("order_id")
    order = db_session.query(Order).get(order_id)
    
    if order:
        order.status = "delivered"
        db_session.commit()
        user = get_or_create_user(order.user_id, order.username)
        # إرسال رسالة للمستخدم بلغته
        await bot.send_message(order.user_id, _("product_delivered", user.language, details=message.text, order_id=order.id))
        await message.answer(f"✅ Product sent to user @{order.username} for Order #{order.id}.")
    else:
        await message.answer("Error: Could not find the order to update.")
    
    await state.finish()

@dp.callback_query_handler(lambda c: c.data.startswith("reject:") and c.from_user.id == config.ADMIN_ID)
async def reject_payment(callback: types.CallbackQuery):
    order_id = int(callback.data.split(":")[1])
    order = db_session.query(Order).get(order_id)
    if order:
        order.status = "rejected"
        db_session.commit()
        user = get_or_create_user(order.user_id, order.username)
        await bot.send_message(order.user_id, _("payment_rejected", user.language, product_name=f"{order.product_name} ({order.option})"))
        await callback.message.edit_text(f"❌ Payment for Order #{order.id} has been rejected.")
    else:
        await callback.message.answer("Order not found.")
    await callback.answer()

@dp.message_handler(lambda msg: msg.text in [_("manage_products", lang) for lang in LANGUAGES.keys()] and msg.from_user.id == config.ADMIN_ID)
async def manage_products(message: types.Message):
    await message.answer("⚙️ Product management is under development.")


# ================== TICKETS SYSTEM ==================
@dp.message_handler(lambda msg: msg.text in [_("report_problem", lang) for lang in LANGUAGES.keys()])
async def report_problem(message: types.Message):
    user = get_or_create_user(message.from_user.id, message.from_user.username)
    open_ticket = db_session.query(Ticket).filter_by(user_id=user.user_id, is_open=True).first()

    if open_ticket:
        await message.answer(_("ticket_exists", user.language))
    else:
        new_ticket = Ticket(user_id=user.user_id)
        db_session.add(new_ticket)
        db_session.commit()
        await message.answer(_("ticket_created", user.language))

# فلتر للرسائل النصية التي ليست أوامر أو أزرار قائمة رئيسية من المستخدمين العاديين
@dp.message_handler(lambda msg: not msg.text.startswith('/') and msg.from_user.id != config.ADMIN_ID and not any(msg.text in [_("select_language_button", lang), _("report_problem", lang)] for lang in LANGUAGES.keys()))
async def handle_user_message(message: types.Message):
    user = get_or_create_user(message.from_user.id, message.from_user.username)
    open_ticket = db_session.query(Ticket).filter_by(user_id=user.user_id, is_open=True).first()

    if open_ticket:
        new_msg = TicketMessage(ticket_id=open_ticket.id, sender='user', text=message.text)
        db_session.add(new_msg)
        db_session.commit()

        keyboard = types.InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            types.InlineKeyboardButton("✍️ Reply", callback_data=f"reply:{open_ticket.id}"),
            types.InlineKeyboardButton("❌ Close Ticket", callback_data=f"close:{open_ticket.id}")
        )
        await bot.send_message(
            config.ADMIN_ID,
            f"📩 New message in Ticket #{open_ticket.id} from @{user.username}:\n\n{message.text}",
            reply_markup=keyboard
        )
        await message.answer(_("message_sent", user.language))

@dp.message_handler(lambda msg: msg.text in [_("view_tickets", lang) for lang in LANGUAGES.keys()] and msg.from_user.id == config.ADMIN_ID)
async def view_open_tickets(message: types.Message):
    open_tickets = db_session.query(Ticket).filter_by(is_open=True).all()
    if not open_tickets:
        await message.answer("📭 No open tickets at the moment.")
        return

    await message.answer("👇 Here are the currently open tickets:")
    for ticket in open_tickets:
        keyboard = types.InlineKeyboardMarkup(row_width=2)
        keyboard.add(
            types.InlineKeyboardButton("✍️ Reply", callback_data=f"reply:{ticket.id}"),
            types.InlineKeyboardButton("❌ Close Ticket", callback_data=f"close:{ticket.id}")
        )
        await message.answer(f"**Ticket #{ticket.id}** - From: @{ticket.user.username}", reply_markup=keyboard, parse_mode="Markdown")

@dp.callback_query_handler(lambda c: c.data.startswith("reply:") and c.from_user.id == config.ADMIN_ID)
async def reply_to_ticket_callback(callback: types.CallbackQuery, state: FSMContext):
    ticket_id = int(callback.data.split(":")[1])
    await state.update_data(ticket_id=ticket_id)
    await ReplyToTicketState.waiting_for_reply.set()
    await callback.message.answer(f"✍️ Please type your reply for Ticket #{ticket_id}:")
    await callback.answer()

@dp.message_handler(state=ReplyToTicketState.waiting_for_reply, user_id=config.ADMIN_ID)
async def process_admin_reply(message: types.Message, state: FSMContext):
    data = await state.get_data()
    ticket_id = data.get("ticket_id")
    ticket = db_session.query(Ticket).get(ticket_id)

    if ticket and ticket.is_open:
        admin_message = TicketMessage(ticket_id=ticket.id, sender='admin', text=message.text)
        db_session.add(admin_message)
        db_session.commit()

        await bot.send_message(ticket.user_id, _("admin_reply_header", ticket.user.language, text=message.text), parse_mode="Markdown")
        await message.answer(f"✅ Your reply has been sent for Ticket #{ticket.id}.")
    else:
        await message.answer("This ticket seems to be closed already.")
    await state.finish()

@dp.callback_query_handler(lambda c: c.data.startswith("close:") and c.from_user.id == config.ADMIN_ID)
async def close_ticket_callback(callback: types.CallbackQuery):
    ticket_id = int(callback.data.split(":")[1])
    ticket = db_session.query(Ticket).get(ticket_id)
    if ticket:
        ticket.is_open = False
        db_session.commit()
        await bot.send_message(ticket.user_id, _("ticket_closed_user", ticket.user.language))
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
    print("Starting bot...")
    load_translations() # تحميل ملفات اللغة عند بدء التشغيل
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.start()
    executor.start_polling(dp, skip_updates=True)
