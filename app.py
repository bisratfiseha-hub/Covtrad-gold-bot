# ==================== FLASK KEEP-ALIVE SERVER ====================
@app.route('/')
def home():
    return "SMC Professional API Trading Bot is active!"

def run_flask():
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))

if __name__ == "__main__":
    # Start Flask background server for Render keep-alive
    flask_thread = threading.Thread(target=run_flask)
    flask_thread.daemon = True
    flask_thread.start()
    
    print("🤖 Starting Telegram Bot polling loop with Professional APIs...")
    
    # 🔴 ADD THIS LINE: Clears any stuck Telegram webhooks so polling works
    bot.remove_webhook()
    
    # Start listening for messages
    bot.infinity_polling()
