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

# --- ASSET SPECS FOR CENT ACCOUNTS (EXPANDED PORTFOLIO) ---
ASSET_SPECS = {
    # --- FOREX (Top 6 Volatile Pairs) ---
    "EUR/USD": {
        "name": "EUR/USD (Euro Cent)",
        "trend_sl": 0.0025,  "trend_tp": 0.0050,
        "scalp_sl": 0.0012,  "scalp_tp": 0.0020,
        "contract_size": 1.0, "pip_factor": 10000, "unit": "pips", "decimals": 5
    },
    "GBP/USD": {
        "name": "GBP/USD (Cable Cent)",
        "trend_sl": 0.0030,  "trend_tp": 0.0060,
        "scalp_sl": 0.0015,  "scalp_tp": 0.0025,
        "contract_size": 1.0, "pip_factor": 10000, "unit": "pips", "decimals": 5
    },
    "USD/JPY": {
        "name": "USD/JPY (Yen Cent)",
        "trend_sl": 0.35,    "trend_tp": 0.70,
        "scalp_sl": 0.18,    "scalp_tp": 0.30,
        "contract_size": 1.0, "pip_factor": 100,   "unit": "pips", "decimals": 3
    },
    "AUD/USD": {
        "name": "AUD/USD (Aussie Cent)",
        "trend_sl": 0.0025,  "trend_tp": 0.0050,
        "scalp_sl": 0.0012,  "scalp_tp": 0.0020,
        "contract_size": 1.0, "pip_factor": 10000, "unit": "pips", "decimals": 5
    },
    "USD/CAD": {
        "name": "USD/CAD (Loonie Cent)",
        "trend_sl": 0.0025,  "trend_tp": 0.0050,
        "scalp_sl": 0.0012,  "scalp_tp": 0.0020,
        "contract_size": 1.0, "pip_factor": 10000, "unit": "pips", "decimals": 5
    },
    "GBP/JPY": {
        "name": "GBP/JPY (Ninja Cent)",
        "trend_sl": 0.45,    "trend_tp": 0.90,
        "scalp_sl": 0.22,    "scalp_tp": 0.40,
        "contract_size": 1.0, "pip_factor": 100,   "unit": "pips", "decimals": 3
    },
    
    # --- CRYPTO ASSETS ---
    "BTC/USD": {
        "name": "BTC/USD (Bitcoin Cent)",
        "trend_sl": 1200.00, "trend_tp": 2400.00,
        "scalp_sl": 600.00,  "scalp_tp": 1000.00,
        "contract_size": 1.0, "pip_factor": 1,   "unit": "points", "decimals": 2
    },
    "ETH/USD": {
        "name": "ETH/USD (Ethereum Cent)",
        "trend_sl": 80.00,   "trend_tp": 160.00,
        "scalp_sl": 40.00,   "scalp_tp": 70.00,
        "contract_size": 1.0, "pip_factor": 1,   "unit": "points", "decimals": 2
    },
    "SOL/USD": {
        "name": "SOL/USD (Solana Cent)",
        "trend_sl": 5.00,    "trend_tp": 10.00,
        "scalp_sl": 2.50,    "scalp_tp": 4.50,
        "contract_size": 1.0, "pip_factor": 1,   "unit": "points", "decimals": 2
    },
    "XRP/USD": {
        "name": "XRP/USD (Ripple Cent)",
        "trend_sl": 0.03,    "trend_tp": 0.06,
        "scalp_sl": 0.015,   "scalp_tp": 0.025,
        "contract_size": 1.0, "pip_factor": 10000, "unit": "pips", "decimals": 4
    },

    # --- COMMODITIES ---
    "XAU/USD": {
        "name": "XAU/USD (Gold Cent)",
        "trend_sl": 3.50,    "trend_tp": 7.00,
        "scalp_sl": 2.00,    "scalp_tp": 3.00,
        "contract_size": 1.0, "pip_factor": 100, "unit": "pips", "decimals": 2
    }
}

# Global Memory State & Live Cache initialized dynamically from ASSET_SPECS
LAST_SIGNALS = {symbol: None for symbol in ASSET_SPECS.keys()}
LIVE_MARKET_CACHE = {symbol: None for symbol in ASSET_SPECS.keys()}

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

# --- PROFESSIONAL CATEGORY KEYBOARDS ---

def get_main_dashboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn_forex = KeyboardButton("📊 Forex Markets (Top 6)")
    btn_crypto = KeyboardButton("🪙 Crypto Assets")
    btn_gold = KeyboardButton("🥇 Commodities (Gold)")
    btn_balance = KeyboardButton("💳 Configure Capital")
    btn_info = KeyboardButton("⚙️ Terminal Diagnostics")
    markup.add(btn_forex, btn_crypto, btn_gold, btn_balance, btn_info)
    return markup

def get_forex_submenu():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("EUR/USD", callback_data="select_EUR/USD"),
        InlineKeyboardButton("GBP/USD", callback_data="select_GBP/USD"),
        InlineKeyboardButton("USD/JPY", callback_data="select_USD/JPY"),
        InlineKeyboardButton("AUD/USD", callback_data="select_AUD/USD"),
        InlineKeyboardButton("USD/CAD", callback_data="select_USD/CAD"),
        InlineKeyboardButton("GBP/JPY", callback_data="select_GBP/JPY")
    )
    return markup

def get_crypto_submenu():
    markup = InlineKeyboardMarkup(row_width=2)
    markup.add(
        InlineKeyboardButton("BTC/USD", callback_data="select_BTC/USD"),
        InlineKeyboardButton("ETH/USD", callback_data="select_ETH/USD"),
        InlineKeyboardButton("SOL/USD", callback_data="select_SOL/USD"),
        InlineKeyboardButton("XRP/USD", callback_data="select_XRP/USD")
    )
    return markup

def get_balance_presets():
    markup = InlineKeyboardMarkup(row_width=3)
    b1 = InlineKeyboardButton("$20 USD", callback_data="setbal_20")
    b2 = InlineKeyboardButton("$25 USD", callback_data="setbal_25")
    b3 = InlineKeyboardButton("$50 USD", callback_data="setbal_50")
    b4 = InlineKeyboardButton("$100 USD", callback_data="setbal_100")
    b5 = InlineKeyboardButton("$250 USD", callback_data="setbal_250")
    b6 = InlineKeyboardButton("$500 USD", callback_data="setbal_500")
    markup.add(b1, b2, b3, b4, b5, b6)
    return markup

def parse_raw_amount(text):
    cleaned = text.replace('$', '').replace(',', '').strip()
    try:
        val = float(cleaned)
        return val if val > 0 else None
    except ValueError:
        return None

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
    time.sleep(1.0)
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
        htf_bias = "RANGING / NEUTRAL ⚪"
    elif htf['sma20'] > htf['sma50']:
        htf_bias = "BULLISH 🟢"
    else:
        htf_bias = "BEARISH 🔴"

    ltf_bullish = ltf['sma20'] > ltf['sma50'] and ltf['rsi'] > 50
    ltf_bearish = ltf['sma20'] < ltf['sma50'] and ltf['rsi'] < 50

    if "BULLISH" in htf_bias and ltf_bullish:
        trade_type = "TREND CONTINUATION"
        signal = "BUY / LONG 🟢"
        sl_dist, tp_dist = spec['trend_sl'], spec['trend_tp']
        note = "Multi-timeframe structural alignment confirmed (4H & 15M)."

    elif "BEARISH" in htf_bias and ltf_bearish:
        trade_type = "TREND CONTINUATION"
        signal = "SELL / SHORT 🔴"
        sl_dist, tp_dist = spec['trend_sl'], spec['trend_tp']
        note = "Multi-timeframe structural alignment confirmed (4H & 15M)."

    elif "BULLISH" in htf_bias and ltf_bearish:
        trade_type = "COUNTER-TREND SCALP"
        signal = "SELL / SHORT (SCALP) 🟡"
        sl_dist, tp_dist = spec['scalp_sl'], spec['scalp_tp']
        note = "Counter-trend volatility capture against 4H macro bias."

    elif "BEARISH" in htf_bias and ltf_bullish:
        trade_type = "COUNTER-TREND SCALP"
        signal = "BUY / LONG (SCALP) 🟡"
        sl_dist, tp_dist = spec['scalp_sl'], spec['scalp_tp']
        note = "Counter-trend volatility capture against 4H macro bias."

    elif "RANGING" in htf_bias and ltf_bullish:
        trade_type = "RANGE BREAKOUT"
        signal = "BUY / LONG (SCALP) 🟢"
        sl_dist, tp_dist = spec['scalp_sl'], spec['scalp_tp']
        note = "Consolidation break with high-momentum 15M expansion."

    elif "RANGING" in htf_bias and ltf_bearish:
        trade_type = "RANGE BREAKOUT"
        signal = "SELL / SHORT (SCALP) 🔴"
        sl_dist, tp_dist = spec['scalp_sl'], spec['scalp_tp']
        note = "Consolidation break with high-momentum 15M breakdown."

    else:
        return {
            "is_sideways": True,
            "text": (
                f"📊 **MARKET PROFILE — {spec['name']}**\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"💵 **Current Price:** `{price:,.{spec['decimals']}f}`\n"
                f"🏛 **4H Macro Context:** {htf_bias}\n"
                f"📈 **15M Momentum (RSI):** `{ltf['rsi']:.1f}`\n\n"
                f"⏳ **Status:** *Consolidation zone detected. Awaiting directional expansion trigger.*"
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

# --- ⚡ INSTITUTIONAL SCANNER ENGINE ---

def live_market_scanner_loop():
    print("⚡ Institutional scanner operational across expanded portfolio...")
    while True:
        try:
            for symbol in ASSET_SPECS.keys():
                sig = generate_multi_timeframe_signal(symbol)
                
                if sig:
                    LIVE_MARKET_CACHE[symbol] = sig

                if not sig or sig.get('is_sideways'):
                    LAST_SIGNALS[symbol] = "SIDEWAYS"
                    time.sleep(1.5)
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
                            f"🚨 **INSTANT TRADE BROADCAST — {sig['name']}**\n"
                            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                            f"💵 **Live Price:** `{sig['price']:,.{spec['decimals']}f}`\n"
                            f"🏛 **Macro Bias (4H):** {sig['htf_bias']}\n"
                            f"🏷 **Setup Type:** `{sig['trade_type']}`\n\n"
                            f"💡 **Directive:** {sig['signal']}\n"
                            f"• **Entry Price:** `{sig['price']:,.{spec['decimals']}f}`\n"
                            f"• **Stop Loss:** `{sig['sl_price']:,.{spec['decimals']}f}` *({pips_sl} {spec['unit']})*\n"
                            f"• **Take Profit:** `{sig['tp_price']:,.{spec['decimals']}f}` *({pips_tp} {spec['unit']})*\n\n"
                            f"⚙️ *Select institutional risk parameters below to compute execution volume:*"
                        )

                        markup = InlineKeyboardMarkup(row_width=3)
                        b_low = InlineKeyboardButton("🛡 Conservative (0.25%)", callback_data=f"calc_{symbol}_{sig['sl_dist']}_{sig['tp_dist']}_0.25_{active_balance}")
                        b_std = InlineKeyboardButton("⚖️ Standard (1.0%)", callback_data=f"calc_{symbol}_{sig['sl_dist']}_{sig['tp_dist']}_1.0_{active_balance}")
                        b_high = InlineKeyboardButton("🚀 Aggressive (5.0%)", callback_data=f"calc_{symbol}_{sig['sl_dist']}_{sig['tp_dist']}_5.0_{active_balance}")
                        markup.add(b_low, b_std, b_high)

                        try:
                            bot.send_message(chat_id, alert_card, reply_markup=markup, parse_mode="Markdown")
                        except Exception as send_err:
                            print(f"Failed to push alert to {chat_id}: {send_err}")

                time.sleep(1.5)

        except Exception as e:
            print(f"Scanner Loop Error: {e}")

        time.sleep(45)

# --- TELEGRAM HANDLERS ---

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    current_bal = get_user_balance(message.chat.id)
    msg = (
        "📈 **INSTANT TRADING TERMINAL ACTIVE**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💳 **Assigned Capital:** `${current_bal:,.2f} USD`\n"
        "⚡ **Engine Status:** Continuous multi-asset surveillance running across Forex, Crypto, & Metals.\n\n"
        "Select a category below to browse live matrices:"
    )
    bot.send_message(message.chat.id, msg, reply_markup=get_main_dashboard(), parse_mode="Markdown")

def process_signal_request(message, symbol):
    bot.send_chat_action(message.chat.id, 'typing')
    active_balance = get_user_balance(message.chat.id)

    sig = LIVE_MARKET_CACHE.get(symbol)
    if not sig:
        sig = generate_multi_timeframe_signal(symbol)
        if sig:
            LIVE_MARKET_CACHE[symbol] = sig

    if not sig:
        bot.send_message(message.chat.id, f"⚠️ Synchronizing market feed for {symbol}. Re-attempting shortly.", reply_markup=get_main_dashboard())
        return

    if sig.get('is_sideways'):
        bot.send_message(message.chat.id, sig['text'], reply_markup=get_main_dashboard(), parse_mode="Markdown")
        return

    spec = sig['spec']
    pips_sl = int(sig['sl_dist'] * spec['pip_factor'])
    pips_tp = int(sig['tp_dist'] * spec['pip_factor'])

    card = (
        f"💎 **PRO-GRADE SIGNAL MATRIX — {sig['name']}**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"💵 **Live Price:** `{sig['price']:,.{spec['decimals']}f}`\n"
        f"🏛 **Macro Bias (4H):** {sig['htf_bias']}\n"
        f"🏷 **Setup Classification:** `{sig['trade_type']}`\n\n"
        f"💡 **Directive:** {sig['signal']}\n"
        f"• **Entry Price:** `{sig['price']:,.{spec['decimals']}f}`\n"
        f"• **Stop Loss:** `{sig['sl_price']:,.{spec['decimals']}f}` *({pips_sl} {spec['unit']})*\n"
        f"• **Take Profit:** `{sig['tp_price']:,.{spec['decimals']}f}` *({pips_tp} {spec['unit']})*\n\n"
        f"📝 **Analytic Context:** {sig['note']}\n\n"
        f"👇 **Select Risk Exposure Profile for Position Sizing:**"
    )

    markup = InlineKeyboardMarkup(row_width=3)
    b_low = InlineKeyboardButton("🛡 Conservative (0.25%)", callback_data=f"calc_{symbol}_{sig['sl_dist']}_{sig['tp_dist']}_0.25_{active_balance}")
    b_std = InlineKeyboardButton("⚖️ Standard (1.0%)", callback_data=f"calc_{symbol}_{sig['sl_dist']}_{sig['tp_dist']}_1.0_{active_balance}")
    b_high = InlineKeyboardButton("🚀 Aggressive (5.0%)", callback_data=f"calc_{symbol}_{sig['sl_dist']}_{sig['tp_dist']}_5.0_{active_balance}")
    markup.add(b_low, b_std, b_high)

    bot.send_message(message.chat.id, card, reply_markup=markup, parse_mode="Markdown")

@bot.message_handler(func=lambda msg: msg.text == "📊 Forex Markets (Top 6)")
def handle_forex_menu(message):
    bot.send_message(
        message.chat.id, 
        "📊 **Select Volatile Forex Pair:**", 
        reply_markup=get_forex_submenu(), 
        parse_mode="Markdown"
    )

@bot.message_handler(func=lambda msg: msg.text == "🪙 Crypto Assets")
def handle_crypto_menu(message):
    bot.send_message(
        message.chat.id, 
        "🪙 **Select Crypto Asset:**", 
        reply_markup=get_crypto_submenu(), 
        parse_mode="Markdown"
    )

@bot.message_handler(func=lambda msg: msg.text in ["🥇 Commodities (Gold)", "/gold"])
def handle_gold(message):
    process_signal_request(message, "XAU/USD")

@bot.message_handler(func=lambda msg: msg.text in ["💳 Configure Capital", "/setbalance"])
def handle_balance_menu(message):
    current_bal = get_user_balance(message.chat.id)
    msg = (
        f"💳 **Capital Management Portal**\n\n"
        f"Active Account Balance: **${current_bal:,.2f} USD**\n\n"
        "Select an institutional tier below or input exact decimal value directly (e.g. `57.59`):"
    )
    bot.send_message(message.chat.id, msg, reply_markup=get_balance_presets(), parse_mode="Markdown")

@bot.message_handler(func=lambda msg: msg.text == "⚙️ Terminal Diagnostics")
def handle_bot_info(message):
    current_bal = get_user_balance(message.chat.id)
    info_text = (
        "⚙️ **System Diagnostic Matrix**\n"
        "━━━━━━━━━━━━━━━━━━━\n"
        "• **Active Feeds:** 11 Instruments (Forex, Crypto, Metals)\n"
        "• **Surveillance Interval:** Continuous background polling\n"
        "• **Risk Parameters:** 0.25% / 1.0% / 5.0% Exposure Tiers\n"
        f"• **Configured Capital:** `${current_bal:,.2f} USD`\n"
        "• **System Status:** Fully Operational 🟢"
    )
    bot.send_message(message.chat.id, info_text, reply_markup=get_main_dashboard(), parse_mode="Markdown")

@bot.message_handler(func=lambda msg: parse_raw_amount(msg.text) is not None)
def handle_raw_number_balance(message):
    new_bal = parse_raw_amount(message.text)
    set_user_balance(message.chat.id, new_bal)
    bot.reply_to(
        message, 
        f"✅ Capital database updated successfully. Active baseline: **${new_bal:,.2f} USD**", 
        reply_markup=get_main_dashboard(), 
        parse_mode="Markdown"
    )

# --- INLINE CALLBACK HANDLERS ---

@bot.callback_query_handler(func=lambda call: call.data.startswith('select_'))
def handle_asset_selection_callback(call):
    try:
        symbol = call.data.split('_', 1)[1]
        bot.answer_callback_query(call.id, text=f"Loading {symbol} analysis...")
        # Create a mock message object wrapper for process_signal_request
        class MockMessage:
            def __init__(self, chat_id):
                self.chat = type('obj', (object,), {'id': chat_id})
        process_signal_request(MockMessage(call.message.chat.id), symbol)
    except Exception as e:
        print(f"Asset selection callback error: {e}")

@bot.callback_query_handler(func=lambda call: call.data.startswith('setbal_'))
def handle_preset_balance(call):
    try:
        new_bal = float(call.data.split('_')[1])
        set_user_balance(call.message.chat.id, new_bal)
        bot.answer_callback_query(call.id, text=f"Capital updated to ${new_bal:,.2f} USD")
        bot.send_message(
            call.message.chat.id, 
            f"✅ Capital baseline reconfigured to **${new_bal:,.2f} USD**", 
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
            f"📐 **POSITION SIZING MATRIX ({risk_pct}% RISK) — {spec['name']}**\n"
            f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            f"• **Assigned Capital:** `${active_balance:,.2f} USD`\n"
            f"• **Recommended Volume:** `{cent_lot_size:.2f} Cent Lots`\n"
            f"• **Maximum Risk Exposure:** -`${risk_dollars:,.2f} USD`\n"
            f"• **Projected Target Yield:** +`${reward_dollars:,.2f} USD` *({pips_tp} {spec['unit']})*\n\n"
            f"💡 *Input volume `{cent_lot_size:.2f}` into your MetaTrader Cent account terminal.*"
        )

        bot.answer_callback_query(call.id, text=f"Calculated for {risk_pct}% Risk Matrix")
        bot.send_message(call.message.chat.id, calc_text, parse_mode="Markdown")

    except Exception as e:
        print(f"Callback Error: {e}")
        bot.answer_callback_query(call.id, text="Calculation error encountered.")

def run_bot():
    print("Telegram terminal online and listening...")
    bot.infinity_polling()

# --- FLASK KEEP-ALIVE SERVER & THREAD LAUNCHERS ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Institutional Multi-Asset Sniper Terminal is active and operational."

if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.daemon = True
    bot_thread.start()

    scanner_thread = threading.Thread(target=live_market_scanner_loop)
    scanner_thread.daemon = True
    scanner_thread.start()
    
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
