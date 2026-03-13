import os
import random
import datetime
from flask import Flask, request, jsonify
from pymongo import MongoClient
from flask_cors import CORS  # ১. একদম ওপরে এটি আনুন

app = Flask(__name__)
CORS(app)  # ২. app = Flask(__name__) এর নিচেই এটি বসবে

# --- ডাটাবেস কানেকশন ---
MONGO_URI = "mongodb+srv://Asfak1:Abdullah6790@cluster0.ykmq2wh.mongodb.net/?retryWrites=true&w=majority"
client = MongoClient(MONGO_URI)
db = client['AAF_TeleEarn']

@app.route('/')
def index(): 
    return "AAF Server is Online!"

# --- ১. অ্যাডমিন স্ট্যাটাস ---
@app.route('/admin/stats', methods=['GET'])
def get_admin_stats():
    total_users = db.users.count_documents({})
    stats = db.admin_stats.find_one({"id": "global"})
    total_withdrawn = stats.get('total_withdrawn', 0) if stats else 0
    return jsonify({
        "total_users": total_users, 
        "total_withdrawn_amount": total_withdrawn,
        "status": "Online"
    })

# --- ২. উইথড্র রিকোয়েস্ট রিসিভ ---
@app.route('/api/withdraw', methods=['POST'])
def handle_withdraw():
    data = request.json
    amount = data.get('amount')
    
    db.withdrawals.insert_one({
        "user_id": data.get('user_id'),
        "phone": data.get('phone'),
        "amount": amount,
        "status": "Pending",
        "date": datetime.datetime.now()
    })
    
    db.admin_stats.update_one(
        {"id": "global"},
        {"$inc": {"total_withdrawn": amount}},
        upsert=True
    )
    return jsonify({"status": "success"})

# --- ৩. ব্যালেন্স ট্রান্সফার ---
@app.route('/api/transfer_to_main', methods=['POST'])
def transfer_to_main():
    data = request.json
    user_id = data.get('user_id')
    source = data.get('source')
    
    user = db.users.find_one({"telegram_id": user_id})
    if not user: return jsonify({"error": "User not found"}), 404
    
    amount = user.get(f'{source}_balance', 0)
    if amount > 0:
        db.users.update_one(
            {"telegram_id": user_id},
            {"$inc": {"main_balance": amount}, "$set": {f"{source}_balance": 0}}
        )
        return jsonify({"status": "success", "message": "Main Balance-এ যোগ হয়েছে!"})
    return jsonify({"error": "ব্যালেন্স নেই"})

# --- ৪. ট্রেডিং চার্ট এবং প্রাইস ডাটা (HTML এর জন্য) ---
@app.route('/get_aaf_price', methods=['GET'])
def get_price():
    # এখানে আমরা ডাটাবেস থেকে রিয়েল টাইম ডাটা নিতে পারি
    stats = db.admin_stats.find_one({"id": "global"})
    total_earned = stats.get('total_earned', 1) if stats else 1
    total_withdrawn = stats.get('total_withdrawn', 0) if stats else 0
    
    ratio = total_withdrawn / total_earned if total_earned > 0 else 0
    
    if ratio >= 0.9:
        price = 1.0 * (1 - ratio + 0.1)
    else:
        price = 1.0 + (total_earned * 0.001) - (total_withdrawn * 0.002)
    
    current_price = round(max(price, 0.1), 2)

    return jsonify({
        "current_price": current_price,
        "main_balance": 500, # এটি পরবর্তীতে ডিনামিক করা যাবে
        "chart_data": [
            {"time": "2026-03-11", "open": 1.0, "high": 1.2, "low": 0.9, "close": 1.1},
            {"time": "2026-03-12", "open": 1.1, "high": 1.5, "low": 1.0, "close": 1.4},
            {"time": "2026-03-13", "open": 1.4, "high": 1.6, "low": 1.3, "close": current_price}
        ]
    })

# --- ৫. সার্ভার রান সেটআপ (সবার নিচে থাকবে) ---
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
