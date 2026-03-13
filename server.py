import sqlite3
from flask import Flask, request, jsonify
from flask_cors import CORS
from Crypto.Cipher import AES
import base64

app = Flask(__name__)
CORS(app)

# Encryption Key (আপনার এটি ৩২ ক্যারেক্টার হতে হবে)
KEY = b'AAF_STRONG_APP_SECURE_32_BIT_KEY'

def encrypt(data):
    cipher = AES.new(KEY, AES.MODE_EAX)
    nonce = cipher.nonce
    ciphertext, tag = cipher.encrypt_and_digest(data.encode())
    return base64.b64encode(nonce + ciphertext).decode()

# টাস্ক ভেরিফিকেশন এপিআই (বট এটি ব্যবহার করবে)
@app.route('/api/verify_task', methods=['POST'])
def verify_task():
    data = request.json
    user_id = data.get('user_id')
    # এখানে টেলিগ্রাম বটের মাধ্যমে চেক করা হবে ইউজার চ্যানেলে জয়েন করেছে কি না
    is_joined = True # সিমুলেশন
    
    if is_joined:
        return jsonify({"status": "success", "reward": 0.08})
    else:
        return jsonify({"status": "fail", "message": "Join Channel First"})

@app.route('/api/get_aaf_price', methods=['GET'])
def get_price():
    # লজিক: ইউজার একটিভিটি বেশি হলে দাম বাড়বে, উইথড্র বেশি হলে কমবে
    current_price = 1.25 # ডাইনামিক লজিক এখানে বসবে
    return jsonify({"price": current_price})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
