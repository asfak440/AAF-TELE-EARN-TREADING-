import os
import asyncio
import nest_asyncio
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from pymongo import MongoClient

nest_asyncio.apply()

app = Flask(__name__)
CORS(app)

# ডাটাবেস
MONGO_URI = "mongodb+srv://abdullahasfakfarvezbd_db_user:Abdullah6790@cluster0.rmulyqq.mongodb.net/?appName=Cluster0"
client_db = MongoClient(MONGO_URI)
db = client_db['AAF_TeleEarn']
users_col = db['users']

@app.route('/')
@app.route('/dashboard')
def dashboard(): return render_template('dashboard.html')

@app.route('/login')
def login(): return render_template('login.html')

@app.route('/task')
def task(): return render_template('task.html')

@app.route('/trading')
def trading(): return render_template('trading.html')

@app.route('/accounts')
def accounts(): return render_template('accounts.html')

@app.route('/wallet')
def wallet(): return render_template('wallet.html')

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 10000))
    app.run(host='0.0.0.0', port=port)
