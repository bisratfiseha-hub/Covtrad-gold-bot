def run_scanner():
    print("Starting Covtrad Gold Market Scanner...")
    # Send test message on boot up
    send_telegram_alert("✅ *Covtrad Gold Scanner Started & Active!*")
    
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
