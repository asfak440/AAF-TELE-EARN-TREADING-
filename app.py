import os
import asyncio
import nest_asyncio
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from pymongo import MongoClient

# ইভেন্ট লুপ ফিক্স
nest_asyncio.apply()

app = Flask(__name__)
CORS(app)

# ডাটাবেস কানেকশন
MONGO_URI = "mongodb+srv://abdullahasfakfarvezbd_db_user:Abdullah6790@cluster0.rmulyqq.mongodb.net/?appName=Cluster0"
client_db = MongoClient(MONGO_URI)
db = client_db['AAF_TeleEarn']
users_col = db['users']

# আপনার সবকটি HTML পেজ কানেক্ট করা হলো
@app.route('/')
@app.route('/dashboard')
def dashboard(): return render_template('dashboard.html')

@app.route('/login')
def login(): return render_template('login.html')

@app.route('/task')
def task(): return render_template('task.html')

@app.route('/trading')
def trading(): return render_template('trading.html')

@app.route('/wallet')
def wallet(): return render_template('wallet.html')

@app.route('/accounts')
def accounts(): return render_template('accounts.html')

# সার্ভার কানেকশন চেক করার এপিআই
@app.route('/api/status', methods=['GET'])
def status(): return jsonify({"status": "online"})

# পোর্ট ফিক্স
if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
