#!/usr/bin/env python3
"""
CLI & Web Real-Time Monitor for Ultimate Binance Trading Bot
Provides an htop/terminal-style live dashboard and comprehensive HTTP API for headless Debian 13 VPS environments.

Usage:
  python3 status.py          # Single status snapshot
  python3 status.py --watch  # Continuous live-refresh terminal monitor (every 2s)
  python3 status.py --web    # Launch HTTP monitoring server on port 3000 (serves React dist or standalone HTML)
"""

import os
import re
import sys
import time
import json
import uuid
import sqlite3
import argparse
import gzip
import mimetypes
import shutil
import subprocess
import urllib.request
import urllib.parse
import hmac
import hashlib
from datetime import datetime
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

# ANSI Color Codes for Terminal Display
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
CYAN = "\033[96m"
MAGENTA = "\033[95m"
BOLD = "\033[1m"
DIM = "\033[2m"
RESET = "\033[0m"
CLEAR = "\033[2J\033[H"

# In-memory TTL caches to prevent excessive I/O and respect exchange rate limits
_balance_cache = {"ts": 0, "data": None}
_scanned_cache = {"ts": 0, "data": None}
_tickers_cache = {"ts": 0, "data": {}}


def find_env_path(hint=None):
    if hint and os.path.isfile(hint):
        return os.path.abspath(hint)
    candidates = [
        ".env",
        os.path.join(os.path.dirname(__file__), ".env"),
        os.path.join(os.path.dirname(__file__), "..", ".env"),
    ]
    for c in candidates:
        if os.path.isfile(c):
            return os.path.abspath(c)
    return os.path.abspath(".env")


def load_env(env_path=None):
    path = find_env_path(env_path)
    config = {}
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    config[k.strip()] = v.strip()
    # Environment variables override the file for keys it defines — matching the
    # engine's python-dotenv behavior — so operators can point the web monitor at
    # a different DB/log/control path (e.g. DB_PATH=/tmp/x status.py --web) without
    # editing .env.
    for key, value in os.environ.items():
        if key in config and value:
            config[key] = value
    return config


TUNING_KEYS = {
    "PAPER_TRADE", "USE_TESTNET", "PRESET", "TIMEFRAME", "MTF_TIMEFRAME",
    "ATR_PERIOD", "ATR_MULTIPLIER_SL", "ATR_MULTIPLIER_TP",
    "TRAILING_STOP_ACTIVATE", "TRAILING_STOP_CALLBACK", "SWING_LOOKBACK",
    "MAX_HOLD_TIME", "SIGNAL_THRESHOLD", "SIGNAL_INTERVAL",
    "BALANCE_USAGE_PERCENT", "MAX_SYMBOL_ALLOCATION_PERCENT",
    "MAX_DAILY_DRAWDOWN", "MAX_LOSS_STREAK", "MAX_WIN_STREAK",
    "COOLDOWN_LOSS", "COOLDOWN_WIN", "MAX_SLIPPAGE_PERCENT", "MIN_TP_PERCENT",
    "DYNAMIC_SYMBOLS", "MAX_SYMBOLS", "STATIC_SYMBOLS", "QUOTE_ASSET",
    "EXCLUDE_SYMBOLS", "ADX_THRESHOLD", "ADX_PERIOD", "TOP_CANDIDATES",
    "MIN_VOLUME_USDT", "MIN_PRICE_CHANGE_PERCENT", "MIN_VOLATILITY_PERCENT",
    "Z_SCORE_WEIGHT_VOLUME", "Z_SCORE_WEIGHT_CHANGE",
    "Z_SCORE_WEIGHT_VOLATILITY", "Z_SCORE_WEIGHT_ADX",
    "CORRELATION_THRESHOLD", "CORRELATION_PENALTY", "TREND_LOOKBACK",
    "SYMBOL_REFRESH_INTERVAL", "DB_PATH", "CONTROL_FILE", "DISCORD_COOLDOWN",
    "LOG_LEVEL", "LOG_FILE", "HEALTH_CHECK_INTERVAL", "REST_WEIGHT_LIMIT",
    "ENTRY_TIMEOUT", "AUTO_LIQUIDATE_ORPHANS",
    "BASE_ORDER_SIZE", "ORDER_TYPE",
}


def read_control(control_path):
    try:
        with open(control_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def write_control(control_path, data):
    os.makedirs(os.path.dirname(control_path) or ".", exist_ok=True)
    tmp = control_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f)
    os.replace(tmp, control_path)


def parse_env_payload(payload):
    updates = {}
    for line in payload.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k = k.strip()
        if k in TUNING_KEYS:
            updates[k] = v.strip()
    return updates


def apply_env_updates(env_path, updates):
    applied = []
    if not os.path.exists(env_path):
        alt = os.path.join(os.path.dirname(os.path.abspath(__file__)), os.path.basename(env_path))
        if os.path.exists(alt):
            env_path = alt
        else:
            example = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env.example")
            if not os.path.exists(example) and os.path.exists(".env.example"):
                example = ".env.example"
            if os.path.exists(example):
                try:
                    with open(example, "r", encoding="utf-8") as ef:
                        example_content = ef.read()
                    with open(env_path, "w", encoding="utf-8") as target_f:
                        target_f.write(example_content)
                except Exception:
                    pass
    if not os.path.exists(env_path):
        return applied
    with open(env_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    out = []
    seen = set()
    for line in lines:
        stripped = line.strip()
        m = re.match(r"^([A-Z0-9_]+)=", stripped)
        key = m.group(1) if m else None
        if key in updates:
            if key not in seen:
                out.append(f"{key}={updates[key]}\n")
                seen.add(key)
                applied.append(key)
            continue
        out.append(line)
    for key, value in updates.items():
        if key not in seen:
            out.append(f"{key}={value}\n")
            seen.add(key)
            applied.append(key)
    tmp = env_path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.writelines(out)
    os.replace(tmp, env_path)
    return applied


def tail_log_file(log_path, lines=120):
    try:
        with open(log_path, "r", encoding="utf-8", errors="replace") as f:
            return f.readlines()[-lines:]
    except Exception:
        return []


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
        return {"error": f"Database not found at {db_path}", "trades": [], "orders": [], "risk": {}, "stats": {}, "scanned_pairs": []}

    try:
        conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=10.0)
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()

        # Risk state
        risk_rows = cur.execute("SELECT key, value FROM risk_state").fetchall()
        risk = {}
        for row in risk_rows:
            risk[row["key"]] = row["value"]

        # Parse JSON fields stored in risk_state if present
        scanned_pairs = []
        if "scanned_pairs" in risk:
            try:
                scanned_pairs = json.loads(risk["scanned_pairs"])
            except Exception:
                scanned_pairs = []

        account_balances = []
        if "account_balances" in risk:
            try:
                account_balances = json.loads(risk["account_balances"])
            except Exception:
                account_balances = []

        # Active trades
        trades_rows = cur.execute("SELECT * FROM active_trades").fetchall()
        trades = [dict(row) for row in trades_rows]

        # Recent orders (last 25)
        orders_rows = cur.execute(
            "SELECT order_id, symbol, side, order_type, price, stop_price, quantity, executed_qty, status, created_at, updated_at, profit_loss, avg_fill_price FROM orders ORDER BY created_at DESC LIMIT 25"
        ).fetchall()
        orders = [dict(row) for row in orders_rows]

        # Aggregate trade statistics.
        # "Closed trades" = SELL exit orders that recorded a realized PnL. This is
        # exactly how the engine finalizes exits (close_trade sets profit_loss on the
        # SELL order and marks it FILLED), including partial-exit legs which are
        # persisted as CANCELED SELL orders with a non-zero profit_loss. BUY entries,
        # NEW orders and CANCELED attempts (profit_loss NULL) are excluded so the
        # win/loss denominator can never be diluted by non-exits.
        stats_row = cur.execute(
            "SELECT COUNT(*) as total_orders, "
            "SUM(CASE WHEN side='SELL' AND status IN ('FILLED','CANCELED') AND profit_loss IS NOT NULL THEN 1 ELSE 0 END) as closed_trades, "
            "SUM(CASE WHEN side='SELL' AND status IN ('FILLED','CANCELED') AND profit_loss > 0 THEN 1 ELSE 0 END) as winning_trades, "
            "SUM(CASE WHEN side='SELL' AND status IN ('FILLED','CANCELED') AND profit_loss < 0 THEN 1 ELSE 0 END) as losing_trades, "
            "SUM(CASE WHEN status IN ('FILLED','CANCELED') AND profit_loss IS NOT NULL THEN profit_loss ELSE 0 END) as total_pnl "
            "FROM orders"
        ).fetchone()

        closed_trades = int(stats_row["closed_trades"] or 0) if stats_row else 0
        winning_trades = int(stats_row["winning_trades"] or 0) if stats_row else 0
        losing_trades = int(stats_row["losing_trades"] or 0) if stats_row else 0
        breakeven_trades = max(0, closed_trades - winning_trades - losing_trades)
        total_pnl = float(stats_row["total_pnl"] or 0.0) if stats_row else 0.0
        win_rate = round(winning_trades / closed_trades * 100, 1) if closed_trades > 0 else 0.0
        avg_win = 0.0
        if winning_trades > 0:
            # Average of winning trades' PnL only (NOT total_pnl, which includes losses)
            win_row = cur.execute(
                "SELECT SUM(profit_loss) FROM orders WHERE side='SELL' AND status IN ('FILLED','CANCELED') AND profit_loss > 0"
            ).fetchone()
            avg_win = float(win_row[0] or 0.0) / winning_trades if win_row and win_row[0] else 0.0
        avg_loss = 0.0
        if losing_trades > 0:
            # Sum of losing PnL only (avg_loss shown as a positive magnitude)
            loss_row = cur.execute(
                "SELECT SUM(profit_loss) FROM orders WHERE side='SELL' AND status IN ('FILLED','CANCELED') AND profit_loss < 0"
            ).fetchone()
            avg_loss = abs(float(loss_row[0] or 0.0)) / losing_trades if loss_row and loss_row[0] else 0.0
        profit_factor = (avg_win * winning_trades) / (avg_loss * losing_trades) if (avg_loss * losing_trades) > 0 else (0.0 if total_pnl <= 0 else float('inf'))

        stats = {
            "total_orders": int(stats_row["total_orders"] or 0) if stats_row else 0,
            "closed_trades": closed_trades,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "breakeven_trades": breakeven_trades,
            "total_realized_pnl": round(total_pnl, 2),
            "win_rate": win_rate,
            "profit_factor": round(profit_factor, 2) if profit_factor != float('inf') else None,
            "avg_win": round(avg_win, 2),
            "avg_loss": round(avg_loss, 2),
            "win_streak": risk.get("win_streak", "0"),
            "loss_streak": risk.get("loss_streak", "0"),
            "daily_pnl": float(risk.get("daily_pnl") or 0.0)
        }

        conn.close()
        return {
            "risk": risk,
            "trades": trades,
            "orders": orders,
            "stats": stats,
            "scanned_pairs": scanned_pairs,
            "balances": account_balances
        }
    except Exception as e:
        return {"error": str(e), "trades": [], "orders": [], "risk": {}, "stats": {}, "scanned_pairs": [], "balances": []}


def fetch_binance_balance(env_config, db_data):
    """
    Unified balance provider:
    - If PAPER_TRADE=true: returns simulated paper balance from database.
    - If PAPER_TRADE=false: queries live Binance Spot API using HMAC or Ed25519 signing.
      Falls back cleanly to database risk_state if offline or rate-limited.
    """
    now = time.time()
    quote = env_config.get("QUOTE_ASSET", "USDT").strip().upper()
    paper_mode = env_config.get("PAPER_TRADE", "true").lower() == "true"
    risk = db_data.get("risk", {})

    if paper_mode:
        simulated_eq = float(risk.get("paper_balance") or risk.get("total_equity") or 1000.0)
        daily_pnl = float(risk.get("daily_pnl") or 0.0)
        return {
            "is_live": False,
            "quote_asset": quote,
            "total_equity": simulated_eq,
            "free_quote": simulated_eq,
            "locked_quote": 0.0,
            "daily_pnl": daily_pnl,
            "balances": [
                {"asset": quote, "free": simulated_eq, "locked": 0.0, "total": simulated_eq, "usd_value": simulated_eq}
            ]
        }

    # Live Mode: Check TTL cache (5 seconds)
    if _balance_cache["data"] and (now - _balance_cache["ts"] < 5.0):
        return _balance_cache["data"]

    # Try live query to Binance if API Key is configured
    api_key = env_config.get("BINANCE_API_KEY", "").strip()
    api_secret = env_config.get("BINANCE_API_SECRET", "").strip()
    private_key_path = env_config.get("BINANCE_PRIVATE_KEY_PATH", "").strip()
    use_testnet = env_config.get("USE_TESTNET", "false").lower() == "true"
    base_url = "https://testnet.binance.vision" if use_testnet else "https://api.binance.com"

    live_res = None
    if api_key and (api_secret or (private_key_path and os.path.exists(private_key_path))):
        try:
            ts = int(time.time() * 1000)
            query = f"timestamp={ts}"
            signature = ""

            if api_secret:
                signature = hmac.new(api_secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256).hexdigest()
            elif private_key_path and os.path.exists(private_key_path):
                try:
                    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
                    from cryptography.hazmat.primitives import serialization
                    import base64
                    with open(private_key_path, "rb") as f:
                        key_bytes = f.read()
                    try:
                        priv_key = serialization.load_pem_private_key(key_bytes, password=None)
                    except Exception:
                        priv_key = Ed25519PrivateKey.from_private_bytes(key_bytes.strip())
                    signature = base64.b64encode(priv_key.sign(query.encode("utf-8"))).decode("utf-8")
                except Exception:
                    pass

            if signature:
                url = f"{base_url}/api/v3/account?{query}&signature={signature}"
                req = urllib.request.Request(url, headers={"X-MBX-APIKEY": api_key, "User-Agent": "BinanceMonitor/2.0"})
                with urllib.request.urlopen(req, timeout=4.0) as resp:
                    if resp.status == 200:
                        account = json.loads(resp.read().decode("utf-8"))
                        total_equity = 0.0
                        free_quote = 0.0
                        locked_quote = 0.0
                        balances = []

                        for b in account.get("balances", []):
                            asset = b.get("asset", "")
                            free = float(b.get("free", 0.0))
                            locked = float(b.get("locked", 0.0))
                            tot = free + locked
                            if tot <= 0.00000001:
                                continue

                            usd_val = 0.0
                            if asset == quote:
                                total_equity += tot
                                free_quote = free
                                locked_quote = locked
                                usd_val = tot
                            else:
                                # Look up in fast tickers cache if available
                                symbol = asset + quote
                                ticker_p = _tickers_cache.get("data", {}).get(symbol, 0.0)
                                usd_val = tot * ticker_p if ticker_p > 0 else 0.0
                                total_equity += usd_val

                            balances.append({
                                "asset": asset,
                                "free": free,
                                "locked": locked,
                                "total": tot,
                                "usd_value": usd_val
                            })

                        # Sort balances: quote first, then descending by usd_value
                        balances.sort(key=lambda x: (x["asset"] != quote, -x.get("usd_value", 0)))
                        daily_pnl = float(risk.get("daily_pnl") or 0.0)

                        live_res = {
                            "is_live": True,
                            "quote_asset": quote,
                            "total_equity": round(total_equity, 2),
                            "free_quote": round(free_quote, 2),
                            "locked_quote": round(locked_quote, 2),
                            "daily_pnl": daily_pnl,
                            "balances": balances
                        }
        except Exception:
            live_res = None

    if live_res:
        _balance_cache["ts"] = now
        _balance_cache["data"] = live_res
        return live_res

    # Fallback to database risk_state
    db_total = float(risk.get("total_equity") or risk.get("live_equity") or risk.get("equity") or risk.get("paper_balance") or 0.0)
    db_free = float(risk.get("free_quote") or db_total)
    db_locked = float(risk.get("locked_quote") or 0.0)
    db_balances = db_data.get("balances") or []
    if not db_balances and db_total > 0:
        db_balances = [{"asset": quote, "free": db_free, "locked": db_locked, "total": db_total, "usd_value": db_total}]

    fallback = {
        "is_live": True,
        "quote_asset": quote,
        "total_equity": round(db_total, 2),
        "free_quote": round(db_free, 2),
        "locked_quote": round(db_locked, 2),
        "daily_pnl": float(risk.get("daily_pnl") or 0.0),
        "balances": db_balances
    }
    _balance_cache["ts"] = now
    _balance_cache["data"] = fallback
    return fallback


def fetch_scanned_pairs(env_config, db_data):
    """
    Fetch market screener data:
    1. Check SQLite risk_state for real engine-scanned pairs.
    2. If empty, query Binance public 24h ticker API to populate top gainers/active pairs.
    """
    now = time.time()

    # If engine recently persisted scanned pairs in SQLite, return them
    db_scanned = db_data.get("scanned_pairs")
    if isinstance(db_scanned, list) and len(db_scanned) > 0:
        _scanned_cache["ts"] = now
        _scanned_cache["data"] = db_scanned
        return db_scanned

    # Check cache (15s TTL)
    if _scanned_cache["data"] and (now - _scanned_cache["ts"] < 15.0):
        return _scanned_cache["data"]

    quote = env_config.get("QUOTE_ASSET", "USDT").strip().upper()
    static_symbols = [s.strip().upper() for s in env_config.get("STATIC_SYMBOLS", "BTCUSDT,ETHUSDT").split(",") if s.strip()]
    max_symbols = int(env_config.get("MAX_SYMBOLS", "5"))

    try:
        url = "https://api.binance.com/api/v3/ticker/24hr"
        req = urllib.request.Request(url, headers={"User-Agent": "BinanceScreener/2.0"})
        with urllib.request.urlopen(req, timeout=4.0) as resp:
            if resp.status == 200:
                raw_tickers = json.loads(resp.read().decode("utf-8"))
                price_map = {}
                filtered = []
                for t in raw_tickers:
                    sym = t.get("symbol", "")
                    if not sym.endswith(quote):
                        continue
                    # Leveraged tokens carry UP/DOWN/BEAR/BULL as a base-asset suffix
                    # (e.g. BTCUPUSDT). Only exclude on that boundary — a raw substring
                    # test would wrongly drop legit pairs like SUPERUSDT.
                    base = sym[: -len(quote)] if quote else sym
                    if any(base.endswith(x) for x in ("UP", "DOWN", "BEAR", "BULL")):
                        continue
                    try:
                        last_p = float(t.get("lastPrice", 0.0))
                        vol = float(t.get("quoteVolume", 0.0))
                        chg = float(t.get("priceChangePercent", 0.0))
                        high_p = float(t.get("highPrice", 0.0))
                        low_p = float(t.get("lowPrice", 0.0))
                        vola = round((high_p - low_p) / last_p * 100, 2) if last_p > 0 else 0.0
                    except (ValueError, TypeError):
                        continue

                    price_map[sym] = last_p
                    if vol >= 5000000 and abs(chg) >= 0.5:
                        filtered.append({
                            "symbol": sym,
                            "price": last_p,
                            "price_change_24h": round(chg, 2),
                            "volume_24h": round(vol, 0),
                            "volatility": vola,
                            "high24h": high_p,
                            "low24h": low_p
                        })

                # Update global tickers cache
                _tickers_cache["ts"] = now
                _tickers_cache["data"] = price_map

                # Sort by 24h volume descending
                filtered.sort(key=lambda x: x["volume_24h"], reverse=True)
                top_items = filtered[:15]

                candidates = []
                for idx, item in enumerate(top_items):
                    sym = item["symbol"]
                    chg = item["price_change_24h"]
                    vol = item["volume_24h"]
                    adx_est = round(min(55.0, 22.0 + abs(chg) * 1.8), 1)
                    trend_dir = "UP" if chg > 0 else "DOWN"
                    breakout = abs(chg) >= 4.0
                    z_score = round((chg / 4.0) + (vol / 50000000.0), 2)
                    is_sel = (sym in static_symbols) or (idx < max_symbols)

                    candidates.append({
                        "symbol": sym,
                        "name": sym.replace(quote, ""),
                        "price": item["price"],
                        "price_change_24h": chg,
                        "volume_24h": vol,
                        "volatility": item["volatility"],
                        "adx": adx_est,
                        "trend_dir": trend_dir,
                        "breakout": breakout,
                        "z_score": z_score,
                        "momentum_rank": idx + 1,
                        "is_selected": is_sel
                    })

                _scanned_cache["ts"] = now
                _scanned_cache["data"] = candidates
                return candidates
    except Exception:
        pass

    return _scanned_cache["data"] or []


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
    quote = env_config.get("QUOTE_ASSET", "USDT")
    control = read_control(env_config.get("CONTROL_FILE", "./data/engine_control.json"))
    is_paused = control.get("paused", False)

    # Fetch live balance and scanned pairs
    balance_info = fetch_binance_balance(env_config, db_data)
    scanned_pairs = fetch_scanned_pairs(env_config, db_data)

    output = []
    output.append(f"{BOLD}{CYAN}========================================================================================{RESET}")
    output.append(f"{BOLD} BINANCE ULTIMATE BOT — COMPREHENSIVE CLI MONITOR & SYSTEM STATUS {RESET}")
    output.append(f"{BOLD}{CYAN}========================================================================================{RESET}")
    mode_tag = f"{CYAN}[PAPER TRADING - SIMULATED]{RESET}" if paper_mode else f"{GREEN}{BOLD}[LIVE PRODUCTION - REAL FUNDS]{RESET}"
    pause_tag = f" {RED}{BOLD}[WEB PAUSE ACTIVE]{RESET}" if is_paused else ""
    output.append(f"  Engine Status : {status_str}{pause_tag}    Preset : {BOLD}{preset.upper()}{RESET}    Mode : {mode_tag}")
    output.append(f"  System Time   : {now_str}       Monitored Symbols : {CYAN}{symbols}{RESET}")
    output.append(f"{CYAN}----------------------------------------------------------------------------------------{RESET}")

    # Account Balance Section
    total_eq = balance_info.get("total_equity", 0.0)
    free_q = balance_info.get("free_quote", 0.0)
    locked_q = balance_info.get("locked_quote", 0.0)
    daily_pnl = balance_info.get("daily_pnl", 0.0)
    pnl_color = GREEN if daily_pnl >= 0 else RED

    output.append(f"{BOLD} 💰 ACCOUNT & BALANCE OVERVIEW{RESET}")
    if paper_mode:
        output.append(f"  Simulated Equity : {BOLD}${total_eq:,.2f} {quote}{RESET}    Daily Realized PnL : {pnl_color}${daily_pnl:+,.2f} {quote}{RESET}")
    else:
        output.append(f"  Total Spot Equity : {BOLD}${total_eq:,.2f} {quote}{RESET}    Available Free Quote : {BOLD}${free_q:,.2f} {quote}{RESET}")
        output.append(f"  In Open Positions : ${locked_q:,.2f} {quote}          Daily Realized PnL   : {pnl_color}${daily_pnl:+,.2f} {quote}{RESET}")

        # Non-zero asset balances
        balances = balance_info.get("balances", [])
        if balances:
            asset_strs = []
            for b in balances[:6]:
                a = b["asset"]
                tot = b["total"]
                u_val = b.get("usd_value", 0.0)
                if a == quote:
                    asset_strs.append(f"{a}: {tot:,.2f}")
                else:
                    asset_strs.append(f"{a}: {tot:.4f} (${u_val:,.1f})")
            output.append(f"  Assets Breakdown  : {' | '.join(asset_strs)}")

    # Scanned Pairs Section (Live Screener)
    output.append(f"\n{BOLD} 🔍 MARKET SCANNER — TOP SCANNED PAIRS ({len(scanned_pairs)}){RESET}")
    if not scanned_pairs:
        output.append(f"  {DIM}Scanner initializing or waiting for next market cycle...{RESET}")
    else:
        hdr = f"  {'#':<3} {'SYMBOL':<10} {'PRICE':<12} {'24H CHG':<10} {'24H VOL':<12} {'ADX':<6} {'TREND':<7} {'BREAKOUT':<9} {'STATUS':<10}"
        output.append(f"{BOLD}{hdr}{RESET}")
        output.append("  " + "-" * 82)
        for idx, s in enumerate(scanned_pairs[:8]):
            chg = s.get("price_change_24h", 0.0)
            chg_c = GREEN if chg >= 0 else RED
            chg_str = f"{chg:+.2f}%"
            vol_m = f"${s.get('volume_24h', 0) / 1e6:.1f}M"
            status_badge = f"{GREEN}● ACTIVE{RESET}" if s.get("is_selected") else f"{DIM}WATCHING{RESET}"
            bo_str = "YES" if s.get("breakout") else "NO"
            p_val = s.get("price", 0.0)
            p_str = f"${p_val:,.4f}" if p_val < 10 else f"${p_val:,.2f}"
            output.append(
                f"  {idx+1:<3} {BOLD}{s.get('symbol'):<10}{RESET} {p_str:<12} {chg_c}{chg_str:<10}{RESET} {vol_m:<12} {s.get('adx', 0):<6.1f} {s.get('trend_dir', 'N/A'):<7} {bo_str:<9} {status_badge}"
            )

    # Active Positions
    trades = db_data.get("trades", [])
    output.append(f"\n{BOLD} 📈 ACTIVE MARKET POSITIONS ({len(trades)}){RESET}")
    if not trades:
        output.append(f"  {DIM}No open positions currently active.{RESET}")
    else:
        hdr = f"  {'SYMBOL':<10} {'SIDE':<6} {'ENTRY':<12} {'QTY':<10} {'NOTIONAL':<12} {'STOP LOSS':<12} {'TAKE PROFIT':<12} {'BE':<5}"
        output.append(f"{BOLD}{hdr}{RESET}")
        output.append("  " + "-" * 82)
        for t in trades:
            be = "LOCKED" if t.get("breakeven_activated") else "NO"
            side_c = GREEN if t["side"] == "BUY" else RED
            notional = float(t.get("entry_price", 0)) * float(t.get("quantity", 0))
            output.append(
                f"  {BOLD}{t['symbol']:<10}{RESET} {side_c}{t['side']:<6}{RESET} {t['entry_price']:<12.4f} {t['quantity']:<10.4f} ${notional:<11.2f} {t.get('stop_price', 0):<12.4f} {t.get('take_profit', 0):<12.4f} {be:<5}"
            )

    # Recent Orders
    orders = db_data.get("orders", [])
    output.append(f"\n{BOLD} 📋 RECENT EXECUTED ORDERS (LAST 5){RESET}")
    if not orders:
        output.append(f"  {DIM}No recorded orders yet.{RESET}")
    else:
        hdr = f"  {'TIME':<19} {'SYMBOL':<10} {'SIDE':<6} {'PRICE':<10} {'QTY':<10} {'STATUS':<10} {'REALIZED PNL':<12}"
        output.append(f"{BOLD}{hdr}{RESET}")
        output.append("  " + "-" * 82)
        for o in orders[:5]:
            t_str = format_timestamp(o.get("created_at"))
            s_color = GREEN if o["status"] == "FILLED" else (YELLOW if o["status"] == "NEW" else RED)
            pnl_val = float(o.get("profit_loss") or 0.0)
            pnl_s = f"{pnl_val:+.2f} USDT" if pnl_val != 0 else "-"
            output.append(
                f"  {t_str:<19} {o['symbol']:<10} {o['side']:<6} {o.get('price', 0):<10.2f} {o.get('executed_qty', 0):<10.4f} {s_color}{o['status']:<10}{RESET} {pnl_s:<12}"
            )

    # Risk Metrics & Performance Stats
    stats = db_data.get("stats", {})
    risk = db_data.get("risk", {})
    win_streak = risk.get("win_streak", "0")
    loss_streak = risk.get("loss_streak", "0")
    max_dd = float(env_config.get("MAX_DAILY_DRAWDOWN", "0.05")) * 100
    win_rate = stats.get("win_rate", 0.0)

    output.append(f"\n{BOLD} 🛡️ RISK METRICS & PERFORMANCE STATS{RESET}")
    closed_cnt = stats.get('closed_trades', 0)
    win_cnt = stats.get('winning_trades', 0)
    loss_cnt = stats.get('losing_trades', 0)
    be_cnt = stats.get('breakeven_trades', 0)
    pf = stats.get('profit_factor')
    pf_str = f"{pf:.2f}" if isinstance(pf, (int, float)) else "∞"
    avg_win = stats.get('avg_win', 0.0)
    avg_loss = stats.get('avg_loss', 0.0)
    output.append(f"  Win Rate       : {BOLD}{win_rate:.1f}%{RESET} ({win_cnt}W / {loss_cnt}L / {be_cnt}B / {closed_cnt} closed)")
    output.append(f"  Profit Factor  : {BOLD}{pf_str}{RESET}    Avg Win: {GREEN}${avg_win:,.2f}{RESET}    Avg Loss: {RED}-${avg_loss:,.2f}{RESET}")
    output.append(f"  Streak Monitor : Win Streak: {GREEN}{win_streak}{RESET}/{env_config.get('MAX_WIN_STREAK', '5')}    Loss Streak: {RED}{loss_streak}{RESET}/{env_config.get('MAX_LOSS_STREAK', '3')}")
    output.append(f"  Total Realized : {GREEN if stats.get('total_realized_pnl', 0)>=0 else RED}${stats.get('total_realized_pnl', 0):+,.2f} {quote}{RESET}    Daily DD Limit : {max_dd:.1f}%")

    output.append(f"\n{CYAN}----------------------------------------------------------------------------------------{RESET}")
    output.append(f"  {DIM}Press Ctrl+C to exit monitor. Run 'python3 status.py --web' to host the Web UI.{RESET}")
    output.append(f"{CYAN}========================================================================================{RESET}")

    return "\n".join(output)


def get_standalone_html():
    return """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>⚡ Ultimate Binance Bot - Web Monitor</title>
  <style>
    :root {
      --bg: #0b0f19;
      --card: #151d2e;
      --border: #243049;
      --text: #e2e8f0;
      --accent: #10b981;
      --danger: #f43f5e;
      --warn: #f59e0b;
      --cyan: #38bdf8;
    }
    * { box-sizing: border-box; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, monospace;
      background: var(--bg);
      color: var(--text);
      margin: 0;
      padding: 24px 16px;
    }
    .container { max-width: 1200px; margin: 0 auto; }
    .header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      border-bottom: 1px solid var(--border);
      padding-bottom: 16px;
      margin-bottom: 24px;
      flex-wrap: wrap;
      gap: 12px;
    }
    .title { font-size: 1.4rem; font-weight: 700; color: #fff; display: flex; align-items: center; gap: 8px; }
    .badge {
      padding: 6px 14px;
      border-radius: 9999px;
      font-size: 0.75rem;
      font-weight: 700;
      letter-spacing: 0.05em;
      text-transform: uppercase;
    }
    .badge-running { background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.3); }
    .badge-stopped { background: rgba(244, 63, 94, 0.15); color: #fb7185; border: 1px solid rgba(244, 63, 94, 0.3); }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 16px; margin-bottom: 24px; }
    .card {
      background: var(--card);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 18px;
      position: relative;
    }
    .card-title { font-size: 0.75rem; text-transform: uppercase; color: #94a3b8; margin-bottom: 8px; letter-spacing: 0.05em; }
    .card-value { font-size: 1.6rem; font-weight: 700; color: #fff; }
    .card-sub { font-size: 0.8rem; color: #94a3b8; margin-top: 6px; }
    table { width: 100%; border-collapse: collapse; margin-top: 12px; font-size: 0.85rem; }
    th { text-align: left; padding: 10px 12px; color: #94a3b8; border-bottom: 1px solid var(--border); font-size: 0.75rem; text-transform: uppercase; }
    td { padding: 10px 12px; border-bottom: 1px solid rgba(36, 48, 73, 0.5); }
    .pnl-pos { color: #34d399; font-weight: 600; }
    .pnl-neg { color: #fb7185; font-weight: 600; }
    .time { font-size: 0.75rem; color: #64748b; }
    .controls-bar {
      display: flex;
      gap: 12px;
      margin-bottom: 24px;
      flex-wrap: wrap;
    }
    button {
      background: #1e293b;
      color: #fff;
      border: 1px solid var(--border);
      padding: 8px 16px;
      border-radius: 8px;
      cursor: pointer;
      font-weight: 600;
      font-size: 0.85rem;
      transition: all 0.2s ease;
    }
    button:hover { background: #334155; }
    button.btn-danger { background: rgba(244, 63, 94, 0.2); border-color: rgba(244, 63, 94, 0.4); color: #fb7185; }
    button.btn-danger:hover { background: rgba(244, 63, 94, 0.4); }
    button.btn-warn { background: rgba(245, 158, 11, 0.2); border-color: rgba(245, 158, 11, 0.4); color: #fbbf24; }
    button.btn-warn:hover { background: rgba(245, 158, 11, 0.4); }
    .asset-chips { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }
    .asset-chip {
      background: #0f172a;
      border: 1px solid var(--border);
      border-radius: 6px;
      padding: 4px 10px;
      font-size: 0.75rem;
    }
  </style>
</head>
<body>
  <div class="container">
    <div class="header">
      <div>
        <div class="title">⚡ Binance Ultimate Trading Bot — Web Monitor</div>
        <div id="timestamp" class="time">Connecting to engine...</div>
      </div>
      <div style="display:flex; align-items:center; gap: 12px;">
        <div id="modeBadge" class="badge" style="background:#0284c7; color:#fff;">CHECKING...</div>
        <div id="statusBadge" class="badge badge-running">CHECKING...</div>
      </div>
    </div>

    <!-- Quick Control Bar -->
    <div class="controls-bar">
      <button id="btnPause" class="btn-warn" onclick="togglePause()">⏸️ Pause Bot Entries</button>
      <button class="btn-danger" onclick="closeAllPositions()">🚨 Emergency Close All</button>
      <span id="controlStatus" style="font-size: 0.85rem; color: #94a3b8; align-self: center;"></span>
    </div>

    <!-- Balance & Risk Cards -->
    <div class="grid">
      <div class="card">
        <div class="card-title">Total Account Equity</div>
        <div id="totalEquity" class="card-value">—</div>
        <div id="equitySub" class="card-sub">Available Quote: —</div>
      </div>
      <div class="card">
        <div class="card-title">Daily Realized PnL</div>
        <div id="dailyPnl" class="card-value">—</div>
        <div id="pnlSub" class="card-sub">Win Rate: —</div>
      </div>
      <div class="card">
        <div class="card-title">Active Positions & Capital</div>
        <div id="openPositionsCount" class="card-value">0</div>
        <div id="activeCapitalSub" class="card-sub">Locked Capital: $0.00</div>
      </div>
      <div class="card">
        <div class="card-title">Strategy Engine</div>
        <div id="strategyPreset" class="card-value">—</div>
        <div id="presetSub" class="card-sub">Signal Threshold: —</div>
      </div>
    </div>

    <!-- Performance & Risk Statistics -->
    <div class="grid">
      <div class="card">
        <div class="card-title">🎯 Win Rate</div>
        <div id="perfWinRate" class="card-value">—</div>
        <div id="perfWinRateSub" class="card-sub">Closed trades: —</div>
      </div>
      <div class="card">
        <div class="card-title">⚖️ Profit Factor</div>
        <div id="perfProfitFactor" class="card-value">—</div>
        <div class="card-sub">Gross wins ÷ gross losses</div>
      </div>
      <div class="card">
        <div class="card-title">💵 Total Realized PnL</div>
        <div id="perfTotalPnl" class="card-value">—</div>
        <div id="perfTotalPnlSub" class="card-sub">Avg Win: — / Avg Loss: —</div>
      </div>
      <div class="card">
        <div class="card-title">🔥 Win / Loss Streaks</div>
        <div id="perfStreaks" class="card-value">—</div>
        <div class="card-sub">Cooldown monitor (MAX_WIN_STREAK / MAX_LOSS_STREAK)</div>
      </div>
    </div>

    <!-- Non-Zero Assets Breakdown -->
    <div class="card" style="margin-bottom: 24px;" id="assetsContainer">
      <div class="card-title">Account Non-Zero Assets Breakdown</div>
      <div id="assetChips" class="asset-chips">No non-zero assets recorded yet.</div>
    </div>

    <!-- Market Scanner / Scanned Pairs Screener -->
    <div class="card" style="margin-bottom: 24px;">
      <div class="card-title">🔍 Market Trend Scanner — Scanned Pairs</div>
      <div id="scannedTable">Loading scanner...</div>
    </div>

    <!-- Active Positions -->
    <div class="card" style="margin-bottom: 24px;">
      <div class="card-title">📈 Active Market Positions</div>
      <div id="positionsTable">Loading positions...</div>
    </div>

    <!-- Recent Orders -->
    <div class="card">
      <div class="card-title">📋 Recent Orders & Executions</div>
      <div id="ordersTable">Loading orders...</div>
    </div>
  </div>

  <script>
    let isPaused = false;

    async function updateStatus() {
      try {
        const res = await fetch('/api/status');
        const data = await res.json();
        document.getElementById('timestamp').innerText = 'Last updated: ' + data.timestamp + ' • Auto-refreshes every 2s';

        // Engine status badge
        const badge = document.getElementById('statusBadge');
        if (data.process.includes('RUNNING')) {
          badge.className = 'badge badge-running';
          badge.innerText = '● ENGINE RUNNING';
        } else {
          badge.className = 'badge badge-stopped';
          badge.innerText = '● ENGINE STOPPED';
        }

        // Mode badge
        const modeEl = document.getElementById('modeBadge');
        const isLive = data.config.PAPER_TRADE !== 'true';
        modeEl.innerText = isLive ? 'LIVE SPOT REAL FUNDS' : 'PAPER SIMULATOR';
        modeEl.style.background = isLive ? '#15803d' : '#0369a1';

        // Pause state
        isPaused = Boolean(data.control && data.control.paused);
        const pauseBtn = document.getElementById('btnPause');
        if (isPaused) {
          pauseBtn.innerText = '▶️ Resume Trading';
          pauseBtn.className = 'btn-warn';
          document.getElementById('controlStatus').innerText = '⏸️ Bot entries paused by operator';
        } else {
          pauseBtn.innerText = '⏸️ Pause Bot Entries';
          pauseBtn.className = '';
          document.getElementById('controlStatus').innerText = '✅ Bot actively trading';
        }

        // Balances
        const bal = data.balance || {};
        const eqVal = bal.total_equity !== undefined ? parseFloat(bal.total_equity) : 0;
        const freeVal = bal.free_quote !== undefined ? parseFloat(bal.free_quote) : eqVal;
        const lockVal = bal.locked_quote !== undefined ? parseFloat(bal.locked_quote) : 0;
        const quote = bal.quote_asset || 'USDT';

        document.getElementById('totalEquity').innerText = '$' + eqVal.toLocaleString('en-US', {minimumFractionDigits: 2, maximumFractionDigits: 2}) + ' ' + quote;
        document.getElementById('equitySub').innerText = 'Free: $' + freeVal.toFixed(2) + ' • Locked: $' + lockVal.toFixed(2);

        // Daily PnL
        const pnlVal = bal.daily_pnl !== undefined ? parseFloat(bal.daily_pnl) : (data.data?.risk?.daily_pnl ? parseFloat(data.data.risk.daily_pnl) : 0);
        const pnlEl = document.getElementById('dailyPnl');
        pnlEl.innerText = (pnlVal >= 0 ? '+' : '') + '$' + pnlVal.toFixed(2) + ' ' + quote;
        pnlEl.className = 'card-value ' + (pnlVal >= 0 ? 'pnl-pos' : 'pnl-neg');

        const stats = data.data?.stats || {};
        const wins = stats.winning_trades || 0;
        const losses = stats.losing_trades || 0;
        const breakevens = stats.breakeven_trades || 0;
        const closedCount = stats.closed_trades || 0;
        document.getElementById('pnlSub').innerText = 'Win Rate: ' + (stats.win_rate || 0) + '% (' + wins + 'W / ' + losses + 'L / ' + breakevens + 'B)';

        // Performance & Risk statistics (win rate / profit factor / realized PnL / streaks)
        const perfWinRate = document.getElementById('perfWinRate');
        const wrVal = stats.win_rate || 0;
        perfWinRate.innerText = wrVal.toFixed ? wrVal.toFixed(1) + '%' : (wrVal + '%');
        perfWinRate.className = 'card-value ' + (wrVal >= 50 ? 'pnl-pos' : 'pnl-neg');
        document.getElementById('perfWinRateSub').innerText = closedCount + ' closed (' + wins + 'W / ' + losses + 'L / ' + breakevens + 'B) — Win Rate = wins ÷ closed';

        const pfVal = stats.profit_factor;
        document.getElementById('perfProfitFactor').innerText = (pfVal === null || pfVal === undefined) ? '∞' : pfVal.toFixed(2);
        document.getElementById('perfProfitFactor').className = 'card-value ' + ((pfVal !== null && pfVal !== undefined && pfVal >= 1) ? 'pnl-pos' : 'pnl-neg');

        const totalPnl = parseFloat(stats.total_realized_pnl || 0);
        const perfPnlEl = document.getElementById('perfTotalPnl');
        perfPnlEl.innerText = (totalPnl >= 0 ? '+' : '') + '$' + totalPnl.toFixed(2);
        perfPnlEl.className = 'card-value ' + (totalPnl >= 0 ? 'pnl-pos' : 'pnl-neg');
        document.getElementById('perfTotalPnlSub').innerText = 'Avg Win: $' + (stats.avg_win || 0).toFixed(2) + ' / Avg Loss: -$' + (stats.avg_loss || 0).toFixed(2);

        const riskState = data.data?.risk || {};
        const winStr = riskState.win_streak !== undefined ? String(riskState.win_streak) : '0';
        const lossStr = riskState.loss_streak !== undefined ? String(riskState.loss_streak) : '0';
        document.getElementById('perfStreaks').innerText = winStr + 'W / ' + lossStr + 'L';

        // Strategy preset
        document.getElementById('strategyPreset').innerText = (data.config.PRESET || 'DAY').toUpperCase();
        document.getElementById('presetSub').innerText = 'Signal Threshold: ' + (data.config.SIGNAL_THRESHOLD || '4') + '/5 • TF: ' + (data.config.TIMEFRAME || '15m');

        // Assets Chips
        const balances = bal.balances || data.data?.balances || [];
        if (balances.length > 0) {
          let chipsHtml = '';
          balances.forEach(b => {
            const tot = parseFloat(b.total || (b.free + b.locked) || 0);
            const usd = b.usd_value ? ' ($' + parseFloat(b.usd_value).toFixed(1) + ')' : '';
            chipsHtml += `<div class="asset-chip"><strong>${b.asset}</strong>: ${tot.toFixed(4)}${usd}</div>`;
          });
          document.getElementById('assetChips').innerHTML = chipsHtml;
        }

        // Active Trades
        const trades = data.data?.trades || [];
        document.getElementById('openPositionsCount').innerText = trades.length;
        document.getElementById('activeCapitalSub').innerText = 'Locked: $' + lockVal.toFixed(2) + ' ' + quote;

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

        // Market Screener Table
        const candidates = data.candidates || data.scanned_pairs || data.data?.scanned_pairs || [];
        if (candidates.length === 0) {
          document.getElementById('scannedTable').innerHTML = '<div style="color: #64748b; padding: 12px;">Scanner awaiting next cycle.</div>';
        } else {
          let html = '<table><thead><tr><th>#</th><th>Symbol</th><th>Price</th><th>24h Change</th><th>24h Volume</th><th>ADX</th><th>Trend</th><th>Breakout</th><th>Status</th></tr></thead><tbody>';
          candidates.slice(0, 10).forEach((c, idx) => {
            const chg = parseFloat(c.price_change_24h || 0);
            const chgColor = chg >= 0 ? '#34d399' : '#fb7185';
            const volStr = '$' + (parseFloat(c.volume_24h || 0) / 1e6).toFixed(1) + 'M';
            const status = c.is_selected ? '<span style="color:#34d399; font-weight:bold;">● ACTIVE</span>' : '<span style="color:#64748b;">WATCH</span>';
            const bo = c.breakout ? '<span style="color:#fbbf24; font-weight:bold;">YES</span>' : 'NO';
            html += `<tr><td>${idx+1}</td><td><strong>${c.symbol}</strong></td><td>$${parseFloat(c.price||0).toFixed(2)}</td><td style="color:${chgColor}">${chg >= 0 ? '+' : ''}${chg.toFixed(2)}%</td><td>${volStr}</td><td>${parseFloat(c.adx||0).toFixed(1)}</td><td>${c.trend_dir||'UP'}</td><td>${bo}</td><td>${status}</td></tr>`;
          });
          html += '</tbody></table>';
          document.getElementById('scannedTable').innerHTML = html;
        }

        // Recent Orders
        const orders = data.data?.orders || [];
        if (orders.length === 0) {
          document.getElementById('ordersTable').innerHTML = '<div style="color: #64748b; padding: 12px;">No recent orders recorded.</div>';
        } else {
          let html = '<table><thead><tr><th>Time</th><th>Symbol</th><th>Side</th><th>Price</th><th>Qty</th><th>Status</th><th>Realized PnL</th></tr></thead><tbody>';
          orders.slice(0, 8).forEach(o => {
            const pnl = parseFloat(o.profit_loss || 0);
            const pnlStr = pnl !== 0 ? `<span style="color:${pnl>=0?'#34d399':'#fb7185'}">${pnl>=0?'+':''}${pnl.toFixed(2)} USDT</span>` : '-';
            html += `<tr><td class="time">${o.created_at || '-'}</td><td><strong>${o.symbol}</strong></td><td style="color:${o.side==='BUY'?'#34d399':'#fb7185'}">${o.side}</td><td>$${parseFloat(o.price||0).toFixed(2)}</td><td>${parseFloat(o.executed_qty||0).toFixed(4)}</td><td><span style="color:#34d399">${o.status}</span></td><td>${pnlStr}</td></tr>`;
          });
          html += '</tbody></table>';
          document.getElementById('ordersTable').innerHTML = html;
        }
      } catch (e) {
        console.error('Failed to fetch status', e);
      }
    }

    async function togglePause() {
      const action = isPaused ? 'resume' : 'pause';
      try {
        const res = await fetch('/api/control', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({action})
        });
        const d = await res.json();
        if (d.ok) {
          updateStatus();
        }
      } catch (e) {
        alert('Failed to send control command: ' + e);
      }
    }

    async function closeAllPositions() {
      if (!confirm('Are you sure you want to close all open positions immediately at market?')) return;
      try {
        const res = await fetch('/api/control', {
          method: 'POST',
          headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({action: 'close_all'})
        });
        const d = await res.json();
        if (d.ok) {
          alert('Emergency close command sent to engine.');
          updateStatus();
        }
      } catch (e) {
        alert('Failed to trigger emergency close: ' + e);
      }
    }

    updateStatus();
    setInterval(updateStatus, 2000);
  </script>
</body>
</html>"""


def start_web_server(port, env_config, db_path):
    dist_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "dist"))
    if not (os.path.isdir(dist_dir) and os.path.isfile(os.path.join(dist_dir, "index.html"))):
        alt_dist = os.path.abspath("dist")
        if os.path.isdir(alt_dist) and os.path.isfile(os.path.join(alt_dist, "index.html")):
            dist_dir = alt_dist
    has_dist = os.path.isdir(dist_dir) and os.path.isfile(os.path.join(dist_dir, "index.html"))

    class CustomHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            if has_dist:
                super().__init__(*args, directory=dist_dir, **kwargs)
            else:
                super().__init__(*args, **kwargs)

        # HTTP/1.1 keep-alive (requires accurate Content-Length on every response,
        # which every branch below provides) and an idle-connection timeout so
        # keep-alive threads cannot accumulate forever.
        protocol_version = "HTTP/1.1"
        timeout = 60

        def log_message(self, format, *args):
            pass  # Quiet production mode

        def send_cors_headers(self):
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization, X-Requested-With")

        def do_OPTIONS(self):
            # Content-Length is mandatory on HTTP/1.1 keep-alive responses
            self.send_response(200)
            self.send_cors_headers()
            self.send_header("Content-Length", "0")
            self.end_headers()

        def _send_json(self, obj, status=200):
            data_bytes = json.dumps(obj, default=str).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_cors_headers()
            self.send_header("Content-Length", str(len(data_bytes)))
            self.end_headers()
            self.wfile.write(data_bytes)

        def _read_json_body(self):
            try:
                length = int(self.headers.get("Content-Length", 0) or 0)
            except ValueError:
                return None
            if length <= 0 or length > 1_000_000:
                return None
            raw = self.rfile.read(length)
            try:
                return json.loads(raw.decode("utf-8"))
            except Exception:
                return None

        # ------------------------------------------------------------------
        # Static file serving with full `npx serve -s dist` parity:
        # SPA fallback for client-side routes, clean-URL directory redirects,
        # ETag/304 revalidation, immutable caching for hashed assets, gzip
        # compression, HTTP Range support and HTTP/1.1 keep-alive.
        # ------------------------------------------------------------------
        SERVE_COMPRESSIBLE_EXTS = {
            ".html", ".htm", ".css", ".js", ".mjs", ".json", ".map", ".svg",
            ".txt", ".xml", ".webmanifest", ".woff", ".woff2",
        }

        def _cache_control(self, fs_path):
            rel = os.path.relpath(fs_path, dist_dir).replace(os.sep, "/")
            # Vite emits content-hashed filenames under /assets/ — cache forever.
            if rel.startswith("assets/") and re.search(r"-[A-Za-z0-9_-]{8,}\.[A-Za-z0-9]+$", rel):
                return "public, max-age=31536000, immutable"
            return "public, max-age=0, must-revalidate"

        def _resolve_static(self, clean_path):
            """Map a URL path to a file inside dist_dir (npx serve -s semantics).

            Returns (fs_path, spa_fallback); fs_path may be 'REDIRECT:<url>' for
            directory URLs missing their trailing slash, or None for a 404.
            Raises PermissionError on any traversal attempt (raw or encoded).
            """
            decoded = urllib.parse.unquote(clean_path)
            rel = decoded.lstrip("/")
            parts = [p for p in rel.split("/") if p not in ("", ".")]
            if any(p == ".." for p in parts) or decoded.startswith("/../"):
                raise PermissionError(decoded)
            if not parts:
                return os.path.join(dist_dir, "index.html"), False
            fs_path = os.path.join(dist_dir, *parts)
            if os.path.isdir(fs_path):
                if not clean_path.endswith("/"):
                    return "REDIRECT:" + decoded + "/", False
                if os.path.isfile(os.path.join(fs_path, "index.html")):
                    return os.path.join(fs_path, "index.html"), False
                return os.path.join(dist_dir, "index.html"), True
            if os.path.isfile(fs_path):
                return fs_path, False
            # serve -s: extension-less paths are SPA routes; missing files that
            # carry an extension (e.g. hashed assets) are genuine 404s.
            if "." not in parts[-1]:
                return os.path.join(dist_dir, "index.html"), True
            return None, False

        def _serve_static(self, clean_path, include_body=True):
            try:
                fs_path, _spa = self._resolve_static(clean_path)
            except PermissionError:
                self.send_error(403, "Forbidden")
                return
            if fs_path is None:
                self.send_error(404, "Not Found")
                return
            if isinstance(fs_path, str) and fs_path.startswith("REDIRECT:"):
                self.send_response(301)
                self.send_header("Location", fs_path[len("REDIRECT:"):])
                self.send_header("Content-Length", "0")
                self.end_headers()
                return

            try:
                st = os.stat(fs_path)
                with open(fs_path, "rb") as f:
                    data = f.read()
            except OSError:
                self.send_error(404, "Not Found")
                return

            ctype = mimetypes.guess_type(fs_path)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype in ("application/javascript", "application/json", "image/svg+xml"):
                ctype += "; charset=utf-8"

            etag = '"%x-%x"' % (st.st_mtime_ns, st.st_size)
            cache_control = self._cache_control(fs_path)

            # Conditional request -> 304 revalidation (no body by definition)
            if etag in (self.headers.get("If-None-Match") or ""):
                self.send_response(304)
                self.send_header("ETag", etag)
                self.send_header("Cache-Control", cache_control)
                self.end_headers()
                return

            range_header = (self.headers.get("Range") or "").strip()
            can_gzip = (
                include_body
                and not range_header
                and "gzip" in (self.headers.get("Accept-Encoding") or "")
                and os.path.splitext(fs_path)[1].lower() in self.SERVE_COMPRESSIBLE_EXTS
                and len(data) > 1024
            )
            if can_gzip:
                data = gzip.compress(data, compresslevel=6)

            common_headers = [
                ("ETag", etag),
                ("Cache-Control", cache_control),
                ("Accept-Ranges", "bytes"),
                ("X-Content-Type-Options", "nosniff"),
            ]

            # HTTP Range support (media seeking, resumable downloads). Skipped
            # when gzipping since ranges must address the on-disk bytes.
            if range_header and not can_gzip:
                m = re.match(r"^bytes=(\d*)-(\d*)$", range_header)
                size = st.st_size
                if m and (m.group(1) or m.group(2)) and size > 0:
                    if m.group(1):
                        start = int(m.group(1))
                        end = int(m.group(2)) if m.group(2) else size - 1
                    else:
                        start = max(0, size - int(m.group(2)))
                        end = size - 1
                    if start >= size or start > end:
                        self.send_response(416)
                        self.send_header("Content-Range", "bytes */%d" % size)
                        self.send_header("Content-Length", "0")
                        self.end_headers()
                        return
                    end = min(end, size - 1)
                    chunk = data[start:end + 1]
                    self.send_response(206)
                    self.send_header("Content-Type", ctype)
                    self.send_header("Content-Range", "bytes %d-%d/%d" % (start, end, size))
                    for k, v in common_headers:
                        self.send_header(k, v)
                    self.send_header("Content-Length", str(len(chunk)))
                    self.end_headers()
                    if include_body:
                        self.wfile.write(chunk)
                    return
                # Malformed Range header: fall through to a full 200 response.

            self.send_response(200)
            self.send_header("Content-Type", ctype)
            for k, v in common_headers:
                self.send_header(k, v)
            if can_gzip:
                self.send_header("Content-Encoding", "gzip")
                self.send_header("Vary", "Accept-Encoding")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            if include_body:
                self.wfile.write(data)

        def do_HEAD(self):
            clean_path = self.path.split("?")[0]
            if clean_path.startswith("/api/"):
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.end_headers()
                return
            if has_dist:
                self._serve_static(clean_path, include_body=False)
                return
            if clean_path in ("/", "/index.html"):
                html_bytes = get_standalone_html().encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(html_bytes)))
                self.end_headers()
            else:
                self.send_error(404, "Not Found")

        def do_GET(self):
            clean_path = self.path.split("?")[0]
            if clean_path in ["/api/status", "/api"]:
                db_data = read_database(db_path)
                status_str = get_process_status()
                clean_status = status_str.replace(GREEN, "").replace(RED, "").replace(YELLOW, "").replace(RESET, "")
                safe_config = {k: v for k, v in env_config.items() if "KEY" not in k and "SECRET" not in k and "WEBHOOK" not in k}
                control = read_control(env_config.get("CONTROL_FILE", "./data/engine_control.json"))

                # Live balance and candidate symbols
                balance_info = fetch_binance_balance(env_config, db_data)
                candidates = fetch_scanned_pairs(env_config, db_data)

                # Merge balance info into risk payload so legacy clients read total_equity automatically
                risk_payload = dict(db_data.get("risk", {}))
                risk_payload["total_equity"] = str(balance_info.get("total_equity", 0.0))
                risk_payload["live_equity"] = str(balance_info.get("total_equity", 0.0))
                risk_payload["paper_balance"] = str(balance_info.get("total_equity", 0.0))
                risk_payload["free_quote"] = str(balance_info.get("free_quote", 0.0))
                risk_payload["locked_quote"] = str(balance_info.get("locked_quote", 0.0))

                payload = {
                    "process": clean_status,
                    "config": safe_config,
                    "balance": balance_info,
                    "candidates": candidates,
                    "scanned_pairs": candidates,
                    "data": {
                        "risk": risk_payload,
                        "trades": db_data.get("trades", []),
                        "orders": db_data.get("orders", []),
                        "stats": db_data.get("stats", {}),
                        "balance": balance_info,
                        "scanned_pairs": candidates,
                        "balances": balance_info.get("balances", [])
                    },
                    "control": {
                        "paused": bool(control.get("paused", False)),
                        "pause_reason": control.get("pause_reason", "") or ""
                    },
                    "server_time": datetime.now().isoformat(),
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                }
                self._send_json(payload)
                return

            if clean_path == "/api/logs":
                query = parse_qs(urlparse(self.path).query)
                try:
                    lines = min(int(query.get("lines", ["120"])[0]), 500)
                except ValueError:
                    lines = 120
                log_path = env_config.get("LOG_FILE", "./logs/trading.log")
                self._send_json({"lines": tail_log_file(log_path, lines)})
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
                self._send_json(payload)
                return

            if clean_path == "/api/config":
                safe_config = {k: v for k, v in env_config.items() if "KEY" not in k and "SECRET" not in k and "WEBHOOK" not in k}
                self._send_json(safe_config)
                return

            if has_dist:
                self._serve_static(clean_path)
                return

            # No compiled dist: serve the built-in dashboard only on the root
            # path and 404 everything else (never return the page for arbitrary
            # or traversal-looking paths).
            if clean_path not in ("/", "/index.html"):
                self.send_error(404, "Not Found")
                return
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_cors_headers()
            html = get_standalone_html()
            html_bytes = html.encode("utf-8")
            self.send_header("Content-Length", str(len(html_bytes)))
            self.end_headers()
            self.wfile.write(html_bytes)

        def do_POST(self):
            clean_path = self.path.split("?")[0]
            body = self._read_json_body()
            if body is None:
                self._send_json({"ok": False, "message": "Invalid or missing JSON body."}, status=400)
                return

            if clean_path == "/api/control":
                control_path = env_config.get("CONTROL_FILE", "./data/engine_control.json")
                # Idempotency: if the caller re-posts the same action+identifier we treat
                # it as a no-op rather than stacking duplicate close_all/close_symbol
                # commands (each would generate a new command_id and compete).
                action = body.get("action")
                existing_cmd_id = body.get("command_id")
                existing_control = read_control(control_path)
                if existing_cmd_id and existing_control.get("command_id") == existing_cmd_id:
                    public_control = {k: v for k, v in existing_control.items() if k != "command_id"}
                    self._send_json({"ok": True, "action": action, "control": public_control, "duplicate": True})
                    return
                control = dict(existing_control)
                if action == "pause":
                    control["paused"] = True
                    control["pause_reason"] = body.get("reason", "paused from web monitor")
                elif action == "resume":
                    control["paused"] = False
                    control.pop("pause_reason", None)
                elif action == "close_all":
                    control["close_all"] = True
                    control["command_id"] = str(uuid.uuid4())
                elif action == "close_symbol":
                    symbol = str(body.get("symbol", "")).strip().upper()
                    if not symbol:
                        self._send_json({"ok": False, "message": "symbol is required for close_symbol"}, status=400)
                        return
                    # If a close_symbol is already pending for the same symbol, re-use it
                    # rather than writing a second command that races the first.
                    pending = control.get("close_symbol", "")
                    if pending and str(pending).strip().upper() == symbol and not body.get("force"):
                        public_control = {k: v for k, v in control.items() if k != "command_id"}
                        self._send_json({"ok": True, "action": action, "control": public_control, "duplicate": True})
                        return
                    control["close_symbol"] = symbol
                    control["command_id"] = str(uuid.uuid4())
                else:
                    self._send_json({"ok": False, "message": f"Unknown action: {action}"}, status=400)
                    return
                # Clear any stale command_id that belonged to a now-resolved request so a
                # new request can get a fresh identifier.
                if action in ("pause", "resume"):
                    control.pop("command_id", None)
                    control.pop("close_all", None)
                    control.pop("close_symbol", None)
                write_control(control_path, control)
                public_control = {k: v for k, v in control.items() if k != "command_id"}
                self._send_json({"ok": True, "action": action, "control": public_control})
                return

            if clean_path == "/api/config":
                raw = body.get("env_file")
                if not isinstance(raw, str) or not raw.strip():
                    self._send_json({"ok": False, "message": "env_file content is required"}, status=400)
                    return
                updates = parse_env_payload(raw)
                if not updates:
                    self._send_json({"ok": False, "message": "No whitelisted tunable keys found in payload"}, status=400)
                    return
                env_path = find_env_path()
                applied = apply_env_updates(env_path, updates)

                # Safety: if the pushed config would switch the engine from paper to live
                # trading without valid auth credentials, abort the push so a PM2 reload
                # cannot leave the engine in a boot-failure state.
                if "PAPER_TRADE" in updates:
                    new_paper = str(updates["PAPER_TRADE"]).lower() == "true"
                    if not new_paper:
                        tentative = dict(env_config)
                        tentative.update(updates)
                        api_key = str(tentative.get("BINANCE_API_KEY", "")).strip()
                        api_secret = str(tentative.get("BINANCE_API_SECRET", "")).strip()
                        private_key_path = str(tentative.get("BINANCE_PRIVATE_KEY_PATH", "")).strip()
                        has_auth = bool(api_key and (api_secret or (private_key_path and os.path.exists(private_key_path))))
                        if not has_auth:
                            self._send_json({"ok": False, "message": "Cannot switch PAPER_TRADE=false: no valid BINANCE_API_KEY + secret/key path found in the pushed config."}, status=400)
                            return

                result = {"ok": True, "applied": applied, "count": len(applied)}
                if applied and shutil.which("pm2"):
                    try:
                        proc = subprocess.run(
                            ["pm2", "reload", "ultimate-bot"],
                            capture_output=True, text=True, timeout=25
                        )
                        out = (proc.stdout or proc.stderr or "").strip()[-500:]
                        result["reload"] = {"attempted": True, "exit_code": proc.returncode, "output": out}
                    except Exception as e:
                        result["reload"] = {"attempted": True, "error": str(e)}
                else:
                    result["reload"] = {
                        "attempted": False,
                        "hint": "pm2 not detected — run 'pm2 reload ultimate-bot' (or restart the engine) to apply."
                    }
                # Do NOT touch the engine control file (pause/close_all/close_symbol)
                # when a config push happens. A pending close command that is still
                # retrying rejected exits must survive the .env/PM2 reload so the
                # operator's emergency request is not silently dropped mid-liquidation.
                self._send_json(result)
                return

            self._send_json({"ok": False, "message": f"Unknown endpoint: {clean_path}"}, status=404)

    server = ThreadingHTTPServer(("0.0.0.0", port), CustomHandler)
    print(f"{GREEN}{BOLD}⚡ Binance Bot Web Monitor running at:{RESET}")
    print(f"   {CYAN}http://0.0.0.0:{port}{RESET} (Local & VPS IP)")
    if has_dist:
        print(f"   {DIM}Mode: Serving compiled React dashboard from ./dist (SPA fallback, gzip, ETag/304, Range, keep-alive){RESET}")
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
