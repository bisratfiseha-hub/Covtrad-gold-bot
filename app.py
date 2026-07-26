import os
import threading
import requests
from flask import Flask
import telebot

# --- CONFIGURATION & ENV VARIABLES ---
BOT_TOKEN = os.environ.get('BOT_TOKEN', 'YOUR_TELEGRAM_BOT_TOKEN_HERE')
TWELVE_DATA_KEY = os.environ.get('TWELVE_DATA_API_KEY', '')

bot = telebot.TeleBot(BOT_TOKEN)

# Clear old webhooks
try:
    bot.remove_webhook()
    print("Old webhook cleared successfully!")
except Exception as e:
    print(f"Webhook reset notice: {e}")

# --- ZERO-LAG DATA FETCHERS ---

def get_binance_price(symbol="BTCUSDT"):
    """Fetches real-time crypto prices from Binance (Zero lag, no key required)"""
    try:
        url = f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}"
        res = requests.get(url, timeout=5).json()
        return float(res['price'])
    except Exception as e:
        print(f"Binance API Error: {e}")
        return None

def get_gold_price():
    """Fetches real-time Gold (XAU/USD) price from Twelve Data"""
    if not TWELVE_DATA_KEY:
        return "API Key Missing"
    try:
        url = f"https://api.twelvedata.com/price?symbol=XAU/USD&apikey={TWELVE_DATA_KEY}"
        res = requests.get(url, timeout=5).json()
        return float(res['price'])
    except Exception as e:
        print(f"Twelve Data Error: {e}")
        return None

# --- TELEGRAM COMMAND HANDLERS ---

@bot.message_handler(commands=['start'])
def send_welcome(message):
    msg = (
        "Sniper Bot 24/7 Engine is active! 🚀\n\n"
        "Commands:\n"
        "/btc - Get real-time Bitcoin price\n"
        "/gold - Get real-time Gold (XAU/USD) price"
    )
    bot.reply_to(message, msg)

@bot.message_handler(commands=['btc'])
def btc_command(message):
    price = get_binance_price("BTCUSDT")
    if price:
        bot.reply_to(message, f"⚡ **BTC/USDT Live Price:** ${price:,.2f}")
    else:
        bot.reply_to(message, "⚠️ Failed to fetch BTC price.")

@bot.message_handler(commands=['gold'])
def gold_command(message):
    price = get_gold_price()
    if isinstance(price, float):
        bot.reply_to(message, f"👑 **Gold (XAU/USD) Live Price:** ${price:,.2f}")
    elif price == "API Key Missing":
        bot.reply_to(message, "⚠️ TWELVE_DATA_API_KEY environment variable is missing on Render.")
    else:
        bot.reply_to(message, "⚠️ Failed to fetch Gold price.")

def run_bot():
    print("Telegram bot is listening...")
    bot.infinity_polling()

# --- FLASK KEEP-ALIVE SERVER ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Sniper Bot is awake and hunting!"

if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.start()
    
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
