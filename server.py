import sqlite3
from flask import Flask, request, jsonify
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

DB_PATH = 'aaf_trading.db'

# ১. ডাটাবেস ইনিশিয়ালাইজেশন (সব টেবিল এখানে তৈরি হবে)
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # ট্রেড হিস্টোরি টেবিল
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            invest_amount REAL,
            fee_amount REAL,
            active_invest REAL,
            entry_price REAL,
            status TEXT DEFAULT 'OPEN',
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # উইথড্র রিকোয়েস্ট টেবিল (নতুন)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS withdrawals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            method TEXT,
            number TEXT,
            amount REAL,
            status TEXT DEFAULT 'Pending',
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()

init_db()

# ২. ট্রেড প্লেস করার রুট (১০% ফি সহ)
@app.route('/api/place_trade', methods=['POST'])
def place_trade():
    data = request.json
    user_id = data.get('user_id', 'Guest')
    amount = float(data.get('amount'))
    entry_price = float(data.get('entry_price'))

    fee = amount * 0.10
    active_invest = amount - fee

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO trades (user_id, invest_amount, fee_amount, active_invest, entry_price)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, amount, fee, active_invest, entry_price))
    conn.commit()
    conn.close()
    return jsonify({"status": "success", "fee": fee})

# ৩. উইথড্র রিকোয়েস্ট গ্রহণ করার রুট (নতুন)
@app.route('/api/withdraw', methods=['POST'])
def withdraw():
    data = request.json
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('''
        INSERT INTO withdrawals (user_id, method, number, amount)
        VALUES (?, ?, ?, ?)
    ''', (data['user_id'], data['method'], data['number'], data['amount']))
    conn.commit()
    conn.close()
    return jsonify({"status": "success"})

# ৪. অ্যাডমিন প্যানেলের জন্য উইথড্র লিস্ট (নতুন)
@app.route('/api/admin/withdraw_list', methods=['GET'])
def get_withdraws():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, user_id, number, amount FROM withdrawals WHERE status='Pending'")
    rows = cursor.fetchall()
    requests = [{"id": r[0], "user_id": r[1], "number": r[2], "amount": r[3]} for r in rows]
    conn.close()
    return jsonify({"requests": requests})

# ৫. মোট অ্যাডমিন ইনকাম দেখা
@app.route('/api/admin/total_earnings', methods=['GET'])
def get_earnings():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute('SELECT SUM(fee_amount) FROM trades')
    total_fee = cursor.fetchone()[0]
    conn.close()
    return jsonify({"total_admin_profit": total_fee or 0})

# ৬. মার্কেট প্রাইস (সিমুলেশন)
@app.route('/api/aaf_market', methods=['GET'])
def get_market():
    return jsonify({"aaf_price_bdt": 1.25})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
