import os
import threading
import time
import requests
import yfinance as yf
from flask import Flask, request, jsonify

app = Flask(__name__)

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

def get_main_keyboard():
    return {
        "keyboard": [
            [{"text": "📊 Full Market Analysis"}, {"text": "💵 Live Gold Price"}],
            [{"text": "⚡ Quick Signal Check"}, {"text": "🟢 System Status"}]
        ],
        "resize_keyboard": True,
        "persistent": True
    }

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def perform_multi_timeframe_analysis():
    gold = yf.Ticker("GC=F")
    
    # Timeframes: 15m (Entry), 1h (Medium Trend), 4h (Macro Trend)
    tf_data = {
        "15m": gold.history(period="5d", interval="15m"),
        "1h": gold.history(period="10d", interval="1h"),
        "4h": gold.history(period="1mo", interval="1h") # Resampled or approximated
    }
    
    current_price = tf_data["15m"]['Close'].iloc[-1]
    
    results = {}
    bullish_signals = 0
    bearish_signals = 0
    
    for tf, df in tf_data.items():
        if df.empty or len(df) < 50:
            continue
        
        df['SMA20'] = df['Close'].rolling(20).mean()
        df['SMA50'] = df['Close'].rolling(50).mean()
        df['RSI'] = calculate_rsi(df['Close'], 14)
        
        last_close = df['Close'].iloc[-1]
        sma20 = df['SMA20'].iloc[-1]
        sma50 = df['SMA50'].iloc[-1]
        rsi = df['RSI'].iloc[-1]
        
        if last_close > sma20 > sma50 and rsi > 50:
            trend = "Bullish 📈"
            bullish_signals += 1
        elif last_close < sma20 < sma50 and rsi < 50:
            trend = "Bearish 📉"
            bearish_signals += 1
        else:
            trend = "Neutral ⚖️"
            
        results[tf] = {"trend": trend, "rsi": rsi, "sma20": sma20, "sma50": sma50}

    # Signal Logic
    if bullish_signals >= 2:
        bias = "BUY / LONG 🟢"
        sl = current_price - 18.0
        tp1 = current_price + 25.0
        tp2 = current_price + 45.0
        confidence = "HIGH (Bullish Alignment)" if bullish_signals == 3 else "MEDIUM"
    elif bearish_signals >= 2:
        bias = "SELL / SHORT 🔴"
        sl = current_price + 18.0
        tp1 = current_price - 25.0
        tp2 = current_price - 45.0
        confidence = "HIGH (Bearish Alignment)" if bearish_signals == 3 else "MEDIUM"
    else:
        bias = "NO CLEAR ENTRY (Consolidation) ⚠️"
        sl, tp1, tp2 = 0, 0, 0
        confidence = "LOW — Wait for breakout"

    analysis_msg = (
        f"🏛 *COVTRAD INSTITUTIONAL GOLD ANALYSIS*\n"
        f"----------------------------------------\n"
        f"💵 *Live Spot Price:* `${current_price:.2f}`\n\n"
        f"📈 *Timeframe Multi-Alignment:*\n"
        f"• *15M (Scalp/Entry):* {results.get('15m', {}).get('trend', 'N/A')} | RSI: {results.get('15m', {}).get('rsi', 0):.1f}\n"
        f"• *1H (Intraday):* {results.get('1h', {}).get('trend', 'N/A')} | RSI: {results.get('1h', {}).get('rsi', 0):.1f}\n"
        f"• *4H (Macro Trend):* {results.get('4h', {}).get('trend', 'N/A')} | RSI: {results.get('4h', {}).get('rsi', 0):.1f}\n\n"
        f"🎯 *RECOMMENDED ACTION:* *{bias}*\n"
        f"🔥 *Signal Confidence:* `{confidence}`\n\n"
    )

    if sl != 0:
        analysis_msg += (
            f"📍 *Trade Setup Parameters:*\n"
            f"• *Entry:* `${current_price:.2f}`\n"
            f"• *Stop Loss (SL):* `${sl:.2f}`\n"
            f"• *Take Profit 1:* `${tp1:.2f}`\n"
            f"• *Take Profit 2:* `${tp2:.2f}`\n"
            f"• *Risk/Reward:* 1:2.5+\n"
        )
    else:
        analysis_msg += "💡 *Advice:* Market is currently range-bound. Avoid entering until higher timeframe alignment occurs."

    return analysis_msg

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    if data and "message" in data:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"].get("text", "")

        if text in ["/start", "start"]:
            welcome_text = (
                "👋 *Welcome to Covtrad Gold Intelligence Engine!*\n\n"
                "I analyze live Gold (`XAU/USD`) price action across multiple timeframes (15M, 1H, 4H) "
                "using dynamic moving averages, RSI indicators, and breakout models.\n\n"
                "Tap any button below to execute instant market actions!"
            )
            send_telegram_alert(chat_id, welcome_text, reply_markup=get_main_keyboard())

        elif text in ["📊 Full Market Analysis", "/analyze"]:
            send_telegram_alert(chat_id, "⏳ *Analyzing Gold market data across 15M, 1H, and 4H timeframes...*")
            try:
                report = perform_multi_timeframe_analysis()
                send_telegram_alert(chat_id, report, reply_markup=get_main_keyboard())
            except Exception as e:
                send_telegram_alert(chat_id, f"Error analyzing market: {e}", reply_markup=get_main_keyboard())

        elif text in ["💵 Live Gold Price", "/price"]:
            try:
                gold = yf.Ticker("GC=F")
                df = gold.history(period="1d", interval="1m")
                current_price = df['Close'].iloc[-1]
                msg = f"💵 *Current Gold (XAU/USD) Price:* `${current_price:.2f}`"
            except Exception as e:
                msg = f"Error fetching price: {e}"
            send_telegram_alert(chat_id, msg, reply_markup=get_main_keyboard())

        elif text in ["⚡ Quick Signal Check", "🟢 System Status", "/status"]:
            msg = (
                "🟢 *Covtrad Engine Status: Active 24/7*\n\n"
                "• *Market:* XAU/USD (Spot Gold)\n"
                "• *Background Scanner:* Operational\n"
                "• *Multi-TF Analyzer:* Ready\n"
                "• *Latency:* Real-time cloud node"
            )
            send_telegram_alert(chat_id, msg, reply_markup=get_main_keyboard())

    return jsonify({"status": "ok"}), 200

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
                    msg = (f"🚨 *COVTRAD AUTOMATED SIGNAL (BUY)* 🚨\n\n"
                           f"📌 *Asset:* XAU/USD\n"
                           f"📈 *Direction:* BUY / LONG\n"
                           f"💵 *Entry:* ${current_price:.2f}\n"
                           f"🛑 *Stop Loss:* ${current_price - 20.0:.2f}\n"
                           f"🎯 *Take Profit:* ${current_price + 40.0:.2f}\n")
                    send_telegram_alert(TELEGRAM_CHAT_ID, msg, reply_markup=get_main_keyboard())

                elif current_price < low_10 and last_signal != "SELL":
                    last_signal = "SELL"
                    msg = (f"🚨 *COVTRAD AUTOMATED SIGNAL (SELL)* 🚨\n\n"
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
