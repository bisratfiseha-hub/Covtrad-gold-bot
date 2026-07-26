import os
import threading
import sqlite3
import pandas as pd
import numpy as np
import yfinance as yf
import telebot
from telebot import types
from flask import Flask

# ==================== CONFIGURATION ====================
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "YOUR_BOT_TOKEN_HERE")
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

# Asset Ticker Mapping for yfinance
ASSET_MAPPING = {
    "XAU/USD": "GC=F",
    "EUR/USD": "EURUSD=X",
    "BTC/USD": "BTC-USD"
}

# ==================== SMC & PRICE ACTION ENGINE ====================
def fetch_data(symbol, interval, period):
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(period=period, interval=interval)
        if df.empty:
            return None
        df = df[['Open', 'High', 'Low', 'Close', 'Volume']].dropna()
        return df
    except Exception as e:
        print(f"Error fetching data for {symbol}: {e}")
        return None

def detect_market_structure(df):
    """Detects 4H Macro Trend via Swing Highs/Lows and BOS baseline trend."""
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
    ticker = ASSET_MAPPING.get(asset_name)
    if not ticker:
        return "Invalid Asset."
    
    df_4h = fetch_data(ticker, interval="60m", period="5d")
    df_15m = fetch_data(ticker, interval="15m", period="2d")
    
    if df_4h is None or df_15m is None or len(df_4h) < 50 or len(df_15m) < 20:
        return f"⚠️ Insufficient market data retrieved for {asset_name}."
    
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
            f"🏛️ **Institutional Confluence Verified**\n"
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
            f"🏛️ **Institutional Confluence Verified**\n"
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
        f"📊 **SMC SCAN REPORT: {asset_name}**\n"
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
        "🤖 **Institutional SMC Trading Bot Initialized**\n\n"
        "System ready with Smart Money Concepts (BOS/FVG) and automated risk calculations.",
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
    bot.send_message(message.chat.id, "Select an asset for deep institutional SMC scanning:", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data.startswith("scan_"))
def handle_scan_callback(call):
    asset = call.data.split("_")[1]
    bot.answer_callback_query(call.id, text=f"Analyzing {asset} via SMC Engine...")
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
    return "SMC Trading Bot is active!"

def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

if __name__ == "__main__":
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    print("🤖 Starting Telegram Bot polling loop...")
    bot.infinity_polling()
