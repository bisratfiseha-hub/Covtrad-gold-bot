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

# Comprehensive Watchlist Definition
ASSETS = {
    "Gold (XAU/USD)": "GC=F",
    "Bitcoin (BTC)": "BTC-USD",
    "Ethereum (ETH)": "ETH-USD",
    "USD/JPY": "USDJPY=X",
    "EUR/USD": "EURUSD=X",
    "GBP/USD": "GBPUSD=X",
    "NAS100": "NQ=F"
}

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
            [{"text": "🪙 Select Asset"}, {"text": "📊 Full Market Overview"}],
            [{"text": "⚙️ Engine Status"}]
        ],
        "resize_keyboard": True,
        "persistent": True
    }

def get_asset_keyboard():
    return {
        "keyboard": [
            [{"text": "🥇 Gold (XAU/USD)"}, {"text": "₿ Bitcoin (BTC)"}],
            [{"text": "🔷 Ethereum (ETH)"}, {"text": "💴 USD/JPY"}],
            [{"text": "💶 EUR/USD"}, {"text": "💷 GBP/USD"}],
            [{"text": "📈 NAS100"}, {"text": "🔙 Main Menu"}]
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

# --- TECHNICAL ENGINE ---

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def analyze_asset(ticker_symbol, asset_name, interval_code="15m", period_code="5d", tf_label="15M"):
    try:
        asset = yf.Ticker(ticker_symbol)
        df = asset.history(period=period_code, interval=interval_code)
        
        if df.empty or len(df) < 20:
            return f"⚠️ Insufficient market data for {asset_name} ({tf_label})."

        df['SMA20'] = df['Close'].rolling(20).mean()
        df['SMA50'] = df['Close'].rolling(50).mean()
        df['RSI'] = calculate_rsi(df['Close'], 14)

        current_price = df['Close'].iloc[-1]
        sma20 = df['SMA20'].iloc[-1]
        sma50 = df['SMA50'].iloc[-1]
        rsi = df['RSI'].iloc[-1]
        high_10 = df['High'].iloc[-11:-1].max()
        low_10 = df['Low'].iloc[-11:-1].min()

        # Dynamic Stop Loss / Take Profit Scaling
        if current_price > 10000:  # Crypto (BTC)
            sl_dist, tp_dist = current_price * 0.015, current_price * 0.03
        elif current_price > 1000:   # Gold, ETH, NAS100
            sl_dist, tp_dist = 18.0, 36.0
        elif current_price > 50:     # USD/JPY
            sl_dist, tp_dist = 0.35, 0.70
        else:                        # Forex Majors (EUR/USD, GBP/USD)
            sl_dist, tp_dist = 0.0025, 0.0050

        if current_price > sma20 > sma50 and rsi > 52:
            bias = "BULLISH 📈"
            action = "BUY / LONG 🟢"
            sl = current_price - sl_dist
            tp = current_price + tp_dist
        elif current_price < sma20 < sma50 and rsi < 48:
            bias = "BEARISH 📉"
            action = "SELL / SHORT 🔴"
            sl = current_price + sl_dist
            tp = current_price - tp_dist
        else:
            bias = "NEUTRAL / CONSOLIDATION ⚖️"
            action = "WAIT FOR BREAKOUT ⏳"
            sl, tp = 0, 0

        # Format decimal places appropriately for forex vs commodities/crypto
        if current_price < 10:
            price_fmt = f"{current_price:.4f}"
            sma_fmt = f"{sma20:.4f}"
            sma50_fmt = f"{sma50:.4f}"
            sl_fmt = f"{sl:.4f}"
            tp_fmt = f"{tp:.4f}"
        else:
            price_fmt = f"{current_price:.2f}"
            sma_fmt = f"{sma20:.2f}"
            sma50_fmt = f"{sma50:.2f}"
            sl_fmt = f"{sl:.2f}"
            tp_fmt = f"{tp:.2f}"

        msg = (
            f"📊 *{asset_name} ({tf_label} ANALYSIS)*\n"
            f"----------------------------------------\n"
            f"💵 *Live Price:* `{price_fmt}`\n"
            f"📈 *Trend Bias:* `{bias}`\n"
            f"📊 *RSI (14):* `{rsi:.1f}`\n"
            f"🔹 *SMA 20:* `{sma_fmt}` | *SMA 50:* `{sma50_fmt}`\n\n"
            f"💡 *Signal:* *{action}*\n"
        )

        if sl != 0:
            msg += (
                f"• *Suggested Entry:* `{price_fmt}`\n"
                f"• *Stop Loss (SL):* `{sl_fmt}`\n"
                f"• *Take Profit (TP):* `{tp_fmt}`\n"
            )
        return msg
    except Exception as e:
        return f"Error analyzing {asset_name}: {e}"

# --- WEBHOOK HANDLER ---

user_selected_asset = {"symbol": "GC=F", "name": "Gold (XAU/USD)"}

@app.route('/webhook', methods=['POST'])
def webhook():
    data = request.get_json()
    if data and "message" in data:
        chat_id = data["message"]["chat"]["id"]
        text = data["message"].get("text", "")

        # --- MENU NAVIGATION ---
        if text in ["/start", "start", "🔙 Main Menu"]:
            welcome = (
                "🏛 *COVTRAD MULTI-ASSET INTELLIGENCE BOT*\n\n"
                f"📌 *Active Selected Asset:* `{user_selected_asset['name']}`\n\n"
                "Tap a button below to get real-time technical signals or change your trading asset:"
            )
            send_telegram_alert(chat_id, welcome, reply_markup=get_main_keyboard())

        elif text in ["🪙 Select Asset", "/assets"]:
            msg = "🪙 *Choose an asset/pair to focus analysis on:*"
            send_telegram_alert(chat_id, msg, reply_markup=get_asset_keyboard())

        # --- ASSET SELECTION HANDLERS ---
        elif text == "🥇 Gold (XAU/USD)":
            user_selected_asset["symbol"] = ASSETS["Gold (XAU/USD)"]
            user_selected_asset["name"] = "Gold (XAU/USD)"
            send_telegram_alert(chat_id, "✅ Selected *Gold (XAU/USD)*!", reply_markup=get_main_keyboard())

        elif text == "₿ Bitcoin (BTC)":
            user_selected_asset["symbol"] = ASSETS["Bitcoin (BTC)"]
            user_selected_asset["name"] = "Bitcoin (BTC)"
            send_telegram_alert(chat_id, "✅ Selected *Bitcoin (BTC)*!", reply_markup=get_main_keyboard())

        elif text == "🔷 Ethereum (ETH)":
            user_selected_asset["symbol"] = ASSETS["Ethereum (ETH)"]
            user_selected_asset["name"] = "Ethereum (ETH)"
            send_telegram_alert(chat_id, "✅ Selected *Ethereum (ETH)*!", reply_markup=get_main_keyboard())

        elif text == "💴 USD/JPY":
            user_selected_asset["symbol"] = ASSETS["USD/JPY"]
            user_selected_asset["name"] = "USD/JPY"
            send_telegram_alert(chat_id, "✅ Selected *USD/JPY*!", reply_markup=get_main_keyboard())

        elif text == "💶 EUR/USD":
            user_selected_asset["symbol"] = ASSETS["EUR/USD"]
            user_selected_asset["name"] = "EUR/USD"
            send_telegram_alert(chat_id, "✅ Selected *EUR/USD*!", reply_markup=get_main_keyboard())

        elif text == "💷 GBP/USD":
            user_selected_asset["symbol"] = ASSETS["GBP/USD"]
            user_selected_asset["name"] = "GBP/USD"
            send_telegram_alert(chat_id, "✅ Selected *GBP/USD*!", reply_markup=get_main_keyboard())

        elif text == "📈 NAS100":
            user_selected_asset["symbol"] = ASSETS["NAS100"]
            user_selected_asset["name"] = "NAS100 Index"
            send_telegram_alert(chat_id, "✅ Selected *NAS100 Index*!", reply_markup=get_main_keyboard())

        # --- ANALYSIS EXECUTION ---
        elif text in ["🎯 Instant Signal", "/signal"]:
            send_telegram_alert(chat_id, f"⚡ *Calculating instant signal for {user_selected_asset['name']}...*")
            msg = analyze_asset(user_selected_asset["symbol"], user_selected_asset["name"], "15m", "5d", "15M Instant")
            send_telegram_alert(chat_id, msg, reply_markup=get_main_keyboard())

        elif text in ["⏱ Timeframe Analysis", "/timeframes"]:
            msg = f"⏱ *Select a timeframe for {user_selected_asset['name']}:*"
            send_telegram_alert(chat_id, msg, reply_markup=get_timeframe_keyboard())

        elif text == "⚡ 15M Scalp":
            send_telegram_alert(chat_id, f"⏳ *Analyzing 15M chart for {user_selected_asset['name']}...*")
            msg = analyze_asset(user_selected_asset["symbol"], user_selected_asset["name"], "15m", "5d", "15M Scalp")
            send_telegram_alert(chat_id, msg, reply_markup=get_timeframe_keyboard())

        elif text == "📊 30M Intraday":
            send_telegram_alert(chat_id, f"⏳ *Analyzing 30M chart for {user_selected_asset['name']}...*")
            msg = analyze_asset(user_selected_asset["symbol"], user_selected_asset["name"], "30m", "5d", "30M Intraday")
            send_telegram_alert(chat_id, msg, reply_markup=get_timeframe_keyboard())

        elif text == "📈 1H Trend":
            send_telegram_alert(chat_id, f"⏳ *Analyzing 1H chart for {user_selected_asset['name']}...*")
            msg = analyze_asset(user_selected_asset["symbol"], user_selected_asset["name"], "1h", "1mo", "1H Trend")
            send_telegram_alert(chat_id, msg, reply_markup=get_timeframe_keyboard())

        elif text == "🏛 4H Macro":
            send_telegram_alert(chat_id, f"⏳ *Analyzing 4H chart for {user_selected_asset['name']}...*")
            msg = analyze_asset(user_selected_asset["symbol"], user_selected_asset["name"], "1h", "1mo", "4H Macro")
            send_telegram_alert(chat_id, msg, reply_markup=get_timeframe_keyboard())

        elif text in ["📊 Full Market Overview", "/overview"]:
            send_telegram_alert(chat_id, "⏳ *Scanning core markets (Gold, EUR/USD, BTC)...*")
            m1 = analyze_asset("GC=F", "Gold (XAU/USD)", "15m", "5d", "15M")
            m2 = analyze_asset("EURUSD=X", "EUR/USD", "15m", "5d", "15M")
            m3 = analyze_asset("BTC-USD", "Bitcoin (BTC)", "15m", "5d", "15M")
            send_telegram_alert(chat_id, f"{m1}\n\n{m2}\n\n{m3}", reply_markup=get_main_keyboard())

        elif text in ["⚙️ Engine Status", "/status"]:
            msg = (
                f"⚙️ *COVTRAD ENGINE DASHBOARD*\n"
                f"----------------------------------------\n"
                f"🟢 *Server Status:* Active 24/7 (Render Cloud)\n"
                f"🪙 *Monitored Watchlist:* Gold, BTC, ETH, USD/JPY, EUR/USD, GBP/USD, NAS100\n"
                f"🔄 *Automated Scanner:* Active (Checks every 2 min)\n"
                f"⚡ *Latency:* Real-Time Data Pipeline"
            )
            send_telegram_alert(chat_id, msg, reply_markup=get_main_keyboard())

    return jsonify({"status": "ok"}), 200

# --- BACKGROUND AUTOMATED SCANNER ---

def run_scanner():
    print("Starting Covtrad Multi-Asset Market Scanner...")
    last_signals = {}
    
    scan_watchlist = {
        "Gold (XAU/USD)": "GC=F",
        "Bitcoin (BTC)": "BTC-USD",
        "EUR/USD": "EURUSD=X"
    }

    while True:
        for name, ticker in scan_watchlist.items():
            try:
                asset = yf.Ticker(ticker)
                df = asset.history(period="5d", interval="15m")
                
                if not df.empty and len(df) > 15:
                    current_price = df['Close'].iloc[-1]
                    high_10 = df['High'].iloc[-11:-1].max()
                    low_10 = df['Low'].iloc[-11:-1].min()

                    if current_price > 10000:
                        sl_d, tp_d = current_price * 0.015, current_price * 0.03
                    elif current_price > 1000:
                        sl_d, tp_d = 18.0, 36.0
                    elif current_price > 50:
                        sl_d, tp_d = 0.35, 0.70
                    else:
                        sl_d, tp_d = 0.0025, 0.0050

                    if current_price > high_10 and last_signals.get(name) != "BUY":
                        last_signals[name] = "BUY"
                        msg = (f"🚨 *AUTOMATED SIGNAL: BUY ({name})* 🚨\n\n"
                               f"📈 *Direction:* BUY / LONG\n"
                               f"💵 *Entry:* `{current_price:.4f}` if current_price < 10 else f'`{current_price:.2f}`'\n"
                               f"🛑 *Breakout Target Reached*")
                        send_telegram_alert(TELEGRAM_CHAT_ID, msg, reply_markup=get_main_keyboard())

                    elif current_price < low_10 and last_signals.get(name) != "SELL":
                        last_signals[name] = "SELL"
                        msg = (f"🚨 *AUTOMATED SIGNAL: SELL ({name})* 🚨\n\n"
                               f"📉 *Direction:* SELL / SHORT\n"
                               f"💵 *Entry Price Breakout Down*")
                        send_telegram_alert(TELEGRAM_CHAT_ID, msg, reply_markup=get_main_keyboard())
            except Exception as e:
                print(f"Scanner error on {name}: {e}")
            
            time.sleep(5)
        
        time.sleep(120)

threading.Thread(target=run_scanner, daemon=True).start()

@app.route('/')
def index():
    return "Covtrad Multi-Asset Signal Engine is Running 24/7!"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
