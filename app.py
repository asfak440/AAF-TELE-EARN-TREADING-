import os
import asyncio
import nest_asyncio
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from pymongo import MongoClient
from telethon import TelegramClient
from telethon.sessions import StringSession

# ১. ইভেন্ট লুপ ফিক্স (টেলিথন ও ফ্লাস্কের ঝগড়া মেটানোর জন্য)
nest_asyncio.apply()

app = Flask(__name__)
CORS(app)

# ২. আপনার ডাটাবেস ও টেলিগ্রাম কনফিগারেশন
API_ID = 36466824
API_HASH = '535ddcb85f2c3c74cc0ff532dd2c3406'
MONGO_URI = "mongodb+srv://abdullahasfakfarvezbd_db_user:Abdullah6790@cluster0.rmulyqq.mongodb.net/?appName=Cluster0"

client_db = MongoClient(MONGO_URI)
db = client_db['AAF_TeleEarn']
users_col = db['users']

temp_clients = {}

# ৩. আপনার সবকটি HTML পেজের রুট (Routes)
@app.route('/')
@app.route('/dashboard')
def dashboard(): return render_template('dashboard.html')

@app.route('/login')
def login(): return render_template('login.html')

@app.route('/task')
def task(): return render_template('task.html')

@app.route('/trading')
def trading(): return render_template('trading.html')

@app.route('/accounts')
def accounts(): return render_template('accounts.html')

@app.route('/wallet')
def wallet(): return render_template('wallet.html')

# ৪. ডাটা আদান-প্রদানের এপিআই (API)
@app.route('/api/user_data/<user_id>', methods=['GET'])
def get_user_data(user_id):
    try:
        user = users_col.find_one({"telegram_id": int(user_id)})
        if user:
            return jsonify({
                "status": "success",
                "name": user.get('name', 'User'),
                "main_balance": user.get('main_balance', 0.0),
                "aaf_balance": user.get('aaf_balance', 0.0),
                "task_income": user.get('task_income', 0.0),
                "trade_profit": user.get('trade_profit', 0.0),
                "active_accounts": user.get('active_accounts', 0),
                "total_accounts": user.get('total_accounts', 0)
            })
        return jsonify({"status": "error", "message": "User not found"}), 404
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ৫. ওটিপি পাঠানোর ফাংশন
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
        return jsonify({"success": True, "message": "OTP Sent!"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

# ৬. পোর্ট বাইন্ডিং (Render সার্ভারের এরর ফিক্স)
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
