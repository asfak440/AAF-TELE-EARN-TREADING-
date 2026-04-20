import os
import random
import time
from datetime import datetime, timedelta
from threading import Thread
from functools import wraps
from flask import Flask, render_template, request, jsonify, session, redirect, url_for
from flask_cors import CORS
from pymongo import MongoClient
from telethon.sync import TelegramClient
from telethon.sessions import StringSession
from telethon.errors import SessionPasswordNeededError
from bson import ObjectId
import firebase_admin
from firebase_admin import credentials, db

# ---------------------------------------------------------
# ১. কনফিগারেশন ও ডাটাবেস সেটআপ
# ---------------------------------------------------------

# সেশন সিকিউরিটি
app.config.update(
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=True,
    SESSION_COOKIE_HTTPONLY=True,
    PERMANENT_SESSION_LIFETIME=timedelta(days=10)

# ================= APP =================
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "aaf_strong_secure_786")

CORS(app, supports_credentials=True)

# ================= DB =================
db = MongoClient(os.getenv("MONGO_URL"))["aaf_tele_earn_db"]

users = db.users
tasks = db.tasks
wallet = db.wallet
ledger = db.ledger
ref_log = db.referrals
withdraws = db.withdraws
settings = db.settings
otp = db.otp

#=============


@app.route('/')
def index():
    if 'uid' in session: return redirect(url_for('render_dashboard_page'))
    return render_template('login.html')

@app.route('/dashboard')
@login_required
def render_dashboard_page(): 
    user = users_col.find_one({"telegram_id": int(session['uid'])})
    admin = settings_col.find_one({"type": "global"}) or {}
    return render_template('dashboard.html', user=user, admin=admin)

@app.route('/task')
@login_required
def render_task_page(): return render_template('task.html')

@app.route('/trading')
@login_required
def render_treading_page(): return render_template('trading.html')

@app.route('/wallet')
@login_required
def render_wallet_page(): return render_template('wallet.html')

@app.route('/account')
@login_required
def render_account_page(): return render_template('account.html')

@app.route('/refer_list')
@login_required
def render_refer_page(): return render_template('refer_list.html')

@app.route('/payment_history')
@login_required
def render_history_page(): return render_template('payment_history.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('index'))
    
# ================= HELPERS =================
def ok(data=None):
    return jsonify({"success": True, "data": data})

def err(msg):
    return jsonify({"success": False, "message": msg})

def get_user(uid):
    if not ObjectId.is_valid(uid):
        return None
    return users.find_one({"_id": ObjectId(uid)})

# ================= REF BONUS =================
def give_ref_bonus(ref_id):
    users.update_one(
        {"_id": ObjectId(ref_id)},
        {"$inc": {"cash": 10, "refer_count": 1}}
    )

# ================= LOGIN =================
@app.route("/api/send_otp", methods=["POST"])
def send_otp():
    phone = request.json.get("phone")
    code = str(random.randint(1000,9999))

    otp.insert_one({"phone": phone, "code": code, "time": time.time()})
    return ok({"otp": code})

@app.route("/api/verify_login", methods=["POST"])
def verify_login():
    data = request.json
    phone = data.get("phone")
    code = data.get("code")
    ref = data.get("ref")

    if not otp.find_one({"phone": phone, "code": code}):
        return err("invalid_otp")

    user = users.find_one({"phone": phone})

    if not user:
        res = users.insert_one({
            "phone": phone,
            "cash": 0,
            "aaf": 0,
            "refer_count": 0,
            "ref_by": ref,
            "is_joined": False,
            "created_at": datetime.now(),
            "ip": request.remote_addr
        })

        uid = res.inserted_id

        if ref:
            give_ref_bonus(ref)
    else:
        uid = user["_id"]

    session["uid"] = str(uid)

    return ok({"user_id": str(uid)})

# ================= USER =================
@app.route("/api/user/data/<uid>")
def user_data(uid):
    user = get_user(uid)
    if not user:
        return err("not_found")

    user["_id"] = str(user["_id"])
    admin = settings.find_one({"type":"global"}) or {}

    return jsonify({"success": True, "user": user, "admin": admin})

# ================= JOIN =================
@app.route("/api/silent_join", methods=["POST"])
def join():
    uid = session.get("uid")
    users.update_one({"_id": ObjectId(uid)}, {"$set":{"is_joined":True}})
    return ok()

# ================= TASK =================
@app.route("/api/task/claim", methods=["POST"])
def claim():
    uid = session.get("uid")
    data = request.json

    task = tasks.find_one({"_id": ObjectId(data["task_id"])})
    if not task:
        return err("invalid")

    # repeat prevention
    if tasks.find_one({"_id": task["_id"], "claimed_by": uid}):
        return err("already_done")

    reward = task["reward"]

    users.update_one(
        {"_id": ObjectId(uid)},
        {"$inc":{"cash": reward}}
    )

    tasks.update_one(
        {"_id": task["_id"]},
        {"$push":{"claimed_by": uid}}
    )

    return ok("done")

# ================= WALLET LEDGER =================
@app.route("/api/wallet/deposit", methods=["POST"])
def deposit():
    data = request.json
    ledger.insert_one({
        "uid": data["telegram_id"],
        "type": "deposit",
        "amount": data["amount"],
        "status": "pending",
        "time": datetime.now()
    })
    return ok()

@app.route("/api/wallet/withdraw", methods=["POST"])
def withdraw():
    data = request.json
    ledger.insert_one({
        "uid": data["telegram_id"],
        "type": "withdraw",
        "amount": data["amount"],
        "status": "pending",
        "time": datetime.now()
    })
    return ok()

# ================= ADMIN =================
@app.route("/api/admin/login", methods=["POST"])
def admin_login():
    if request.json.get("pin") == os.getenv("ADMIN_PIN","1234"):
        session["admin"] = True
        return ok()
    return err("no")

@app.route("/api/admin/withdraw/approve", methods=["POST"])
def approve():
    wid = request.json.get("id")

    ledger.update_one(
        {"_id": ObjectId(wid)},
        {"$set":{"status":"approved"}}
    )

    return ok()

# ================= RUN =================
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port, debug=False)
