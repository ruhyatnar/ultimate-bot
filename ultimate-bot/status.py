#!/usr/bin/env python3
"""
CLI Real-Time Monitor for Ultimate Binance Trading Bot
Provides an htop/terminal-style live dashboard for headless Debian 13 VPS environments.

Usage:
  python3 status.py          # Single status snapshot
  python3 status.py --watch  # Continuous live-refresh monitor (every 2s)
"""

import os
import sys
import time
import json
import sqlite3
import argparse
from datetime import datetime
from http.server import HTTPServer, SimpleHTTPRequestHandler

# ANSI Color Codes for Debian CLI
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
MAGENTA = "\033[95m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"
CLEAR = "\033[2J\033[H"

def load_env(env_path=".env"):
    config = {}
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    config[k.strip()] = v.strip()
    return config

def get_process_status():
    lock_file = "/tmp/ultimate_bot.lock"
    if not os.path.exists(lock_file):
        return f"{RED}● STOPPED{RESET}"
    try:
        import fcntl
        with open(lock_file, "r") as f:
            try:
                fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
                fcntl.flock(f, fcntl.LOCK_UN)
                return f"{RED}● STOPPED (Lock released){RESET}"
            except BlockingIOError:
                return f"{GREEN}● RUNNING (Lock active){RESET}"
    except Exception:
        return f"{YELLOW}● UNKNOWN{RESET}"

def read_database(db_path):
    if not os.path.exists(db_path):
        return {"error": f"Database not found at {db_path}", "trades": [], "orders": [], "risk": {}, "stats": {}}

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10.0)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # Risk state
        risk_rows = cur.execute("SELECT key, value FROM risk_state").fetchall()
        risk = {row["key"]: row["value"] for row in risk_rows}

        # Active trades
        trades_rows = cur.execute("SELECT * FROM active_trades").fetchall()
        trades = [dict(row) for row in trades_rows]

        # Recent orders (last 25)
        orders_rows = cur.execute(
            "SELECT order_id, symbol, side, order_type, price, stop_price, quantity, executed_qty, status, created_at, updated_at, profit_loss, avg_fill_price FROM orders ORDER BY created_at DESC LIMIT 25"
        ).fetchall()
        orders = [dict(row) for row in orders_rows]

        # Aggregate trade statistics
        stats_row = cur.execute(
            "SELECT COUNT(*) as total_orders, "
            "SUM(CASE WHEN side='SELL' AND status='FILLED' THEN 1 ELSE 0 END) as closed_trades, "
            "SUM(CASE WHEN side='SELL' AND status='FILLED' AND profit_loss > 0 THEN 1 ELSE 0 END) as winning_trades, "
            "SUM(CASE WHEN side='SELL' AND status='FILLED' AND profit_loss < 0 THEN 1 ELSE 0 END) as losing_trades, "
            "SUM(CASE WHEN status='FILLED' THEN profit_loss ELSE 0 END) as total_pnl "
            "FROM orders"
        ).fetchone()

        stats = {
            "total_orders": stats_row["total_orders"] if stats_row else 0,
            "closed_trades": stats_row["closed_trades"] if stats_row and stats_row["closed_trades"] else 0,
            "winning_trades": stats_row["winning_trades"] if stats_row and stats_row["winning_trades"] else 0,
            "losing_trades": stats_row["losing_trades"] if stats_row and stats_row["losing_trades"] else 0,
            "total_realized_pnl": float(stats_row["total_pnl"] or 0.0) if stats_row else 0.0,
            "win_rate": round(
                (float(stats_row["winning_trades"] or 0) / float(stats_row["closed_trades"] or 1) * 100), 1
            ) if stats_row and (stats_row["closed_trades"] or 0) > 0 else 0.0
        }

        conn.close()
        return {"risk": risk, "trades": trades, "orders": orders, "stats": stats}
    except Exception as e:
        return {"error": str(e), "trades": [], "orders": [], "risk": {}, "stats": {}}

def format_timestamp(ts_ms):
    if not ts_ms:
        return "-"
    try:
        dt = datetime.fromtimestamp(int(ts_ms) / 1000)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return str(ts_ms)

def render_dashboard(env_config, db_path):
    status_str = get_process_status()
    db_data = read_database(db_path)
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")

    paper_mode = env_config.get("PAPER_TRADE", "true").lower() == "true"
    preset = env_config.get("PRESET", "day")
    symbols = env_config.get("STATIC_SYMBOLS", "BTCUSDT,ETHUSDT")

    output = []
    output.append(f"{BOLD}{CYAN}========================================================================{RESET}")
    output.append(f"{BOLD} BINANCE ULTIMATE BOT — LIVE CLI TERMINAL DASHBOARD {RESET}")
    output.append(f"{BOLD}{CYAN}========================================================================{RESET}")
    output.append(f"  Engine Status : {status_str}    Preset : {BOLD}{preset.upper()}{RESET}    Mode : {YELLOW if paper_mode else GREEN}{'PAPER TRADING' if paper_mode else 'LIVE PRODUCTION'}{RESET}")
    output.append(f"  System Time   : {now_str}    Monitored Symbols : {CYAN}{symbols}{RESET}")
    output.append(f"{CYAN}------------------------------------------------------------------------{RESET}")

    if "error" in db_data:
        output.append(f"  {YELLOW}Database info: {db_data['error']}{RESET}")
    else:
        risk = db_data.get("risk", {})
        daily_pnl = float(risk.get("daily_pnl", 0.0))
        paper_bal = float(risk.get("paper_balance", 1000.0))
        pnl_color = GREEN if daily_pnl >= 0 else RED

        output.append(f"{BOLD} ACCOUNT & RISK OVERVIEW{RESET}")
        if paper_mode:
            output.append(f"  Simulated Equity : {BOLD}${paper_bal:.2f} USDT{RESET}    Daily PnL : {pnl_color}${daily_pnl:+.2f} USDT{RESET}")
        else:
            output.append(f"  Daily PnL        : {pnl_color}${daily_pnl:+.2f} USDT{RESET}")

        trades = db_data.get("trades", [])
        output.append(f"\n{BOLD} ACTIVE POSITIONS ({len(trades)}){RESET}")
        if not trades:
            output.append(f"  {DIM}No open positions currently active.{RESET}")
        else:
            header = f"  {'SYMBOL':<10} {'SIDE':<6} {'ENTRY':<12} {'QTY':<10} {'STOP':<12} {'TP':<12} {'BE':<5}"
            output.append(f"{BOLD}{header}{RESET}")
            output.append("  " + "-" * 70)
            for t in trades:
                be = "YES" if t.get("breakeven_activated") else "NO"
                output.append(f"  {BOLD}{t['symbol']:<10}{RESET} {GREEN if t['side']=='BUY' else RED}{t['side']:<6}{RESET} {t['entry_price']:<12.4f} {t['quantity']:<10.4f} {t.get('stop_price', 0):<12.4f} {t.get('take_profit', 0):<12.4f} {be:<5}")

        orders = db_data.get("orders", [])
        output.append(f"\n{BOLD} RECENT ORDERS & FILLS (LAST 5){RESET}")
        if not orders:
            output.append(f"  {DIM}No recorded orders yet.{RESET}")
        else:
            header = f"  {'TIME':<19} {'SYMBOL':<10} {'SIDE':<6} {'PRICE':<10} {'QTY':<10} {'STATUS':<10}"
            output.append(f"{BOLD}{header}{RESET}")
            output.append("  " + "-" * 70)
            for o in orders:
                t_str = format_timestamp(o.get("created_at"))
                s_color = GREEN if o["status"] == "FILLED" else (YELLOW if o["status"] == "NEW" else RED)
                output.append(f"  {t_str:<19} {o['symbol']:<10} {o['side']:<6} {o.get('price', 0):<10.2f} {o.get('executed_qty', 0):<10.4f} {s_color}{o['status']:<10}{RESET}")

    output.append(f"\n{CYAN}------------------------------------------------------------------------{RESET}")
    output.append(f"  {DIM}Press Ctrl+C to exit monitor. Run 'pm2 logs ultimate-bot' for indicator debug streams.{RESET}")
    output.append(f"{CYAN}========================================================================{RESET}")

    return "\n".join(output)

def get_standalone_html():
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Ultimate Binance Bot - Web Monitor</title>
  <style>
    :root { --bg: #0b0f19; --card: #151d2e; --border: #243049; --text: #e2e8f0; --accent: #10b981; --danger: #f43f5e; --warn: #f59e0b; }
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, monospace; background: var(--bg); color: var(--text); margin: 0; padding: 20px; }
    .container { max-width: 1100px; margin: 0 auto; }
    .header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid var(--border); padding-bottom: 15px; margin-bottom: 20px; }
    .title { font-size: 1.25rem; font-weight: 700; color: #fff; }
    .badge { padding: 4px 10px; border-radius: 9999px; font-size: 0.75rem; font-weight: 600; text-transform: uppercase; }
    .badge-running { background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3); }
    .badge-stopped { background: rgba(244, 63, 94, 0.15); color: #fb7185; border: 1px solid rgba(244, 63, 94, 0.3); }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 15px; margin-bottom: 20px; }
    .card { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 15px; }
    .card-title { font-size: 0.75rem; text-transform: uppercase; color: #94a3b8; margin-bottom: 6px; letter-spacing: 0.05em; }
    .card-value { font-size: 1.35rem; font-weight: 700; color: #fff; }
    table { width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 0.85rem; }
    th { text-align: left; padding: 8px 12px; color: #94a3b8; border-bottom: 1px solid var(--border); }
    td { padding: 8px 12px; border-bottom: 1px solid rgba(36, 48, 73, 0.5); }
    .pnl-pos { color: #34d399; }
    .pnl-neg { color: #fb7185; }
    .time { font-size: 0.75rem; color: #64748b; }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <div>
        <div class="title">⚡ Binance Ultimate Trading Bot - Live Web Monitor</div>
        <div id="timestamp" class="time">Connecting to engine...</div>
      </div>
      <div id="statusBadge" class="badge badge-running">CHECKING...</div>
    </div>
    <div class="grid">
      <div class="card"><div class="card-title">Trading Mode</div><div id="tradingMode" class="card-value">-</div></div>
      <div class="card"><div class="card-title">Strategy Preset</div><div id="preset" class="card-value">-</div></div>
      <div class="card"><div class="card-title">Signal Threshold</div><div id="signalThresh" class="card-value">-</div></div>
      <div class="card"><div class="card-title">Daily Realized PnL</div><div id="dailyPnl" class="card-value">-</div></div>
    </div>
    <div class="card" style="margin-bottom: 20px;">
      <div class="card-title">Active Market Positions</div>
      <div id="positionsTable">Loading positions...</div>
    </div>
    <div class="card">
      <div class="card-title">Recent Orders & Fills</div>
      <div id="ordersTable">Loading orders...</div>
    </div>
  </div>
  <script>
    async function updateStatus() {
      try {
        const res = await fetch('/api/status');
        const data = await res.json();
        document.getElementById('timestamp').innerText = 'Last updated: ' + data.timestamp + ' • Auto-refreshes every 2s';
        const badge = document.getElementById('statusBadge');
        if (data.process.includes('RUNNING')) {
          badge.className = 'badge badge-running';
          badge.innerText = '● ENGINE RUNNING';
        } else {
          badge.className = 'badge badge-stopped';
          badge.innerText = '● ENGINE STOPPED';
        }
        document.getElementById('tradingMode').innerText = data.config.PAPER_TRADE === 'true' ? 'PAPER (Simulated)' : 'LIVE REAL FUNDS';
        document.getElementById('tradingMode').style.color = data.config.PAPER_TRADE === 'true' ? '#38bdf8' : '#fbbf24';
        document.getElementById('preset').innerText = (data.config.PRESET || 'DAY').toUpperCase();
        document.getElementById('signalThresh').innerText = (data.config.SIGNAL_THRESHOLD || '4') + ' / 5 Confluence';
        const pnlVal = data.data.risk ? parseFloat(data.data.risk.daily_pnl || 0) : 0;
        const pnlEl = document.getElementById('dailyPnl');
        pnlEl.innerText = (pnlVal >= 0 ? '+' : '') + pnlVal.toFixed(2) + ' USDT';
        pnlEl.className = 'card-value ' + (pnlVal >= 0 ? 'pnl-pos' : 'pnl-neg');

        const trades = data.data.trades || [];
        if (trades.length === 0) {
          document.getElementById('positionsTable').innerHTML = '<div style="color: #64748b; padding: 12px;">No active open positions.</div>';
        } else {
          let html = '<table><thead><tr><th>Symbol</th><th>Side</th><th>Entry Price</th><th>Quantity</th><th>Stop Loss</th><th>Take Profit</th><th>Breakeven</th></tr></thead><tbody>';
          trades.forEach(t => {
            html += `<tr><td><strong>${t.symbol}</strong></td><td style="color:${t.side==='BUY'?'#34d399':'#fb7185'}">${t.side}</td><td>$${parseFloat(t.entry_price).toFixed(4)}</td><td>${parseFloat(t.quantity).toFixed(4)}</td><td>$${parseFloat(t.stop_price||0).toFixed(4)}</td><td>$${parseFloat(t.take_profit||0).toFixed(4)}</td><td>${t.breakeven_activated?'<span style="color:#34d399">LOCKED</span>':'No'}</td></tr>`;
          });
          html += '</tbody></table>';
          document.getElementById('positionsTable').innerHTML = html;
        }

        const orders = data.data.orders || [];
        if (orders.length === 0) {
          document.getElementById('ordersTable').innerHTML = '<div style="color: #64748b; padding: 12px;">No recent orders recorded.</div>';
        } else {
          let html = '<table><thead><tr><th>Time</th><th>Symbol</th><th>Side</th><th>Price</th><th>Qty</th><th>Status</th></tr></thead><tbody>';
          orders.forEach(o => {
            html += `<tr><td class="time">${o.created_at || '-'}</td><td><strong>${o.symbol}</strong></td><td style="color:${o.side==='BUY'?'#34d399':'#fb7185'}">${o.side}</td><td>$${parseFloat(o.price||0).toFixed(2)}</td><td>${parseFloat(o.executed_qty||0).toFixed(4)}</td><td><span style="color:#34d399">${o.status}</span></td></tr>`;
          });
          html += '</tbody></table>';
          document.getElementById('ordersTable').innerHTML = html;
        }
      } catch (e) {
        console.error('Failed to fetch status', e);
      }
    }
    updateStatus();
    setInterval(updateStatus, 2000);
  </script>
</body>
</html>"""

def start_web_server(port, env_config, db_path):
    dist_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "dist"))
    has_dist = os.path.isdir(dist_dir) and os.path.isfile(os.path.join(dist_dir, "index.html"))

    class CustomHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            if has_dist:
                super().__init__(*args, directory=dist_dir, **kwargs)
            else:
                super().__init__(*args, **kwargs)

        def log_message(self, format, *args):
            pass  # Keep output quiet like a production server

        def send_cors_headers(self):
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With")

        def do_OPTIONS(self):
            self.send_response(200)
            self.send_cors_headers()
            self.end_headers()

        def do_GET(self):
            clean_path = self.path.split("?")[0]
            if clean_path in ["/api/status", "/api"]:
                db_data = read_database(db_path)
                status_str = get_process_status()
                clean_status = status_str.replace(GREEN, "").replace(RED, "").replace(YELLOW, "").replace(RESET, "")
                safe_config = {k: v for k, v in env_config.items() if "KEY" not in k and "SECRET" not in k and "WEBHOOK" not in k}
                payload = {
                    "process": clean_status,
                    "config": safe_config,
                    "data": db_data,
                    "server_time": datetime.now().isoformat(),
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                data_bytes = json.dumps(payload, default=str).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_cors_headers()
                self.send_header("Content-Length", str(len(data_bytes)))
                self.end_headers()
                self.wfile.write(data_bytes)
                return

            if clean_path == "/api/health":
                status_str = get_process_status()
                clean_status = status_str.replace(GREEN, "").replace(RED, "").replace(YELLOW, "").replace(RESET, "")
                payload = {
                    "status": "ok",
                    "engine": clean_status,
                    "db_exists": os.path.exists(db_path),
                    "timestamp": datetime.now().isoformat()
                }
                data_bytes = json.dumps(payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_cors_headers()
                self.send_header("Content-Length", str(len(data_bytes)))
                self.end_headers()
                self.wfile.write(data_bytes)
                return

            if clean_path == "/api/config":
                safe_config = {k: v for k, v in env_config.items() if "KEY" not in k and "SECRET" not in k and "WEBHOOK" not in k}
                data_bytes = json.dumps(safe_config).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_cors_headers()
                self.send_header("Content-Length", str(len(data_bytes)))
                self.end_headers()
                self.wfile.write(data_bytes)
                return

            if has_dist:
                req_path = os.path.join(dist_dir, self.path.lstrip("/"))
                if not os.path.exists(req_path) and "." not in os.path.basename(self.path):
                    self.path = "/index.html"
                super().do_GET()
            else:
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_cors_headers()
                html = get_standalone_html()
                html_bytes = html.encode("utf-8")
                self.send_header("Content-Length", str(len(html_bytes)))
                self.end_headers()
                self.wfile.write(html_bytes)

    server = HTTPServer(("0.0.0.0", port), CustomHandler)
    print(f"{GREEN}{BOLD}⚡ Binance Bot Web Monitor running at:{RESET}")
    print(f"   {CYAN}http://0.0.0.0:{port}{RESET} (Local & VPS IP)")
    if has_dist:
        print(f"   {DIM}Mode: Serving compiled interactive React Web Dashboard from ./dist{RESET}")
    else:
        print(f"   {DIM}Mode: Serving standalone dark-mode monitoring dashboard (Auto-refreshing){RESET}")
    print(f"   {DIM}Press Ctrl+C to stop the web server.{RESET}\n")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print(f"\n{YELLOW}Stopping web monitor.{RESET}")
        server.server_close()

def main():
    parser = argparse.ArgumentParser(description="Binance Bot CLI & Web Terminal Dashboard")
    parser.add_argument("--watch", "-w", action="store_true", help="Continuously refresh terminal every 2 seconds")
    parser.add_argument("--interval", "-i", type=int, default=2, help="Terminal refresh interval in seconds")
    parser.add_argument("--web", type=int, nargs="?", const=3000, help="Launch HTTP web monitoring server on specified port (default: 3000)")
    args = parser.parse_args()

    env_config = load_env(".env")
    db_path = env_config.get("DB_PATH", "./data/trading.db")

    if args.web is not None:
        start_web_server(args.web, env_config, db_path)
        return

    if not args.watch:
        print(render_dashboard(env_config, db_path))
        return

    try:
        while True:
            sys.stdout.write(CLEAR)
            sys.stdout.write(render_dashboard(env_config, db_path) + "\n")
            sys.stdout.flush()
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nExiting monitor.")

if __name__ == "__main__":
    main()
