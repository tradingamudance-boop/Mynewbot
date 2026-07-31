import telebot
from telebot import types
from flask import Flask
import os
import json
import time
import base64
import threading
from datetime import datetime
from dotenv import load_dotenv
from google import genai

# =========================
# ENV
# =========================
load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

if not BOT_TOKEN:
    raise Exception("BOT_TOKEN missing")

if not GEMINI_API_KEY:
    raise Exception("GEMINI_API_KEY missing")

# =========================
# BANK DETAILS
# =========================
BANK_NAME = "OPay"
ACCOUNT_NUMBER = "7048508048"
ACCOUNT_NAME = "AMUJO TIMILEHIN"

# =========================
# INIT
# =========================
bot = telebot.TeleBot(
    BOT_TOKEN,
    parse_mode="HTML"
)

client = genai.Client(
    api_key=GEMINI_API_KEY
)

app = Flask(__name__)

# =========================
# FILES
# =========================
FILES = [
    "users.json",
    "credits.json",
    "free_trial.json",
    "pending_payments.json"
]

for f in FILES:

    if not os.path.exists(f):

        with open(f, "w") as x:
            json.dump({}, x)

# =========================
# GEMINI MODEL
# =========================
GEMINI_MODEL = "gemini-2.5-flash"

# =========================
# HELPERS
# =========================
def load(f):

    try:

        with open(f, "r") as x:
            return json.load(x)

    except:
        return {}

def save(f, d):

    with open(f, "w") as x:
        json.dump(d, x, indent=4)

# =========================
# REGISTER USERS
# =========================
def register_user(uid):

    users = load("users.json")

    uid = str(uid)

    if uid not in users:

        users[uid] = {
            "joined": str(datetime.now())
        }

    save("users.json", users)

# =========================
# MAIN MENU
# =========================
def main_menu():

    markup = types.ReplyKeyboardMarkup(
        resize_keyboard=True
    )

    markup.row(
        "📊 Analyze Market",
        "💳 Buy Credits"
    )

    markup.row(
        "💰 My Balance",
        "📞 Support"
    )

    markup.row(
        "📢 Broadcast"
    )

    return markup

# =========================
# LIMIT MESSAGE
# =========================
def limit_message():

    return (
        "⚠️ Server busy or analysis temporarily unavailable.\n\n"
        "Please try again later."
    )

# =========================
# SAFE SEND
# FIX TOO LONG ERROR
# =========================
def safe_send(
    chat_id,
    text,
    reply_markup=None
):

    MAX = 4000

    if len(text) <= MAX:

        bot.send_message(
            chat_id,
            text,
            reply_markup=reply_markup
        )

        return

    parts = [
        text[i:i+MAX]
        for i in range(
            0,
            len(text),
            MAX
        )
    ]

    for part in parts:

        bot.send_message(
            chat_id,
            part,
            reply_markup=reply_markup
        )

# =========================
# CREDIT SYSTEM
# =========================
def get_credit(uid):

    return load(
        "credits.json"
    ).get(str(uid), 0)

def add_credit(uid, amt):

    data = load("credits.json")

    uid = str(uid)

    data[uid] = data.get(uid, 0) + amt

    save("credits.json", data)

def use_credit(uid):

    data = load("credits.json")

    uid = str(uid)

    if data.get(uid, 0) > 0:

        data[uid] -= 1

        save("credits.json", data)

        return True

    return False

# =========================
# FREE TRIAL
# FIRST TIME ONLY
# =========================
FREE_LIMIT = 2

def get_free_used(uid):

    data = load("free_trial.json")

    return data.get(str(uid), 0)

def can_use_free(uid):

    return get_free_used(uid) < FREE_LIMIT

def use_free(uid):

    data = load("free_trial.json")

    uid = str(uid)

    data[uid] = data.get(uid, 0) + 1

    save("free_trial.json", data)

# =========================
# HUMAN EFFECT
# =========================
def human_delay(chat_id, sec=1):

    bot.send_chat_action(
        chat_id,
        "typing"
    )

    time.sleep(sec)

# =========================
# GEMINI CALL
# =========================
def call_gemini(
    prompt,
    image_base64
):

    try:

        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[
                prompt,
                {
                    "inline_data": {
                        "mime_type": "image/jpeg",
                        "data": image_base64
                    }
                }
            ]
        )

        if response.text:
            return response.text

    except Exception as e:

        print(
            "Gemini Error:",
            e
        )

    return None

# =========================
# AI ANALYSIS
# =========================
def analyze_market(
    message,
    file_info
):

    try:

        file = bot.download_file(
            file_info.file_path
        )

        path = f"""
chart_{message.chat.id}.jpg
""".strip()

        with open(path, "wb") as f:
            f.write(file)

        prompt = """
You are an elite institutional forex trader and Smart Money Concepts expert.

Analyze this forex chart professionally using:
- Smart Money Concepts (SMC)
- ICT concepts
- Liquidity theory
- Institutional order flow
- Market structure

IMPORTANT RULES:
- DO NOT use markdown symbols like ** or *
- Use clean Telegram-friendly formatting
- Use professional emojis correctly
- Keep spacing clean and premium
- Avoid confusing explanations
- Make the analysis understandable even for beginners
- Sound like a professional hedge fund analyst
- Be direct and accurate
- ALWAYS give one final signal:
BUY / SELL / NO TRADE

VERY IMPORTANT:
If the setup is weak or unclear:
→ Return NO TRADE

If buyers are dominant:
→ Return BUY

If sellers are dominant:
→ Return SELL

STRICT FORMAT:

━━━━━━━━━━━━━━━━━━
🚀 AMUDANCE FX
━━━━━━━━━━━━━━━━━━

📈 MARKET ANALYSIS

🕒 Timeframe:
Mention timeframe clearly.

📊 Market Direction:
Bullish 📈 / Bearish 📉 / Ranging 🔄

🏗 Market Structure:
Explain BOS or CHoCH simply.

💧 Liquidity Zones:
Show major liquidity clearly.

🏦 Institutional Bias:
Explain smart money direction.

🎯 Trade Setup:
Explain setup clearly.

📥 Entry Zone:
Give exact entry.

🛑 Stop Loss:
Give exact SL.

💰 Take Profit Targets:
TP1:
TP2:
TP3:

⚠️ Risk Level:
Low / Moderate / High

🔥 Confidence Level:
Low / Moderate / High

📌 Trading Signal:
BUY 📈
SELL 📉
or
NO TRADE ⛔

🧠 Professional Advice:
Give short professional advice.

━━━━━━━━━━━━━━━━━━
⚠️ Trade responsibly
━━━━━━━━━━━━━━━━━━
"""

        bot.send_message(
            message.chat.id,
            "📡 Upload received..."
        )

        human_delay(message.chat.id)

        bot.send_message(
            message.chat.id,
            "🧠 AI analyzing chart..."
        )

        human_delay(message.chat.id)

        bot.send_message(
            message.chat.id,
            "📊 Processing market structure..."
        )

        human_delay(message.chat.id)

        bot.send_message(
            message.chat.id,
            "💧 Detecting liquidity zones..."
        )

        human_delay(message.chat.id)

        bot.send_message(
            message.chat.id,
            "🏦 Tracking institutional flow..."
        )

        human_delay(message.chat.id)

        with open(path, "rb") as f:

            image_bytes = f.read()

        image_base64 = base64.b64encode(
            image_bytes
        ).decode()

        result = call_gemini(
            prompt,
            image_base64
        )

        if not result:

            bot.send_message(
                message.chat.id,
                limit_message(),
                reply_markup=main_menu()
            )

            return

        safe_send(
            message.chat.id,
            result,
            reply_markup=main_menu()
        )

        try:
            os.remove(path)
        except:
            pass

    except Exception as e:

        print(
            "Analysis Error:",
            e
        )

        bot.send_message(
            message.chat.id,
            limit_message(),
            reply_markup=main_menu()
        )

# =========================
# START
# =========================
@bot.message_handler(
    commands=['start']
)
def start(m):

    register_user(m.chat.id)

    bot.send_message(
        m.chat.id,
        f"""
━━━━━━━━━━━━━━━━━━
🚀 AMUDANCE FX
━━━━━━━━━━━━━━━━━━

📊 Professional Market Analysis

💎 Credits:
{get_credit(m.chat.id)}

🎁 Free Trial Left:
{FREE_LIMIT - get_free_used(m.chat.id)}

Choose an option below 👇
""",
        reply_markup=main_menu()
    )

# =========================
# BUY CREDITS
# =========================
@bot.message_handler(
    func=lambda m:
    m.text == "💳 Buy Credits"
)
def buy(m):

    markup = types.InlineKeyboardMarkup()

    plans = [
        (500, 1),
        (1000, 2),
        (2000, 4),
        (3000, 6),
        (5000, 10),
        (10000, 20)
    ]

    for price, credits in plans:

        markup.add(
            types.InlineKeyboardButton(
                f"{credits} Credits - ₦{price}",
                callback_data=f"""
buy_{price}_{credits}
""".strip()
            )
        )

    bot.send_message(
        m.chat.id,
        "💎 Choose your credit plan:",
        reply_markup=markup
    )

# =========================
# BUY CALLBACK
# =========================
@bot.callback_query_handler(
    func=lambda c:
    c.data.startswith("buy_")
)
def buy_callback(c):

    _, amount, credits = c.data.split("_")

    uid = str(c.message.chat.id)

    pending = load(
        "pending_payments.json"
    )

    pending[uid] = {
        "amount": int(amount),
        "credits": int(credits),
        "time": str(datetime.now())
    }

    save(
        "pending_payments.json",
        pending
    )

    markup = types.InlineKeyboardMarkup()

    markup.add(
        types.InlineKeyboardButton(
            "✅ I HAVE PAID",
            callback_data=f"paid_{uid}"
        )
    )

    bot.send_message(
        uid,
        f"""
🏦 PAYMENT DETAILS

Bank:
{BANK_NAME}

Account Number:
{ACCOUNT_NUMBER}

Account Name:
{ACCOUNT_NAME}

💰 Amount:
₦{amount}

💎 Credits:
{credits}

⚠️ After payment click the button below.
""",
        reply_markup=markup
    )

# =========================
# USER PAID
# =========================
@bot.callback_query_handler(
    func=lambda c:
    c.data.startswith("paid_")
)
def user_paid(c):

    uid = c.data.split("_")[1]

    pending = load(
        "pending_payments.json"
    )

    if uid not in pending:

        return bot.answer_callback_query(
            c.id,
            "No pending payment found"
        )

    data = pending[uid]

    user = bot.get_chat(uid)

    username = (
        f"@{user.username}"
        if user.username
        else "No Username"
    )

    full_name = user.first_name

    markup = types.InlineKeyboardMarkup()

    markup.row(
        types.InlineKeyboardButton(
            "✅ APPROVE",
            callback_data=f"approve_{uid}"
        ),
        types.InlineKeyboardButton(
            "❌ REJECT",
            callback_data=f"reject_{uid}"
        )
    )

    bot.send_message(
        ADMIN_ID,
        f"""
💰 PAYMENT REQUEST

👤 Name:
{full_name}

🆔 User ID:
{uid}

🌐 Username:
{username}

💵 Amount:
₦{data['amount']}

💎 Credits:
{data['credits']}

🕒 Time:
{data['time']}
""",
        reply_markup=markup
    )

    bot.answer_callback_query(
        c.id,
        "Payment sent for review ✅"
    )

# =========================
# ADMIN ACTION
# =========================
@bot.callback_query_handler(
    func=lambda c:
    c.data.startswith("approve_")
    or c.data.startswith("reject_")
)
def admin_action(c):

    if c.from_user.id != ADMIN_ID:

        return bot.answer_callback_query(
            c.id,
            "Not allowed"
        )

    action, uid = c.data.split("_")

    pending = load(
        "pending_payments.json"
    )

    if uid not in pending:

        return bot.answer_callback_query(
            c.id,
            "Already processed"
        )

    data = pending[uid]

    if action == "approve":

        add_credit(
            uid,
            data["credits"]
        )

        bot.send_message(
            uid,
            f"""
✅ PAYMENT APPROVED

🎉 {data['credits']} credits added successfully.
""",
            reply_markup=main_menu()
        )

        bot.send_message(
            ADMIN_ID,
            "✅ Payment approved"
        )

    else:

        bot.send_message(
            uid,
            """
❌ Payment rejected.

Contact support.
""",
            reply_markup=main_menu()
        )

        bot.send_message(
            ADMIN_ID,
            "❌ Payment rejected"
        )

    del pending[uid]

    save(
        "pending_payments.json",
        pending
    )

    bot.answer_callback_query(
        c.id,
        "Done"
    )

# =========================
# IMAGE HANDLER
# =========================
@bot.message_handler(
    content_types=[
        'photo',
        'document'
    ]
)
def handle_image(m):

    try:

        if m.content_type == "photo":

            file_info = bot.get_file(
                m.photo[-1].file_id
            )

        else:

            if not m.document.mime_type.startswith(
                "image/"
            ):

                return bot.reply_to(
                    m,
                    "❌ Only image files allowed"
                )

            file_info = bot.get_file(
                m.document.file_id
            )

        uid = str(m.chat.id)

        # PAID USERS
        if get_credit(uid) > 0:

            if not use_credit(uid):

                return bot.reply_to(
                    m,
                    "❌ No credits left"
                )

            threading.Thread(
                target=analyze_market,
                args=(m, file_info)
            ).start()

            return

        # FREE USERS
        if can_use_free(uid):

            use_free(uid)

            threading.Thread(
                target=analyze_market,
                args=(m, file_info)
            ).start()

            return

        bot.reply_to(
            m,
            """
❌ Free trial finished.

💳 Buy credits to continue.
""",
            reply_markup=main_menu()
        )

    except Exception as e:

        print(
            "Image Handler Error:",
            e
        )

        bot.reply_to(
            m,
            limit_message(),
            reply_markup=main_menu()
        )

# =========================
# BALANCE
# =========================
@bot.message_handler(
    func=lambda m:
    m.text == "💰 My Balance"
)
def balance(m):

    bot.reply_to(
        m,
        f"""
💎 Credits:
{get_credit(m.chat.id)}

🎁 Free Trial Left:
{FREE_LIMIT - get_free_used(m.chat.id)}
""",
        reply_markup=main_menu()
    )

# =========================
# SUPPORT
# =========================
@bot.message_handler(
    func=lambda m:
    m.text == "📞 Support"
)
def support(m):

    bot.reply_to(
        m,
        """
📞 Support:
@Amudancefx
""",
        reply_markup=main_menu()
    )

# =========================
# ANALYZE BUTTON
# =========================
@bot.message_handler(
    func=lambda m:
    m.text == "📊 Analyze Market"
)
def ask_chart(m):

    bot.reply_to(
        m,
        """
📸 Send your chart screenshot for analysis.
""",
        reply_markup=main_menu()
    )

# =========================
# BROADCAST SYSTEM
# =========================
broadcast_mode = {}

@bot.message_handler(
    func=lambda m:
    m.text == "📢 Broadcast"
)
def broadcast(m):

    if m.chat.id != ADMIN_ID:

        return bot.reply_to(
            m,
            "❌ Admin only."
        )

    broadcast_mode[m.chat.id] = True

    bot.reply_to(
        m,
        """
📢 Send your announcement now.
"""
    )

@bot.message_handler(
    func=lambda m:
    broadcast_mode.get(m.chat.id)
)
def send_broadcast(m):

    if m.chat.id != ADMIN_ID:
        return

    users = load("users.json")

    sent = 0
    failed = 0

    bot.reply_to(
        m,
        "📡 Broadcasting message..."
    )

    for uid in users:

        try:

            bot.send_message(
                uid,
                f"""
📢 ANNOUNCEMENT

{m.text}
"""
            )

            sent += 1

            time.sleep(0.1)

        except:

            failed += 1

    broadcast_mode[m.chat.id] = False

    bot.send_message(
        ADMIN_ID,
        f"""
✅ Broadcast Completed

👥 Sent:
{sent}

❌ Failed:
{failed}
"""
    )

# =========================
# FLASK
# =========================
@app.route("/")
def home():

    return "BOT RUNNING"

# =========================
# RUN BOT
# =========================
if __name__ == "__main__":

    print("BOT STARTED")

    bot.infinity_polling(
        skip_pending=True
            )