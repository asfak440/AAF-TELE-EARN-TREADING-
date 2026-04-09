import os
import asyncio
import requests
import time
import random
from datetime import datetime, timedelta
from functools import wraps
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_cors import CORS
from pymongo import MongoClient
from telethon.sync import TelegramClient
from telethon.sessions import StringSession
from bson import ObjectId
import firebase_admin
from firebase_admin import credentials, db

# ---------------------------------------------------------
# ১. কনফিগারেশন ও ডাটাবেস সেটআপ
# ---------------------------------------------------------
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "aaf_strong_secure_786")
CORS(app)

# API & DB Credentials
API_ID = 36466824
API_HASH = "535ddcb85f2c3c74cc0ff532dd2c3406"
MONGO_URI = "mongodb+srv://abdullahasfakfarvezbd_db_user:Abdullah6790@cluster0.rmulyqq.mongodb.net/?retryWrites=true&w=majority"

# Firebase Setup (Update with your databaseURL)
if not firebase_admin._apps:
    cred = credentials.Certificate("firebase-adminsdk.json") # আপনার ফায়ারবেস জেসন ফাইলটি আপলোড করুন
    firebase_admin.initialize_app(cred, {
        'databaseURL': 'https://teleearnbd-781d6-default-rtdb.firebaseio.com'
    })

# MongoDB কানেকশন
client_db = MongoClient(MONGO_URI)
mdb = client_db['aaf_tele_earn_db']
users_col = mdb['users']
tasks_col = mdb['tasks']
settings_col = mdb['settings']

# ---------------------------------------------------------
# ২. হেল্পার ফাংশন ও ডেকোরেটর
# ---------------------------------------------------------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'uid' not in session:
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

def get_admin_settings():
    """ফায়ারবেস থেকে লাইভ সেটিংস নিয়ে আসে"""
    return db.reference('admin_settings').get() or {}


# ---------------------------------------------------------
# ৩. ইউজার ডাটা ও ড্যাশবোর্ড API
# ---------------------------------------------------------
@app.route('/api/user/data')
@login_required
def get_user_data():
    uid = session.get('uid')
    user = users_col.find_one({"telegram_id": uid})
    admin_data = get_admin_settings() # ডাটাবেস থেকে অ্যাডমিন সেটিংস আনছে

    if not user:
        return jsonify({"error": "User not found"}), 404

    # ইউজার চ্যানেলে আছে কি না চেক করার লজিক (উদাহরণ)
    is_joined = check_membership(uid, admin_data.get('channel_id')) 

    return jsonify({
        "user": {
            "name": user.get("name", "User"),
            "cash": f"{user.get('main_balance', 0.0):.2f}",
            "aaf": f"{user.get('aaf_balance', 0):.0f}",
            "is_joined": is_joined # এটি True হলে ড্যাশবোর্ড ONLINE দেখাবে
        },
        "admin": {
            "channel_url": admin_data.get('channel_link', '#')
        }
    })
# ---------------------------------------------------------
# ৪. টাস্ক সিস্টেম (Task Engine)
# ---------------------------------------------------------
# এই অংশটুকু আপনার app.py এর টাস্ক ক্লেইম সেকশনে বসান
@app.route('/api/user/tasks/claim', methods=['POST'])
@login_required
def claim_task():
    uid = session.get('uid')
    task_id = request.json.get('task_id')
    user_ip = request.headers.get('X-Forwarded-For', request.remote_addr)

    # ফায়ারবেস থেকে আইপি সিকিউরিটি সেটিংস চেক
    admin_data = db.reference('admin_settings').get() or {}
    ip_security_on = admin_data.get('ip_security', True) 

    task = tasks_col.find_one({"id": task_id})
    user = users_col.find_one({"telegram_id": uid})

    if not task or not user:
        return jsonify({"success": False, "message": "Invalid Task/User"})

    # চেক ১: একই আইডি দিয়ে আগে করেছে কি না
    if task_id in user.get("completed_tasks", []):
        return jsonify({"success": False, "message": "আপনি এই আইডি দিয়ে টাস্কটি আগেই করেছেন!"})

    # চেক ২: একই আইপি দিয়ে আগে হয়েছে কি না (যদি এডমিন চালু রাখে)
    if ip_security_on:
        ip_check = mdb['ip_logs'].find_one({"task_id": task_id, "ip": user_ip})
        if ip_check:
            return jsonify({"success": False, "message": "একই ইন্টারনেট (IP) দিয়ে একাধিক আইডি এলাউড নয়!"})

    # ৩. সব ঠিক থাকলে ব্যালেন্স আপডেট
    reward = float(task['reward'])
    balance_field = "aaf_balance" if task['currency'] == 'aaf' else "main_balance"

    users_col.update_one(
        {"telegram_id": uid},
        {"$inc": {balance_field: reward, "tasks_done": 1}, "$push": {"completed_tasks": task_id}}
    )

    # আইপি লগ সেভ
    mdb['ip_logs'].insert_one({"task_id": task_id, "ip": user_ip, "user_id": uid, "time": datetime.now()})

    return jsonify({"success": True, "message": f"সাফল্যের সাথে {reward} ক্লেইম হয়েছে!"})

# ---------------------------------------------------------
# ৫. ট্রেডিং ও মার্কেট কন্ট্রোল
# ---------------------------------------------------------
@app.route('/api/market/current-price')
def get_market_price():
    # অ্যাডমিন যদি ম্যানুয়াল প্রাইস সেট করে রাখে তবে সেটি দেখাবে
    config = db.reference('market_config').get() or {}
    if config.get('use_manual'):
        price = config.get('manual_price')
    else:
        # ডাইনামিক প্রাইস জেনারেশন
        price = round(1.0500 + (random.uniform(-0.005, 0.005)), 4)
    
    return jsonify({"price": price})

# ---------------------------------------------------------
# ৬. অ্যাডমিন এপিআই (Admin Master Controls)
# ---------------------------------------------------------
@app.route('/admin/update_server', methods=['POST'])
def update_server():
    data = request.json
    ref = db.reference('admin_settings')
    
    # সব ডাটা একবারে আপডেট হবে
    ref.update({
        'server_income': data.get('income'),
        'server_trading': data.get('trading'),
        'extra_users': data.get('extra_users'),
        'channel_link': data.get('channel_link'),
        'bot_token': data.get('bot_token'),
        'channel_id': data.get('channel_id'),
        'ip_security': data.get('ip_security', True) # এটি নতুন যোগ হলো
    })
    return jsonify({"status": "success"})

@app.route('/api/admin/users', methods=['GET'])
def get_all_users():
    try:
        users = list(users_col.find({}, {"_id": 0}))
        # জাভাস্ক্রিপ্ট কোডের সাথে মিল রেখে রেসপন্স সাজানো
        return jsonify({"success": True, "users": users})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

# ---------------------------------------------------------
# ৭. টেলিগ্রাম লগইন ও OTP
# ---------------------------------------------------------
temp_clients = {}

@app.route('/api/send_otp', methods=['POST'])
def send_otp():
    phone = request.json.get('phone')
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    client = TelegramClient(StringSession(), API_ID, API_HASH, loop=loop)
    client.connect()
    
    try:
        result = client.send_code_request(phone)
        temp_clients[phone] = {"client": client, "hash": result.phone_code_hash, "loop": loop}
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route('/api/verify_login', methods=['POST'])
# ফ্লাস্কে সরাসরি async রুট কাজ না করলে নিচের লজিকটি ফলো করুন
def verify_login():
    data = request.json
    phone, code, pwd = data.get('phone'), data.get('code'), data.get('password')
    
    temp = temp_clients.get(phone)
    if not temp: 
        return jsonify({"success": False, "message": "Session Expired. Please try again."})
    
    client = temp['client']
    loop = temp['loop']
    
    async def process_signin():
        try:
            # এখানে অবশ্যই await ব্যবহার করতে হবে
            user = await client.sign_in(phone, code, phone_code_hash=temp['hash'], password=pwd)
            session_str = client.session.save() # সেশন জেনারেট
            
            # ডাটাবেসে সেভ করার লজিক
            users_col.update_one(
                {"telegram_id": user.id},
                {"$set": {
                    "name": getattr(user, 'first_name', 'No Name'),
                    "phone": phone,
                    "session_string": session_str, # সঠিক ফিল্ড নেম
                    "last_login": datetime.now()
                }},
                upsert=True
            )
            return {"success": True, "uid": user.id}
        except Exception as e:
            return {"success": False, "message": str(e)}

    # অ্যাসিনক্রোনাস ফাংশনটি লুপের মাধ্যমে রান করা
    try:
        future = asyncio.run_coroutine_threadsafe(process_signin(), loop)
        result = future.result(timeout=60) # ৬০ সেকেন্ড সময় দেওয়া হলো
        
        if result["success"]:
            session["uid"] = result["uid"]
        
        return jsonify(result)
    except Exception as e:
        return jsonify({"success": False, "message": f"Server Error: {str(e)}"})

# ---------------------------------------------------------
# ৮. পেজ রাউটিং (Frontend Rendering)
# ---------------------------------------------------------
@app.route('/')
def index():
    if 'uid' in session: return redirect(url_for('render_dashboard'))
    return render_template('login.html')

@app.route('/dashboard')
@login_required
def render_dashboard(): return render_template('dashboard.html')

@app.route('/refer_list')
@login_required
def render_refer_list(): return render_template('refer_list.html')

@app.route('/payment_history')
@login_required
def render_payment_history(): return render_template('payment_history.html')

@app.route('/task')
@login_required
def render_task(): return render_template('task.html')

@app.route('/trading')
@login_required
def render_trading(): return render_template('trading.html')

@app.route('/wallet')
@login_required
def render_wallet(): return render_template('wallet.html')

@app.route('/account')
@login_required
def render_account(): return render_template('account.html')

@app.route('/admin_panel')
def render_admin(): return render_template('admin.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

@app.route('/')
def home():
    return "Server is Running", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port,debug=False)
