import os
import threading
import requests
from flask import Flask
import telebot

# --- CONFIGURATION & ENV VARIABLES ---
BOT_TOKEN = os.environ.get('BOT_TOKEN', 'YOUR_TELEGRAM_BOT_TOKEN_HERE')
TWELVE_DATA_KEY = os.environ.get('TWELVE_DATA_API_KEY', '')

# In-memory balance store (Defaults to $1,000 if user hasn't set one)
DEFAULT_BALANCE = 1000.0
DEFAULT_RISK_PCT = 1.0  # 1% standard risk on trend setups
USER_BALANCES = {}

bot = telebot.TeleBot(BOT_TOKEN)

try:
    bot.remove_webhook()
    print("Old webhook cleared successfully!")
except Exception as e:
    print(f"Webhook reset notice: {e}")

# --- TECHNICAL ANALYSIS FETCHERS ---

def fetch_tf_data(symbol, interval):
    """Fetches RSI, SMA20, and SMA50 for a specific timeframe"""
    if not TWELVE_DATA_KEY:
        return None
    try:
        rsi_url = f"https://api.twelvedata.com/rsi?symbol={symbol}&interval={interval}&time_period=14&apikey={TWELVE_DATA_KEY}"
        rsi = float(requests.get(rsi_url, timeout=5).json()['values'][0]['rsi'])

        sma20_url = f"https://api.twelvedata.com/sma?symbol={symbol}&interval={interval}&time_period=20&apikey={TWELVE_DATA_KEY}"
        sma20 = float(requests.get(sma20_url, timeout=5).json()['values'][0]['sma'])

        sma50_url = f"https://api.twelvedata.com/sma?symbol={symbol}&interval={interval}&time_period=50&apikey={TWELVE_DATA_KEY}"
        sma50 = float(requests.get(sma50_url, timeout=5).json()['values'][0]['sma'])

        return {"rsi": rsi, "sma20": sma20, "sma50": sma50}
    except Exception as e:
        print(f"Error fetching {interval} for {symbol}: {e}")
        return None

def fetch_gold_analysis():
    """Performs Multi-Timeframe Analysis on Gold (4H Macro + 15M Setup)"""
    if not TWELVE_DATA_KEY:
        return None
    try:
        price_url = f"https://api.twelvedata.com/price?symbol=XAU/USD&apikey={TWELVE_DATA_KEY}"
        price = float(requests.get(price_url, timeout=5).json()['price'])

        htf_data = fetch_tf_data("XAU/USD", "4h")
        ltf_data = fetch_tf_data("XAU/USD", "15min")

        if not htf_data or not ltf_data:
            return None

        return {
            "price": price,
            "htf": htf_data,
            "ltf": ltf_data
        }
    except Exception as e:
        print(f"Gold MTF Error: {e}")
        return None

def generate_gold_signal(active_balance):
    data = fetch_gold_analysis()
    if not data:
        return "⚠️ Unable to calculate Gold signal right now."

    price = data['price']
    htf = data['htf']
    ltf = data['ltf']

    htf_bias = "BULLISH 🟢" if htf['sma20'] > htf['sma50'] else "BEARISH 🔴"
    
    ltf_bullish = ltf['sma20'] > ltf['sma50'] and ltf['rsi'] > 50
    ltf_bearish = ltf['sma20'] < ltf['sma50'] and ltf['rsi'] < 50

    # Multi-Timeframe Logic & Risk Rules
    if "BULLISH" in htf_bias and ltf_bullish:
        trade_type = "TREND CONTINUATION 🚀"
        signal = "BUY / LONG 🟢"
        risk_pct = DEFAULT_RISK_PCT  # 1.0% Full Risk
        sl_dist = 3.50               # 350 pips SL ($3.50 move)
        tp_dist = 7.00               # 700 pips TP ($7.00 move)
        note = "4H & 15M aligned! Standard trend setup."

    elif "BEARISH" in htf_bias and ltf_bullish:
        trade_type = "COUNTER-TREND SCALP ⚡"
        signal = "BUY / LONG (SCALP) 🟡"
        risk_pct = DEFAULT_RISK_PCT * 0.5  # 0.5% Reduced Risk
        sl_dist = 2.00                    # 200 pips SL ($2.00 move)
        tp_dist = 3.00                    # 300 pips TP ($3.00 move)
        note = "⚠️ Counter 4H Trend! Reduced risk recommended for a quick scalp."

    elif "BEARISH" in htf_bias and ltf_bearish:
        trade_type = "TREND CONTINUATION 🚀"
        signal = "SELL / SHORT 🔴"
        risk_pct = DEFAULT_RISK_PCT  # 1.0% Full Risk
        sl_dist = 3.50               # 350 pips SL
        tp_dist = 7.00               # 700 pips TP
        note = "4H & 15M aligned! Standard trend setup."

    elif "BULLISH" in htf_bias and ltf_bearish:
        trade_type = "COUNTER-TREND SCALP ⚡"
        signal = "SELL / SHORT (SCALP) 🟡"
        risk_pct = DEFAULT_RISK_PCT * 0.5  # 0.5% Reduced Risk
        sl_dist = 2.00                    # 200 pips SL
        tp_dist = 3.00                    # 300 pips TP
        note = "⚠️ Counter 4H Trend! Reduced risk recommended for a quick scalp."

    else:
        return (
            f"📊 **Gold (XAU/USD) Market Context**\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"💵 **Live Price:** ${price:,.2f}\n"
            f"🏛 **4H Macro Trend:** {htf_bias}\n"
            f"📊 **15M RSI:** {ltf['rsi']:.1f}\n\n"
            f"💡 **Signal:** SIDEWAYS / WAIT FOR BREAKOUT ⏳"
        )

    # Calculate Entry, SL, and TP
    if "BUY" in signal:
        sl_price = price - sl_dist
        tp_price = price + tp_dist
    else:
        sl_price = price + sl_dist
        tp_price = price - tp_dist

    # Active Account Risk Math
    risk_dollars = active_balance * (risk_pct / 100.0)
    reward_dollars = risk_dollars * (tp_dist / sl_dist)
    
    # Gold Lot Size Math (1 Standard Lot = $100 per $1 move)
    lot_size = risk_dollars / (sl_dist * 100.0)

    # Reference Lot Scaling per $1,000 Equity
    ref_risk_dollars = 1000.0 * (risk_pct / 100.0)
    ref_lot_size = ref_risk_dollars / (sl_dist * 100.0)

    card = (
        f"🎯 **GOLD (XAU/USD) INTELLIGENT SIGNAL**\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"💵 **Live Price:** ${price:,.2f}\n"
        f"🏛 **4H Macro Trend:** {htf_bias}\n"
        f"🏷 **Trade Type:** {trade_type}\n\n"
        f"💡 **Signal:** {signal}\n"
        f"• **Entry:** ${price:,.2f}\n"
        f"• **Stop Loss (SL):** ${sl_price:,.2f} ({int(sl_dist*100)} pips)\n"
        f"• **Take Profit (TP):** ${tp_price:,.2f} ({int(tp_dist*100)} pips)\n\n"
        f"⚖️ **POSITION SIZING (${active_balance:,.0f} Account)**\n"
        f"• **Recommended Lot Size:** `{lot_size:.2f} Lots`\n"
        f"• **Max Risk:** -${risk_dollars:,.2f} ({risk_pct:.1f}%)\n"
        f"• **Target Reward:** +${reward_dollars:,.2f}\n\n"
        f"📏 **QUICK SCALING REFERENCE:**\n"
        f"• `Use {ref_lot_size:.2f} Lots per $1,000 Equity`\n\n"
        f"📝 **Bot Context:** {note}"
    )
    return card

# --- TELEGRAM COMMAND HANDLERS ---

@bot.message_handler(commands=['start', 'help'])
def send_welcome(message):
    msg = (
        "🎯 **Sniper Trading Assistant Active!** 24/7 Cloud Engine\n\n"
        "**Commands:**\n"
        "• `/gold` - Gold Signal (uses your saved balance)\n"
        "• `/gold 5200` - Gold Signal for a specific $5,200 balance\n"
        "• `/setbalance 5000` - Update your saved account balance"
    )
    bot.reply_to(message, msg, parse_mode="Markdown")

@bot.message_handler(commands=['setbalance'])
def set_balance_command(message):
    try:
        args = message.text.split()
        if len(args) < 2:
            bot.reply_to(message, "⚠️ Usage: `/setbalance 5000` (Enter your balance amount).", parse_mode="Markdown")
            return
        
        new_balance = float(args[1])
        USER_BALANCES[message.chat.id] = new_balance
        bot.reply_to(message, f"✅ Saved! Your default account balance is now set to **${new_balance:,.2f}**.", parse_mode="Markdown")
    except ValueError:
        bot.reply_to(message, "⚠️ Please enter a valid number, e.g., `/setbalance 5000`.", parse_mode="Markdown")

@bot.message_handler(commands=['gold', 'GOLD'])
def gold_command(message):
    bot.send_chat_action(message.chat.id, 'typing')
    
    # Check if user provided an on-the-fly balance argument (e.g., /gold 4500)
    args = message.text.split()
    if len(args) > 1:
        try:
            active_balance = float(args[1])
        except ValueError:
            active_balance = USER_BALANCES.get(message.chat.id, DEFAULT_BALANCE)
    else:
        active_balance = USER_BALANCES.get(message.chat.id, DEFAULT_BALANCE)

    card = generate_gold_signal(active_balance)
    bot.reply_to(message, card, parse_mode="Markdown")

def run_bot():
    print("Telegram bot is listening...")
    bot.infinity_polling()

# --- FLASK KEEP-ALIVE SERVER ---
app = Flask(__name__)

@app.route('/')
def home():
    return "Sniper Bot Engine is awake and hunting!"

if __name__ == "__main__":
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.start()
    
    port = int(os.environ.get('PORT', 10000))
    app.run(host='0.0.0.0', port=port)
