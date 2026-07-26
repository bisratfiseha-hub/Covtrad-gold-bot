import os
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
DB_NAME = "bot_data.db"

bot = telebot.TeleBot(BOT_TOKEN)

try:
    bot.remove_webhook()
    print("Old webhook cleared successfully!")
except Exception as e:
    print(f"Webhook reset notice: {e}")

# --- DATABASE PERSISTENCE (SQLite) ---

def init_db():
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

init_db()

# --- DASHBOARD KEYBOARDS ---

def get_main_dashboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn_gold = KeyboardButton("🥇 Gold (XAUUSDc)")
    btn_btc = KeyboardButton("₿ Bitcoin (BTCUSDc)")
    btn_eur = KeyboardButton("💶 EUR/USD (EURUSDc)")
    btn_balance = KeyboardButton("💰 Set Balance")
    btn_info = KeyboardButton("ℹ️ Bot Info")
    markup.add(btn_gold, btn_btc, btn_eur, btn_balance, btn_info)
    return markup

def get_balance_presets():
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
    cleaned = text.replace('$', '').replace(',', '').strip()
    try:
        val = float(cleaned)
        return val if val > 0 else None
    except ValueError:
        return None

# --- ASSET SPECS FOR CENT ACCOUNTS ---
# contract_size represents price impact per 1.00 Cent Lot in USD
ASSET_SPECS = {
    "XAU/USD": {
        "name": "GOLD CENT (XAUUSDc)",
        "trend_sl": 3.50,    "trend_tp": 7.00,
        "scalp_sl": 2.00,    "scalp_tp": 3.00,
        "contract_size": 1.0, "pip_factor": 100, "unit": "pips", "decimals": 2
    },
    "BTC/USD": {
        "name": "BITCOIN CENT (BTCUSDc)",
        "trend_sl": 1200.00, "trend_tp": 2400.00,
        "scalp_sl": 600.00,  "scalp_tp": 1000.00,
        "contract_size": 0.01, "pip_factor": 1,   "unit": "points", "decimals": 2
    },
    "EUR/USD": {
        "name": "EURO CENT (EURUSDc)",
        "trend_sl": 0.0025,  "trend_tp": 0.0050,
        "scalp_sl": 0.0012,  "scalp_tp": 0.0020,
        "contract_size": 1000.0, "pip_factor": 10000, "unit": "pips", "decimals": 5
    }
}

# --- TECHNICAL ANALYSIS ENGINE ---

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

def fetch_asset_analysis(symbol):
    if not TWELVE_DATA_KEY:
        return None
    try:
        price_url = f"https://api.twelvedata.com/price?symbol={symbol}&apikey={TWELVE_DATA_KEY}"
        price = float(requests.get(price_url, timeout=5).json()['price'])

        htf_data = fetch_tf_data(symbol, "4h")
        ltf_data = fetch_tf_data(symbol, "15min")

        if not htf_data or not ltf_data:
            return None

        return {"price": price, "htf": htf_data, "ltf": ltf_data}
    except Exception as e:
        print(f"Analysis Error for {symbol}: {e}")
        return None

def generate_multi_timeframe_signal(symbol):
    data = fetch_asset_analysis(symbol)
    if not data:
        return None

    spec = ASSET_SPECS[symbol]
    price = data['price']
    htf = data['htf']
    ltf = data['ltf']

    # HTF Macro Classification
    if 45.0 <= htf['rsi'] <= 55.0 or abs(htf['sma20'] - htf['sma50']) / price < 0.0005:
        htf_bias = "RANGING / SIDEWAYS 🟡"
    elif htf['sma20'] > htf['sma50']:
        htf_bias = "BULLISH 🟢"
    else:
        htf_bias = "BEARISH 🔴"

    # LTF Micro Signals
    ltf_bullish = ltf['sma20'] > ltf['sma50'] and ltf['rsi'] > 50
    ltf_bearish = ltf['sma20'] < ltf['sma50'] and ltf['rsi'] < 50

    # Multi-Timeframe Strategy Matrix
    if "BULLISH" in htf_bias and ltf_bullish:
        trade_type = "TREND CONTINUATION 🚀"
        signal = "BUY / LONG 🟢"
        risk_pct = 1.0
        sl_dist, tp_dist = spec['trend_sl'], spec['trend_tp']
        note = "4H & 15M aligned in strong uptrend."

    elif "BEARISH" in htf_bias and ltf_bearish:
        trade_type = "TREND CONTINUATION 🚀"
        signal = "SELL / SHORT 🔴"
        risk_pct = 1.0
        sl_dist, tp_dist = spec['trend_sl'], spec['trend_tp']
        note = "4H & 15M aligned in strong downtrend."

    elif "BULLISH" in htf_bias and ltf_bearish:
        trade_type = "COUNTER-TREND SCALP ⚡"
        signal = "SELL / SHORT (SCALP) 🟡"
        risk_pct = 0.5
        sl_dist, tp_dist = spec['scalp_sl'], spec['scalp_tp']
        note = "⚠️ Counter 4H Trend! Reduced risk for a quick pullback scalp."

    elif "BEARISH" in htf_bias and ltf_bullish:
        trade_type = "COUNTER-TREND SCALP ⚡"
        signal = "BUY / LONG (SCALP) 🟡"
        risk_pct = 0.5
        sl_dist, tp_dist = spec['scalp_sl'], spec['scalp_tp']
        note = "⚠️ Counter 4H Trend! Reduced risk for a quick pullback scalp."

    elif "RANGING" in htf_bias and ltf_bullish:
        trade_type = "RANGE BREAKOUT / SCALP ⚡"
        signal = "BUY / LONG (SCALP) 🟢"
        risk_pct = 0.5
        sl_dist, tp_dist = spec['scalp_sl'], spec['scalp_tp']
        note = "4H Consolidation with 15M momentum bullish breakout."

    elif "RANGING" in htf_bias and ltf_bearish:
        trade_type = "RANGE BREAKOUT / SCALP ⚡"
        signal = "SELL / SHORT (SCALP) 🔴"
        risk_pct = 0.5
        sl_dist, tp_dist = spec['scalp_sl'], spec['scalp_tp']
        note = "4H Consolidation with 15M momentum bearish breakdown."

    else:
        return {
            "is_sideways": True,
            "text": (
                f"📊 **{spec['name']} Market Context**\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"💵 **Live Price:** {price:,.{spec['decimals']}f}\n"
                f"🏛 **4H Macro Trend:** {htf_bias}\n"
                f"📊 **15M RSI:** {ltf['rsi']:.1f}\n\n"
                f"💡 **Signal:** SIDEWAYS / WAIT FOR CLEAR BREAKOUT ⏳"
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
        "symbol": symbol,
        "name": spec['name'],
        "price": price,
        "htf_bias": htf_bias,
        "trade_type": trade_type,
        "signal": signal,
        "sl_price": sl_price,
        "tp_price": tp_price,
        "sl_dist": sl_dist,
        "tp_dist": tp_dist,
        "risk_pct": risk_pct,
        "note": note,
        "spec": spec
    }

# --- TELEGRAM HANDLERS ---

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    current_bal = get_user_balance(message.chat.id)
    msg = (
        "🎯 **Sniper Trading Dashboard Active (Cent Account Mode)!**\n\n"
        f"💰 **Active Account Balance:** `${current_bal:,.2f}`\n\n"
        "Tap any market button below to analyze signals, or type your balance directly (e.g. `57.49` or `5749`)."
    )
    bot.send_message(message.chat.id, msg, reply_markup=get_main_dashboard(), parse_mode="Markdown")

def process_signal_request(message, symbol):
    bot.send_chat_action(message.chat.id, 'typing')
    active_balance = get_user_balance(message.chat.id)

    sig = generate_multi_timeframe_signal(symbol)
    if not sig:
        bot.send_message(message.chat.id, f"⚠️ Unable to fetch market data for {symbol} right now.", reply_markup=get_main_dashboard())
        return

    if sig.get('is_sideways'):
        bot.send_message(message.chat.id, sig['text'], reply_markup=get_main_dashboard(), parse_mode="Markdown")
        return

    spec = sig['spec']
    pips_sl = int(sig['sl_dist'] * spec['pip_factor'])
    pips_tp = int(sig['tp_dist'] * spec['pip_factor'])

    card = (
        f"🎯 **{sig['name']} INTELLIGENT SIGNAL**\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"💵 **Live Price:** {sig['price']:,.{spec['decimals']}f}\n"
        f"🏛 **4H Macro Trend:** {sig['htf_bias']}\n"
        f"🏷 **Trade Type:** {sig['trade_type']}\n\n"
        f"💡 **Signal:** {sig['signal']}\n"
        f"• **Entry:** {sig['price']:,.{spec['decimals']}f}\n"
        f"• **Stop Loss (SL):** {sig['sl_price']:,.{spec['decimals']}f} ({pips_sl} {spec['unit']})\n"
        f"• **Take Profit (TP):** {sig['tp_price']:,.{spec['decimals']}f} ({pips_tp} {spec['unit']})\n\n"
        f"📝 **Bot Context:** {sig['note']}"
    )

    markup = InlineKeyboardMarkup()
    calc_button = InlineKeyboardButton(
        text="⚖️ Calculate Cent Lot Size", 
        callback_data=f"calc_{symbol}_{sig['sl_dist']}_{sig['tp_dist']}_{sig['risk_pct']}_{active_balance}"
    )
    markup.add(calc_button)

    bot.send_message(message.chat.id, card, reply_markup=markup, parse_mode="Markdown")

@bot.message_handler(func=lambda msg: msg.text in ["🥇 Gold (XAUUSDc)", "/gold"])
def handle_gold(message):
    process_signal_request(message, "XAU/USD")

@bot.message_handler(func=lambda msg: msg.text in ["₿ Bitcoin (BTCUSDc)", "/btc"])
def handle_btc(message):
    process_signal_request(message, "BTC/USD")

@bot.message_handler(func=lambda msg: msg.text in ["💶 EUR/USD (EURUSDc)", "/eur"])
def handle_eur(message):
    process_signal_request(message, "EUR/USD")

@bot.message_handler(func=lambda msg: msg.text in ["💰 Set Balance", "/setbalance"])
def handle_balance_menu(message):
    current_bal = get_user_balance(message.chat.id)
    msg = (
        f"💰 **Account Balance Settings**\n\n"
        f"Current Balance: **${current_bal:,.2f} USD**\n\n"
        "Tap a preset button below or simply type your balance directly (e.g. `57.49`):"
    )
    bot.send_message(message.chat.id, msg, reply_markup=get_balance_presets(), parse_mode="Markdown")

@bot.message_handler(func=lambda msg: msg.text == "ℹ️ Bot Info")
def handle_bot_info(message):
    current_bal = get_user_balance(message.chat.id)
    info_text = (
        "🤖 **Sniper Assistant (Cent Engine)**\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "• **Supported Cent Pairs:** XAUUSDc, BTCUSDc, EURUSDc\n"
        "• **Strategy Matrix:** 4H Macro + 15M Micro Alignment & Range Breakout\n"
        "• **Risk Rules:** 1.0% Trend / 0.5% Scalp & Breakout\n"
        f"• **Active Balance:** ${current_bal:,.2f} USD\n"
        "• **Status:** Connected & Hunting 24/7 🚀"
    )
    bot.send_message(message.chat.id, info_text, reply_markup=get_main_dashboard(), parse_mode="Markdown")

@bot.message_handler(func=lambda msg: parse_raw_amount(msg.text) is not None)
def handle_raw_number_balance(message):
    new_bal = parse_raw_amount(message.text)
    set_user_balance(message.chat.id, new_bal)
    bot.reply_to(
        message, 
        f"✅ Account balance updated and saved as **${new_bal:,.2f} USD**!", 
        reply_markup=get_main_dashboard(), 
        parse_mode="Markdown"
    )

# --- INLINE CALLBACK HANDLERS ---

@bot.callback_query_handler(func=lambda call: call.data.startswith('setbal_'))
def handle_preset_balance(call):
    try:
        new_bal = float(call.data.split('_')[1])
        set_user_balance(call.message.chat.id, new_bal)
        bot.answer_callback_query(call.id, text=f"Balance set to ${new_bal:,.2f} USD!")
        bot.send_message(
            call.message.chat.id, 
            f"✅ Account balance updated to **${new_bal:,.2f} USD**!", 
            reply_markup=get_main_dashboard(), 
            parse_mode="Markdown"
        )
    except Exception as e:
        print(f"Preset balance error: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('calc_'))
def handle_lot_calculation(call):
    try:
        _, symbol, sl_dist, tp_dist, risk_pct, active_balance = call.data.split('_')
        sl_dist = float(sl_dist)
        tp_dist = float(tp_dist)
        risk_pct = float(risk_pct)
        active_balance = float(active_balance)

        spec = ASSET_SPECS[symbol]

        risk_dollars = active_balance * (risk_pct / 100.0)
        reward_dollars = risk_dollars * (tp_dist / sl_dist)
        
        # Exact Cent Lot Calculation Formula
        cent_lot_size = risk_dollars / (sl_dist * spec['contract_size'])

        calc_text = (
            f"⚖️ **CENT LOT POSITION SIZING — {spec['name']}**\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"• **Account Capital:** `${active_balance:,.2f} USD`\n"
            f"• **Recommended Lot Size:** `{cent_lot_size:.2f} Cent Lots`\n"
            f"• **Max Risk:** -${risk_dollars:,.2f} USD ({risk_pct:.1f}%)\n"
            f"• **Target Reward:** +${reward_dollars:,.2f} USD\n\n"
            f"💡 *Enter `{cent_lot_size:.2f}` directly into your MetaTrader Cent account terminal.*"
        )

        bot.answer_callback_query(call.id, text="Cent Lot Size Calculated!")
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
