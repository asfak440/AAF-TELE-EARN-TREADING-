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

# --- ১. অ্যাডমিন কন্ট্রোল ---
@app.route('/admin/stats', methods=['GET'])
def get_admin_stats():
    try:
        total_users = db.users.count_documents({})
        stats = db.admin_stats.find_one({"id": "global"})
        total_withdraw = stats.get('total_withdraw', 0) if stats else 0
        
        return jsonify({
            "server_total_users": total_users,
            "total_withdraw_amount": total_withdraw,
            "status": "Online"
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

# --- ২. উইথড্রয়াল অ্যাপ্রুভ ---
@app.route('/admin/approve_withdraw', methods=['POST'])
def approve_withdraw():
    data = request.json
    withdraw_id = data.get('id')
    db.withdrawals.update_one({"id": withdraw_id}, {"$set": {"status": "success"}})
    return jsonify({"status": "Success", "message": "Withdraw Approved!"})

# --- ৩. ট্রেডিং এবং কয়েন প্রাইস কন্ট্রোল ---
@app.route('/trading/update_price', methods=['POST'])
def update_price():
    new_price = request.json.get('price')
    db.admin_stats.update_one({"id": "global"}, {"$set": {"aaf_coin_price": new_price}}, upsert=True)
    return jsonify({"message": "Price Updated Successfully"})

# --- ৪. ট্রেডিং অ্যালগরিদম ও ক্যান্ডেলস্টিক ডাটা ---
@app.route('/trading/live_chart', methods=['GET'])
def live_chart():
    config = db.admin_stats.find_one({"id": "global"})
    if not config:
        config = {"total_withdraw": 0, "total_earn": 1, "aaf_coin_price": 1.0}
    
    total_withdraw = config.get('total_withdraw', 0)
    total_earn = config.get('total_earn', 1) 
    current_price = config.get('aaf_coin_price', 1.0)

    # লজিক: উইথড্র ৯০% এর বেশি হলে দাম কমবে
    if (total_withdraw / total_earn) >= 0.9:
        price_change = random.uniform(-0.1, -0.05)
    else:
        price_change = random.uniform(-0.02, 0.05)

    new_price = round(current_price + price_change, 2)
    if new_price < 0.1: new_price = 0.1

    db.admin_stats.update_one({"id": "global"}, {"$set": {"aaf_coin_price": new_price}})

    return jsonify({
        "price": new_price,
        "time": datetime.datetime.now().strftime("%H:%M:%S"),
        "trend": "down" if price_change < 0 else "up"
    })

# --- ৫. Render এর জন্য রান সেটআপ ---
if __name__ == "__main__":
    # অবশ্যই 'os' ইমপোর্ট থাকতে হবে পোর্ট ধরার জন্য
    port = int(os.environ.get("PORT", 5000))
    # host='0.0.0.0' দেওয়া বাধ্যতামূলক
    app.run(host='0.0.0.0', port=port)
