import telebot
from pymongo import MongoClient
import os
from flask import Flask
import threading
from telethon import TelegramClient, functions # সেশন চেক করার জন্য লাগবে

# --- কনফিগারেশন ---
BOT_TOKEN = '7855928951:AAGjr9T_mDACh3C3rQCwZesKTjntBuXHp3Y' 
MONGO_URI = "mongodb+srv://Asfak1:Abdullah6790@cluster0.ykmq2wh.mongodb.net/?retryWrites=true&w=majority"
CHANNEL_USERNAME = "@aaf_tele_earn" # আপনার চ্যানেলের ইউজারনেম

# ডাটাবেস সেটআপ
client = MongoClient(MONGO_URI)
db = client['AAF_TeleEarn']
users_col = db['users']

bot = telebot.TeleBot(BOT_TOKEN)

# --- ১. চ্যানেল মেম্বারশিপ চেক ফাংশন ---
def is_joined(user_id):
    try:
        status = bot.get_chat_member(CHANNEL_USERNAME, user_id).status
        return status in ['member', 'administrator', 'creator']
    except Exception:
        return False

# --- ২. টাস্ক ভেরিফিকেশন ও আর্নিং লজিক ---
@bot.message_handler(commands=['verify'])
def handle_verify(message):
    user_id = message.from_user.id
    
    if is_joined(user_id):
        # আপনার মডেল অনুযায়ী: একটিভ হলে ইনকাম শুরু এবং ব্যালেন্স যোগ
        users_col.update_one(
            {"telegram_id": user_id},
            {
                "$set": {"status": "Active", "income_enabled": True},
                "$inc": {"task_balance": 0.08, "main_balance": 0.08}
            },
            upsert=True
        )
        bot.send_message(user_id, "✅ অভিনন্দন! আপনার টাস্ক ভেরিফাই হয়েছে। ৳ ০.০৮ আপনার ব্যালেন্সে যোগ হয়েছে এবং ইনকাম Active হয়েছে।")
    else:
        # মডেল অনুযায়ী: লিভ করলে বা জয়েন না করলে ইনকাম বন্ধ
        users_col.update_one(
            {"telegram_id": user_id},
            {"$set": {"status": "Inactive", "income_enabled": False}}
        )
        bot.send_message(user_id, f"❌ আপনি এখনও {CHANNEL_USERNAME} এ জয়েন করেননি। জয়েন না করলে আপনার ইনকাম বন্ধ থাকবে।")

# --- ৩. সেশন এনক্রিপশন লজিক (অ্যাকাউন্ট অ্যাড করার জন্য) ---
# এই পার্টটি আপনার অ্যাপের All-Account পেজে ডাটা পাঠাবে
@bot.message_handler(commands=['start'])
def welcome(message):
    welcome_text = (
        "👋 স্বাগতম AAF TELE-EARN-TRADING এ!\n\n"
        "💰 ইনকাম শুরু করতে নিচের ধাপে কাজ করুন:\n"
        "১. আমাদের চ্যানেলে জয়েন করুন।\n"
        "২. /verify লিখে আপনার স্ট্যাটাস একটিভ করুন।\n"
        "৩. অ্যাপ থেকে মাল্টি-অ্যাকাউন্ট অ্যাড করে আয় বাড়ান।"
    )
    bot.send_message(message.chat.id, welcome_text)

# --- Render Web Server (বটকে ২৪ ঘণ্টা সচল রাখার জন্য) ---
server = Flask(__name__)

@server.route("/")
def home():
    return "AAF Tele-Earn Bot is Online!"

def run_web_server():
    port = int(os.environ.get("PORT", 5000))
    server.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    print("AAF Bot is starting...")
    # পোলিং চালু করা
    threading.Thread(target=lambda: bot.infinity_polling(timeout=20), daemon=True).start()
    # ওয়েব সার্ভার চালু করা
    run_web_server()
