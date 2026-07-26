import os
import re
import sqlite3
import threading
import requests
from flask import Flask
import telebot
from telebot.types import (
    InlineKeyboardMarkup, 
    InlineKeyboardButton, 
    ReplyKeyboardMarkup, 
    KeyboardButton
)

# --- CONFIGURATION & ENV VARIABLES ---
BOT_TOKEN = os.environ.get('BOT_TOKEN', 'YOUR_TELEGRAM_BOT_TOKEN_HERE')
TWELVE_DATA_KEY = os.environ.get('TWELVE_DATA_API_KEY', '')

DEFAULT_BALANCE = 50.0
DEFAULT_RISK_PCT = 1.0
DB_NAME = "bot_data.db"

bot = telebot.TeleBot(BOT_TOKEN)

try:
    bot.remove_webhook()
    print("Old webhook cleared successfully!")
except Exception as e:
    print(f"Webhook reset notice: {e}")

# --- DATABASE PERSISTENCE (SQLite) ---

def init_db():
    """Initializes SQLite table for storing user balances across reboots"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS user_balances (
            chat_id INTEGER PRIMARY KEY,
            balance REAL NOT NULL
        )
    """)
    conn.commit()
    conn.close()

def get_user_balance(chat_id):
    """Retrieves saved user balance from database or returns default"""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT balance FROM user_balances WHERE chat_id = ?", (chat_id,))
        row = cursor.fetchone()
        conn.close()
        return row[0] if row else DEFAULT_BALANCE
    except Exception as e:
        print(f"DB Read Error: {e}")
        return DEFAULT_BALANCE

def set_user_balance(chat_id, balance):
    """Saves user balance persistently to SQLite database"""
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO user_balances (chat_id, balance)
            VALUES (?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET balance = excluded.balance
        """, (chat_id, balance))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"DB Write Error: {e}")

# Initialize Database
init_db()

# --- PERSISTENT KEYBOARD DASHBOARD & PRESETS ---

def get_main_dashboard():
    """Generates persistent bottom menu keyboard"""
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn_signal = KeyboardButton("📊 Get Gold Signal")
    btn_balance = KeyboardButton("💰 Set Balance")
    btn_info = KeyboardButton("ℹ️ Bot Info")
    markup.add(btn_signal, btn_balance, btn_info)
    return markup

def get_balance_presets():
    """Generates updated micro/small account balance presets"""
    markup = InlineKeyboardMarkup(row_width=3)
    b1 = InlineKeyboardButton("$20", callback_data="setbal_20")
    b2 = InlineKeyboardButton("$25", callback_data="setbal_25")
    b3 = InlineKeyboardButton("$50", callback_data="setbal_50")
    b4 = InlineKeyboardButton("$100", callback_data="setbal_100")
    b5 = InlineKeyboardButton("$250", callback_data="setbal_250")
    b6 = InlineKeyboardButton("$500", callback_data="setbal_500")
    markup.add(b1, b2, b3, b4, b5, b6)
    return markup

def parse_raw_amount(text):
    """Extracts numeric float value from text (e.g. '$56.59' -> 56.59)"""
    cleaned = text.replace('$', '').replace(',', '').strip()
    try:
        val = float(cleaned)
        return val if val > 0 else None
    except ValueError:
        return None

# --- TECHNICAL ANALYSIS FETCHERS ---

def fetch_tf_data(symbol, interval):
    if not TWELVE_DATA_KEY:
        return None
    try:
        rsi_url = f"https://api.twelvedata.com/rsi?symbol={symbol}&interval={interval}&time_period=14&apikey={TWELVE_DATA_KEY}"
        rsi = float(requests.get(rsi_url, timeout=5).json()['values'][0]['rsi'])

        sma20_url = f"https://api.twelvedata.com/sma?symbol={symbol}&interval={interval}&time_period=20&apikey={TWELVE_DATA_KEY}"
        sma20 = float(requests.get(sma20_url, timeout=5).json()['values'][0]['sma'])

        sma50_url = f"https://api.twelvedata.com/sma?symbol={symbol}&interval={interval}&time_period=50&apikey={TWELVE_DATA_KEY}"
        sma50 = float(requests.get(sma50_url, timeout=5).json()['values'][0]['sma'])

        return {"rsi": rsi, "sma20": sma20, "sma50": sma50}
    except Exception as e:
        print(f"Error fetching {interval} for {symbol}: {e}")
        return None

def fetch_gold_analysis():
    if not TWELVE_DATA_KEY:
        return None
    try:
        price_url = f"https://api.twelvedata.com/price?symbol=XAU/USD&apikey={TWELVE_DATA_KEY}"
        price = float(requests.get(price_url, timeout=5).json()['price'])

        htf_data = fetch_tf_data("XAU/USD", "4h")
        ltf_data = fetch_tf_data("XAU/USD", "15min")

        if not htf_data or not ltf_data:
            return None

        return {
            "price": price,
            "htf": htf_data,
            "ltf": ltf_data
        }
    except Exception as e:
        print(f"Gold MTF Error: {e}")
        return None

def get_gold_signal_data():
    data = fetch_gold_analysis()
    if not data:
        return None

    price = data['price']
    htf = data['htf']
    ltf = data['ltf']

    htf_bias = "BULLISH 🟢" if htf['sma20'] > htf['sma50'] else "BEARISH 🔴"
    
    ltf_bullish = ltf['sma20'] > ltf['sma50'] and ltf['rsi'] > 50
    ltf_bearish = ltf['sma20'] < ltf['sma50'] and ltf['rsi'] < 50

    if "BULLISH" in htf_bias and ltf_bullish:
        trade_type = "TREND CONTINUATION 🚀"
        signal = "BUY / LONG 🟢"
        risk_pct = DEFAULT_RISK_PCT
        sl_dist = 3.50
        tp_dist = 7.00
        note = "4H & 15M aligned! Standard trend setup."

    elif "BEARISH" in htf_bias and ltf_bullish:
        trade_type = "COUNTER-TREND SCALP ⚡"
        signal = "BUY / LONG (SCALP) 🟡"
        risk_pct = DEFAULT_RISK_PCT * 0.5
        sl_dist = 2.00
        tp_dist = 3.00
        note = "⚠️ Counter 4H Trend! Reduced risk recommended for a quick scalp."

    elif "BEARISH" in htf_bias and ltf_bearish:
        trade_type = "TREND CONTINUATION 🚀"
        signal = "SELL / SHORT 🔴"
        risk_pct = DEFAULT_RISK_PCT
        sl_dist = 3.50
        tp_dist = 7.00
        note = "4H & 15M aligned! Standard trend setup."

    elif "BULLISH" in htf_bias and ltf_bearish:
        trade_type = "COUNTER-TREND SCALP ⚡"
        signal = "SELL / SHORT (SCALP) 🟡"
        risk_pct = DEFAULT_RISK_PCT * 0.5
        sl_dist = 2.00
        tp_dist = 3.00
        note = "⚠️ Counter 4H Trend! Reduced risk recommended for a quick scalp."

    else:
        return {
            "is_sideways": True,
            "text": (
                f"📊 **Gold (XAU/USD) Market Context**\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"💵 **Live Price:** ${price:,.2f}\n"
                f"🏛 **4H Macro Trend:** {htf_bias}\n"
                f"📊 **15M RSI:** {ltf['rsi']:.1f}\n\n"
                f"💡 **Signal:** SIDEWAYS / WAIT FOR BREAKOUT ⏳"
            )
        }

    if "BUY" in signal:
        sl_price = price - sl_dist
        tp_price = price + tp_dist
    else:
        sl_price = price + sl_dist
        tp_price = price - tp_dist

    return {
        "is_sideways": False,
        "price": price,
        "htf_bias": htf_bias,
        "trade_type": trade_type,
        "signal": signal,
        "sl_price": sl_price,
        "tp_price": tp_price,
        "sl_dist": sl_dist,
        "tp_dist": tp_dist,
        "risk_pct": risk_pct,
        "note": note
    }

# --- TELEGRAM HANDLERS ---

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    current_bal = get_user_balance(message.chat.id)
    msg = (
        "🎯 **Sniper Trading Dashboard Active!**\n\n"
        f"💰 **Active Account Balance:** `${current_bal:,.2f}`\n\n"
        "Use the bottom menu buttons to get live signals, or simply type your current balance (e.g. `56.59`)."
    )
    bot.send_message(message.chat.id, msg, reply_markup=get_main_dashboard(), parse_mode="Markdown")

@bot.message_handler(func=lambda msg: msg.text in ["📊 Get Gold Signal", "/gold"])
def handle_gold_request(message):
    bot.send_chat_action(message.chat.id, 'typing')
    active_balance = get_user_balance(message.chat.id)

    sig = get_gold_signal_data()
    if not sig:
        bot.send_message(message.chat.id, "⚠️ Unable to calculate Gold signal right now.", reply_markup=get_main_dashboard())
        return

    if sig.get('is_sideways'):
        bot.send_message(message.chat.id, sig['text'], reply_markup=get_main_dashboard(), parse_mode="Markdown")
        return

    # Clean Technical Card
    card = (
        f"🎯 **GOLD (XAU/USD) INTELLIGENT SIGNAL**\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"💵 **Live Price:** ${sig['price']:,.2f}\n"
        f"🏛 **4H Macro Trend:** {sig['htf_bias']}\n"
        f"🏷 **Trade Type:** {sig['trade_type']}\n\n"
        f"💡 **Signal:** {sig['signal']}\n"
        f"• **Entry:** ${sig['price']:,.2f}\n"
        f"• **Stop Loss (SL):** ${sig['sl_price']:,.2f} ({int(sig['sl_dist']*100)} pips)\n"
        f"• **Take Profit (TP):** ${sig['tp_price']:,.2f} ({int(sig['tp_dist']*100)} pips)\n\n"
        f"📝 **Bot Context:** {sig['note']}"
    )

    markup = InlineKeyboardMarkup()
    calc_button = InlineKeyboardButton(
        text="⚖️ Calculate Position & Lot Size", 
        callback_data=f"calc_{sig['sl_dist']}_{sig['tp_dist']}_{sig['risk_pct']}_{active_balance}"
    )
    markup.add(calc_button)

    bot.send_message(message.chat.id, card, reply_markup=markup, parse_mode="Markdown")

@bot.message_handler(func=lambda msg: msg.text in ["💰 Set Balance", "/setbalance"])
def handle_balance_menu(message):
    current_bal = get_user_balance(message.chat.id)
    msg = (
        f"💰 **Account Balance Settings**\n\n"
        f"Current Balance: **${current_bal:,.2f}**\n\n"
        "Tap a preset button below or simply type your balance number directly (e.g. `56.59`):"
    )
    bot.send_message(message.chat.id, msg, reply_markup=get_balance_presets(), parse_mode="Markdown")

@bot.message_handler(func=lambda msg: msg.text == "ℹ️ Bot Info")
def handle_bot_info(message):
    current_bal = get_user_balance(message.chat.id)
    info_text = (
        "🤖 **Sniper Assistant Engine**\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "• **Strategy:** 4H Macro Trend + 15M Entry Alignment\n"
        "• **Risk Rules:** 1.0% Trend / 0.5% Counter-Trend\n"
        f"• **Active Balance:** ${current_bal:,.2f}\n"
        "• **Status:** Connected & Hunting 24/7 🚀"
    )
    bot.send_message(message.chat.id, info_text, reply_markup=get_main_dashboard(), parse_mode="Markdown")

# --- RAW NUMBER DIRECT BALANCE HANDLER ---
@bot.message_handler(func=lambda msg: parse_raw_amount(msg.text) is not None)
def handle_raw_number_balance(message):
    new_bal = parse_raw_amount(message.text)
    set_user_balance(message.chat.id, new_bal)
    bot.reply_to(
        message, 
        f"✅ Account balance updated and saved as **${new_bal:,.2f}**!", 
        reply_markup=get_main_dashboard(), 
        parse_mode="Markdown"
    )

# --- INLINE CALLBACK HANDLERS ---

@bot.callback_query_handler(func=lambda call: call.data.startswith('setbal_'))
def handle_preset_balance(call):
    try:
        new_bal = float(call.data.split('_')[1])
        set_user_balance(call.message.chat.id, new_bal)
        bot.answer_callback_query(call.id, text=f"Balance set to ${new_bal:,.2f}!")
        bot.send_message(
            call.message.chat.id, 
            f"✅ Account balance updated to **${new_bal:,.2f}**!", 
            reply_markup=get_main_dashboard(), 
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"Preset balance error: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('calc_'))
def handle_lot_calculation(call):
    try:
        _, sl_dist, tp_dist, risk_pct, active_balance = call.data.split('_')
        sl_dist = float(sl_dist)
        tp_dist = float(tp_dist)
        risk_pct = float(risk_pct)
        active_balance = float(active_balance)

        risk_dollars = active_balance * (risk_pct / 100.0)
        reward_dollars = risk_dollars * (tp_dist / sl_dist)
        lot_size = risk_dollars / (sl_dist * 100.0)

        ref_risk_dollars = 1000.0 * (risk_pct / 100.0)
        ref_lot_size = ref_risk_dollars / (sl_dist * 100.0)

        calc_text = (
            f"⚖️ **POSITION SIZING (${active_balance:,.2f} Account)**\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"• **Recommended Lot Size:** `{lot_size:.2f} Lots`\n"
            f"• **Max Risk:** -${risk_dollars:,.2f} ({risk_pct:.1f}%)\n"
            f"• **Target Reward:** +${reward_dollars:,.2f}\n\n"
            f"📏 **QUICK SCALING REFERENCE:**\n"
            f"• `Use {ref_lot_size:.2f} Lots per $1,000 Equity`"
        )

        bot.answer_callback_query(call.id, text="Position Sizing Calculated!")
        bot.send_message(call.message.chat.id, calc_text, parse_mode="Markdown")

    except Exception as e:
        print(f"Callback Error: {e}")
        bot.answer_callback_query(call.id, text="Error calculating lot size.")

def run_bot():
    print("Telegram bot is listening...")
    bot.infinity_polling()

# --- FLASK KEEP-ALIVE SERVER ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Sniper Bot Engine is awake and hunting!"

if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.start()
    
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
