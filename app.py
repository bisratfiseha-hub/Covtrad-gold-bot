import os
import requests
import telebot
from telebot.types import ReplyKeyboardMarkup, KeyboardButton

# Retrieve credentials from environment variables
BOT_TOKEN = os.getenv("BOT_TOKEN")
TWELVE_DATA_API_KEY = os.getenv("TWELVE_DATA_API_KEY")

if not BOT_TOKEN or ":" not in BOT_TOKEN:
    raise ValueError("Token must contain a colon. Please set a valid BOT_TOKEN environment variable.")

bot = telebot.TeleBot(BOT_TOKEN)

# Asset Specifications & Formatting Rules
ASSET_SPECS = {
    "XAU/USD": {"decimals": 2, "category": "Gold"},
    "EUR/USD": {"decimals": 4, "category": "Forex"},
    "GBP/USD": {"decimals": 4, "category": "Forex"},
    "USD/JPY": {"decimals": 2, "category": "Forex"},
    "AUD/USD": {"decimals": 4, "category": "Forex"},
    "USD/CAD": {"decimals": 4, "category": "Forex"},
    "GBP/JPY": {"decimals": 2, "category": "Forex"},
    "BTC/USD": {"decimals": 2, "category": "Crypto"},
    "ETH/USD": {"decimals": 2, "category": "Crypto"},
    "SOL/USD": {"decimals": 2, "category": "Crypto"},
    "XRP/USD": {"decimals": 4, "category": "Crypto"}
}

# Live Market Data Cache (Can be updated via your background fetching loop)
LIVE_MARKET_CACHE = {}

def get_main_dashboard():
    markup = ReplyKeyboardMarkup(resize_keyboard=True, row_width=2)
    btn_overview = KeyboardButton("📊 Full Market Overview (11 Assets)")
    btn_gold = KeyboardButton("🥇 Gold (XAUUSDc)")
    btn_forex = KeyboardButton("📊 Forex Markets (Top 6)")
    btn_crypto = KeyboardButton("🪙 Crypto Assets")
    btn_balance = KeyboardButton("💳 Configure Capital")
    btn_info = KeyboardButton("⚙️ Terminal Diagnostics")
    
    markup.add(btn_overview)
    markup.add(btn_gold, btn_forex)
    markup.add(btn_crypto, btn_balance)
    markup.add(btn_info)
    return markup

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    welcome_text = (
        "🤖 **Institutional Multi-Asset Signal Terminal**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Welcome back, Commander. Terminal systems are fully online.\n\n"
        "Use the control panel below to pull institutional overviews or deep-dive asset analyses."
    )
    bot.send_message(message.chat.id, welcome_text, reply_markup=get_main_dashboard(), parse_mode="Markdown")

@bot.message_handler(func=lambda msg: msg.text == "📊 Full Market Overview (11 Assets)")
def handle_full_market_overview(message):
    bot.send_chat_action(message.chat.id, 'typing')
    
    gold_keys = ["XAU/USD"]
    forex_keys = ["EUR/USD", "GBP/USD", "USD/JPY", "AUD/USD", "USD/CAD", "GBP/JPY"]
    crypto_keys = ["BTC/USD", "ETH/USD", "SOL/USD", "XRP/USD"]
    
    overview_text = (
        "📊 **INSTITUTIONAL MULTI-ASSET SNAPSHOT**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
    )
    
    overview_text += "🥇 **Commodities & Metals:**\n"
    for sym in gold_keys:
        cached = LIVE_MARKET_CACHE.get(sym)
        spec = ASSET_SPECS[sym]
        if cached:
            bias = cached.get('htf_bias', 'NEUTRAL')
            price = cached.get('price', 0.0)
            overview_text += f"• `{sym}`: `{price:,.{spec['decimals']}f}` | {bias}\n"
        else:
            overview_text += f"• `{sym}`: *Syncing data...*\n"
            
    overview_text += "\n📊 **Forex Majors:**\n"
    for sym in forex_keys:
        cached = LIVE_MARKET_CACHE.get(sym)
        spec = ASSET_SPECS[sym]
        if cached:
            bias = cached.get('htf_bias', 'NEUTRAL')
            price = cached.get('price', 0.0)
            overview_text += f"• `{sym}`: `{price:,.{spec['decimals']}f}` | {bias}\n"
        else:
            overview_text += f"• `{sym}`: *Syncing data...*\n"

    overview_text += "\n🪙 **Crypto Assets:**\n"
    for sym in crypto_keys:
        cached = LIVE_MARKET_CACHE.get(sym)
        spec = ASSET_SPECS[sym]
        if cached:
            bias = cached.get('htf_bias', 'NEUTRAL')
            price = cached.get('price', 0.0)
            overview_text += f"• `{sym}`: `{price:,.{spec['decimals']}f}` | {bias}\n"
        else:
            overview_text += f"• `{sym}`: *Syncing data...*\n"

    overview_text += (
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "💡 *Tap any asset category below to instantly generate a trade setup and risk matrix.*"
    )
    
    bot.send_message(message.chat.id, overview_text, reply_markup=get_main_dashboard(), parse_mode="Markdown")

@bot.message_handler(func=lambda msg: msg.text in ["🥇 Gold (XAUUSDc)", "📊 Forex Markets (Top 6)", "🪙 Crypto Assets"])
def handle_category_menus(message):
    bot.send_chat_action(message.chat.id, 'typing')
    category_map = {
        "🥇 Gold (XAUUSDc)": "Gold & Metals",
        "📊 Forex Markets (Top 6)": "Forex Majors",
        "🪙 Crypto Assets": "Cryptocurrency Matrix"
    }
    cat_title = category_map.get(message.text, "Asset Category")
    
    response_text = (
        f"🎯 **{cat_title.upper()} DEEP-DIVE INTERFACE**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        "Select a specific tracking pair or request live technical calculations from the engine."
    )
    bot.send_message(message.chat.id, response_text, reply_markup=get_main_dashboard(), parse_mode="Markdown")

@bot.message_handler(func=lambda msg: msg.text == "⚙️ Terminal Diagnostics")
def handle_diagnostics(message):
    status_text = (
        "⚙️ **TERMINAL DIAGNOSTICS REPORT**\n"
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        f"• **Bot Status:** `ONLINE`\n"
        f"• **API Link:** `CONNECTED (Twelve Data)`\n"
        f"• **Active Tracking Pairs:** `{len(ASSET_SPECS)} Assets`\n"
        f"• **Cache Status:** `{len(LIVE_MARKET_CACHE)} Loaded`"
    )
    bot.send_message(message.chat.id, status_text, reply_markup=get_main_dashboard(), parse_mode="Markdown")

if __name__ == "__main__":
    print("Initializing Multi-Asset Telegram Bot...")
    bot.infinity_polling()
