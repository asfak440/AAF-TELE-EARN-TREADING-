import telebot
from pymongo import MongoClient
import os
from flask import Flask
import threading

# --- কনফিগারেশন ---
BOT_TOKEN = '7855928951:AAGjr9T_mDACh3C3rQCwZesKTjntBuXHp3Y' 
MONGO_URI = "mongodb+srv://Asfak1:Abdullah6790@cluster0.ykmq2wh.mongodb.net/?retryWrites=true&w=majority"
CHANNEL_USERNAME = "@aaf_tele_earn" 

# ডাটাবেস সেটআপ
client = MongoClient(MONGO_URI)
db = client['AAF_TeleEarn']
users_col = db['users']

bot = telebot.TeleBot(BOT_TOKEN)

# --- ১. চ্যানেল মেম্বারশিপ চেক ফাংশন ---
def is_joined(user_id):
    try:
        # এখানে অবশ্যই চ্যানেলের ইউজারনেম ঠিক থাকতে হবে
        status = bot.get_chat_member(CHANNEL_USERNAME, user_id).status
        return status in ['member', 'administrator', 'creator']
    except Exception as e:
        print(f"Membership check error: {e}")
        return False

# --- ২. টাস্ক ভেরিফিকেশন ও আর্নিং লজিক ---
@bot.message_handler(commands=['verify'])
def handle_verify(message):
    user_id = message.from_user.id
    # ডাটাবেসের সাথে মিল রাখার জন্য স্ট্রিং আইডি ব্যবহার করা ভালো
    str_id = str(user_id)
    
    if is_joined(user_id):
        try:
            # ব্যালেন্স এবং স্ট্যাটাস আপডেট
            users_col.update_one(
                {"telegram_id": str_id},
                {
                    "$set": {"status": "Active", "income_enabled": True},
                    "$inc": {"task_balance": 0.08, "main_balance": 0.08}
                },
                upsert=True
            )
            bot.send_message(user_id, "✅ অভিনন্দন! আপনার টাস্ক ভেরিফাই হয়েছে। ৳ ০.০৮ আপনার ব্যালেন্সে যোগ হয়েছে।")
        except Exception as e:
            bot.send_message(user_id, f"⚠️ ডাটাবেস এরর: {str(e)}")
    else:
        bot.send_message(user_id, f"❌ আপনি এখনও {CHANNEL_USERNAME} এ জয়েন করেননি।")

# --- ৩. স্টার্ট মেসেজ ---
@bot.message_handler(commands=['start'])
def welcome(message):
    welcome_text = (
        "👋 স্বাগতম AAF TELE-EARN-TRADING এ!\n\n"
        "💰 ইনকাম শুরু করতে /verify লিখে আপনার স্ট্যাটাস একটিভ করুন।"
    )
    bot.reply_to(message, welcome_text)

# --- Render Web Server ---
server = Flask(__name__)

@server.route("/")
def home():
    return "AAF Tele-Earn Bot is Online!"

def run_web_server():
    port = int(os.environ.get("PORT", 5000))
    server.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    print("AAF Bot is starting...")
    # পোলিং আলাদা থ্রেডে চালু করা
    threading.Thread(target=lambda: bot.infinity_polling(none_stop=True, timeout=60)).start()
    # ওয়েব সার্ভার চালু করা
    run_web_server()
