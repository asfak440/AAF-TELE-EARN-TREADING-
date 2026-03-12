from flask import Flask, request, jsonify
from pymongo import MongoClient
import datetime

app = Flask(__name__)

# --- ডাটাবেস কানেকশন (আপনার স্ক্রিনশট অনুযায়ী) ---
# <db_password> এর জায়গায় আপনার তৈরি করা পাসওয়ার্ডটি বসান
MONGO_URI = "mongodb+srv://Asfak1:<Abdullah6790>@cluster0.ykmq2wh.mongodb.net/?retryWrites=true&w=majority"
client = MongoClient(MONGO_URI)
db = client['AAF_TeleEarn']

# --- ১. অ্যাডমিন কন্ট্রোল (সব এক জায়গা থেকে) ---
@app.route('/admin/stats', methods=['GET'])
def get_admin_stats():
    # ড্যাশবোর্ডে দেখানোর জন্য সব ডাটা
    total_users = db.users.count_documents({})
    total_withdraw = db.admin_stats.find_one({"id": "global"})['total_withdraw']
    
    return jsonify({
        "server_total_users": total_users,
        "total_withdraw_amount": total_withdraw,
        "status": "Online"
    })

# --- ২. উইথড্রয়াল অ্যাপ্রুভ এবং অ্যানিমেশন ট্রিগার ---
@app.route('/admin/approve_withdraw', methods=['POST'])
def approve_withdraw():
    data = request.json
    withdraw_id = data.get('id')
    
    # অ্যাডমিন অ্যাপ্রুভ করলে ডাটাবেস আপডেট হবে
    db.withdrawals.update_one({"id": withdraw_id}, {"$set": {"status": "success"}})
    
    # এরপর অ্যাপে অটোমেটিক 'Success Animation' দেখাবে
    return jsonify({"status": "Success", "message": "Withdraw Approved!"})

# --- ৩. ট্রেডিং এবং কয়েন প্রাইস কন্ট্রোল ---
@app.route('/trading/update_price', methods=['POST'])
def update_price():
    # অ্যাডমিন চাইলে এখান থেকে AAF কয়েনের দাম বাড়াতে বা কমাতে পারবে
    new_price = request.json.get('price')
    db.admin_stats.update_one({"id": "global"}, {"$set": {"aaf_coin_price": new_price}})
    return jsonify({"message": "Price Updated Successfully"})

if __name__ == '__main__':
    app.run(debug=True)
# --- ট্রেডিং অ্যালগরিদম ও ক্যান্ডেলস্টিক ডাটা ---
import random

@app.route('/trading/live_chart', methods=['GET'])
def live_chart():
    # অ্যাডমিন ডাটা থেকে বর্তমান স্ট্যাটাস চেক করা
    config = db.admin_stats.find_one({"id": "global"})
    total_withdraw = config.get('total_withdraw', 0)
    total_earn = config.get('total_earn', 1) # ০ দিয়ে ভাগ হওয়া এড়াতে
    
    current_price = config.get('aaf_coin_price', 1.0)

    # রুল: উইথড্র ৯০% এর বেশি হলে দাম কমে লাল ক্যান্ডেল হবে
    if (total_withdraw / total_earn) >= 0.9:
        price_change = random.uniform(-0.1, -0.05) # দাম কমবে
    else:
        price_change = random.uniform(-0.02, 0.05) # স্বাভাবিক উঠানামা

    new_price = round(current_price + price_change, 2)
    if new_price < 0.1: new_price = 0.1 # সর্বনিম্ন দাম ০.১ রাখা

    # ডাটাবেসে নতুন দাম আপডেট
    db.admin_stats.update_one({"id": "global"}, {"$set": {"aaf_coin_price": new_price}})

    return jsonify({
        "price": new_price,
        "time": datetime.datetime.now().strftime("%H:%M:%S"),
        "trend": "down" if price_change < 0 else "up"
    })
