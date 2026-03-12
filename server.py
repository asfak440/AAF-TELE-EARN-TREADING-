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
def index(): return "AAF Server is Online!"

@app.route('/admin/stats', methods=['GET'])
def get_admin_stats():
    total_users = db.users.count_documents({})
    return jsonify({"total_users": total_users, "status": "Online"})

# --- উইথড্র রিকোয়েস্ট রিসিভ ---
@app.route('/api/withdraw', methods=['POST'])
def handle_withdraw():
    data = request.json
    db.withdrawals.insert_one({
        "user_id": data.get('user_id'),
        "phone": data.get('phone'),
        "amount": data.get('amount'),
        "status": "Pending",
        "date": datetime.datetime.now()
    })
    return jsonify({"status": "success"})

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
