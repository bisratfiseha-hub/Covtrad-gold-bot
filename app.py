import os
import threading
import time
import requests
import yfinance as yf
from flask import Flask

app = Flask(__name__)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8153490508:AAG5Hjr8mjLw5QAaNLn5n4S1CpQSKJE7whs")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "8153490508")

def send_telegram_alert(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "Markdown"}
    try:
        requests.post(url, json=payload)
    except Exception as e:
        print(f"Error sending Telegram alert: {e}")

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
                    msg = (f"🚨 *COVTRAD GOLD SIGNAL (BUY)* 🚨\n\n"
                           f"📌 *Asset:* XAU/USD\n"
                           f"📈 *Direction:* BUY / LONG\n"
                           f"💵 *Entry:* ${current_price:.2f}\n"
                           f"🛑 *Stop Loss:* ${current_price - 25.0:.2f}\n"
                           f"🎯 *Take Profit:* ${current_price + 50.0:.2f}\n")
                    send_telegram_alert(msg)

                elif current_price < low_10 and last_signal != "SELL":
                    last_signal = "SELL"
                    msg = (f"🚨 *COVTRAD GOLD SIGNAL (SELL)* 🚨\n\n"
                           f"📌 *Asset:* XAU/USD\n"
                           f"📉 *Direction:* SELL / SHORT\n"
                           f"💵 *Entry:* ${current_price:.2f}\n"
                           f"🛑 *Stop Loss:* ${current_price + 25.0:.2f}\n"
                           f"🎯 *Take Profit:* ${current_price - 25.0:.2f}\n")
                    send_telegram_alert(msg)
        except Exception as e:
            print(f"Scanner error: {e}")
        
        time.sleep(120)

threading.Thread(target=run_scanner, daemon=True).start()

@app.route('/')
def index():
    return "Covtrad Gold Signal Engine is Running 24/7!"

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
