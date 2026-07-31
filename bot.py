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
# ANALYSIS STATE (in-memory)
# Tracks multi-timeframe chart collection per user
# =========================
analysis_state = {}

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
def safe_send(chat_id, text, reply_markup=None):
    MAX = 4000
    if len(text) <= MAX:
        bot.send_message(
            chat_id,
            text,
            reply_markup=reply_markup
        )
        return

    parts = [
        text[i:i + MAX]
        for i in range(0, len(text), MAX)
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
    return load("credits.json").get(str(uid), 0)

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
FREE_LIMIT = 1

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
    bot.send_chat_action(chat_id, "typing")
    time.sleep(sec)

# =========================
# CLEANUP TEMP FILES
# =========================
def cleanup_files(*paths):
    for path in paths:
        try:
            if path and os.path.exists(path):
                os.remove(path)
        except:
            pass

# =========================
# GEMINI CALL (MULTI-IMAGE)
# =========================
def call_gemini(prompt, image_base64_list):
    try:
        contents = [prompt]
        for b64 in image_base64_list:
            contents.append({
                "inline_data": {
                    "mime_type": "image/jpeg",
                    "data": b64
                }
            })

        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=contents
        )

        if response.text:
            return response.text

    except Exception as e:
        print("Gemini Error:", e)

    return None

# =========================
# AI ANALYSIS (MULTI-TIMEFRAME)
# =========================
def analyze_market(message, htf_path, ltf_path):
    try:
        prompt = """
You are an elite institutional forex trader and Smart Money Concepts (SMC) / ICT expert working at a top-tier hedge fund.

You will receive TWO charts in this exact order:
1. HIGHER TIMEFRAME chart (HTF)
2. LOWER TIMEFRAME chart (LTF)

STRICT ANALYSIS ORDER:

STEP 1 — HIGHER TIMEFRAME (Primary Bias)
- Determine overall trend and institutional bias
- Identify Market Structure (HH, HL, LH, LL)
- Detect Break of Structure (BOS) and Change of Character (CHoCH)
- Map major Liquidity pools (Equal Highs/Lows, buy-side & sell-side liquidity)
- Identify Order Blocks (bullish & bearish)
- Spot Fair Value Gaps (FVG / Imbalances)
- Determine Premium / Discount zones relative to the dealing range
- Note any Breaker Blocks, Mitigation Blocks, or Inducement
- Assess Institutional Order Flow

STEP 2 — LOWER TIMEFRAME (Confirmation & Entry Only)
- Use LTF strictly for confirmation of the HTF bias and precise entry
- Look for alignment: LTF structure, liquidity sweep, order block, FVG, or inducement that supports the HTF direction
- If LTF shows clear opposing structure or strong counter bias → NO TRADE

CRITICAL RULES:
- Accuracy is more important than frequency
- NEVER force a trade
- If HTF and LTF disagree → Return NO TRADE ⛔
- If setup is weak, unclear, low probability, or missing clear entry/SL/TP → Return NO TRADE ⛔
- Do not guess. If confidence is not high enough for a clean institutional setup → NO TRADE
- Only give BUY or SELL when both timeframes align and a high-probability setup is present

OUTPUT RULES:
- DO NOT use markdown symbols like ** or *
- Use clean Telegram-friendly formatting
- Use professional emojis correctly
- Keep spacing clean and premium
- Sound like a professional hedge fund analyst
- Be direct and precise
- Always give one final signal: BUY / SELL / NO TRADE

STRICT OUTPUT FORMAT (follow exactly):

━━━━━━━━━━━━━━━━━━
🚀 AMUDANCE FX
━━━━━━━━━━━━━━━━━━

📈 MARKET ANALYSIS

🕒 Higher Timeframe Bias
(Explain HTF structure, trend, and institutional bias clearly)

🕒 Lower Timeframe Confirmation
(Explain whether LTF confirms or rejects the HTF bias)

📊 Market Direction
Bullish 📈 / Bearish 📉 / Ranging 🔄

🏗 Market Structure
(Explain BOS / CHoCH on both timeframes simply)

💧 Liquidity Analysis
(Major liquidity pools, equal highs/lows, inducement)

🏦 Institutional Bias
(Smart money direction based on HTF)

📦 Order Blocks
(Key bullish/bearish order blocks relevant to the setup)

🟨 Fair Value Gap
(Relevant FVGs that may act as targets or entries)

📍 Premium / Discount
(Where price is relative to the dealing range)

🎯 Trade Setup
(Clear explanation of the setup)

📥 Entry Zone
(Exact zone or level)

🛑 Stop Loss
(Exact level)

💰 Take Profit
TP1:
TP2:
TP3:

⚖️ Risk : Reward
(e.g. 1:2, 1:3, etc.)

🔥 Confidence (%)
(e.g. 75%)

⚠️ Risk Level
Low / Moderate / High

📌 Final Signal
BUY 📈
SELL 📉
or
NO TRADE ⛔

🧠 Professional Advice
(Short professional advice)

━━━━━━━━━━━━━━━━━━
⚠️ Trade Responsibly
━━━━━━━━━━━━━━━━━━

If the final signal is NO TRADE, still fill the analysis sections honestly but clearly state why no trade is taken. Do not invent entry, SL, or TP levels when the signal is NO TRADE.
"""

        bot.send_message(
            message.chat.id,
            "📡 Both charts received..."
        )
        human_delay(message.chat.id)

        bot.send_message(
            message.chat.id,
            "🧠 Analyzing Higher Timeframe bias..."
        )
        human_delay(message.chat.id)

        bot.send_message(
            message.chat.id,
            "📉 Checking Lower Timeframe confirmation..."
        )
        human_delay(message.chat.id)

        bot.send_message(
            message.chat.id,
            "📊 Mapping market structure & liquidity..."
        )
        human_delay(message.chat.id)

        bot.send_message(
            message.chat.id,
            "🏦 Tracking institutional order flow..."
        )
        human_delay(message.chat.id)

        image_base64_list = []

        with open(htf_path, "rb") as f:
            image_base64_list.append(
                base64.b64encode(f.read()).decode()
            )

        with open(ltf_path, "rb") as f:
            image_base64_list.append(
                base64.b64encode(f.read()).decode()
            )

        result = call_gemini(prompt, image_base64_list)

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

    except Exception as e:
        print("Analysis Error:", e)
        bot.send_message(
            message.chat.id,
            limit_message(),
            reply_markup=main_menu()
        )

    finally:
        cleanup_files(htf_path, ltf_path)

# =========================
# START
# =========================
@bot.message_handler(commands=['start'])
def start(m):
    register_user(m.chat.id)

    # Clear any incomplete analysis state
    analysis_state.pop(str(m.chat.id), None)

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
    func=lambda m: m.text == "💳 Buy Credits"
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
                callback_data=f"buy_{price}_{credits}"
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
    func=lambda c: c.data.startswith("buy_")
)
def buy_callback(c):
    _, amount, credits = c.data.split("_")

    uid = str(c.message.chat.id)

    pending = load("pending_payments.json")

    pending[uid] = {
        "amount": int(amount),
        "credits": int(credits),
        "time": str(datetime.now())
    }

    save("pending_payments.json", pending)

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
    func=lambda c: c.data.startswith("paid_")
)
def user_paid(c):
    uid = c.data.split("_")[1]

    pending = load("pending_payments.json")

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
    func=lambda c: c.data.startswith("approve_") or c.data.startswith("reject_")
)
def admin_action(c):
    if c.from_user.id != ADMIN_ID:
        return bot.answer_callback_query(
            c.id,
            "Not allowed"
        )

    action, uid = c.data.split("_")

    pending = load("pending_payments.json")

    if uid not in pending:
        return bot.answer_callback_query(
            c.id,
            "Already processed"
        )

    data = pending[uid]

    if action == "approve":
        add_credit(uid, data["credits"])

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
    save("pending_payments.json", pending)

    bot.answer_callback_query(c.id, "Done")

# =========================
# IMAGE HANDLER (MULTI-TIMEFRAME)
# =========================
@bot.message_handler(content_types=['photo', 'document'])
def handle_image(m):
    try:
        uid = str(m.chat.id)

        # Determine file info
        if m.content_type == "photo":
            file_info = bot.get_file(m.photo[-1].file_id)
        else:
            if not m.document.mime_type or not m.document.mime_type.startswith("image/"):
                return bot.reply_to(
                    m,
                    "❌ Only image files allowed"
                )
            file_info = bot.get_file(m.document.file_id)

        state = analysis_state.get(uid)

        # ---------- Not in analysis flow ----------
        if not state:
            bot.reply_to(
                m,
                """
📸 To start analysis, first click:

📊 Analyze Market
""",
                reply_markup=main_menu()
            )
            return

        # ---------- Waiting for Higher Timeframe ----------
        if state["step"] == "waiting_htf":
            file = bot.download_file(file_info.file_path)
            htf_path = f"htf_{m.chat.id}.jpg"

            with open(htf_path, "wb") as f:
                f.write(file)

            analysis_state[uid] = {
                "step": "waiting_ltf",
                "htf_path": htf_path
            }

            bot.send_message(
                m.chat.id,
                """
✅ Higher timeframe received.

📉 Now send the LOWER TIMEFRAME chart.

Recommended:
• M15
• M5
• M1
"""
            )
            return

        # ---------- Waiting for Lower Timeframe ----------
        if state["step"] == "waiting_ltf":
            file = bot.download_file(file_info.file_path)
            ltf_path = f"ltf_{m.chat.id}.jpg"

            with open(ltf_path, "wb") as f:
                f.write(file)

            htf_path = state["htf_path"]

            # Clear state immediately
            analysis_state.pop(uid, None)

            # Check credits / free trial NOW (only when both charts are ready)
            if get_credit(uid) > 0:
                if not use_credit(uid):
                    cleanup_files(htf_path, ltf_path)
                    return bot.reply_to(
                        m,
                        "❌ No credits left",
                        reply_markup=main_menu()
                    )

                threading.Thread(
                    target=analyze_market,
                    args=(m, htf_path, ltf_path)
                ).start()
                return

            if can_use_free(uid):
                use_free(uid)

                threading.Thread(
                    target=analyze_market,
                    args=(m, htf_path, ltf_path)
                ).start()
                return

            cleanup_files(htf_path, ltf_path)

            bot.reply_to(
                m,
                """
❌ Free trial finished.

💳 Buy credits to continue.
""",
                reply_markup=main_menu()
            )
            return

    except Exception as e:
        print("Image Handler Error:", e)
        analysis_state.pop(str(m.chat.id), None)
        bot.reply_to(
            m,
            limit_message(),
            reply_markup=main_menu()
        )

# =========================
# BALANCE
# =========================
@bot.message_handler(
    func=lambda m: m.text == "💰 My Balance"
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
    func=lambda m: m.text == "📞 Support"
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
# ANALYZE BUTTON (START MULTI-TIMEFRAME FLOW)
# =========================
@bot.message_handler(
    func=lambda m: m.text == "📊 Analyze Market"
)
def ask_chart(m):
    uid = str(m.chat.id)

    # Reset any previous incomplete state
    old_state = analysis_state.pop(uid, None)
    if old_state and "htf_path" in old_state:
        cleanup_files(old_state.get("htf_path"))

    analysis_state[uid] = {
        "step": "waiting_htf"
    }

    bot.reply_to(
        m,
        """
📈 Please send the HIGHER TIMEFRAME chart first.

Recommended:
• D1
• H4
• H1
""",
        reply_markup=main_menu()
    )

# =========================
# BROADCAST SYSTEM
# =========================
broadcast_mode = {}

@bot.message_handler(
    func=lambda m: m.text == "📢 Broadcast"
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
    func=lambda m: broadcast_mode.get(m.chat.id)
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
    bot.infinity_polling(skip_pending=True)
