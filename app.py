import os
import asyncio
import nest_asyncio
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from pymongo import MongoClient
from telethon import TelegramClient
from telethon.sessions import StringSession

# ১. ইভেন্ট লুপ ফিক্স (Telethon ও Flask এর সংঘর্ষ এড়াতে)
nest_asyncio.apply()

app = Flask(__name__)
CORS(app)

# ২. কনফিগারেশন
API_ID = 36466824
API_HASH = '535ddcb85f2c3c74cc0ff532dd2c3406'
MONGO_URI = "mongodb+srv://abdullahasfakfarvezbd_db_user:Abdullah6790@cluster0.rmulyqq.mongodb.net/?appName=Cluster0"

client_db = MongoClient(MONGO_URI)
db = client_db['AAF_TeleEarn']
users_col = db['users']

temp_clients = {}

# ৩. আপনার সবকটি HTML পেজের কানেকশন (Routes)
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

# ৪. ডাটাবেস থেকে তথ্য আনার API (Dashboard-এর জন্য)
@app.route('/api/user_data/<user_id>', methods=['GET'])
def get_user_data(user_id):
    try:
        user = users_col.find_one({"telegram_id": int(user_id)})
        if user:
            return jsonify({
                "status": "success",
                "main_balance": user.get('main_balance', 0.0),
                "aaf_balance": user.get('aaf_balance', 0.0)
            })
        return jsonify({"status": "error", "message": "User not found"}), 404
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500

# ৫. পোর্ট বাইন্ডিং (Render সার্ভারের এরর ফিক্স)
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
