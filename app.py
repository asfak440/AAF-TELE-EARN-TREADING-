import os
import base64
import asyncio
import nest_asyncio
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from pymongo import MongoClient
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad

# ১. ইভেন্ট লুপ প্যাচ (Conflict এড়ানোর জন্য)
nest_asyncio.apply()

app = Flask(__name__)
CORS(app)

# ২. কনফিগারেশন ও ডাটাবেস
API_ID = 36466824      
API_HASH = '535ddcb85f2c3c74cc0ff532dd2c3406'  
SECRET_KEY = b'AAF_STRONG_APP_SECURE_32_BIT_KEY' 
MONGO_URI = "mongodb+srv://abdullahasfakfarvezbd_db_user:Abdullah6790@cluster0.rmulyqq.mongodb.net/?appName=Cluster0"

client_db = MongoClient(MONGO_URI)
db = client_db['AAF_TeleEarn']
users_col = db['users']
sessions_col = db['sessions']

temp_clients = {}

# ৩. পেজ রুটস
@app.route('/')
@app.route('/dashboard')
def dashboard(): return render_template('dashboard.html')

@app.route('/login')
def login(): return render_template('login.html')

# ৪. ওটিপি এপিআই (Task এর ভেতর টাইমআউট ফিক্সসহ)
@app.route('/api/send_otp', methods=['POST'])
async def send_otp():
    data = request.json
    phone = data.get('phone')
    try:
        loop = asyncio.get_event_loop()
        client = TelegramClient(StringSession(), API_ID, API_HASH, loop=loop)
        
        async def connect_and_send():
            if not client.is_connected(): await client.connect()
            return await client.send_code_request(phone)
            
        sent_code = await asyncio.wait_for(asyncio.create_task(connect_and_send()), timeout=35)
        temp_clients[phone] = {'client': client, 'phone_code_hash': sent_code.phone_code_hash}
        return jsonify({"success": True, "message": "ওটিপি পাঠানো হয়েছে!"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

# ৫. ড্যাশবোর্ডের জন্য প্রোফাইল ডাটা এপিআই
@app.route('/api/user_profile/<user_id>', methods=['GET'])
def get_user_profile(user_id):
    user = users_col.find_one({"telegram_id": int(user_id)})
    if user:
        return jsonify({
            "status": "success",
            "name": user.get('name', 'User'),
            "telegram_id": user.get('telegram_id'),
            "phone": user.get('phone', 'N/A'),
            "main_balance": user.get('main_balance', 0.0),
            "aaf_balance": user.get('aaf_balance', 0.0),
            "total_accounts": user.get('total_accounts', 0),
            "active_accounts": user.get('active_accounts', 0),
            "is_joined_channel": user.get('is_joined_channel', False)
        })
    return jsonify({"status": "error"}), 404

# ৬. পোর্ট বাইন্ডিং ফিক্স (Render এর জন্য)
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
