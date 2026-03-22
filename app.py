import os
import asyncio
import nest_asyncio
from flask import Flask, render_template, request, jsonify, session
from flask_cors import CORS
from pymongo import MongoClient
from telethon import TelegramClient
from telethon.sessions import StringSession
from datetime import datetime

# ১. সিস্টেম ফিক্স (nest_asyncio)
nest_asyncio.apply()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "aaf_super_secret_key_123")

# ২. CORS ফিক্স (ব্রাউজার কানেকশন এরর দূর করার জন্য)
CORS(app, resources={r"/api/*": {"origins": "*"}}, supports_credentials=True)

# ৩. আপনার কনফিগারেশন
API_ID = 36466824
API_HASH = "535ddcb85f2c3c74cc0ff532dd2c3406"
MONGO_URI = "mongodb+srv://abdullahasfakfarvezbd_db_user:Abdullah6790@cluster0.rmulyqq.mongodb.net/?retryWrites=true&w=majority"

# ৪. ডাটাবেস কানেকশন
client_db = MongoClient(MONGO_URI)
db = client_db['AAF_TeleEarn']
users_col = db['users']
settings_col = db['settings']

temp_clients = {}

# ---------------- ৫. HTML রাউটস (HTML ROUTES) ----------------

@app.route('/')
@app.route('/login')
def login(): return render_template('login.html')

@app.route('/dashboard')
def dashboard(): return render_template('dashboard.html')

@app.route('/task')
def task(): return render_template('task.html')

@app.route('/trading')
def trading(): return render_template('treading.html') # আপনার ফাইলের বানান অনুযায়ী

@app.route('/account')
def account(): return render_template('account.html')

@app.route('/wallet')
def wallet(): return render_template('wallet.html')

@app.route('/admin')
def admin_page(): return render_template('admin.html')

# ---------------- ৬. এডমিন এপিআই (ADMIN API) ----------------

@app.route('/api/admin/users')
def get_users():
    users = list(users_col.find({}, {"_id": 0}))
    return jsonify(users)

@app.route('/api/admin/update_balance', methods=['POST'])
def update_balance():
    data = request.json
    try:
        users_col.update_one(
            {"telegram_id": int(data['uid'])},
            {"$set": {"main_balance": float(data['balance'])}}
        )
        return jsonify({"success": True})
    except:
        return jsonify({"success": False})

# ---------------- ৭. টেলিগ্রাম লগইন এপিআই (OTP & LOGIN) ----------------

@app.route('/api/send_otp', methods=['POST'])
async def send_otp(): # async যোগ করা হয়েছে
    data = request.json
    phone = data.get('phone')
    try:
        loop = asyncio.get_event_loop()
        client = TelegramClient(StringSession(), API_ID, API_HASH, loop=loop)
        await client.connect() # await ব্যবহার করা হয়েছে
        result = await client.send_code_request(phone)
        
        temp_clients[phone] = {
            "client": client,
            "hash": result.phone_code_hash
        }
        return jsonify({"success": True, "message": "OTP Sent!"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route('/api/verify_login', methods=['POST'])
async def verify_login():
    data = request.json
    phone = data.get('phone')
    code = data.get('code')

    if phone not in temp_clients:
        return jsonify({"success": False, "message": "Session expired"})

    try:
        client = temp_clients[phone]["client"]
        h = temp_clients[phone]["hash"]
        
        user = await client.sign_in(phone, code, phone_code_hash=h)
        
        user_data = {
            "telegram_id": user.id,
            "phone": phone,
            "name": f"{user.first_name or ''} {user.last_name or ''}",
            "joined": datetime.utcnow()
        }
        
        # ডাটাবেসে ইউজার সেভ (মেইন ব্যালেন্স ০ সেট করবে নতুন ইউজারের জন্য)
        users_col.update_one(
            {"telegram_id": user.id},
            {"$set": user_data, "$setOnInsert": {"main_balance": 0}},
            upsert=True
        )
        
        session["uid"] = user.id
        return jsonify({"success": True, "uid": user.id})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

# ---------------- ৮. টেস্ট রুট (সার্ভার চেক) ----------------

@app.route('/test')
def test():
    return "SERVER RUNNING SUCCESSFULLY"

# ---------------- ৯. পোর্ট সেটিংস (RENDER FIX) ----------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
