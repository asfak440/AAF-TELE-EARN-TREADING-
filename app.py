import os
import asyncio
import nest_asyncio
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from pymongo import MongoClient
from telethon import TelegramClient
from telethon.sessions import StringSession

# ইভেন্ট লুপ ফিক্স
nest_asyncio.apply()

app = Flask(__name__)
CORS(app)

# কনফিগারেশন
API_ID = 36466824
API_HASH = '535ddcb85f2c3c74cc0ff532dd2c3406'
MONGO_URI = "mongodb+srv://abdullahasfakfarvezbd_db_user:Abdullah6790@cluster0.rmulyqq.mongodb.net/?appName=Cluster0"

# ডাটাবেস কানেকশন
client_db = MongoClient(MONGO_URI)
db = client_db['AAF_TeleEarn']
users_col = db['users']

temp_clients = {}

@app.route('/')
def home(): return render_template('dashboard.html')

@app.route('/login')
def login_page(): return render_template('login.html')

# ওটিপি পাঠানোর এপিআই
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
        return jsonify({"success": True, "message": "ওটিপি পাঠানো হয়েছে!"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

# ড্যাশবোর্ড ডাটা এপিআই
@app.route('/api/user_data/<user_id>', methods=['GET'])
def get_user_data(user_id):
    user = users_col.find_one({"telegram_id": int(user_id)})
    if user:
        return jsonify({
            "status": "success",
            "name": user.get('name', 'User'),
            "telegram_id": user.get('telegram_id'),
            "main_balance": user.get('main_balance', 0.0),
            "aaf_balance": user.get('aaf_balance', 0.0),
            "phone": user.get('phone', 'N/A'),
            "active_accounts": user.get('active_accounts', 0),
            "total_accounts": user.get('total_accounts', 0)
        })
    return jsonify({"status": "error"}), 404

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
