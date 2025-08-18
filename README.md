# telegram_bot_store
store
---

# Telegram Shop Bot

A simple Telegram bot for selling electronic tools and services.
The bot allows users to place orders, send payment, and notify the admin.
Admin can manage orders (approve, cancel, deliver).

---

## 🚀 Features

* Product catalog with multiple options (hours & prices).
* Order creation with unique order ID.
* JSON-based storage (no SQL required).
* Payment flow:

  1. User selects a product.
  2. Bot sends product + price + Binance ID for payment.
  3. User clicks **"✅ I have paid"** after payment.
  4. Admin receives notification.
* Admin commands:

  * `/orders` → list all orders.
  * `/delivered <order_id>` → mark order as delivered.
  * `/cancel <order_id>` → cancel an order.

---

## 📦 Installation

1. **Clone project**

```bash
git clone https://github.com/yourusername/telegram-shop-bot.git
cd telegram-shop-bot
```

2. **Install dependencies**

```bash
pip install python-telegram-bot==20.3
```

3. **Set your Bot Token**

* Create a bot on Telegram via [BotFather](https://t.me/BotFather).
* Copy the API token.
* Replace `"YOUR_BOT_TOKEN_HERE"` in `bot.py` with your token.

4. **Set your Admin ID**

* Get your Telegram user ID (use [@userinfobot](https://t.me/userinfobot)).
* Replace `ADMIN_ID = 123456789` with your ID.

---

## ▶️ Run the bot

```bash
python bot.py
```

---

## 📂 Project Structure

```
telegram-shop-bot/
│-- bot.py        # Main bot code
│-- products.json # Product catalog
│-- orders.json   # Order storage (auto-created)
│-- README.md     # Documentation
```

---

## 🛒 Product Catalog

Example `products.json`:

```json
{
  "Unlock tool": {
    "6h": 6,
    "8h": 7,
    "12h": 9,
    "24h": 12
  },
  "Android Multi Tool AMT": {
    "2h": 6,
    "2h + 5 credits": 12,
    "Credit": 1.5
  },
  "TSM TOOL": {
    "6h": 5,
    "12h": 8,
    "24h": 12
  },
  "Cheetah Pro Tool": {
    "4h": 5,
    "8h": 8,
    "12h": 12
  },
  "TFM Tool Pro": {
    "6h": 5,
    "12h": 8,
    "24h": 12,
    "24h + 5 credits": 16,
    "Credit": 1.5
  },
  "DFT Pro Tool": {
    "48h": 9,
    "4 days": 14,
    "6 days": 16
  }
}
```

---

## 🔑 Admin Workflow

1. User places order.
2. Admin gets notification.
3. Admin checks with `/orders`.
4. Admin decides:

   * `/delivered <id>` → order delivered
   * `/cancel <id>` → order canceled

---
