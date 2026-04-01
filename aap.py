from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from pymongo import MongoClient
import firebase_admin
from firebase_admin import credentials, db
import requests
import uuid
import datetime
from functools import wraps

app = Flask(__name__)
app.secret_key = "AAF_STRONG_SECURE_KEY_99" # এটি সেশন এনক্রিপ্ট রাখে

# --- ১. ডাটাবেজ কানেকশন (MongoDB & Firebase) ---
# MongoDB Atlas
MONGO_URI = "mongodb+srv://abdullahasfakfarvezbd_db_user:Abdullah6790@cluster0.rmulyqq.mongodb.net/?appName=Cluster0"
client = MongoClient(MONGO_URI)
mdb = client['aaf_database']
users_col = mdb['users']
settings_col = mdb['settings']

# Firebase (Candlestick Chart Data - ২ মাসের হিস্ট্রি)
# নোট: Firebase Admin SDK এর জন্য আপনার .json ফাইল লাগবে। আপাতত placeholder দিচ্ছি।
try:
    if not firebase_admin._apps:
        cred = credentials.Certificate("firebase_key.json") # আপনার ফায়ারবেজ এডমিন কি এখানে দিবেন
        firebase_admin.initialize_app(cred, {
            'databaseURL': 'https://teleearnbd-default-rtdb.firebaseio.com/'
        })
except Exception as e:
    print(f"Firebase Sync Error: {e}")

# --- ২. সিকিউরিটি চেক (Login Required Decorator) ---
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login_page'))
        
        # স্ট্রং সেশন চেক: ডাটাবেজের সেশনের সাথে ম্যাচ না করলে লগআউট
        user = users_col.find_one({"_id": session['user_id']})
        if not user or user.get('current_session_id') != session.get('sid'):
            session.clear()
            return redirect(url_for('login_page'))
            
        return f(*args, **kwargs)
    return decorated_function

# --- ৩. টেলিগ্রাম মাল্টি-অ্যাকাউন্ট লজিক (Routes) ---

@app.route('/')
@login_required
def dashboard():
    # ড্যাশবোর্ডে ডাটা পাঠানো
    user_data = users_col.find_one({"_id": session['user_id']})
    admin_settings = settings_col.find_one({"type": "global"})
    return render_template('aaf442.html', user=user_data, admin=admin_settings)

@app.route('/login', methods=['GET', 'POST'])
def login_page():
    if request.method == 'POST':
        phone = request.form.get('phone')
        # এখানে আপনার টেলিগ্রাম ওটিপি ভেরিফিকেশন লজিক বসবে (Telethon/Bot API)
        
        # সেশন আইডি জেনারেট (নতুন লগইন হলে পুরানোটা রিমুভ হবে)
        new_sid = str(uuid.uuid4())
        
        # ডাটাবেজে ইউজার আপডেট বা তৈরি
        user = users_col.find_one({"phone": phone})
        if user:
            # পুরানো সেশন রিমুভ করে নতুন সেশন অ্যাড (Strong Session)
            users_col.update_one({"phone": phone}, {"$set": {"current_session_id": new_sid, "last_login": datetime.datetime.now()}})
            user_id = user["_id"]
        else:
            # নতুন ইউজার ক্রিয়েট
            res = users_col.insert_one({
                "phone": phone,
                "username": f"User_{phone[-4:]}",
                "aaf_balance": 0.0,
                "cash_balance": 0.0,
                "trade_count": 0,
                "is_2fa_enabled": False, # ডিফল্ট অফ
                "current_session_id": new_sid,
                "is_joined": False,
                "ip_address": request.remote_addr
            })
            user_id = res.inserted_id

        # সেশনে সেভ করা
        session['user_id'] = str(user_id)
        session['sid'] = new_sid
        return jsonify({"status": "success", "redirect": "/dashboard"})
        
    return render_template('aaf441.html')

# --- ৪. API Endpoints (ডাইনামিক ডাটা আদান-প্রদান) ---

@app.route('/api/get_user_data')
@login_required
def get_user_data():
    user = users_col.find_one({"_id": session['user_id']})
    admin = settings_col.find_one({"type": "global"})
    
    # ObjectId স্ট্রিং এ কনভার্ট করা (JSON এর জন্য)
    user['_id'] = str(user['_id'])
    return jsonify({"user": user, "admin": admin})

if __name__ == '__main__':
    app.run(debug=True, port=5000)

from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError
import asyncio

# --- ৫. টেলিগ্রাম কনফিগারেশন ---
API_ID = 36466824
API_HASH = '535ddcb85f2c3c74cc0ff532dd2c3406'
# সেশন ফাইলগুলো 'sessions/' ফোল্ডারে সেভ হবে
import os
if not os.path.exists('sessions'):
    os.makedirs('sessions')

# --- ৬. ২-স্টেপ ভেরিফিকেশন ও ওটিপি লজিক ---

@app.route('/send_otp', methods=['POST'])
async def send_otp():
    phone = request.json.get('phone')
    # প্রতিটি ফোনের জন্য আলাদা সেশন ফাইল তৈরি হবে (Multi-account support)
    client = TelegramClient(f'sessions/{phone}', API_ID, API_HASH)
    await client.connect()
    
    try:
        # ওটিপি পাঠানো
        send_code = await client.send_code_request(phone)
        session['temp_phone'] = phone
        session['phone_code_hash'] = send_code.phone_code_hash
        return jsonify({"status": "success", "message": "OTP Sent to Telegram"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/verify_login', methods=['POST'])
async def verify_login():
    data = request.json
    otp = data.get('otp')
    password_2fa = data.get('password') # ২-স্টেপ পাসওয়ার্ড (যদি থাকে)
    phone = session.get('temp_phone')
    
    client = TelegramClient(f'sessions/{phone}', API_ID, API_HASH)
    await client.connect()

    try:
        # ওটিপি ভেরিফাই
        await client.sign_in(phone, otp, phone_code_hash=session.get('phone_code_hash'))
        return finalize_login(phone)
        
    except SessionPasswordNeededError:
        # যদি ২-স্টেপ ভেরিফিকেশন অন থাকে
        if not password_2fa:
            return jsonify({"status": "2fa_required", "message": "Please enter your 2-Step Password"})
        
        try:
            await client.sign_in(password=password_2fa)
            return finalize_login(phone)
        except Exception:
            return jsonify({"status": "error", "message": "Wrong 2-Step Password"})
            
    except Exception as e:
        return jsonify({"status": "error", "message": "Invalid OTP"})

def finalize_login(phone):
    # সেশন ও ডাটাবেজ আপডেট (Part 1 এ যেভাবে করা হয়েছে)
    new_sid = str(uuid.uuid4())
    user = users_col.find_one_and_update(
        {"phone": phone},
        {"$set": {"current_session_id": new_sid, "last_login": datetime.datetime.now()}},
        upsert=True, return_document=True
    )
    session['user_id'] = str(user['_id'])
    session['sid'] = new_sid
    return jsonify({"status": "success", "redirect": "/dashboard"})

# --- ৭. ট্রেডিং ও উইথড্র লিমিট (Security Logic) ---

@app.route('/api/execute_trade', methods=['POST'])
@login_required
def execute_trade():
    user_id = session['user_id']
    # আইপি চেক (এক আইপি থেকে বারবার টাস্ক রোধ)
    current_ip = request.remote_addr
    
    # অ্যাডমিন সেটিংস থেকে লিমিট চেক
    admin = settings_col.find_one({"type": "global"})
    if admin.get('ip_limit') == 'on':
        existing = users_col.find_one({"ip_address": current_ip, "_id": {"$ne": user_id}})
        if existing:
            return jsonify({"status": "error", "message": "Multi-account detected on same IP!"})

    # ট্রেড কাউন্টার বৃদ্ধি
    users_col.update_one({"_id": user_id}, {"$inc": {"trade_count": 1}})
    return jsonify({"status": "success", "message": "Trade Completed Successfully"})

@app.route('/api/withdraw_request', methods=['POST'])
@login_required
def withdraw_request():
    user = users_col.find_one({"_id": session['user_id']})
    admin = settings_col.find_one({"type": "global"})
    
    # উইথড্র শর্ত চেক (ট্রেড সংখ্যা)
    min_trades = admin.get('min_trades', 5)
    if user.get('trade_count', 0) < min_trades:
        return jsonify({"status": "error", "message": f"You need at least {min_trades} trades to withdraw!"})
    
    # বাকি উইথড্র লজিক...
    return jsonify({"status": "success", "message": "Withdraw Request Sent"})

# --- ৮. বোনাস লজিক (Channel Join Check) ---
@app.route('/api/claim_bonus', methods=['POST'])
@login_required
def claim_bonus():
    user = users_col.find_one({"_id": session['user_id']})
    # এখানে বট এপিআই দিয়ে চেক করা হবে ইউজার চ্যানেলে আছে কি না
    # যদি থাকে এবং প্রতিদিনের টাস্ক শেষ হয়, তবে ব্যালেন্স বাড়বে
    return jsonify({"status": "success", "message": "Daily Bonus Added!"})

# --- ৯. অ্যাডমিন কন্ট্রোল প্যানেল লজিক (aaf449) ---

@app.route('/admin/settings', methods=['GET', 'POST'])
@login_required
def admin_settings():
    # চেক করুন ইউজার কি অ্যাডমিন? (আপনার ফোন নম্বর দিয়ে সিকিউরিটি)
    user = users_col.find_one({"_id": session['user_id']})
    if user.get('phone') != "+8801XXXXXXXXX": # এখানে আপনার নিজের নম্বর দিন
        return "Access Denied!", 403

    if request.method == 'POST':
        data = request.json
        # গ্লোবাল সেটিংস আপডেট (চ্যানেল লিঙ্ক, ফি, লিমিট)
        settings_col.update_one(
            {"type": "global"},
            {"$set": {
                "channel_link": data.get('channel_link'),
                "trading_fee": float(data.get('fee', 0.1)),
                "min_trades": int(data.get('min_trades', 5)),
                "ip_limit": data.get('ip_limit', 'on'),
                "bonus_amount": float(data.get('bonus', 10))
            }},
            upsert=True
        )
        return jsonify({"status": "success", "message": "Settings Updated!"})

    # বর্তমান সেটিংস লোড করা
    config = settings_col.find_one({"type": "global"})
    return render_template('aaf449.html', config=config)

# --- ১০. ইউজার ম্যানেজমেন্ট (অ্যাডমিন ভিউ) ---

@app.route('/admin/users')
@login_required
def list_users():
    # সব ইউজারের লিস্ট এবং তাদের ব্যালেন্স দেখা
    all_users = list(users_col.find({}, {"phone": 1, "aaf_balance": 1, "cash_balance": 1, "trade_count": 1}))
    for u in all_users: u['_id'] = str(u['_id'])
    return jsonify(all_users)

@app.route('/admin/user/action', methods=['POST'])
@login_required
def user_action():
    # ইউজারকে ব্যান করা বা ব্যালেন্স অ্যাড করা
    data = request.json
    target_id = data.get('user_id')
    action = data.get('action') # 'ban' or 'add_balance'
    
    if action == 'ban':
        users_col.update_one({"_id": target_id}, {"$set": {"current_session_id": "BANNED"}})
        return jsonify({"status": "success", "message": "User Banned & Session Terminated"})
    
    return jsonify({"status": "error"})

# --- ১১. ক্যান্ডেলস্টিক ডাটা (Firebase Bridge) ---

@app.route('/api/get_live_candle')
def get_live_candle():
    # এটি aaf444 ট্রেডিং চার্টের জন্য ফায়ারবেজ থেকে লেটেস্ট ক্যান্ডেল আনবে
    try:
        ref = db.reference('trading/current_candle')
        candle_data = ref.get()
        return jsonify(candle_data)
    except:
        return jsonify({"error": "Firebase Connection Failed"})

# --- ১২. রান অ্যাপ্লিকেশন ---
if __name__ == '__main__':
    # সেশন ডিরেক্টরি নিশ্চিত করা
    if not os.path.exists('sessions'):
        os.makedirs('sessions')
    
    # আপনার লোকাল পিসি বা সার্ভারে রান করুন
    app.run(host='0.0.0.0', port=5000, debug=True)
