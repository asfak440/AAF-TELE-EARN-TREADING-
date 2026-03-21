<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AAF Strong - Master Dashboard</title>
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <style>
        :root { 
            --primary: #39d353; --bg: #0d1117; --card-bg: #161b22;
            --border: #30363d; --text-gray: #8b949e; --accent-cyan: #00ffcc; --gold: #f1c40f;
        }
        body { background: var(--bg); color: #f0f6fc; font-family: 'Inter', sans-serif; margin: 0; padding-bottom: 90px; }
        
        /* Top Bar */
        .top-bar { padding: 20px; display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border); background: var(--card-bg); position: sticky; top: 0; z-index: 1000; }
        .user-info h3 { margin: 0; font-size: 18px; color: var(--primary); }
        .user-info span { font-size: 11px; color: var(--text-gray); }

        .container { padding: 15px; }

        /* Balance Cards */
        .balance-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 15px; }
        .card { background: var(--card-bg); padding: 18px; border-radius: 12px; border: 1px solid var(--border); transition: 0.3s; }
        .card:active { transform: scale(0.98); }

        .card.main-tk { grid-column: span 2; background: linear-gradient(135deg, #1c2128 0%, #0d1117 100%); border-color: var(--primary); display: flex; justify-content: space-between; align-items: center; }
        .card.aaf-coin { grid-column: span 2; border-color: var(--gold); background: rgba(241, 196, 15, 0.05); }

        .card h4 { margin: 0; font-size: 10px; color: var(--text-gray); text-transform: uppercase; letter-spacing: 0.5px; }
        .card p { margin: 8px 0 0; font-size: 24px; font-weight: bold; }
        .currency-label { font-size: 14px; color: var(--primary); margin-right: 4px; }
        .coin-label { font-size: 14px; color: var(--gold); margin-left: 5px; }

        .action-btns { display: flex; gap: 8px; }
        .btn-sm { background: var(--primary); color: black; padding: 8px 12px; border-radius: 8px; font-size: 11px; text-decoration: none; font-weight: bold; text-align: center; }
        .btn-gold { background: var(--gold); }

        /* Income Details */
        .income-details { background: var(--card-bg); border-radius: 15px; padding: 15px; border: 1px solid var(--border); margin-bottom: 15px; }
        .income-row { display: flex; justify-content: space-between; padding: 10px 0; border-bottom: 1px solid #30363d; font-size: 13px; }
        .income-row:last-child { border-bottom: none; }

        /* Footer Nav */
        .slim-nav { position: fixed; bottom: 0; left: 0; width: 100%; height: 70px; background: #0d1117; display: flex; justify-content: space-around; align-items: center; border-top: 1px solid var(--border); z-index: 9999; }
        .nav-item { text-decoration: none; color: var(--text-gray); text-align: center; flex: 1; font-size: 10px; transition: 0.3s; }
        .nav-item i { font-size: 20px; margin-bottom: 4px; display: block; }
        .nav-item.active { color: var(--primary); font-weight: bold; }

        .status-badge { padding: 6px 12px; border-radius: 8px; font-size: 11px; font-weight: bold; text-decoration: none; display: inline-block; }
        .active-bg { background: var(--primary); color: black; }
        .inactive-bg { background: #ea2027; color: white; }
        .btn-logout { background: transparent; border: 1px solid #ff4d4d; color: #ff4d4d; padding: 8px; border-radius: 8px; cursor: pointer; }
    </style>
</head>
<body>

    <div class="top-bar">
        <div class="user-info">
            <h3 id="u-name">Loading...</h3>
            <span id="u-id">UID: #AAF-------</span>
        </div>
        <div style="text-align:right;">
            <div id="status-dot" style="color: var(--primary); font-size: 12px; font-weight: bold;">● Online</div>
            <div style="font-size: 9px; color: var(--text-gray);">v2.0 Real-Time</div>
        </div>
    </div>

    <div class="container">
        
        <div class="card" style="margin-bottom: 15px; border-color: rgba(57, 211, 83, 0.2);">
            <p style="margin: 0 0 10px 0; font-size: 10px; color: var(--text-gray); text-transform: uppercase;">
                <i class="fas fa-server"></i> Server Account Analytics
            </p>
            <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 8px;">
                <div style="text-align: center;">
                    <h4 style="font-size: 8px;">TOTAL</h4>
                    <p style="font-size: 16px; margin-top: 5px;" id="total-added">0</p>
                </div>
                <div style="text-align: center; color: var(--primary);">
                    <h4 style="font-size: 8px;">ACTIVE</h4>
                    <p style="font-size: 16px; margin-top: 5px;" id="active-count">0</p>
                </div>
                <div style="text-align: center; color: #ea2027;">
                    <h4 style="font-size: 8px;">OFFLINE</h4>
                    <p style="font-size: 16px; margin-top: 5px;" id="inactive-count">0</p>
                </div>
            </div>
        </div>

        <div class="card main-tk">
            <div>
                <h4><i class="fas fa-wallet"></i> Main Balance</h4>
                <p><span class="currency-label">৳</span><span id="m-bal">0.00</span></p>
            </div>
            <div class="action-btns">
                <a href="/withdraw" class="btn-sm">Withdraw</a>
            </div>
        </div>

        <div class="balance-grid" style="margin-top: 15px;">
            <div class="card aaf-coin">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <div>
                        <h4><i class="fas fa-coins"></i> AAF Coin</h4>
                        <p><span id="aaf-bal" style="color: var(--gold);">0.00</span><span class="coin-label">AAF</span></p>
                    </div>
                    <a href="/trading" class="btn-sm btn-gold">Convert</a>
                </div>
            </div>
        </div>

        <div class="income-details">
            <div class="income-row"><span>Task Income</span><span id="task-inc">0.00 AAF</span></div>
            <div class="income-row"><span>Trading Profit</span><span id="trade-profit">৳ 0.00</span></div>
            <div class="income-row"><span>24h Bonus</span><span id="bonus-inc">0.00 AAF</span></div>
        </div>

        <div class="card">
            <div style="display: flex; justify-content: space-between; align-items: center;">
                <div>
                    <p style="margin: 0; font-size: 14px; font-weight: bold;" id="u-phone">Checking...</p>
                    <small id="bonus-status" style="color: #ff4d4d;">❌ চ্যানেল জয়েন করুন</small>
                </div>
                <div style="display: flex; gap: 8px; align-items: center;">
                    <a href="https://t.me/aaf_tele_earn" id="status-btn" target="_blank" class="status-badge inactive-bg">JOIN</a>
                    <button class="btn-logout" onclick="confirmLogout()"><i class="fas fa-power-off"></i></button>
                </div>
            </div>
        </div>
    </div>

    <nav class="slim-nav">
        <a href="/dashboard" class="nav-item active"><i class="fas fa-home"></i><span>Home</span></a>
        <a href="/task" class="nav-item"><i class="fas fa-tasks"></i><span>Task</span></a>
        <a href="/trading" class="nav-item"><i class="fas fa-chart-line"></i><span>Trade</span></a>
        <a href="/account" class="nav-item"><i class="fas fa-user-circle"></i><span>Account</span></a>
        <a href="/wallet" class="nav-item"><i class="fas fa-wallet"></i><span>Wallet</span></a>
    </nav>

    <script>
        // ইউজার আইডি চেক
        const USER_ID = localStorage.getItem('user_id');
        if (!USER_ID) { window.location.href = "/login"; }

        // সার্ভার থেকে ডাটা আনা
        async function loadDashboardData() {
            try {
                const response = await fetch(`/api/user_profile/${USER_ID}`);
                const data = await response.json();

                if (data.status === "success") {
                    // UI আপডেট
                    document.getElementById('u-name').innerText = data.name || "User";
                    document.getElementById('u-id').innerText = "UID: #AAF" + data.telegram_id;
                    document.getElementById('u-phone').innerText = data.phone;
                    document.getElementById('m-bal').innerText = parseFloat(data.main_balance).toFixed(2);
                    document.getElementById('aaf-bal').innerText = parseFloat(data.aaf_balance || 0).toFixed(2);
                    
                    document.getElementById('task-inc').innerText = (data.task_income || 0).toFixed(2) + " AAF";
                    document.getElementById('bonus-inc').innerText = (data.daily_bonus_total || 0).toFixed(2) + " AAF";
                    document.getElementById('trade-profit').innerText = "৳ " + (data.trade_profit || 0).toFixed(2);

                    document.getElementById('total-added').innerText = data.total_accounts || 0;
                    document.getElementById('active-count').innerText = data.active_accounts || 0;
                    document.getElementById('inactive-count').innerText = (data.total_accounts - data.active_accounts) || 0;

                    updateBonusUI(data.is_joined_channel);
                }
            } catch (err) {
                console.error("Error loading data:", err);
                document.getElementById('status-dot').innerText = "● Offline";
                document.getElementById('status-dot').style.color = "red";
            }
        }

        function updateBonusUI(isJoined) {
            const btn = document.getElementById('status-btn');
            const text = document.getElementById('bonus-status');
            if (isJoined) {
                btn.innerText = "ACTIVE";
                btn.className = "status-badge active-bg";
                text.style.color = "#39d353";
                text.innerHTML = "✅ বোনাস সচল আছে";
            }
        }

        function confirmLogout() {
            if (confirm("আপনি কি লগআউট করতে চান?")) {
                localStorage.clear();
                window.location.href = "/login";
            }
        }

        // পেজ লোড হলে ফাংশনটি চলবে
        window.onload = loadDashboardData;
    </script>
</body>
</html>
