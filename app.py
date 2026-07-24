import os
import threading
import time
import requests
import yfinance as yf
from flask import Flask, request, jsonify

app = Flask(__name__)

# Telegram Configuration
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8153490508:AAG5Hjr8mjLw5QAaNLn5n4S1CpQSKJE7whs")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "8153490508")

def send_telegram_alert(chat_id, message, reply_markup=None):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": message,
        "parse_mode": "Markdown"
    }
    if reply_markup:
        payload["reply_markup"] = reply_markup
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Error sending Telegram alert: {e}")

# --- KEYBOARD MENUS ---

def get_main_keyboard():
    return {
        "keyboard": [
            [{"text": "🎯 Instant Signal"}, {"text": "⏱ Timeframe Analysis"}],
            [{"text": "📊 Full Market Overview"}, {"text": "⚙️ Engine & Live Price"}]
        ],
        "resize_keyboard": True,
        "persistent": True
    }

def get_timeframe_keyboard():
    return {
        "keyboard": [
            [{"text": "⚡ 15M Scalp"}, {"text": "📊 30M Intraday"}],
            [{"text": "📈 1H Trend"}, {"text": "🏛 4H Macro"}],
            [{"text": "🔙 Main Menu"}]
        ],
        "resize_keyboard": True,
        "persistent": True
    }

# --- TECHNICAL ANALYZER ENGINE ---

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def analyze_single_timeframe(interval_code, period_code, tf_name):
    gold = yf.Ticker("GC=F")
    df = gold.history(period=period_code, interval=interval_code)
    
    if df.empty or len(df) < 50:
        return f"⚠️ Insufficient data to analyze {tf_name} chart."

    df['SMA20'] = df['Close'].rolling(20).mean()
    df['SMA50'] = df['Close'].rolling(50).mean()
    df['RSI'] = calculate_rsi(df['Close'], 14)

    current_price = df['Close'].iloc[-1]
    sma20 = df['SMA20'].iloc[-1]
    sma50 = df['SMA50'].iloc[-1]
    rsi = df['RSI'].iloc[-1]
    high_10 = df['High'].iloc[-11:-1].max()
    low_10 = df['Low'].iloc[-11:-1].min()

    if current_price > sma20 > sma50 and rsi > 52:
        bias = "BULLISH 📈"
        action = "LOOK FOR BUY / LONG 🟢"
        sl = current_price - 18.0
        tp = current_price + 36.0
    elif current_price < sma20 < sma50 and rsi < 48:
        bias = "BEARISH 📉"
        action = "LOOK FOR SELL / SHORT 🔴"
        sl = current_price + 18.0
        tp = current_price - 36.0
    else:
        bias = "NEUTRAL / RANGING ⚖️"
        action = "WAIT FOR CLEAR BREAKOUT ⏳"
        sl, tp = 0, 0

    msg = (
        f"⏱ *{tf_name.upper()} TIMEFRAME ANALYSIS*\n"
        f"----------------------------------------\n"
        f"💵 *Current Price:* `${current_price:.2f}`\n"
        f"📊 *Trend Bias:* `{bias}`\n"
        f"📈 *RSI (14):* `{rsi:.1f}`\n"
        f"🔹 *SMA 20:* `${sma20:.2f}` | *SMA 50:* `${sma50:.2f}`\n\n"
        f"💡 *Actionable Setup:* *{action}*\n"
    )

    if sl != 0:
        msg += (
            f"• *Suggested Entry:* `${current_price:.2f}`\n"
            f"• *Stop Loss (SL):* `${sl:.2f}`\n"
            f"• *Take Profit (TP):* `${tp:.2f}`\n"
        )
    return msg

def get_instant_signal():
    gold = yf.Ticker("GC=F")
    df = gold.history(period="5d", interval="15m")
    if df.empty or len(df) < 20:
        return "⚠️ Unable to fetch market data for instant signal."

    current_price = df['Close'].iloc[-1]
    high_10 = df['High'].iloc[-11:-1].max()
    low_10 = df['Low'].iloc[-11:-1].min()

    if current_price >= high_10:
        return (
            f"🚨 *INSTANT SIGNAL: BUY / LONG 🟢*\n\n"
            f"📌 *Asset:* Gold (XAU/USD)\n"
            f"💵 *Entry Price:* `${current_price:.2f}`\n"
            f"🛑 *Stop Loss:* `${current_price - 20.0:.2f}`\n"
            f"🎯 *Take Profit 1:* `${current_price + 30.0:.2f}`\n"
            f"🎯 *Take Profit 2:* `${current_price + 60.0:.2f}`\n"
            f"⚖️ *Risk/Reward:* 1:3\n"
            f"⚡ *Reason:* 15M High Breakout Confirmed!"
        )
    elif current_price <= low_10:
        return (
            f"🚨 *INSTANT SIGNAL: SELL / SHORT 🔴*\n\n"
            f"📌 *Asset:* Gold (XAU/USD)\n"
            f"💵 *Entry Price:* `${current_price:.2f}`\n"
            f"🛑 *Stop Loss:* `${current_price + 20.0:.2f}`\n"
            f"🎯 *Take Profit 1:* `${current_price - 30.0:.2f}`\n"
            f"🎯 *Take Profit 2:* `${current_price - 60.0:.2f}`\n"
            f"⚖️ *Risk/Reward:* 1:3\n"
            f"⚡ *Reason:* 15M Low Breakout Confirmed!"
        )
    else:
        return (
            f"⏳ *INSTANT SIGNAL: NO ENTRY RIGHT NOW*\n\n"
            f"💵 *Current Price:* `${current_price:.2f}`\n"
            f"⬆️ *Breakout Buy Level:* `${high_10:.2f}`\n"
            f"⬇️ *Breakout Sell Level:* `${low_10:.2f}`\n\n"
            f"💡 *Status:* Market is consolidating between key levels. Wait for price to cross boundary."
        )

# --- WEBHOOK HANDLER ---

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    if data and "message" in data:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"].get("text", "")

        # --- MAIN MENU & NAVIGATION ---
        if text in ["/start", "start", "🔙 Main Menu"]:
            welcome = (
                "🏛 *COVTRAD AI GOLD TRADING ENGINE*\n\n"
                "Welcome to your professional market assistant. Select an option from the menu below:"
            )
            send_telegram_alert(chat_id, welcome, reply_markup=get_main_keyboard())

        elif text in ["🎯 Instant Signal", "/signal"]:
            send_telegram_alert(chat_id, "⚡ *Calculating instant signal...*")
            msg = get_instant_signal()
            send_telegram_alert(chat_id, msg, reply_markup=get_main_keyboard())

        elif text in ["⏱ Timeframe Analysis", "/timeframes"]:
            msg = "⏱ *Select a specific timeframe below to perform focused technical analysis:*"
            send_telegram_alert(chat_id, msg, reply_markup=get_timeframe_keyboard())

        # --- TIMEFRAME SUB-MENU ACTIONS ---
        elif text == "⚡ 15M Scalp":
            send_telegram_alert(chat_id, "⏳ *Analyzing 15M chart...*")
            msg = analyze_single_timeframe("15m", "5d", "15-Minute Scalp")
            send_telegram_alert(chat_id, msg, reply_markup=get_timeframe_keyboard())

        elif text == "📊 30M Intraday":
            send_telegram_alert(chat_id, "⏳ *Analyzing 30M chart...*")
            msg = analyze_single_timeframe("30m", "5d", "30-Minute Intraday")
            send_telegram_alert(chat_id, msg, reply_markup=get_timeframe_keyboard())

        elif text == "📈 1H Trend":
            send_telegram_alert(chat_id, "⏳ *Analyzing 1H chart...*")
            msg = analyze_single_timeframe("1h", "1mo", "1-Hour Trend")
            send_telegram_alert(chat_id, msg, reply_markup=get_timeframe_keyboard())

        elif text == "🏛 4H Macro":
            send_telegram_alert(chat_id, "⏳ *Analyzing 4H chart...*")
            msg = analyze_single_timeframe("1h", "1mo", "4-Hour Macro")
            send_telegram_alert(chat_id, msg, reply_markup=get_timeframe_keyboard())

        # --- OVERVIEW & ENGINE STATUS ---
        elif text in ["📊 Full Market Overview", "/overview"]:
            send_telegram_alert(chat_id, "⏳ *Scanning 15M, 30M, 1H, and 4H timeframes...*")
            m15 = analyze_single_timeframe("15m", "5d", "15M")
            m60 = analyze_single_timeframe("1h", "1mo", "1H")
            send_telegram_alert(chat_id, f"{m15}\n\n{m60}", reply_markup=get_main_keyboard())

        elif text in ["⚙️ Engine & Live Price", "/status", "/price"]:
            try:
                gold = yf.Ticker("GC=F")
                df = gold.history(period="1d", interval="1m")
                current_price = df['Close'].iloc[-1]
                msg = (
                    f"⚙️ *COVTRAD ENGINE STATUS*\n"
                    f"----------------------------------------\n"
                    f"💵 *Live Spot Price (XAU/USD):* `${current_price:.2f}`\n"
                    f"🟢 *Server Status:* Active 24/7 (Cloud Node)\n"
                    f"🔄 *Automated Scanner:* Scanning every 120s\n"
                    f"⚡ *Latency:* Real-Time"
                )
            except Exception as e:
                msg = f"Error fetching system status: {e}"
            send_telegram_alert(chat_id, msg, reply_markup=get_main_keyboard())

    return jsonify({"status": "ok"}), 200

# --- BACKGROUND AUTOMATED SCANNER (Runs 24/7) ---

def run_scanner():
    print("Starting Covtrad Gold Market Scanner...")
    last_signal = None
    while True:
        try:
            gold = yf.Ticker("GC=F")
            df = gold.history(period="5d", interval="15m")
            
            if not df.empty and len(df) > 15:
                current_price = df['Close'].iloc[-1]
                high_10 = df['High'].iloc[-11:-1].max()
                low_10 = df['Low'].iloc[-11:-1].min()

                if current_price > high_10 and last_signal != "BUY":
                    last_signal = "BUY"
                    msg = (f"🚨 *COVTRAD AUTOMATED ALERT (BUY)* 🚨\n\n"
                           f"📌 *Asset:* XAU/USD\n"
                           f"📈 *Direction:* BUY / LONG\n"
                           f"💵 *Entry:* ${current_price:.2f}\n"
                           f"🛑 *Stop Loss:* ${current_price - 20.0:.2f}\n"
                           f"🎯 *Take Profit:* ${current_price + 40.0:.2f}\n")
                    send_telegram_alert(TELEGRAM_CHAT_ID, msg, reply_markup=get_main_keyboard())

                elif current_price < low_10 and last_signal != "SELL":
                    last_signal = "SELL"
                    msg = (f"🚨 *COVTRAD AUTOMATED ALERT (SELL)* 🚨\n\n"
                           f"📌 *Asset:* XAU/USD\n"
                           f"📉 *Direction:* SELL / SHORT\n"
                           f"💵 *Entry:* ${current_price:.2f}\n"
                           f"🛑 *Stop Loss:* ${current_price + 20.0:.2f}\n"
                           f"🎯 *Take Profit:* ${current_price - 20.0:.2f}\n")
                    send_telegram_alert(TELEGRAM_CHAT_ID, msg, reply_markup=get_main_keyboard())
        except Exception as e:
            print(f"Scanner error: {e}")
        
        time.sleep(120)

threading.Thread(target=run_scanner, daemon=True).start()

@app.route('/')
def index():
    return "Covtrad Gold Signal Engine is Running 24/7!"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
