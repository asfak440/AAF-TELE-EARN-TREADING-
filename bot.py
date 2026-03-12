import telebot
from pymongo import MongoClient
import os
from flask import Flask
import threading

# --- কনফিগারেশন ---
BOT_TOKEN = 'YOUR_BOT_TOKEN_HERE'  # @BotFather থেকে পাওয়া টোকেন দিন
MONGO_URI = "mongodb+srv://Asfak1:YOUR_PASSWORD@cluster0.ykmq2wh.mongodb.net/?retryWrites=true&w=majority"

client = MongoClient(MONGO_URI)
db = client['AAF_TeleEarn']
users_col = db['users']

bot = telebot.TeleBot(BOT_TOKEN)

# --- টাস্ক ভেরিফিকেশন কমান্ড ---
@bot.message_handler(commands=['verify'])
def verify_task(message):
    user_id = message.from_user.id
    channel_username = "@aaf_tele_earn" # আপনার চ্যানেল ইউজারনেম
    
    try:
        status = bot.get_chat_member(channel_username, user_id).status
        
        if status in ['member', 'administrator', 'creator']:
            users_col.update_one(
                {"telegram_id": user_id},
                {"$inc": {"task_balance": 0.08}},
                upsert=True
            )
            bot.reply_to(message, "✅ অভিনন্দন! আপনি চ্যানেলে আছেন। আপনার ব্যালেন্সে ০.০৮ টাকা যোগ হয়েছে।")
        else:
            bot.reply_to(message, "❌ আপনি এখনো চ্যানেলে জয়েন করেননি! আগে জয়েন করুন।")
            
    except Exception as e:
        bot.reply_to(message, "⚠️ ত্রুটি: নিশ্চিত করুন বটটি আপনার চ্যানেলের এডমিন।")

# --- Render-এর জন্য Flask Web Server ---
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
    threading.Thread(target=bot.infinity_polling, daemon=True).start()
    
    # মেইন থ্রেডে ওয়েব সার্ভার চালানো (Render এর জন্য জরুরি)
    run_web_server()
