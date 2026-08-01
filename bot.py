import telebot
from telebot import types
from flask import Flask
import os
import json
import time
import base64
import threading
import random
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

# Session expires after 12 minutes of inactivity
SESSION_TIMEOUT = 12 * 60

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
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True)
    markup.row("📊 Analyze Market", "💳 Buy Credits")
    markup.row("💰 My Balance", "📞 Support")
    markup.row("📢 Broadcast")
    return markup

# =========================
# LIMIT MESSAGE
# =========================
def limit_message():
    return (
        "⚠️ <b>Analysis Unavailable</b>\n\n"
        "Server is busy or temporarily unavailable.\n"
        "Please try again shortly."
    )

# =========================
# SAFE SEND
# =========================
def safe_send(chat_id, text, reply_markup=None):
    MAX = 4000
    if len(text) <= MAX:
        bot.send_message(chat_id, text, reply_markup=reply_markup)
        return

    parts = [text[i:i + MAX] for i in range(0, len(text), MAX)]
    for part in parts:
        bot.send_message(chat_id, part, reply_markup=reply_markup)

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

def has_access(uid):
    """True if user has credits or free trial remaining."""
    return get_credit(uid) > 0 or can_use_free(uid)

# =========================
# HUMAN EFFECT
# =========================
def human_delay(chat_id, sec=None):
    bot.send_chat_action(chat_id, "typing")
    time.sleep(sec if sec is not None else random.uniform(0.9, 1.6))

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
# SESSION HELPERS
# =========================
def clear_session(uid, notify=False, chat_id=None):
    """Clear analysis state and optionally notify user."""
    state = analysis_state.pop(str(uid), None)
    if state and "htf_path" in state:
        cleanup_files(state.get("htf_path"))
    if notify and chat_id:
        try:
            bot.send_message(
                chat_id,
                "⏱ <b>Session expired</b>\n\n"
                "Please tap <b>📊 Analyze Market</b> to start again.",
                reply_markup=main_menu()
            )
        except:
            pass

def is_session_expired(uid):
    state = analysis_state.get(str(uid))
    if not state:
        return False
    started = state.get("started", 0)
    return (time.time() - started) > SESSION_TIMEOUT

def refresh_session(uid):
    """Update timestamp so active users don't expire mid-flow."""
    state = analysis_state.get(str(uid))
    if state:
        state["started"] = time.time()

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
You are a senior proprietary desk trader specialising in Smart Money Concepts (SMC) and ICT.

You receive TWO charts in this exact order:
1. HIGHER TIMEFRAME (HTF) — primary bias
2. LOWER TIMEFRAME (LTF) — confirmation and entry only

ANALYSIS ORDER (strict):

STEP 1 — HTF (Primary Bias)
- Overall trend and institutional bias
- Market Structure (HH, HL, LH, LL)
- BOS and CHoCH
- Major liquidity (equal highs/lows, buy-side & sell-side)
- Order Blocks, Fair Value Gaps, Breaker / Mitigation Blocks
- Premium / Discount relative to the dealing range
- Inducement and institutional order flow
- Note the trading session if visible (Asian / London / New York)

STEP 2 — LTF (Confirmation & Entry only)
- Use LTF only to confirm HTF bias and locate precise entry
- Look for liquidity sweep, order block, FVG, or inducement that aligns with HTF
- If LTF shows opposing structure or strong counter-bias → NO TRADE

HARD RULES (never break these):
- Accuracy over frequency. Never force a trade.
- If HTF and LTF disagree → NO TRADE ⛔
- If the setup is weak, unclear, or missing a clean entry / SL / TP → NO TRADE ⛔
- NO CHASE: If price has already run a large portion of the expected move, or the only available entry is after a strong impulsive candle with no pullback → NO TRADE ⛔
- Prefer waiting for a return to a point of interest (OB / FVG / mitigation) rather than chasing.
- Prefer high-probability setups during London and New York. Be more selective in dead Asian ranges.
- Do not invent levels. If you cannot determine accurate Entry, SL and TPs → NO TRADE.

WRITING STYLE:
- Write like a senior prop-desk analyst briefing a colleague.
- Never say “As an AI”, “Based on the chart provided”, or similar.
- Be direct, precise and calm.
- Professional Advice must be 2–3 short lines maximum.
- When signal is NO TRADE, state the main reason in one clear sentence first.

OUTPUT RULES:
- DO NOT use markdown symbols like ** or *
- Clean Telegram-friendly formatting only
- Professional emojis, clean spacing
- Always give exactly one final signal: BUY / SELL / NO TRADE

STRICT OUTPUT FORMAT:

━━━━━━━━━━━━━━━━━━
🚀 PROFITPULSE AI
━━━━━━━━━━━━━━━━━━

📈 MARKET ANALYSIS

🕒 Higher Timeframe Bias
(Clear HTF structure, trend and institutional bias)

🕒 Lower Timeframe Confirmation
(Does LTF confirm or reject the HTF bias?)

📊 Market Direction
Bullish 📈 / Bearish 📉 / Ranging 🔄

🏗 Market Structure
(BOS / CHoCH on both timeframes, simply)

💧 Liquidity Analysis
(Major pools, equal highs/lows, inducement)

🏦 Institutional Bias
(Smart money direction from HTF)

📦 Order Blocks
(Key relevant OBs)

🟨 Fair Value Gap
(Relevant FVGs)

📍 Premium / Discount
(Where price sits in the dealing range)

🎯 Trade Setup
(Clear explanation — or why there is none)

📥 Entry Zone
(Exact zone/level — or N/A if NO TRADE)

🛑 Stop Loss
(Exact level — or N/A if NO TRADE)

💰 Take Profit
TP1:
TP2:
TP3:

⚖️ Risk : Reward
(e.g. 1:2 — or N/A if NO TRADE)

🔥 Confidence (%)
(e.g. 75% — or Low if NO TRADE)

⚠️ Risk Level
Low / Moderate / High

📌 Final Signal
BUY 📈
SELL 📉
or
NO TRADE ⛔

🧠 Professional Advice
(2–3 short lines max. If NO TRADE, state the main reason clearly.)

━━━━━━━━━━━━━━━━━━
⚠️ Trade responsibly. This is analysis, not financial advice.
━━━━━━━━━━━━━━━━━━
"""

        # Slightly varied progress messages for realism
        steps = [
            "📡 Charts received",
            "🧠 Reading higher timeframe structure…",
            "📉 Checking lower timeframe for confirmation…",
            "🏦 Mapping liquidity and institutional flow…"
        ]

        for step in steps:
            bot.send_message(message.chat.id, step)
            human_delay(message.chat.id)

        image_base64_list = []

        with open(htf_path, "rb") as f:
            image_base64_list.append(base64.b64encode(f.read()).decode())

        with open(ltf_path, "rb") as f:
            image_base64_list.append(base64.b64encode(f.read()).decode())

        result = call_gemini(prompt, image_base64_list)

        if not result:
            bot.send_message(
                message.chat.id,
                limit_message(),
                reply_markup=main_menu()
            )
            return

        safe_send(message.chat.id, result, reply_markup=main_menu())

        # Soft reminder when credits are running low
        remaining = get_credit(message.chat.id)
        if 0 < remaining <= 2:
            bot.send_message(
                message.chat.id,
                f"💎 You have <b>{remaining}</b> credit{'s' if remaining != 1 else ''} left."
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
    clear_session(m.chat.id)

    bot.send_message(
        m.chat.id,
        f"""━━━━━━━━━━━━━━━━━━
🚀 <b>PROFITPULSE AI</b>
━━━━━━━━━━━━━━━━━━

Professional Multi-Timeframe Analysis

💎 Credits: <b>{get_credit(m.chat.id)}</b>
🎁 Free Trial Left: <b>{FREE_LIMIT - get_free_used(m.chat.id)}</b>

Choose an option below 👇""",
        reply_markup=main_menu()
    )

# =========================
# BUY CREDITS
# =========================
@bot.message_handler(func=lambda m: m.text == "💳 Buy Credits")
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
                f"{credits} Credits — ₦{price}",
                callback_data=f"buy_{price}_{credits}"
            )
        )

    bot.send_message(
        m.chat.id,
        "💎 <b>Select a credit plan</b>",
        reply_markup=markup
    )

# =========================
# BUY CALLBACK
# =========================
@bot.callback_query_handler(func=lambda c: c.data.startswith("buy_"))
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
        f"""🏦 <b>PAYMENT DETAILS</b>

Bank: <b>{BANK_NAME}</b>
Account Number: <code>{ACCOUNT_NUMBER}</code>
Account Name: <b>{ACCOUNT_NAME}</b>

💰 Amount: <b>₦{amount}</b>
💎 Credits: <b>{credits}</b>

After payment, tap the button below.""",
        reply_markup=markup
    )

# =========================
# USER PAID
# =========================
@bot.callback_query_handler(func=lambda c: c.data.startswith("paid_"))
def user_paid(c):
    uid = c.data.split("_")[1]
    pending = load("pending_payments.json")

    if uid not in pending:
        return bot.answer_callback_query(c.id, "No pending payment found")

    data = pending[uid]
    user = bot.get_chat(uid)
    username = f"@{user.username}" if user.username else "No Username"
    full_name = user.first_name

    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton("✅ APPROVE", callback_data=f"approve_{uid}"),
        types.InlineKeyboardButton("❌ REJECT", callback_data=f"reject_{uid}")
    )

    bot.send_message(
        ADMIN_ID,
        f"""💰 <b>PAYMENT REQUEST</b>

👤 Name: {full_name}
🆔 User ID: <code>{uid}</code>
🌐 Username: {username}

💵 Amount: ₦{data['amount']}
💎 Credits: {data['credits']}
🕒 Time: {data['time']}""",
        reply_markup=markup
    )

    bot.answer_callback_query(c.id, "Payment sent for review ✅")

# =========================
# ADMIN ACTION
# =========================
@bot.callback_query_handler(
    func=lambda c: c.data.startswith("approve_") or c.data.startswith("reject_")
)
def admin_action(c):
    if c.from_user.id != ADMIN_ID:
        return bot.answer_callback_query(c.id, "Not allowed")

    action, uid = c.data.split("_")
    pending = load("pending_payments.json")

    if uid not in pending:
        return bot.answer_callback_query(c.id, "Already processed")

    data = pending[uid]

    if action == "approve":
        add_credit(uid, data["credits"])
        bot.send_message(
            uid,
            f"""✅ <b>PAYMENT APPROVED</b>

{data['credits']} credits added successfully.
You can now run multi-timeframe analysis.""",
            reply_markup=main_menu()
        )
        bot.send_message(ADMIN_ID, "✅ Payment approved")
    else:
        bot.send_message(
            uid,
            """❌ <b>Payment Rejected</b>

Please contact support if you believe this is an error.""",
            reply_markup=main_menu()
        )
        bot.send_message(ADMIN_ID, "❌ Payment rejected")

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

        # Expire stale sessions first
        if is_session_expired(uid):
            clear_session(uid, notify=True, chat_id=m.chat.id)
            return

        if m.content_type == "photo":
            file_info = bot.get_file(m.photo[-1].file_id)
        else:
            if not m.document.mime_type or not m.document.mime_type.startswith("image/"):
                return bot.reply_to(m, "❌ Only image files are allowed.")
            file_info = bot.get_file(m.document.file_id)

        state = analysis_state.get(uid)

        # Not in analysis flow
        if not state:
            bot.reply_to(
                m,
                "📸 To start analysis, first tap:\n\n<b>📊 Analyze Market</b>",
                reply_markup=main_menu()
            )
            return

        # Waiting for Higher Timeframe
        if state["step"] == "waiting_htf":
            file = bot.download_file(file_info.file_path)
            htf_path = f"htf_{m.chat.id}.jpg"

            with open(htf_path, "wb") as f:
                f.write(file)

            analysis_state[uid] = {
                "step": "waiting_ltf",
                "htf_path": htf_path,
                "started": time.time()
            }

            bot.send_message(
                m.chat.id,
                """✅ <b>Higher timeframe received</b>

📉 Now send the <b>LOWER TIMEFRAME</b> chart.

Recommended:
• M15
• M5
• M1"""
            )
            return

        # Waiting for Lower Timeframe
        if state["step"] == "waiting_ltf":
            file = bot.download_file(file_info.file_path)
            ltf_path = f"ltf_{m.chat.id}.jpg"

            with open(ltf_path, "wb") as f:
                f.write(file)

            htf_path = state["htf_path"]
            analysis_state.pop(uid, None)

            # Deduct only when both charts are ready
            if get_credit(uid) > 0:
                if not use_credit(uid):
                    cleanup_files(htf_path, ltf_path)
                    return bot.reply_to(
                        m,
                        "❌ No credits left.\n\nBuy credits to continue.",
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
                """❌ <b>Free trial finished</b>

Buy credits to continue analysis.""",
                reply_markup=main_menu()
            )
            return

    except Exception as e:
        print("Image Handler Error:", e)
        analysis_state.pop(str(m.chat.id), None)
        bot.reply_to(m, limit_message(), reply_markup=main_menu())

# =========================
# BALANCE
# =========================
@bot.message_handler(func=lambda m: m.text == "💰 My Balance")
def balance(m):
    bot.reply_to(
        m,
        f"""💎 Credits: <b>{get_credit(m.chat.id)}</b>
🎁 Free Trial Left: <b>{FREE_LIMIT - get_free_used(m.chat.id)}</b>""",
        reply_markup=main_menu()
    )

# =========================
# SUPPORT
# =========================
@bot.message_handler(func=lambda m: m.text == "📞 Support")
def support(m):
    bot.reply_to(
        m,
        "📞 <b>Support</b>\n\n@Profitpulseai",
        reply_markup=main_menu()
    )

# =========================
# ANALYZE BUTTON (START MULTI-TIMEFRAME FLOW)
# =========================
@bot.message_handler(func=lambda m: m.text == "📊 Analyze Market")
def ask_chart(m):
    uid = str(m.chat.id)

    # Clear any previous incomplete session
    clear_session(uid)

    # Block early if user has no access
    if not has_access(uid):
        bot.reply_to(
            m,
            """❌ <b>No credits remaining</b>

Buy credits to run multi-timeframe analysis.""",
            reply_markup=main_menu()
        )
        return

    analysis_state[uid] = {
        "step": "waiting_htf",
        "started": time.time()
    }

    bot.reply_to(
        m,
        """📈 <b>Send the HIGHER TIMEFRAME chart first</b>

Recommended:
• D1
• H4
• H1""",
        reply_markup=main_menu()
    )

# =========================
# BROADCAST SYSTEM
# =========================
broadcast_mode = {}

@bot.message_handler(func=lambda m: m.text == "📢 Broadcast")
def broadcast(m):
    if m.chat.id != ADMIN_ID:
        return bot.reply_to(m, "❌ Admin only.")

    broadcast_mode[m.chat.id] = True
    bot.reply_to(m, "📢 Send your announcement now.")

@bot.message_handler(func=lambda m: broadcast_mode.get(m.chat.id))
def send_broadcast(m):
    if m.chat.id != ADMIN_ID:
        return

    users = load("users.json")
    sent = 0
    failed = 0

    bot.reply_to(m, "📡 Broadcasting…")

    for uid in users:
        try:
            bot.send_message(
                uid,
                f"""📢 <b>ANNOUNCEMENT</b>

{m.text}"""
            )
            sent += 1
            time.sleep(0.1)
        except:
            failed += 1

    broadcast_mode[m.chat.id] = False

    bot.send_message(
        ADMIN_ID,
        f"""✅ <b>Broadcast Completed</b>

👥 Sent: {sent}
❌ Failed: {failed}"""
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
