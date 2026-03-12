import telebot
from pymongo import MongoClient

# --- কনফিগারেশন ---
BOT_TOKEN = 'আপনার_বট_টোকেন_এখানে' # @BotFather থেকে পাওয়া টোকেন দিন
MONGO_URI = "mongodb+srv://Asfak1:আপনার_পাসওয়ার্ড@cluster0.ykmq2wh.mongodb.net/?retryWrites=true&w=majority"

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
        # টেলিগ্রাম এপিআই দিয়ে চেক করা হচ্ছে ইউজার চ্যানেলে আছে কি না
        status = bot.get_chat_member(channel_username, user_id).status
        
        if status in ['member', 'administrator', 'creator']:
            # ডাটাবেসে ০.০৮ টাকা যোগ করার লজিক
            users_col.update_one(
                {"telegram_id": user_id},
                {"$inc": {"task_balance": 0.08}},
                upsert=True
            )
            bot.reply_to(message, "✅ অভিনন্দন! আপনি চ্যানেলে আছেন। আপনার ব্যালেন্সে ০.০৮ টাকা যোগ হয়েছে।")
        else:
            bot.reply_to(message, "❌ আপনি এখনো চ্যানেলে জয়েন করেননি! আগে জয়েন করুন।")
            
    except Exception as e:
        bot.reply_to(message, "⚠️ ত্রুটি: নিশ্চিত করুন বটটি আপনার চ্যানেলের এডমিন।")

print("AAF Bot is running...")
bot.polling()
