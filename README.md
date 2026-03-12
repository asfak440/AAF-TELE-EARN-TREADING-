# 📱 AAF TELE-EARN-TRADING
**The ultimate Telegram-based earning and trading ecosystem.**

## 🌟 Overview
AAF Tele-Earn-Trading is a powerful platform that combines Telegram automation with micro-task earning and a professional trading simulator. Users can link multiple Telegram accounts, complete tasks, and trade the native **AAF Coin**.

## 🛠 Features & Rules
- **Multi-Account Login:** Link multiple Telegram accounts via API (`api_id: 36466824`).
- **Micro-Tasks:** Earn **0.08 BDT** per task. Verified by `@aaf_tele_earn_bot`.
- **AAF Trading:** Professional candlestick charts with a custom price algorithm.
- **Withdrawal:** Minimum **50 BDT** via Nagad. Requires 5+ active Telegram accounts.
- **Security:** AES Encryption for sessions and JWT for secure login.

## 📊 Business Logic (Admin Control)
- **Activity Rule:** Income stops if no tasks are done within 24 hours.
- **Price Control:** AAF coin price drops if withdrawal ratio hits 90%.
- **Automatic Logout:** Sessions expire after 30 days for security.

## 🚀 Technical Setup
- **Backend:** Python (Flask) in `server.py`.
- **Database:** MongoDB Atlas (Cluster0).
- **Frontend:** Flutter/Dart (located in `lib/`).

---
*Developed with ❤️ for the AAF Community.*
