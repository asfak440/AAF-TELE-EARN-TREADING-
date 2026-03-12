import os
import random
import datetime
from flask import Flask, request, jsonify
from pymongo import MongoClient

app = Flask(__name__)

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

# --- ২. উইথড্র রিকোয়েস্ট রিসিভ ---
@app.route('/api/withdraw', methods=['POST'])
def handle_withdraw():
    data = request.json
    amount = data.get('amount')
    
    # উইথড্র রিকোয়েস্ট সেভ করা
    db.withdrawals.insert_one({
        "user_id": data.get('user_id'),
        "phone": data.get('phone'),
        "amount": amount,
        "status": "Pending",
        "date": datetime.datetime.now()
    })
    
    # গ্লোবাল উইথড্রয়াল স্ট্যাটাস আপডেট (কয়েনের দাম কমানোর জন্য)
    db.admin_stats.update_one(
        {"id": "global"},
        {"$inc": {"total_withdrawn": amount}},
        upsert=True
    )
    return jsonify({"status": "success"})

# --- ৩. ব্যালেন্স ট্রান্সফার (Task/Account থেকে Main Balance-এ) ---
@app.route('/api/transfer_to_main', methods=['POST'])
def transfer_to_main():
    data = request.json
    user_id = data.get('user_id')
    source = data.get('source') # 'task' বা 'account' বা 'trading'
    
    user = db.users.find_one({"telegram_id": user_id})
    if not user: return jsonify({"error": "User not found"}), 404
    
    amount = user.get(f'{source}_balance', 0)
    if amount > 0:
        db.users.update_one(
            {"telegram_id": user_id},
            {"$inc": {"main_balance": amount}, "$set": {f"{source}_balance": 0}}
        )
        return jsonify({"status": "success", "message": "Main Balance-এ যোগ হয়েছে!"})
    return jsonify({"error": "ব্যালেন্স নেই"})

# --- ৪. ট্রেডিং মার্কেট লজিক (দাম বাড়া/কমা) ---
@app.route('/api/aaf_market', methods=['GET'])
def aaf_market():
    stats = db.admin_stats.find_one({"id": "global"})
    if not stats:
        return jsonify({"aaf_price_bdt": 1.0, "status": "Initializing"})

    total_earned = stats.get('total_earned', 1)
    total_withdrawn = stats.get('total_withdrawn', 0)
    
    # আপনার রিকোয়ারমেন্ট: উইথড্র ৯০% হলে দাম কমবে, ইনকাম বাড়লে বাড়বে
    ratio = total_withdrawn / total_earned if total_earned > 0 else 0
    
    if ratio >= 0.9:
        current_price = 1.0 * (1 - ratio + 0.1) # দাম ক্র্যাশ করবে
    else:
        current_price = 1.0 + (total_earned * 0.001) - (total_withdrawn * 0.002)
        
    return jsonify({
        "aaf_price_bdt": round(max(current_price, 0.1), 2),
        "status": "Market Live",
        "ratio": round(ratio, 2)
    })

# --- ৫. সার্ভার রান সেটআপ (এটি সবার নিচে থাকবে) ---
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
