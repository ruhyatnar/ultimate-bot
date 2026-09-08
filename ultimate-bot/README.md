# 🚀 Ultimate Binance Market-Only Trading Bot

A production-grade, algorithmic trading bot designed specifically for **Binance Spot Trading** with **Market-Only Execution**, a **5-Factor Smart Money Confluence Strategy**, **Strict Risk & Drawdown Management**, and **Ed25519 Asymmetric Cryptography**.

Engineered for **Debian 13 (Trixie) CLI-only VPS** environments with zero GUI overhead, complete PEP 668 compliance, process supervision via PM2, and a unified terminal **and** web monitor (`status.py`).

---

## 📑 Table of Contents

1. [Core Features & Architecture](#-core-features--architecture)
2. [Architecture & Data Flow](#-architecture--data-flow)
3. [5-Factor Confluence Strategy](#-5-factor-confluence-strategy)
4. [Paper vs. Live Trading](#-paper-vs-live-trading)
5. [Live Readiness Checklist & Safety Protocols](#-live-readiness-checklist--safety-protocols)
6. [Installation & Setup (Debian 13 VPS)](#-installation--setup-debian-13-vps)
7. [Ed25519 Asymmetric API Key Setup](#-ed25519-asymmetric-api-key-setup)
8. [Configuration Reference (`.env`)](#-configuration-reference-env)
9. [Strategy Presets (Scalping, Day, Swing)](#-strategy-presets-scalping-day-swing)
10. [Running the Bot (PM2 Supervision)](#-running-the-bot-pm2-supervision)
11. [Monitoring: CLI, Web Server & Control API](#-monitoring-cli-web-server--control-api)
12. [Risk Management & Safety Mechanisms](#-risk-management--safety-mechanisms)
13. [Troubleshooting & Emergency Procedures](#-troubleshooting--emergency-procedures)

---

## ⚡ Core Features & Architecture

- **100% Market Orders Only**: Zero maker orders, zero orphaned limit orders. Positions enter and exit immediately with slippage guards and post-exit orphan-order cleanup.
- **Ed25519 Signing**: Asymmetric (`ed25519`) signing on both the REST and WebSocket API paths — no shared HMAC secret, matching Binance's modern institutional security standard. (HMAC-SHA256 via `BINANCE_API_SECRET` is still supported as a fallback.)
- **Multi-Stream WebSockets**: Public market-data WebSocket streaming for real-time tick prices (aggTrade + kline bars) with automatic REST fallback, plus the authenticated Binance WebSocket API v3 for low-latency order routing.
- **SQLite State Machine**: ACID-compliant persistence (`data/trading.db`) with **WAL mode**, a **dedicated read-only connection** for the monitor, and an **asynchronous batched write queue** that eliminates `database is locked` errors.
- **Debian 13 & PEP 668 Native**: Runs inside an isolated Python virtual environment (`python3-venv`), never polluting system packages.
- **PM2 Process Supervision**: `ecosystem.config.js` supervises **both** the engine (`main.py`) and the web monitor (`status.py --web 3000`) with auto-restart, a 2 GB memory cap, and rotating log files.
- **Unified Terminal & Web Monitor**: `status.py` serves an `htop`-style terminal dashboard **and** an embedded HTTP API (`/api/status`, `/api/logs`, `/api/health`, `/api/config`, `/api/control`) used by the interactive React web dashboard.
- **Remote Operation**: The web dashboard can pause new entries, resume, liquidate all positions, close a single symbol, and push tuned `.env` parameters — no SSH required.
- **Config Boot Validation**: `config.py` validates every tunable key at startup (ranges, non-negativity, integer minimums) so a typo in `.env` fails fast with a clear message instead of producing silent bad behavior.
- **Feeds the Web Operations Center**: the engine persists live positions, orders, risk state, scanned candidates and balances to SQLite, and the React dashboard reads them over `status.py`'s API — the UI never fabricates server-side figures.

---

## 🎯 5-Factor Confluence Strategy

A `BUY` order is only evaluated when `SIGNAL_THRESHOLD` independent factors align simultaneously (default **4 of 5**). Every factor is recomputed on each scan pass over the candle data. **SELL** confluence is also computed for symmetry, but **never executed** — the engine is spot long-only.

| # | Factor | Calculation | Bullish Signal Condition |
|---|---|---|---|
| **1** | Multi-Timeframe Trend (HTF) | Dual EMA on the higher timeframe (`MTF_TIMEFRAME`) | `EMA(50) > EMA(200)` on the MTF (bearish when inverted) |
| **2** | Break of Structure (BOS) | Fractal swing highs/lows (`SWING_LOOKBACK`) | Higher swing high **and** higher swing low, or price trading above the last swing high |
| **3** | Fair Value Gap (FVG) | 3-candle displacement on **closed** candles | Candle low 2 bars back > the high 3 candles back by > 0.05% of price (bullish gap) |
| **4** | Order-Flow CVD | Cumulative Volume Delta over the last 20 bars (`taker_buy_quote − (quote_volume − taker_buy_quote)`) | Net taker buy dominance (`CVD > 0`) |
| **5** | Volume POC | Point of Control = highest-volume price bin over the last 20 bars | Current price trades **above** the POC (support) |

Confluence score = number of aligned factors (1–5). When `bullish >= SIGNAL_THRESHOLD` a market **BUY** is triggered. Requires `SIGNAL_THRESHOLD` of 1–5 (validated at boot).

### Exit Management

Open positions are re-evaluated every cycle and closed by market order on the first condition that fires:

- **ATR Stop Loss** — `entry − ATR × ATR_MULTIPLIER_SL`.
- **Take Profit** — `entry + ATR × ATR_MULTIPLIER_TP` (never closer than `MIN_TP_PERCENT`).
- **Gap-Breach Protection** — stop/TP checks compare both the just-closed and the currently forming candle's low/high (not only the live tick), so violent wicks that pierce the stop between polls still trigger the exit.
- **Trailing Stop** — activates at `TRAILING_STOP_ACTIVATE` profit and ratchets up with `TRAILING_STOP_CALLBACK`.
- **Fee-Aware Breakeven Lock** — at ≥ +1% profit the stop moves to `entry × 1.0025`, covering the 0.2% round-trip taker fees.
- **Max Hold Time** — positions older than `MAX_HOLD_TIME` seconds are closed (TIME_STOP).
- **Partial-Fill Handling** — a partially filled exit order is cancelled, remaining marketable balance is re-quantized and re-tracked; non-tradable dust is treated as a full exit.

All realized PnL is **net of 0.1% taker fees on both legs** (0.2% round-trip) so paper results match live expectations.

> **Important long-only note**: `SELL` confluence is computed for symmetry but never executed — the engine is spot long-only. A bearish confluence score therefore does **not** open a short; it just means that symbol is skipped for entries until the trend flips back.

---

## 📊 Paper vs. Live Trading

| Feature | Paper Trading (`PAPER_TRADE=true`) | Live Trading (`PAPER_TRADE=false`) |
|---|---|---|
| **Real Funds at Risk** | ❌ None (simulated equity, seeded from `paper_balance` risk state) | ⚠️ Real Binance Spot balance |
| **Market Data** | ✅ Real-time public Binance WebSocket | ✅ Real-time public Binance WebSocket |
| **Order Placement** | Simulated instant fills at the current market price | Real execution via Binance WebSocket API / REST |
| **Exchange Filters** | Sanitized against `LOT_SIZE` & `MIN_NOTIONAL` | Sanitized against `LOT_SIZE` & `MIN_NOTIONAL` |
| **API Keys Required** | ❌ None | ✅ `BINANCE_API_KEY` + Ed25519 private key **or** `BINANCE_API_SECRET` |
| **Position Reconciliation** | N/A (simulated) | Periodic + startup reconciliation against real spot balances |
| **Database & Dashboard** | ✅ Logged to `trading.db`, visible in `status.py` | ✅ Logged to `trading.db`, visible in `status.py` |

> 💡 **Recommendation**: Run the bot in **Paper mode for 24–48 hours** to validate signals and exits on your VPS before switching to live funds.

### Potential Issues Identified & Fixed

1. **Fee Drag & Net PnL Miscalculation (FIXED)** — PnL is now net of 0.1% taker fees on both legs so a "profitable" strategy cannot hide fee bleed.
2. **Orphan Orders on Exit (FIXED)** — `close_trade` purges any lingering open orders for the symbol (`DELETE /api/v3/openOrders`) to prevent late unexpected fills.
3. **Database Locking Conflicts (FIXED)** — `status.py` reads via `mode:ro` + WAL + 10 s busy timeout; the engine batches writes through a single writer coroutine.
4. **Dust / Fee-Deduction Sell Rejections (FIXED)** — exit SELL quantities are auto-clamped to the actual free base-asset balance so Binance `-2010 Insufficient Balance` rejections are avoided when the taker fee is deducted from the base asset.
5. **Min Notional Floor** — every order is checked against `MIN_NOTIONAL` (Binance `NOTIONAL` filter). Keep at least $25–$100 USDT so allocations cleanly clear the $5–$10 floor.
6. **Rejected Exit Orders Could Abandon Positions (FIXED)** — if an exit order is rejected (network outage, dust balance, exchange hiccup), the position is now re-armed with its stop and the next cycle retries the close. Remote `close_all` / `close_symbol` commands also retry rejected exits until every requested position is actually closed; new entries stay blocked while a close command is pending.
7. **Gap-Breach Stop Could Miss Closed-Candle Wicks (FIXED)** — the stop/TP check now evaluates both the just-closed candle and the forming candle's low/high, not only the live tick, so a wick that pierced the stop on a candle that closed between polls is still caught.
8. **Zero-Equity Entry Safeguard (FIXED)** — `calculate_position_size` explicitly returns `0.0` when total equity or entry price is non-positive, preventing an empty or wiped wallet from attempting to place fallback base orders.
9. **8-Decimal Quantization & Formatting (FIXED)** — order quantity string generation now formats up to 8 decimal places (`.8f`), preventing truncation or scientific notation rejections on high-precision / low-price crypto assets (e.g. BTC, SHIB, PEPE).
10. **High-Volatility Slippage Parameter Range (FIXED)** — `MAX_SLIPPAGE_PERCENT` validator expanded from `(0, 1]` to `(0, 10.0]`, allowing traders to set custom slippage thresholds for fast-moving pairs without boot-time errors.
11. **Directory-Agnostic Environment Discovery (FIXED)** — `status.py` dynamically locates `.env` regardless of whether invoked from the project root or the `ultimate-bot/` directory.

---

## 🛡️ Live Readiness Checklist & Safety Protocols

Before setting `PAPER_TRADE=false` in `.env`, run through this mandatory checklist:

- [ ] **1. API Key Permissions**: Enable **Reading** and **Spot & Margin Trading**. **CRITICAL: never enable withdrawals**.
- [ ] **2. IP Restriction**: Restrict the key to your VPS static public IP.
- [ ] **3. Ed25519 Private Key**: `keys/private_key.pem` exists on the VPS with `chmod 600`. The matching public key is registered on Binance API Management (or `BINANCE_API_SECRET` is set for HMAC auth).
- [ ] **4. BNB Fee Discount (Optional)**: hold a little BNB with "Use BNB for fees" for a 25% discount.
- [ ] **5. Paper Run First**: 24–48 h of `PAPER_TRADE=true` observing signals, trailing stops and daily resets.
- [ ] **6. Conservative Initial Risk**: e.g. `MAX_SYMBOLS=2`, `BALANCE_USAGE_PERCENT=0.30`, `MAX_SYMBOL_ALLOCATION_PERCENT=0.15`, `MAX_DAILY_DRAWDOWN=0.03`.
- [ ] **7. System Clock Sync**: `timedatectl status` shows NTP active (Binance `-1021` timestamps are otherwise possible; the bot also auto-syncs server time).

---

## 📦 Installation & Setup (Debian 13 VPS)

### Step 1 — System packages
```bash
sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install -y python3 python3-venv python3-pip git curl openssl
```

### Step 2 — Node.js & PM2 (for the web monitor / optional dashboard hosting)
```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs
sudo npm install -g pm2
```

### Step 3 — Project & virtual environment (PEP 668 compliant)
```bash
cd /path/to/ultimate-bot

python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt
```

### Step 4 — Generate Ed25519 keys (skip if you plan paper-only, but do this before live)
```bash
mkdir -p keys && chmod 700 keys
openssl genpkey -algorithm Ed25519 -out keys/private_key.pem
chmod 600 keys/private_key.pem
openssl pkey -in keys/private_key.pem -pubout -out keys/public_key.pem
cat keys/public_key.pem
```

### Step 5 — Configure
```bash
cp .env.example .env
nano .env          # start with PAPER_TRADE=true
```

---

## 🔑 Ed25519 Asymmetric API Key Setup

```bash
cd /path/to/ultimate-bot
mkdir -p keys && chmod 700 keys

openssl genpkey -algorithm Ed25519 -out keys/private_key.pem
chmod 600 keys/private_key.pem

openssl pkey -in keys/private_key.pem -pubout -out keys/public_key.pem
cat keys/public_key.pem
```

1. Log in to [Binance.com](https://www.binance.com) → **API Management**.
2. **Create API** → select **Self-Generated (Ed25519)**.
3. Paste the contents of `keys/public_key.pem`.
4. Copy the generated **API Key** into `.env` as `BINANCE_API_KEY`.
5. Enable **Enable Spot & Margin Trading**. Keep **Permit Withdrawals DISABLED**.
6. Under **IP Access Restriction**, restrict to your VPS static IP.

---

## ⚙️ Configuration Reference (`.env`)

Copy the documented example (`cp .env.example .env`) — every key below is read by the engine at boot. Keys that are absent fall back to the preset/profile defaults shown.

### Trading mode & credentials
```ini
# true = paper simulation (no keys required) | false = live spot trading
PAPER_TRADE=true
# Route live orders to the Binance Spot testnet
USE_TESTNET=false

# Live mode requires BINANCE_API_KEY plus the Ed25519 private key path ...
BINANCE_API_KEY=your_binance_api_key_here
BINANCE_PRIVATE_KEY_PATH=./keys/private_key.pem
# ... OR a classic HMAC-SHA256 secret instead of the private key file:
# BINANCE_API_SECRET=your_hmac_secret_here
```

### Strategy profile & timeframes
```ini
# scalping | day | swing  (see preset table below)
PRESET=day

# Optional overrides — if omitted the active preset supplies them:
TIMEFRAME=5m                # execution timeframe
MTF_TIMEFRAME=1h            # higher timeframe for the HTF trend factor
ATR_PERIOD=14
ATR_MULTIPLIER_SL=1.5       # stop distance = ATR * multiplier
ATR_MULTIPLIER_TP=2.5       # take profit distance = ATR * multiplier
TRAILING_STOP_ACTIVATE=0.015
TRAILING_STOP_CALLBACK=0.005
SWING_LOOKBACK=5
MAX_HOLD_TIME=28800         # seconds before a TIME_STOP exit
```

### Signal confluence engine
```ini
SIGNAL_THRESHOLD=4          # minimum 1–5 aligned bullish factors to BUY
SIGNAL_INTERVAL=10          # seconds between scan passes per symbol
ENTRY_TIMEOUT=15            # seconds to wait for a market order fill
MAX_SLIPPAGE_PERCENT=0.5    # skip entry if price moved more than this
MIN_TP_PERCENT=0.005        # take-profit never closer than this fraction
```

### Symbols
```ini
STATIC_SYMBOLS=BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT
DYNAMIC_SYMBOLS=false       # true = screen top momentum pairs instead
MAX_SYMBOLS=5               # max concurrent monitored symbols / positions
QUOTE_ASSET=USDT
EXCLUDE_SYMBOLS=USDC,BUSD,FDUSD,TUSD,UP,DOWN
SYMBOL_REFRESH_INTERVAL=3600  # seconds between dynamic rescreens
```

### Dynamic screener tuning
```ini
TOP_CANDIDATES=50
MIN_VOLUME_USDT=1000000
MIN_PRICE_CHANGE_PERCENT=0.5
MIN_VOLATILITY_PERCENT=0.3
ADX_THRESHOLD=25
ADX_PERIOD=14
Z_SCORE_WEIGHT_VOLUME=0.20
Z_SCORE_WEIGHT_CHANGE=0.20
Z_SCORE_WEIGHT_VOLATILITY=0.20
Z_SCORE_WEIGHT_ADX=0.40
CORRELATION_THRESHOLD=0.70   # penalize pairs correlated above this
CORRELATION_PENALTY=0.90
TREND_LOOKBACK=20
```

### Risk & portfolio management
```ini
BALANCE_USAGE_PERCENT=0.5      # max fraction of total equity deployed
MAX_SYMBOL_ALLOCATION_PERCENT=0.2  # max fraction per single position
MAX_DAILY_DRAWDOWN=0.05        # halt new entries at a 5% daily loss (incl. unrealized)
MAX_LOSS_STREAK=3              # cooldown after N losses on a symbol
COOLDOWN_LOSS=3600             # seconds
MAX_WIN_STREAK=5               # cooldown after N wins on a symbol (profit lock)
COOLDOWN_WIN=1800              # seconds
BASE_ORDER_SIZE=0.001          # sizing fallback when equity is unknown
```

### Storage, webhooks, logging, operations
```ini
DB_PATH=./data/trading.db
CONTROL_FILE=./data/engine_control.json   # remote pause/close channel from the web monitor

DISCORD_WEBHOOK_URL=           # blank = alerts silently disabled
DISCORD_COOLDOWN=30            # seconds between Discord messages

LOG_LEVEL=INFO                 # DEBUG | INFO | WARNING | ERROR
LOG_FILE=./logs/trading.log    # 10 MB rotating, 5 backups

HEALTH_CHECK_INTERVAL=60       # seconds between REST/WS/DB health probes
REST_WEIGHT_LIMIT=1200         # aiolimiter budget per minute
AUTO_LIQUIDATE_ORPHANS=false   # true = SELL unmanaged tradable spot balances
```

> ⚠️ **Wallet safety**: keep `AUTO_LIQUIDATE_ORPHANS=false` so pre-existing spot balances in your wallet are never automatically sold.

---

## 📊 Strategy Presets (Scalping, Day, Swing)

Set `PRESET=scalping|day|swing` in `.env`. Presets only apply where a key is **not** explicitly set in `.env`.

| Setting | Scalping (`scalping`) | Day Trading (`day`) | Swing Trading (`swing`) |
|---|---|---|---|
| Execution Timeframe | `1m` | `5m` | `15m` |
| HTF Timeframe | `15m` | `1h` | `4h` |
| ATR Period | `10` | `14` | `20` |
| Stop Loss Multiplier | `0.8× ATR` | `1.5× ATR` | `2.0× ATR` |
| Take Profit Multiplier | `1.2× ATR` | `2.5× ATR` | `4.0× ATR` |
| Trailing Stop Activation | `+0.5%` | `+1.5%` | `+2.5%` |
| Trailing Stop Callback | `0.2%` | `0.5%` | `1.0%` |
| Swing Lookback | `3` | `5` | `8` |
| Max Hold Time | `1 hour` | `8 hours` | `24 hours` |

---

## 🏃 Running the Bot (PM2 Supervision)

`ecosystem.config.js` launches two supervised processes:

| App name | Purpose |
|---|---|
| `ultimate-bot` | Core 5-factor trading engine (`main.py`) |
| `bot-web-monitor` | Web API + dashboard server (`status.py --web 3000`) |

```bash
cd /path/to/ultimate-bot
pm2 start ecosystem.config.js
pm2 save
pm2 startup        # survive reboots

pm2 status                          # process state
pm2 logs ultimate-bot               # stream engine logs
pm2 restart ultimate-bot            # restart engine
pm2 reload ultimate-bot             # zero-downtime config reload
pm2 restart bot-web-monitor         # restart the web monitor
```

---

## 🖥️ Monitoring: CLI, Web Server & Control API

### CLI terminal dashboard
```bash
./venv/bin/python3 status.py          # single snapshot
./venv/bin/python3 status.py --watch  # live-refresh every 2 s
```

### Web monitor
```bash
# Option 1 — direct (recommended for quick checks)
./venv/bin/python3 status.py --web 3000

# Option 2 — supervised 24/7 via PM2 (already in ecosystem.config.js)
pm2 start ecosystem.config.js

# Option 3 — prebuilt React dashboard (if a compiled ./dist exists next to status.py)
npx serve -s dist -l 3000
```

Then open `http://YOUR_VPS_IP:3000`. The React dashboard auto-connects to `/api/status` on the same origin, or you can point the **VPS Connection Bar** at any remote endpoint. If no compiled `dist/` is found, `status.py --web` falls back to a built-in standalone dark-mode dashboard.

> **Candle subscription note**: the WebSocket market stream subscribes to each monitored symbol's `aggTrade` + `kline_<TIMEFRAME>` streams. Binance public streams are free and do not require an API key, but each connection is limited to 500 streams — the bot bounds symbol lists to that cap.

### HTTP API

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/status` | GET | Full snapshot: engine process state, SQLite trades/orders/risk/stats, live balance, scanned candidates, sanitized config, pause state |
| `/api/logs?lines=120` | GET | Tail `logs/trading.log` for the web Debug Console |
| `/api/health` | GET | Lightweight liveness probe |
| `/api/config` | GET / POST | Read sanitized config / apply a whitelisted `.env` payload |
| `/api/control` | POST | `{"action": "pause" \| "resume" \| "close_all" \| "close_symbol", "symbol": "…"}` |

Notes:

- `pause` blocks **new entries** while open positions stay fully managed (stops/TP/trailing remain armed). `close_all` / `close_symbol` write one-shot commands (`command_id`) into `CONTROL_FILE`; the engine executes them **and retries rejected exits until every requested position is actually closed** (new entries stay blocked while a close command is pending).
- `/api/config` accepts only a **whitelist of tuning keys** — credentials, key paths, and webhooks are never writable from the browser. After applying, it runs `pm2 reload ultimate-bot` when PM2 is detected.
- Secrets (`BINANCE_API_KEY`, secrets, webhook URLs) are stripped from every API response.
- CORS is enabled so the React dashboard can be hosted anywhere (e.g. a static host) and pointed at the VPS.
- The `/api/status` response also returns the engine's **control state** (`paused`, etc.) so the dashboard can reflect a remote pause without waiting for the next manual refresh.

---

## 🛡️ Risk Management & Safety Mechanisms

1. **Single-Instance Lock** — `fcntl` file lock on `/tmp/ultimate_bot.lock` prevents duplicate instances from double-executing orders.
2. **Daily Drawdown Circuit Breaker** — new entries halt when realized + unrealized daily loss reaches `MAX_DAILY_DRAWDOWN`; resets at UTC midnight.
3. **Per-Symbol Streak Cooldowns** — after `MAX_LOSS_STREAK` consecutive losses (or `MAX_WIN_STREAK` wins) a symbol rests for `COOLDOWN_LOSS` / `COOLDOWN_WIN`. Streaks and cooldowns persist across restarts via SQLite.
4. **Health Check & Self-Healing** — periodic REST ping, WS API/stream connectivity, and a real SQLite read probe; components are reconnected automatically and trading pauses during exchange maintenance windows.
5. **Exchange Position Reconciliation** — on startup and every 60 s in live mode the engine matches tracked positions against real balances, removes external-closed/dust positions, and optionally liquidates orphan balances (`AUTO_LIQUIDATE_ORPHANS`).
6. **Rate-Limit Protection** — `aiolimiter` caps REST weight at 1,200/min; kline caches are bounded (FIFO, 60 s TTL) so dynamic screening cannot exhaust the budget or memory.
7. **Filter-Exact Order Sanitization** — every order is quantized with `Decimal` against `stepSize`/`minQty`/`maxQty` and validated against `NOTIONAL`/`MIN_NOTIONAL`.
8. **Timestamp Sync** — server-time offset refreshed every 10 minutes to avoid `-1021` rejections.
9. **Exit Failsafes** — a rejected/crashed exit re-arms the position with its stop and alerts loudly; it is retried on the next cycle (or by remote-command retry) and never silently dropped.
10. **Exit Fill Accuracy** — live exits always read the exchange `avgPrice` for slippage-accurate PnL.
11. **Order-Quantity Edge Cases** — quantity strings are never allowed to become empty (which would send a blank `quantity` and get rejected), and `Decimal` quantization guards against floating-point step-size artifacts.
12. **WebSocket Timeouts Are Retryable** — the authenticated WS-API client now retries the per-request `recv()` up to ~100 s before treating a response as lost, so momentary stalls don't abort orders.
13. **Kline Cache Coherence** — completed kline updates are applied atomically so the tick price, ATR refresh, and gap-breach checks never see a partially-written candle.

---

## 🚨 Troubleshooting & Emergency Procedures

### Emergency stop (close all positions)
```bash
# Option A — from the web dashboard: press "Close All"
# Option B — via the control API:
curl -X POST http://YOUR_VPS_IP:3000/api/control -H "Content-Type: application/json" \
  -d '{"action": "close_all"}'

# Option C — stop the engine (positions then need manual handling in the Binance app)
pm2 stop ultimate-bot
./venv/bin/python3 status.py
```

### "Another instance is already running"
A stale lock file after a crash:
```bash
rm -f /tmp/ultimate_bot.lock
pm2 restart ultimate-bot
```

### Timestamp / `-1021` errors
The bot auto-syncs with Binance server time, but keep NTP healthy:
```bash
sudo timedatectl set-ntp on
sudo systemctl restart systemd-timesyncd
```

### Discord alerts not arriving
Ensure `DISCORD_WEBHOOK_URL` is populated. When blank, alerts are cleanly silenced and never interrupt trading.

### Web monitor shows stale/zero data
Confirm `status.py --web 3000` and the engine share the same `DB_PATH`/`.env`, and that port 3000 is open in the cloud security group (TCP inbound). The dashboard reads live state from SQLite — it never fabricates server figures.

