import sqlite3
from flask import Flask, request, jsonify
from flask_cors import CORS # গিটহাব পেজ থেকে এক্সেস করার জন্য জরুরি

app = Flask(__name__)
CORS(app) # এটি আপনার এপিআইকে সব জায়গা থেকে কাজ করার অনুমতি দেবে

# ডাটাবেস ফাইল পাথ
DB_PATH = 'aaf_trading.db'

# ডাটাবেস টেবিল তৈরি করা
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # ট্রেড টেবিল: যেখানে ইনভেস্টমেন্ট এবং ফি জমা থাকবে
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            invest_amount REAL,
            fee_amount REAL,
            active_invest REAL,
            entry_price REAL,
            close_price REAL,
            status TEXT DEFAULT 'OPEN',
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# ১. নতুন ট্রেড প্লেস করা (১০% ফি কাটার লজিক সহ)
@app.route('/api/place_trade', methods=['POST'])
def place_trade():
    try:
        data = request.json
        user_id = data.get('user_id', 'Guest')
        raw_amount = float(data.get('amount'))
        entry_price = float(data.get('entry_price'))

        # আপনার লজিক: ১০% ফি অ্যাডমিন পাবে
        fee = raw_amount * 0.10
        active_invest = raw_amount - fee

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO trades (user_id, invest_amount, fee_amount, active_invest, entry_price)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, raw_amount, fee, active_invest, entry_price))
        
        trade_id = cursor.lastrowid
        conn.commit()
        conn.close()

        return jsonify({
            "status": "success",
            "trade_id": trade_id,
            "fee_charged": fee,
            "active_invest": active_invest
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 400

# ২. অ্যাডমিন প্যানেলের জন্য আয় দেখা
@app.route('/api/admin/total_earnings', methods=['GET'])
def get_earnings():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    # মোট ফি (Admin Profit) যোগফল
    cursor.execute('SELECT SUM(fee_amount) FROM trades')
    total_fee = cursor.fetchone()[0]
    
    # মোট কয়টি ট্রেড হয়েছে
    cursor.execute('SELECT COUNT(id) FROM trades')
    total_trades = cursor.fetchone()[0]
    
    conn.close()
    return jsonify({
        "total_admin_profit": total_fee or 0,
        "total_trades_count": total_trades or 0
    })

# ৩. লাইভ প্রাইস ডাটা (আপনার ট্রেডিং পেজের জন্য)
@app.route('/api/aaf_market', methods=['GET'])
def get_market():
    # এখানে আপনি সোলানা বা আপনার কাস্টম প্রাইস রিটার্ন করতে পারেন
    # ডামি হিসেবে ১.২৫ রিটার্ন করছি
    return jsonify({
        "aaf_price_bdt": 1.25, 
        "currency": "BDT"
    })

# সার্ভার রান করার শেষ পোর্টিং কোড
if __name__ == '__main__':
    # Render বা অন্য প্ল্যাটফর্মে হোস্টিংয়ের জন্য পোর্ট 5000 বা 8080 ব্যবহার করা হয়
    app.run(host='0.0.0.0', port=5000, debug=False)
