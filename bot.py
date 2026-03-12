import telebot
from pymongo import MongoClient
import os
from flask import Flask
import threading

# --- কনফিগারেশন ---
BOT_TOKEN = '7855928951:AAGjr9T_mDACh3C3rQCwZesKTjntBuXHp3Y' 
# নিচের লাইনে 'YOUR_PASSWORD' এর জায়গায় আপনার আসল পাসওয়ার্ডটি দিন
MONGO_URI = "mongodb+srv://Asfak1:Abdullah6790@cluster0.ykmq2wh.mongodb.net/?retryWrites=true&w=majority"

client = MongoClient(MONGO_URI)
db = client['AAF_TeleEarn']
users_col = db['users']

bot = telebot.TeleBot(BOT_TOKEN)

# --- টাস্ক ভেরিফিকেশন কমান্ড ---
@bot.message_handler(commands=['verify'])
def verify_task(message):
    user_id = message.from_user.id
    channel_username = "@aaf_tele_earn" 
    
    try:
        status = bot.get_chat_member(channel_username, user_id).status
        if status in ['member', 'administrator', 'creator']:
            users_col.update_one(
                {"telegram_id": user_id},
                {"$inc": {"task_balance": 0.08}},
                upsert=True
            )
            bot.reply_to(message, "✅ অভিনন্দন! আপনি চ্যানেলে আছেন। ০.০৮ টাকা যোগ হয়েছে।")
        else:
            bot.reply_to(message, "❌ আগে চ্যানেলে জয়েন করুন!")
    except Exception as e:
        bot.reply_to(message, "⚠️ বটকে চ্যানেলের এডমিন করুন।")

# --- Render Web Server ---
server = Flask(__name__)
@server.route("/")
def home(): return "AAF Bot is Running!"

def run_web_server():
    port = int(os.environ.get("PORT", 5000))
    server.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    threading.Thread(target=bot.infinity_polling, daemon=True).start()
    run_web_server()
