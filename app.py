Skip to content
bisratfiseha-hub
Covtrad-gold-bot
Repository navigation
Code
Issues
Pull requests
Actions
Projects
Wiki
Security and quality
1
 (1)
Insights
Settings
Covtrad-gold-bot
/
app.py
in
main

Edit

Preview
Indent mode

Spaces
Indent size

4
Line wrap mode

No wrap
Editing app.py file contents
  1
  2
  3
  4
  5
  6
  7
  8
  9
 10
 11
 12
 13
 14
 15
 16
 17
 18
 19
 20
 21
 22
 23
 24
 25
 26
 27
 28
 29
 30
 31
 32
 33
 34
 35
 36
import os
import time
import sqlite3
import threading
import requests
from flask import Flask
import telebot
from telebot.types import (
    InlineKeyboardMarkup, 
    InlineKeyboardButton, 
    ReplyKeyboardMarkup, 
    KeyboardButton
)

# --- CONFIGURATION & ENV VARIABLES ---
BOT_TOKEN = os.environ.get('BOT_TOKEN', 'YOUR_TELEGRAM_BOT_TOKEN_HERE')
TWELVE_DATA_KEY = os.environ.get('TWELVE_DATA_API_KEY', '')

DEFAULT_BALANCE = 50.0
DB_NAME = "bot_data.db"

bot = telebot.TeleBot(BOT_TOKEN)

try:
    bot.remove_webhook()
    print("Old webhook cleared successfully!")
except Exception as e:
    print(f"Webhook reset notice: {e}")

# --- ASSET SPECS FOR CENT ACCOUNTS (EXPANDED PORTFOLIO) ---
ASSET_SPECS = {
    # --- FOREX (Top 6 Volatile Pairs) ---
    "EUR/USD": {
        "name": "EUR/USD (Euro Cent)",
        "trend_sl": 0.0025,  "trend_tp": 0.0050,
        "contract_size": 1.0, "pip_factor": 10000, "unit": "pips", "decimals": 5
Use Control + Shift + m to toggle the tab key moving focus. Alternatively, use esc then tab to move to the next interactive element on the page.
