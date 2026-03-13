import telebot
from pymongo import MongoClient
import os
from flask import Flask
import threading

# --- কনফিগারেশন ---
# আপনার দেওয়া সঠিক তথ্যগুলো এখানে বসানো হয়েছে
BOT_TOKEN = '7855928951:AAGjr9T_mDACh3C3rQCwZesKTjntBuXHp3Y' 
MONGO_URI = "mongodb+srv://abdullahasfakfarvezbd_db_user:Abdullah6790@cluster0.rmulyqq.mongodb.net/?appName=Cluster0"
CHANNEL_USERNAME = "@aaf_tele_earn" 

# ভবিষ্যতে প্রয়োজন হলে ব্যবহার করার জন্য (telebot এ এটি বাধ্যতামূলক নয়)
API_ID = 36466824
API_HASH = '535ddcb85f2c3c74cc0ff532dd2c3406'

# --- ডাটাবেস সেটআপ ---
try:
    client = MongoClient(MONGO_URI)
    db = client['AAF_TeleEarn']
    users_col = db['users']
    # কানেকশন চেক
    client.admin.command('ping')
    print("✅ MongoDB Connected Successfully!")
except Exception as e:
    print(f"❌ MongoDB Connection Error: {e}")

bot = telebot.TeleBot(BOT_TOKEN)

# --- ১. চ্যানেল মেম্বারশিপ চেক ফাংশন ---
def is_joined(user_id):
    try:
        status = bot.get_chat_member(CHANNEL_USERNAME, user_id).status
        return status in ['member', 'administrator', 'creator']
    except Exception as e:
        print(f"Membership check error: {e}")
        return False

# --- ২. টাস্ক ভেরিফিকেশন ও আর্নিং লজিক ---
@bot.message_handler(commands=['verify'])
def handle_verify(message):
    user_id = message.from_user.id
    str_id = str(user_id)
    
    if is_joined(user_id):
        try:
            # ব্যালেন্স এবং স্ট্যাটাস আপডেট
            users_col.update_one(
                {"telegram_id": str_id},
                {
                    "$set": {
                        "username": message.from_user.username,
                        "status": "Active", 
                        "income_enabled": True
                    },
                    "$inc": {"task_balance": 0.08, "main_balance": 0.08}
                },
                upsert=True
            )
            bot.send_message(user_id, "✅ অভিনন্দন! আপনার টাস্ক ভেরিফাই হয়েছে।\n💰 ৳ ০.০৮ আপনার ব্যালেন্সে যোগ হয়েছে।")
        except Exception as e:
            bot.send_message(user_id, f"⚠️ ডাটাবেস এরর: কিছু সময় পর চেষ্টা করুন।")
            print(f"Database update error: {e}")
    else:
        bot.send_message(user_id, f"❌ আপনি এখনও আমাদের চ্যানেলে জয়েন করেননি।\n\nঅনুগ্রহ করে আগে এখানে জয়েন করুন: {CHANNEL_USERNAME}\nতারপর আবার /verify কমান্ড দিন।")

# --- ৩. স্টার্ট মেসেজ ---
@bot.message_handler(commands=['start'])
def welcome(message):
    welcome_text = (
        f"👋 স্বাগতম {message.from_user.first_name}!\n\n"
        "এটি AAF TELE-EARN-TRADING এর অফিসিয়াল বট।\n\n"
        "💰 ইনকাম শুরু করতে নিচের ধাপগুলো অনুসরণ করুন:\n"
        f"১. আমাদের চ্যানেলে জয়েন করুন: {CHANNEL_USERNAME}\n"
        "২. /verify লিখে আপনার অ্যাকাউন্ট একটিভ করুন।"
    )
    bot.reply_to(message, welcome_text)

# --- Render Web Server (Keep Alive) ---
server = Flask(__name__)

@server.route("/")
def home():
    return "AAF Tele-Earn Bot is Online!"

def run_web_server():
    # Render এর জন্য পোর্ট সেটআপ
    port = int(os.environ.get("PORT", 5000))
    server.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    print("🚀 AAF Bot is starting...")
    # পোলিং আলাদা থ্রেডে চালু করা
    threading.Thread(target=lambda: bot.infinity_polling(none_stop=True, timeout=60)).start()
    # ওয়েব সার্ভার চালু করা (এটি মেইন থ্রেডে থাকবে)
    run_web_server()
