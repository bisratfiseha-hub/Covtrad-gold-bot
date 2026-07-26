import os
import time
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

# Global Memory State & Live Cache
LAST_SIGNALS = {
    "XAU/USD": None,
    "BTC/USD": None,
    "EUR/USD": None
}

# Live cache populated by the background scanner
LIVE_MARKET_CACHE = {
    "XAU/USD": None,
    "BTC/USD": None,
    "EUR/USD": None
}

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

def get_all_active_chat_ids():
    try:
        conn = sqlite3.connect(DB_NAME)
        cursor = conn.cursor()
        cursor.execute("SELECT chat_id FROM user_balances")
        rows = cursor.fetchall()
        conn.close()
        return [r[0] for r in rows]
    except Exception as e:
        print(f"Error fetching users: {e}")
        return []

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

def calculate_sma(prices, period):
    if len(prices) < period:
        return None
    return sum(prices[:period]) / period

def calculate_rsi(prices, period=14):
    if len(prices) < period + 1:
        return 50.0
    p = prices[::-1]
    gains = []
    losses = []
    for i in range(1, len(p)):
        change = p[i] - p[i-1]
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
    
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))

def fetch_tf_data(symbol, interval):
    if not TWELVE_DATA_KEY:
        return None
    try:
        url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval={interval}&outputsize=60&apikey={TWELVE_DATA_KEY}"
        res = requests.get(url, timeout=5).json()
        if 'values' not in res:
            print(f"API Limit/Error for {symbol}: {res.get('message', 'No values')}")
            return None
        closes = [float(item['close']) for item in res['values']]
        
        rsi = calculate_rsi(closes, 14)
        sma20 = calculate_sma(closes, 20)
        sma50 = calculate_sma(closes, 50)
        
        return {"rsi": rsi, "sma20": sma20, "sma50": sma50, "price": closes[0]}
    except Exception as e:
        print(f"Error fetching {interval} for {symbol}: {e}")
        return None

def fetch_asset_analysis(symbol):
    htf_data = fetch_tf_data(symbol, "4h")
    time.sleep(1.5)  # Throttle to prevent 429 rate limit errors
    ltf_data = fetch_tf_data(symbol, "15min")

    if not htf_data or not ltf_data:
        return None

    return {"price": ltf_data['price'], "htf": htf_data, "ltf": ltf_data}

def generate_multi_timeframe_signal(symbol):
    data = fetch_asset_analysis(symbol)
    if not data:
        return None

    spec = ASSET_SPECS[symbol]
    price = data['price']
    htf = data['htf']
    ltf = data['ltf']

    if 45.0 <= htf['rsi'] <= 55.0 or abs(htf['sma20'] - htf['sma50']) / price < 0.0005:
        htf_bias = "RANGING / SIDEWAYS 🟡"
    elif htf['sma20'] > htf['sma50']:
        htf_bias = "BULLISH 🟢"
    else:
        htf_bias = "BEARISH 🔴"

    ltf_bullish = ltf['sma20'] > ltf['sma50'] and ltf['rsi'] > 50
    ltf_bearish = ltf['sma20'] < ltf['sma50'] and ltf['rsi'] < 50

    if "BULLISH" in htf_bias and ltf_bullish:
        trade_type = "TREND CONTINUATION 🚀"
        signal = "BUY / LONG 🟢"
        sl_dist, tp_dist = spec['trend_sl'], spec['trend_tp']
        note = "4H & 15M aligned in strong uptrend."

    elif "BEARISH" in htf_bias and ltf_bearish:
        trade_type = "TREND CONTINUATION 🚀"
        signal = "SELL / SHORT 🔴"
        sl_dist, tp_dist = spec['trend_sl'], spec['trend_tp']
        note = "4H & 15M aligned in strong downtrend."

    elif "BULLISH" in htf_bias and ltf_bearish:
        trade_type = "COUNTER-TREND SCALP ⚡"
        signal = "SELL / SHORT (SCALP) 🟡"
        sl_dist, tp_dist = spec['scalp_sl'], spec['scalp_tp']
        note = "⚠️ Counter 4H Trend! Quick pullback scalp."

    elif "BEARISH" in htf_bias and ltf_bullish:
        trade_type = "COUNTER-TREND SCALP ⚡"
        signal = "BUY / LONG (SCALP) 🟡"
        sl_dist, tp_dist = spec['scalp_sl'], spec['scalp_tp']
        note = "⚠️ Counter 4H Trend! Quick pullback scalp."

    elif "RANGING" in htf_bias and ltf_bullish:
        trade_type = "RANGE BREAKOUT / SCALP ⚡"
        signal = "BUY / LONG (SCALP) 🟢"
        sl_dist, tp_dist = spec['scalp_sl'], spec['scalp_tp']
        note = "4H Consolidation with 15M momentum bullish breakout."

    elif "RANGING" in htf_bias and ltf_bearish:
        trade_type = "RANGE BREAKOUT / SCALP ⚡"
        signal = "SELL / SHORT (SCALP) 🔴"
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
        "note": note,
        "spec": spec
    }

# --- ⚡ SCANNER ENGINE WITH SMART CACHING ---

def live_market_scanner_loop():
    print("⚡ Instant market scanner loop initialized!")
    while True:
        try:
            for symbol in ASSET_SPECS.keys():
                sig = generate_multi_timeframe_signal(symbol)
                
                # Store fresh analysis in memory cache
                if sig:
                    LIVE_MARKET_CACHE[symbol] = sig

                if not sig or sig.get('is_sideways'):
                    LAST_SIGNALS[symbol] = "SIDEWAYS"
                    time.sleep(2)
                    continue

                signal_key = f"{sig['signal']}_{sig['trade_type']}"

                if LAST_SIGNALS.get(symbol) != signal_key:
                    LAST_SIGNALS[symbol] = signal_key
                    active_users = get_all_active_chat_ids()

                    spec = sig['spec']
                    pips_sl = int(sig['sl_dist'] * spec['pip_factor'])
                    pips_tp = int(sig['tp_dist'] * spec['pip_factor'])

                    for chat_id in active_users:
                        active_balance = get_user_balance(chat_id)
                        
                        alert_card = (
                            f"🚨 **INSTANT SIGNAL ALERT — {sig['name']}** 🚨\n"
                            f"━━━━━━━━━━━━━━━━━━━\n"
                            f"💵 **Live Price:** {sig['price']:,.{spec['decimals']}f}\n"
                            f"🏛 **4H Macro Trend:** {sig['htf_bias']}\n"
                            f"🏷 **Trade Type:** {sig['trade_type']}\n\n"
                            f"💡 **Signal:** {sig['signal']}\n"
                            f"• **Entry:** {sig['price']:,.{spec['decimals']}f}\n"
                            f"• **Stop Loss (SL):** {sig['sl_price']:,.{spec['decimals']}f} ({pips_sl} {spec['unit']})\n"
                            f"• **Take Profit (TP):** {sig['tp_price']:,.{spec['decimals']}f} ({pips_tp} {spec['unit']})\n\n"
                            f"⚡ *Fresh market setup formed live! Tap below for lot size:* "
                        )

                        markup = InlineKeyboardMarkup(row_width=3)
                        b_low = InlineKeyboardButton("🛡 Low (0.25%)", callback_data=f"calc_{symbol}_{sig['sl_dist']}_{sig['tp_dist']}_0.25_{active_balance}")
                        b_std = InlineKeyboardButton("⚖️ Std (1.0%)", callback_data=f"calc_{symbol}_{sig['sl_dist']}_{sig['tp_dist']}_1.0_{active_balance}")
                        b_high = InlineKeyboardButton("🚀 High (5.0%)", callback_data=f"calc_{symbol}_{sig['sl_dist']}_{sig['tp_dist']}_5.0_{active_balance}")
                        markup.add(b_low, b_std, b_high)

                        try:
                            bot.send_message(chat_id, alert_card, reply_markup=markup, parse_mode="Markdown")
                        except Exception as send_err:
                            print(f"Failed to push alert to {chat_id}: {send_err}")

                time.sleep(2)  # Pause between assets to stay within rate limits

        except Exception as e:
            print(f"Scanner Loop Error: {e}")

        time.sleep(60)

# --- TELEGRAM HANDLERS ---

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    current_bal = get_user_balance(message.chat.id)
    msg = (
        "🎯 **Sniper Trading Dashboard Active (Instant Scan Mode)!**\n\n"
        f"💰 **Active Capital:** `${current_bal:,.2f} USD`\n"
        "⚡ **Scanner Status:** Hunting continuously for instant push alerts.\n\n"
        "Tap any market button below for analysis, or type your balance directly (e.g. `57.59`)."
    )
    bot.send_message(message.chat.id, msg, reply_markup=get_main_dashboard(), parse_mode="Markdown")

def process_signal_request(message, symbol):
    bot.send_chat_action(message.chat.id, 'typing')
    active_balance = get_user_balance(message.chat.id)

    # Fast cache lookup: avoid making new API requests if scanner already fetched it
    sig = LIVE_MARKET_CACHE.get(symbol)
    if not sig:
        sig = generate_multi_timeframe_signal(symbol)
        if sig:
            LIVE_MARKET_CACHE[symbol] = sig

    if not sig:
        bot.send_message(message.chat.id, f"⚠️ Fetching market data for {symbol}. Please try again in a few seconds.", reply_markup=get_main_dashboard())
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
        f"📝 **Bot Context:** {sig['note']}\n\n"
        f"👇 **Select Risk Exposure to Calculate Cent Lot Size:**"
    )

    markup = InlineKeyboardMarkup(row_width=3)
    b_low = InlineKeyboardButton("🛡 Low (0.25%)", callback_data=f"calc_{symbol}_{sig['sl_dist']}_{sig['tp_dist']}_0.25_{active_balance}")
    b_std = InlineKeyboardButton("⚖️ Std (1.0%)", callback_data=f"calc_{symbol}_{sig['sl_dist']}_{sig['tp_dist']}_1.0_{active_balance}")
    b_high = InlineKeyboardButton("🚀 High (5.0%)", callback_data=f"calc_{symbol}_{sig['sl_dist']}_{sig['tp_dist']}_5.0_{active_balance}")
    markup.add(b_low, b_std, b_high)

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
        "Tap a preset button below or simply type your balance number directly (e.g. `57.59`):"
    )
    bot.send_message(message.chat.id, msg, reply_markup=get_balance_presets(), parse_mode="Markdown")

@bot.message_handler(func=lambda msg: msg.text == "ℹ️ Bot Info")
def handle_bot_info(message):
    current_bal = get_user_balance(message.chat.id)
    info_text = (
        "🤖 **Sniper Assistant (Cent Engine)**\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "• **Supported Pairs:** XAUUSDc, BTCUSDc, EURUSDc\n"
        "• **Live Scanner:** 60-second continuous background loop ⚡\n"
        "• **Risk Modes:** 0.25% (Low), 1.0% (Standard), 5.0% (High Exposure)\n"
        f"• **Active Balance:** ${current_bal:,.2f} USD\n"
        "• **Status:** Connected & Hunting Live 24/7 🚀"
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
        
        cent_lot_size = risk_dollars / (sl_dist * spec['contract_size'])
        pips_tp = int(tp_dist * spec['pip_factor'])

        calc_text = (
            f"⚖️ **POSITION SIZING ({risk_pct}% RISK) — {spec['name']}**\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"• **Account Capital:** `${active_balance:,.2f} USD`\n"
            f"• **Recommended Lot Size:** `{cent_lot_size:.2f} Cent Lots`\n"
            f"• **Max Risk (Loss):** -${risk_dollars:,.2f} USD\n"
            f"• **Target Reward (Win):** +${reward_dollars:,.2f} USD ({pips_tp} {spec['unit']})\n\n"
            f"💡 *Enter `{cent_lot_size:.2f}` into your MetaTrader Cent account terminal.*"
        )

        bot.answer_callback_query(call.id, text=f"Calculated for {risk_pct}% Risk!")
        bot.send_message(call.message.chat.id, calc_text, parse_mode="Markdown")

    except Exception as e:
        print(f"Callback Error: {e}")
        bot.answer_callback_query(call.id, text="Error calculating lot size.")

def run_bot():
    print("Telegram bot is listening...")
    bot.infinity_polling()

# --- FLASK KEEP-ALIVE SERVER & THREAD LAUNCHERS ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Sniper Bot Engine is active and hunting live!"

if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.daemon = True
    bot_thread.start()

    scanner_thread = threading.Thread(target=live_market_scanner_loop)
    scanner_thread.daemon = True
    scanner_thread.start()
    
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
