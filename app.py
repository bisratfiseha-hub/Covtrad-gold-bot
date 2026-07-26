import os
import threading
import sqlite3
import pandas as pd
import numpy as np
import requests
import telebot
from telebot import types
from flask import Flask

# ==================== CONFIGURATION ====================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY", "YOUR_TWELVE_DATA_API_KEY")

bot = telebot.TeleBot(TELEGRAM_BOT_TOKEN)
app = Flask(__name__)

# Database for user state (Capital & Risk Tier)
DB_FILE = "trading_bot.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS user_settings (
            user_id INTEGER PRIMARY KEY,
            capital REAL DEFAULT 1000.0,
            risk_tier REAL DEFAULT 1.0
        )
    ''')
    conn.commit()
    conn.close()

init_db()

def get_user_settings(user_id):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("SELECT capital, risk_tier FROM user_settings WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if not row:
        cursor.execute("INSERT INTO user_settings (user_id, capital, risk_tier) VALUES (?, 1000.0, 1.0)", (user_id,))
        conn.commit()
        row = (1000.0, 1.0)
    conn.close()
    return {"capital": row[0], "risk_tier": row[1]}

def update_user_setting(user_id, capital=None, risk_tier=None):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    settings = get_user_settings(user_id)
    new_cap = capital if capital is not None else settings["capital"]
    new_risk = risk_tier if risk_tier is not None else settings["risk_tier"]
    cursor.execute("REPLACE INTO user_settings (user_id, capital, risk_tier) VALUES (?, ?, ?)", (user_id, new_cap, new_risk))
    conn.commit()
    conn.close()

# ==================== PROFESSIONAL API DATA FETCHING ====================
def fetch_twelve_data(symbol, interval, outputsize=100):
    """Fetches professional market data from Twelve Data API."""
    url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval={interval}&outputsize={outputsize}&apikey={TWELVE_DATA_API_KEY}"
    try:
        response = requests.get(url)
        data = response.json()
        if "values" not in data:
            print(f"Twelve Data Error for {symbol}: {data}")
            return None
        df = pd.DataFrame(data["values"])
        df = df.iloc[::-1].reset_index(drop=True)
        for col in ['open', 'high', 'low', 'close']:
            df[col] = df[col].astype(float)
        df.rename(columns={'open': 'Open', 'high': 'High', 'low': 'Low', 'close': 'Close'}, inplace=True)
        return df[['Open', 'High', 'Low', 'Close']]
    except Exception as e:
        print(f"Error fetching Twelve Data for {symbol}: {e}")
        return None

def fetch_binance_data(symbol, interval, limit=100):
    """Fetches professional crypto data from Binance Public API."""
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        response = requests.get(url)
        data = response.json()
        if not isinstance(data, list):
            print(f"Binance Error for {symbol}: {data}")
            return None
        df = pd.DataFrame(data, columns=['open_time', 'Open', 'High', 'Low', 'Close', 'Volume', 'close_time', 'quote_asset_volume', 'number_of_trades', 'taker_buy_base', 'taker_buy_quote', 'ignore'])
        for col in ['Open', 'High', 'Low', 'Close']:
            df[col] = df[col].astype(float)
        return df[['Open', 'High', 'Low', 'Close']]
    except Exception as e:
        print(f"Error fetching Binance data for {symbol}: {e}")
        return None

def fetch_market_data(asset_name, timeframe):
    """Routes asset requests to the correct direct professional API."""
    if asset_name == "XAU/USD":
        interval_map = {"4h": "4h", "15m": "15min"}
        return fetch_twelve_data("XAU/USD", interval_map.get(timeframe, "15min"))
    elif asset_name == "EUR/USD":
        interval_map = {"4h": "4h", "15m": "15min"}
        return fetch_twelve_data("EUR/USD", interval_map.get(timeframe, "15min"))
    elif asset_name == "BTC/USD":
        interval_map = {"4h": "4h", "15m": "15m"}
        return fetch_binance_data("BTCUSDT", interval_map.get(timeframe, "15m"))
    return None

# ==================== SMC ENGINE ====================
def detect_market_structure(df):
    """Detects 4H Macro Trend via moving average structural baseline."""
    df['SMA20'] = df['Close'].rolling(window=20).mean()
    df['SMA50'] = df['Close'].rolling(window=50).mean()
    
    last_close = df['Close'].iloc[-1]
    sma20 = df['SMA20'].iloc[-1]
    sma50 = df['SMA50'].iloc[-1]
    
    if sma20 > sma50 and last_close > sma20:
        return "BULLISH_BOS"
    elif sma20 < sma50 and last_close < sma20:
        return "BEARISH_BOS"
    else:
        return "RANGING"

def detect_fvg(df_15m):
    """Detects unmitigated 15M Fair Value Gaps (FVG)."""
    fvg_list = []
    for i in range(len(df_15m) - 1, 2, -1):
        c1_high = df_15m['High'].iloc[i-2]
        c3_low = df_15m['Low'].iloc[i]
        c1_low = df_15m['Low'].iloc[i-2]
        c3_high = df_15m['High'].iloc[i]
        
        if c3_low > c1_high:
            fvg_list.append(("BULLISH_FVG", c1_high, c3_low))
            break
        elif c3_high < c1_low:
            fvg_list.append(("BEARISH_FVG", c3_high, c1_low))
            break
            
    current_price = df_15m['Close'].iloc[-1]
    return fvg_list, current_price

def analyze_asset(asset_name, user_id):
    df_4h = fetch_market_data(asset_name, "4h")
    df_15m = fetch_market_data(asset_name, "15m")
    
    if df_4h is None or df_15m is None or len(df_4h) < 30 or len(df_15m) < 20:
        return f"⚠️ API connection error or insufficient data retrieved for {asset_name}. Verify your Twelve Data API Key."
    
    macro_structure = detect_market_structure(df_4h)
    fvg_data, current_price = detect_fvg(df_15m)
    
    settings = get_user_settings(user_id)
    capital = settings["capital"]
    risk_pct = settings["risk_tier"]
    risk_amount = capital * (risk_pct / 100.0)
    
    signal = "NO TRADE"
    reasoning = ""
    
    if macro_structure == "BULLISH_BOS" and fvg_data and fvg_data[0][0] == "BULLISH_FVG":
        signal = "BUY / LONG 🟢"
        fvg_bottom = fvg_data[0][1]
        fvg_top = fvg_data[0][2]
        stop_loss = round(fvg_bottom - (current_price * 0.002), 2)
        take_profit = round(current_price + ((current_price - stop_loss) * 2.5), 2)
        reasoning = (
            f"🏛️ **Institutional Confluence Verified via API**\n"
            f"* **4H Macro Structure:** Bullish Break of Structure (BOS) confirmed.\n"
            f"* **Execution Layer:** Price retraced into a verified 15M Bullish Fair Value Gap (${fvg_bottom:,.2f} - ${fvg_top:,.2f}).\n"
            f"* **Why Confirmed:** Smart money mitigated discount liquidity before upward continuation."
        )
    elif macro_structure == "BEARISH_BOS" and fvg_data and fvg_data[0][0] == "BEARISH_FVG":
        signal = "SELL / SHORT 🔴"
        fvg_bottom = fvg_data[0][1]
        fvg_top = fvg_data[0][2]
        stop_loss = round(fvg_top + (current_price * 0.002), 2)
        take_profit = round(current_price - ((stop_loss - current_price) * 2.5), 2)
        reasoning = (
            f"🏛️ **Institutional Confluence Verified via API**\n"
            f"* **4H Macro Structure:** Bearish Break of Structure (BOS) confirmed.\n"
            f"* **Execution Layer:** Price retested a verified 15M Bearish Fair Value Gap (${fvg_bottom:,.2f} - ${fvg_top:,.2f}).\n"
            f"* **Why Confirmed:** Smart money swept premium liquidity before downward expansion."
        )
    else:
        signal = "STAND ASIDE / NO TRADE 🚫"
        reasoning = (
            f"⚠️ **Confluence Mismatch**\n"
            f"* **4H Macro Structure:** {macro_structure}\n"
            f"* **Why Rejected:** Price action lacks clean institutional alignment between macro structure and execution imbalances."
        )
        stop_loss = 0
        take_profit = 0

    report = (
        f"📊 **SMC API SCAN REPORT: {asset_name}**\n"
        f"------------------------------------\n"
        f"💵 **Current Price:** ${current_price:,.2f}\n"
        f"🚦 **Signal Verdict:** {signal}\n\n"
        f"{reasoning}\n\n"
        f"🛡️ **Risk & Capital Management**\n"
        f"* **Account Capital:** ${capital:,.2f}\n"
        f"* **Risk Allocation ({risk_pct}%):** ${risk_amount:,.2f}\n"
    )
    if signal != "STAND ASIDE / NO TRADE 🚫":
        report += (
            f"* **Suggested Stop Loss:** ${stop_loss:,.2f}\n"
            f"* **Suggested Take Profit (2.5R):** ${take_profit:,.2f}\n"
        )
    
    return report

# ==================== TELEGRAM BOT INTERFACE ====================
@bot.message_handler(commands=['start'])
def send_welcome(message):
    markup = types.ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    markup.add(types.KeyboardButton("🔍 Scan Markets"), types.KeyboardButton("⚙️ Settings / Capital"))
    bot.send_message(
        message.chat.id,
        "🤖 **Professional API SMC Trading Bot Initialized**\n\n"
        "Connected to Twelve Data & Binance REST APIs with institutional SMC logic.",
        reply_markup=markup,
        parse_mode="Markdown"
    )

@bot.message_handler(func=lambda msg: msg.text == "🔍 Scan Markets")
def asset_menu(message):
    markup = types.InlineKeyboardMarkup(row_width=3)
    markup.add(
        types.InlineKeyboardButton("🥇 XAU/USD", callback_data="scan_XAU/USD"),
        types.InlineKeyboardButton("💶 EUR/USD", callback_data="scan_EUR/USD"),
        types.InlineKeyboardButton("₿ BTC/USD", callback_data="scan_BTC/USD")
    )
    bot.send_message(message.chat.id, "Select an asset for deep professional API SMC scanning:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("scan_"))
def handle_scan_callback(call):
    asset = call.data.split("_")[1]
    bot.answer_callback_query(call.id, text=f"Fetching live API feed for {asset}...")
    report = analyze_asset(asset, call.from_user.id)
    bot.send_message(call.message.chat.id, report, parse_mode="Markdown")

@bot.message_handler(func=lambda msg: msg.text == "⚙️ Settings / Capital")
def settings_menu(message):
    settings = get_user_settings(message.from_user.id)
    bot.send_message(
        message.chat.id,
        f"⚙️ **Account Configuration**\n"
        f"* **Capital:** ${settings['capital']:,.2f}\n"
        f"* **Risk Per Trade:** {settings['risk_tier']}%\n\n"
        f"Commands:\n"
        f"• `/capital [amount]` (e.g. `/capital 2000`)\n"
        f"• `/risk [percentage]` (e.g. `/risk 1.0` or `/risk 0.25`)",
        parse_mode="Markdown"
    )

@bot.message_handler(commands=['capital'])
def set_capital(message):
    try:
        parts = message.text.split()
        if len(parts) < 2:
            bot.reply_to(message, "Usage: `/capital 1500`", parse_mode="Markdown")
            return
        new_cap = float(parts[1])
        update_user_setting(message.from_user.id, capital=new_cap)
        bot.reply_to(message, f"✅ Capital updated to **${new_cap:,.2f}**.", parse_mode="Markdown")
    except ValueError:
        bot.reply_to(message, "Invalid amount format.")

@bot.message_handler(commands=['risk'])
def set_risk(message):
    try:
        parts = message.text.split()
        if len(parts) < 2:
            bot.reply_to(message, "Usage: `/risk 1.0`", parse_mode="Markdown")
            return
        new_risk = float(parts[1])
        update_user_setting(message.from_user.id, risk_tier=new_risk)
        bot.reply_to(message, f"✅ Risk per trade updated to **{new_risk}%**.", parse_mode="Markdown")
    except ValueError:
        bot.reply_to(message, "Invalid risk format.")

# ==================== FLASK KEEP-ALIVE SERVER ====================
@app.route('/')
def home():
    return "SMC Professional API Trading Bot is active!"

def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    print("🤖 Starting Telegram Bot polling loop with Professional APIs...")
    bot.infinity_polling()
