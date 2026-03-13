import telebot
from pymongo import MongoClient
import os
from flask import Flask
import threading

# --- কনফিগারেশন ---
BOT_TOKEN = '7855928951:AAGjr9T_mDACh3C3rQCwZesKTjntBuXHp3Y' 
MONGO_URI = "mongodb+srv://Asfak1:Abdullah6790@cluster0.ykmq2wh.mongodb.net/?retryWrites=true&w=majority"

client = MongoClient(MONGO_URI)
db = client['AAF_TeleEarn']
users_col = db['users']

bot = telebot.TeleBot(BOT_TOKEN)

# --- টাস্ক ভেরিফিকেশন ও স্ট্যাটাস চেক ---
@bot.message_handler(commands=['verify'])
def verify_task(message):
    user_id = message.from_user.id
    channel_username = "@aaf_tele_earn" 
    
    try:
        # টেলিগ্রাম থেকে চেক করা হচ্ছে ইউজার চ্যানেলে আছে কি না
        status = bot.get_chat_member(channel_username, user_id).status
        
        if status in ['member', 'administrator', 'creator']:
            # ইনকাম চালু (Active) এবং ব্যালেন্স যোগ করা
            users_col.update_one(
                {"telegram_id": user_id},
                {
                    "$set": {"status": "Active"}, 
                    "$inc": {"task_balance": 0.08}
                },
                upsert=True
            )
            bot.reply_to(message, "✅ অভিনন্দন! আপনি Active। আপনার ইনকাম চালু হয়েছে এবং ০.০৮ টাকা যোগ হয়েছে।")
        else:
            # ইনকাম বন্ধ (Inactive)
            users_col.update_one(
                {"telegram_id": user_id}, 
                {"$set": {"status": "Inactive"}}
            )
            bot.reply_to(message, "❌ আগে চ্যানেলে জয়েন করুন! নাহলে আপনার ইনকাম বন্ধ (Inactive) থাকবে।")
            
    except Exception as e:
        bot.reply_to(message, "⚠️ ত্রুটি: নিশ্চিত করুন বটটি আপনার চ্যানেলের এডমিন।")

# --- Render Web Server (বটকে ২৪ ঘণ্টা সচল রাখার জন্য) ---
server = Flask(__name__)

@server.route("/")
def home():
    return "AAF Bot is Running!"

def run_web_server():
    port = int(os.environ.get("PORT", 5000))
    server.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    print("AAF Bot is starting...")
    # বটের পোলিং আলাদা থ্রেডে চালানো
    threading.Thread(target=lambda: bot.infinity_polling(timeout=10, long_polling_timeout=5), daemon=True).start()
    
    # মেইন থ্রেডে ওয়েব সার্ভার চালানো
    run_web_server()
