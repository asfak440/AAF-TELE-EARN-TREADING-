import os
import base64
import sqlite3
from flask import Flask, request, jsonify
from flask_cors import CORS
from pymongo import MongoClient
from Crypto.Cipher import AES
from Crypto.Util.Padding import pad, unpad

app = Flask(__name__)
CORS(app)

# --- কনফিগারেশন ---
# আপনার দেওয়া MongoDB URI
MONGO_URI = "mongodb+srv://Asfak1:Abdullah6790@cluster0.ykmq2wh.mongodb.net/?retryWrites=true&w=majority"
client = MongoClient(MONGO_URI)
db = client['AAF_TeleEarn']
users_col = db['users']

# AES এনক্রিপশন কি (৩২ ক্যারেক্টার হতে হবে)
# আপনার সেশনগুলো সুরক্ষিত রাখতে এটি ব্যবহার করা হবে
SECRET_KEY = b'AAF_STRONG_APP_SECURE_32_BIT_KEY' 

# --- এনক্রিপশন লজিক ---
def encrypt_data(text):
    cipher = AES.new(SECRET_KEY, AES.MODE_CBC)
    ct_bytes = cipher.encrypt(pad(text.encode(), AES.block_size))
    iv = base64.b64encode(cipher.iv).decode('utf-8')
    ct = base64.b64encode(ct_bytes).decode('utf-8')
    return f"{iv}:{ct}"

# --- এপিআই এন্ডপয়েন্টসমূহ ---

# ১. ড্যাশবোর্ডের জন্য ইউজারের সব ব্যালেন্স নিয়ে আসা
@app.route('/api/user_data/<telegram_id>', methods=['GET'])
def get_user_data(telegram_id):
    user = users_col.find_one({"telegram_id": int(telegram_id)})
    if user:
        return jsonify({
            "status": "success",
            "name": user.get("name", "User"),
            "main_balance": user.get("main_balance", 0.0),
            "task_balance": user.get("task_balance", 0.0),
            "trade_balance": user.get("trade_balance", 0.0),
            "acc_balance": user.get("acc_balance", 0.0),
            "acc_status": user.get("status", "Inactive")
        })
    return jsonify({"status": "error", "message": "User not found"})

# ২. উইথড্র রিকোয়েস্ট (আপনার শর্ত অনুযায়ী)
@app.route('/api/withdraw', methods=['POST'])
def withdraw_request():
    data = request.json
    uid = data.get('telegram_id')
    amount = float(data.get('amount'))
    
    user = users_col.find_one({"telegram_id": int(uid)})
    
    # শর্ত: কমপক্ষে ৫টি অ্যাকাউন্ট থাকতে হবে (আপনার মডেল অনুযায়ী)
    added_accounts = user.get("added_accounts", 0)
    if added_accounts < 5:
        return jsonify({"status": "error", "message": "কমপক্ষে ৫টি অ্যাকাউন্ট অ্যাড থাকতে হবে!"})
    
    if user['main_balance'] >= amount and amount >= 50:
        # ব্যালেন্স কাটানো এবং রিকোয়েস্ট সেভ
        users_col.update_one({"telegram_id": int(uid)}, {"$inc": {"main_balance": -amount}})
        # এখানে আপনার উইথড্র কালেকশনে ডাটা সেভ হবে
        return jsonify({"status": "success", "message": "Withdraw successful animation trigger"})
    
    return jsonify({"status": "error", "message": "Insufficient balance or invalid amount"})

# ৩. AAF Coin প্রাইস লজিক (আপনার লজিক অনুযায়ী)
@app.route('/api/aaf_price', methods=['GET'])
def aaf_price():
    # লজিক: ইউজার একটিভিটি বেশি হলে প্রাইস বাড়বে
    total_users = users_col.count_documents({})
    base_price = 1.25
    # একটিভ ইউজার অনুযায়ী প্রাইস বৃদ্ধি (সিম্পল অ্যালগরিদম)
    current_price = base_price + (total_users * 0.0001)
    return jsonify({"price": round(current_price, 4)})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
