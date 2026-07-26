import os
import threading
from flask import Flask
import telebot

# --- 1. TELEGRAM BOT SETUP ---
BOT_TOKEN = os.environ.get('BOT_TOKEN', 'YOUR_TELEGRAM_BOT_TOKEN_HERE')
bot = telebot.TeleBot(BOT_TOKEN)

@bot.message_handler(commands=['start'])
def send_welcome(message):
    bot.reply_to(message, "Sniper Bot Beta is live 24/7 on Render! 🚀")

def run_bot():
    print("Telegram bot is listening...")
    bot.infinity_polling()

# --- 2. FLASK WEB SERVER (KEEP-ALIVE TRICK) ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Sniper Bot is awake and hunting!"

if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.start()
    
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
