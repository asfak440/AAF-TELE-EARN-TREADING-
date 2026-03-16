import os
import base64
import asyncio
import requests
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from flask_pymongo import PyMongo
from datetime import datetime, timedelta
from telethon import TelegramClient, functions
from telethon.sessions import StringSession
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

app = Flask(__name__)
CORS(app)

# --- ১. কনফিগারেশন ---
API_ID = 36466824      
API_HASH = '535ddcb85f2c3c74cc0ff532dd2c3406'  
SECRET_KEY = b'AAF_STRONG_APP_SECURE_32_BIT_KEY' # এনক্রিপশন কি

# ডাটাবেস কানেকশন (Mongo_URI অটোমেটিক এনভায়রনমেন্ট থেকে নিবে)
app.config["MONGO_URI"] = os.environ.get("MONGO_URI", "mongodb+srv://abdullahasfakfarvezbd_db_user:Abdullah6790@cluster0.rmulyqq.mongodb.net/AAF_TeleEarn?appName=Cluster0")
mongo = PyMongo(app)

# --- ২. এনক্রিপশন লজিক (AES CBC) ---
def encrypt_session(session_str):
    cipher = AES.new(SECRET_KEY, AES.MODE_CBC)
    ct_bytes = cipher.encrypt(pad(session_str.encode(), AES.block_size))
    iv = base64.b64encode(cipher.iv).decode('utf-8')
    ct = base64.b64encode(ct_bytes).decode('utf-8')
    return f"{iv}:{ct}"

def decrypt_session(encrypted_str):
    try:
        iv_b64, ct_b64 = encrypted_str.split(':')
        iv = base64.b64decode(iv_b64)
        ct = base64.b64decode(ct_b64)
        cipher = AES.new(SECRET_KEY, AES.MODE_CBC, iv)
        return unpad(cipher.decrypt(ct), AES.block_size).decode('utf-8')
    except:
        return encrypted_str # যদি এনক্রিপ্টেড না থাকে

# --- ৩. ইউজার এবং সেশন লজিক ---

@app.route('/api/add_account', methods=['POST'])
def add_account():
    data = request.json
    uid = data.get('telegram_id')
    raw_session = data.get('session_string') 
    phone = data.get('phone')
    
    encrypted = encrypt_session(raw_session)
    mongo.db.sessions.update_one(
        {"phone": phone},
        {"$set": {"telegram_id": int(uid), "session": encrypted, "status": "Active"}},
        upsert=True
    )
    mongo.db.users.update_one({"telegram_id": int(uid)}, {"$inc": {"added_accounts": 1}})
    return jsonify({"status": "success"})

@app.route('/api/user_data/<telegram_id>', methods=['GET'])
def get_user_data(telegram_id):
    user = mongo.db.users.find_one({"telegram_id": int(telegram_id)}, {'_id': 0})
    if user:
        return jsonify({"status": "success", **user})
    return jsonify({"status": "error", "message": "User not found"})

# --- ৪. টাস্ক এবং ইনকাম লজিক (৮ পয়সা ও ১ টাকা বোনাস) ---

@app.route('/api/get_admin_tasks', methods=['GET'])
def get_user_tasks():
    tasks = list(mongo.db.tasks.find({}, {'_id': 0}))
    return jsonify(tasks)

@app.route('/api/add_reward', methods=['POST'])
def add_reward():
    data = request.json
    uid = data.get('user_id')
    amount = float(data.get('amount', 0.08))
    mongo.db.users.update_one({"telegram_id": int(uid)}, {"$inc": {"task_balance": amount}})
    return jsonify({"status": "success"})

@app.route('/api/claim_daily_bonus', methods=['POST'])
def claim_daily():
    uid = request.json['user_id']
    user = mongo.db.users.find_one({"telegram_id": int(uid)})
    now = datetime.now()
    last = user.get('last_bonus_time')
    if last and now < last + timedelta(hours=24):
        return jsonify({"status": "error", "message": "Wait 24h!"})
    mongo.db.users.update_one({"telegram_id": int(uid)}, {"$inc": {"task_balance": 1.0}, "$set": {"last_bonus_time": now}})
    return jsonify({"status": "success"})

# --- ৫. অ্যাডমিন মাস্টার কন্ট্রোল (ভিজ্যুয়াল টেবিল কন্ট্রোল) ---

@app.route('/admin/get_all_users', methods=['GET'])
def get_all_users():
    users = list(mongo.db.users.find({}, {'_id': 0}))
    return jsonify(users)

@app.route('/admin/add_task', methods=['POST'])
def admin_add_task():
    task_data = request.json
    mongo.db.tasks.insert_one(task_data)
    return jsonify({"status": "success"})

@app.route('/admin/update_user', methods=['POST'])
def admin_update_user():
    data = request.json
    mongo.db.users.update_one(
        {"telegram_id": int(data['user_id'])},
        {"$set": {"task_balance": float(data['balance']), "status": data['status']}}
    )
    return jsonify({"status": "success"})

# --- ৬. অ্যাডমিন Force Join (টেলিগ্রাম কন্ট্রোল) ---
async def perform_join(channel_to_join):
    all_sessions = mongo.db.sessions.find({"status": "Active"})
    count = 0
    for sess in all_sessions:
        try:
            string_session = decrypt_session(sess['session'])
            async with TelegramClient(StringSession(string_session), API_ID, API_HASH) as client:
                await client(functions.channels.JoinChannelRequest(channel=channel_to_join))
                count += 1
        except: pass
    return count

@app.route('/api/admin/force_join', methods=['POST'])
def force_join_trigger():
    data = request.json
    channel = data.get('channel', '@aaf_tele_earn')
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    count = loop.run_until_complete(perform_join(channel))
    return jsonify({"status": "success", "joined": count})

# --- ৭. এক্সট্রা এবং রেন্ডারিং ---
@app.route('/api/sol_price', methods=['GET'])
def sol_price():
    r = requests.get("https://api.binance.com/api/v3/ticker/price?symbol=SOLUSDT")
    return jsonify(r.json())

@app.route('/')
def dashboard(): return render_template('index.html')

@app.route('/tasks')
def task_page(): return render_template('task.html')

@app.route('/aaf-admin-master')
def admin_panel(): return render_template('admin.html')

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
