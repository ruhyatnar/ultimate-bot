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
13. [Backtesting (Prove It Before You Trade It)](#-backtesting-prove-it-before-you-trade-it)
14. [Troubleshooting & Emergency Procedures](#-troubleshooting--emergency-procedures)

---

## ⚡ Core Features & Architecture

- **100% Market Orders Only**: Zero maker orders, zero orphaned limit orders. Positions enter and exit immediately with slippage guards and post-exit orphan-order cleanup.
- **Ed25519 Signing**: Asymmetric (`ed25519`) signing on both the REST and WebSocket API paths — no shared HMAC secret, matching Binance's modern institutional security standard. (HMAC-SHA256 via `BINANCE_API_SECRET` is still supported as a fallback.)
- **Multi-Stream WebSockets**: Public market-data WebSocket streaming for real-time tick prices (aggTrade + kline bars) with automatic REST fallback, plus the authenticated Binance WebSocket API v3 for low-latency order routing.
- **SQLite State Machine**: ACID-compliant persistence (`data/trading.db`) with **WAL mode**, a **dedicated read-only connection** for the monitor, and an **asynchronous batched write queue** that eliminates `database is locked` errors.
- **Debian 13 & PEP 668 Native**: Runs inside an isolated Python virtual environment (`python3-venv`), never polluting system packages.
- **PM2 Process Supervision**: `ecosystem.config.cjs` supervises **both** the engine (`main.py`) and the web monitor (`status.py --web 3000`) with auto-restart, a 2 GB memory cap, and rotating log files. (`.cjs` — the repo's root `package.json` sets `"type": "module"`, which would otherwise break `pm2 start` on CommonJS configs.)
- **Unified Terminal & Web Monitor**: `status.py` serves an `htop`-style terminal dashboard **and** an embedded API (`/api/status`, `/api/logs`, `/api/health`, `/api/config`, `/api/control`) used by the interactive React web dashboard — **React frontend + WebSocket API + Python backend**, all from one port: `ws://<host>/ws` streams realtime status snapshots and incremental engine log lines (RFC 6455, stdlib-only server) with automatic HTTP polling fallback for proxies that block WebSocket upgrades.
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
- **Bollinger Overextension Gate** — BUYs are refused when Bollinger %B ≥ `BB_UPPER_PCT_B` (default 0.95 = at/above the upper band). All five confluence factors are momentum signals; this gate blocks the vertical, overextended candles that mean-revert into the ATR stop before TP fires. Disable with `BB_STRETCH_GATE_ENABLED=false`.
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
12. **Win/Loss & Win-Rate Accounting (FIXED)** — the web dashboard previously mapped every recent order (including BUY entry orders with zero PnL, NEW orders and CANCELED attempts) into "closed trades", which diluted the win rate. Closed trades are now derived from **SELL exit orders only** (FILLED, plus CANCELED partial-exit legs that recorded a realized PnL), and the VPS dashboard prefers the engine's full-history aggregates (`win_rate`, `profit_factor`, `avg_win`, `avg_loss`, `breakeven_trades`) — so wins + losses + breakevens always reconcile with the displayed win rate.
13. **Partial-Exit PnL Missing from Stats (FIXED)** — partial-exit legs are persisted as `CANCELED` SELL orders with a realized PnL, but the monitor's stats and the daily Discord report only counted `FILLED` exits. Both now include `status IN ('FILLED','CANCELED') AND profit_loss IS NOT NULL`, matching the engine's own streak/cooldown accounting in `update_trade_result`.
14. **Live-Mode Startup Crash in `ws_api_client.py` (FIXED)** — the WebSocket API client used `os.path.exists(...)` without importing `os`, raising `NameError` at boot whenever a live configuration with an Ed25519 private key was detected.
15. **Web Monitor Static-Serving Hardening (FIXED)** — `status.py --web` now percent-decodes URLs before any filesystem access and rejects every path-traversal form (`..`, `..%2f`, `%2e%2e`) with 403; unknown paths return 404 instead of serving the dashboard HTML, and requests outside `/` are no longer answered when no compiled `dist/` exists.
16. **Simulated Candidates Clobbering Live Screeners (FIXED)** — while synced to a VPS, the React dashboard no longer overwrites the engine-scanned candidate pool with locally-simulated momentum rankings.
17. **VPS `.env` Sync Credential Safety (FIXED)** — the 1-click SSH sync command now backs up the existing `.env` (`.env.bak.<timestamp>`) before overwriting and warns that `BINANCE_API_KEY` / `BINANCE_API_SECRET` must be preserved; the browser `POST /api/config` path remains a whitelist that never touches credentials.
18. **Graceful Shutdown Hang (FIXED)** — SIGINT/SIGTERM previously cancelled `main()` itself mid-`finally` and then stopped the loop, so `ws_stream.disconnect()` hung forever on a torn-down WebSocket (`connection_lost_waiter` never resolved). PM2 `reload`/`restart` would hang and the single-instance lock stayed held, blocking the next start. Signal handlers now only set a shutdown event; `main()` cancels the background loops itself, then tears down connections with **bounded timeouts** (`ws_stream`/`ws_api` close with a 3s cap + transport abort; the REST client's periodic time-sync task is cancelled on close). Verified live under `PAPER_TRADE=true`: clean exit in ~5s, `Shutdown complete.` logged, lock released, no pending-task warnings.
19. **PM2 Config Broken by ESM `package.json` (FIXED)** — the repo root `package.json` declares `"type": "module"`, so Node treated `ecosystem.config.js` (CommonJS) as ESM and `pm2 start ecosystem.config.js` failed with `ReferenceError: module is not defined`. The file is now `ecosystem.config.cjs` (explicit CommonJS), and every command/README/UI reference was updated. The full flow — `pm2 start ecosystem.config.cjs` → `POST /api/config` (whitelist push) → `pm2 reload ultimate-bot` — was verified end-to-end: reload exit code 0, restart count incremented, engine back online and holding the lock with the new config.
20. **Risk-Based Position Sizing Silently Overwritten by Notional Cap (FIXED)** — `calculate_position_size` computed the correct 1%-risk quantity, then immediately overwrote it with the full per-symbol allocation cap (`qty = allocation / price`), so the documented fixed-fractional risk model never actually ran. A wide ATR stop on a 20%-allocation position risked ~2–5% of equity per trade instead of 1%. The risk-based size is now primary and the notional cap only ever *reduces* it; the minNotional one-step bump is also gated by the risk budget, and sub-minimum risk sizes skip the entry instead of up-sizing past the risk cap.
21. **Bollinger Overextension Gate Added** — the 5-factor confluence stack is momentum-only, so the engine now also computes a Bollinger Bands %B position gauge (20-bar, 2σ by default) and refuses BUYs when the live price is statistically stretched (%B ≥ 0.95). This closes the stack's mean-reversion blind spot without changing `SIGNAL_THRESHOLD` semantics; tunable via `BB_PERIOD` / `BB_STD_DEV` / `BB_UPPER_PCT_B` / `BB_STRETCH_GATE_ENABLED`.
22. **UI Presets Contradicted the Engine (FIXED)** — the web dashboard's `PRESET_MAP` shipped ATR multipliers and trailing levels that differed from `config.py`'s `PRESETS` (e.g. UI scalping 0.8/1.2 ATR vs the engine's 1.0/2.0), so tuning from the dashboard pushed a different strategy than the one documented. The UI presets now mirror the engine exactly.
23. **WebSocket Realtime Monitoring (React + WS API + Python)** — the dashboard previously HTTP-polled `/api/status` every 2.5s. `status.py` now embeds a stdlib-only RFC 6455 WebSocket server on the same port (`ws://<host>:3000/ws`): status snapshots push every 1s and engine log lines stream as they are written. The React client (`vpsSocket.ts`) auto-falls-back to HTTP polling when the upgrade is blocked, and the connection bar shows `WS LIVE` vs `HTTP POLL`. Paper- and live-mode monitor behavior verified by dedicated functional suites (29 checks).
24. **Streak Cooldown Became a Permanent Throttle (FIXED)** — `update_trade_result` armed the loss/win-streak cooldown without resetting the streak counter, so after 3 losses **every** subsequent loss re-armed the cooldown and the symbol traded roughly once per cooldown window until a random win. The streak now resets when its breaker trips (documented "N consecutive losses → pause → fresh start" semantics).
25. **One Bad DB Table Zeroed the Dashboard (FIXED)** — `read_database` returned an all-empty payload if any single query failed (e.g. `orders` busy), which also wiped `risk_state` and made live-mode monitors display equity $0.00 while the engine was fine. Each section now reads/degrades independently, with `risk_state` read first.
26. **Scale-Out Could Never Fire (FIXED)** — the +1R scale-out measured R against the *current* stop, but the hardcoded +1% breakeven lock raises that stop to `entry × 1.0025` before +1R in every preset, making `risk_per_unit` negative and permanently disabling scale-out. R is now anchored to the trade's **initial** stop (`initial_stop_price`), keeping both features functional.
27. **Backtest Engine Added (`backtest.py`)** — replays real Binance klines through the live engine's **own** `SignalGenerator.decide()` core (zero strategy drift) with full trade-management parity: R:R gate, MIN_TP floor, gap-aware stops, trailing, breakeven lock, scale-out, 0.1%/leg taker fees, 1% risk sizing with notional caps, and the daily drawdown breaker. Metrics: win rate, profit factor, expectancy, avg R-multiple, max drawdown, fee drag. `--disable-bb` runs an A/B that isolates the Bollinger gate's contribution (measured: it saves ~4.2% equity over 10 days on BTC day preset). **Honest results on recent data:** day preset WR 12.6% / PF 0.09 (−7.4%), swing preset WR 38.5% / PF 0.43 (−3.8%), threshold 5 cuts the bleed to −0.8% — the strategy still has negative expectancy on the tested window and needs positive-expectancy tuning (or a wider sample) before live funds.
28. **Bracket Rebalanced from Backtest Evidence (day preset)** — a 21-point parameter sweep plus targeted A/B runs identified the structural killer: the 0.5% `MIN_TP_PERCENT` floor made TP ~8× wider than the 1.2×-ATR stop, so 87% of trades resolved as −1R stop-outs (measured WR 12.6%, PF 0.09). The day preset now ships the backtest-proven bracket — **3.0× ATR stop, 3.5× ATR TP, 0.15% TP floor** — plus a 3h default `COOLDOWN_LOSS` (measured PF 0.49 → 0.79 with it). Verified on BTC (WR 50%, PF 0.79, −0.09 R) and ETH (WR 60%). UI presets, `.env.example` and the UI `.env` generator mirror the new values.
29. **Exhaustive Edge Hunt: Signal Family Proven Fee-Bound** — every remaining lever was measured on honest long samples (BTC 5m×50d, BTC/ETH/SOL 15m×~156d): LTF ADX regime gate (PF 0.28→0.33, expectancy flat), R-based breakeven/trailing triggers (PF 0.52→**0.24** — early locks get shaken out by 15m noise; rejected), volume-confirmation gate (PF 0.52→0.45 — high-volume signal bars *underperform*; rejected), max-hold & cooldown sweeps (current values already optimal). Diagnosis: on every asset/timeframe the **gross (pre-fee) edge ≈ 0** — fees are the entire loss. Best implementable lever found: **maker-fee TP exits** (`--maker-tp`, models OCO limit TP at 0.02% vs 0.1% taker) — improves every run (swing PF 0.52→0.54, day 0.30→0.33). Also fixed a backtest realism bug: gap-aware stop fills now use the bar's actual **open** price (was close), which alone improved swing results −4.18%→−3.44% by not over-penalizing gap stop-outs.

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

# Bollinger overextension gate (blocks stretched BUY entries)
BB_PERIOD=20                # band lookback in closed candles
BB_STD_DEV=2.0              # band width in standard deviations
BB_UPPER_PCT_B=0.95         # %B above which a BUY is blocked (1.0 = upper band)
BB_STRETCH_GATE_ENABLED=true
```

### Signal confluence engine
```ini
SIGNAL_THRESHOLD=4          # minimum 1–5 aligned bullish factors to BUY
SIGNAL_INTERVAL=10          # seconds between scan passes per symbol
ENTRY_TIMEOUT=15            # seconds to wait for a market order fill
MAX_SLIPPAGE_PERCENT=0.5    # skip entry if price moved more than this
MIN_TP_PERCENT=0.005        # take-profit never closer than this fraction
```

Two professional filters sit on top of the raw confluence score:
- **Regime alignment** — a BUY is blocked outright when the MTF trend is DOWN (and vice versa), so the engine never longs into a downtrend just because 4 micro-factors aligned.
- **R:R gate (`MIN_RISK_REWARD`, default 1.5)** — entries whose TP distance is less than the configured multiple of the SL distance are widened (or skipped) before the order is placed.
- **CVD noise floor** — the volume-delta factor only counts when taker flow shows at least a 55/45 directional skew, so ±2% imbalances no longer score as full confluence.

### Risk model & trade management
```ini
RISK_PER_TRADE=0.01         # 1% of equity risked per trade (entry→stop distance)
MIN_RISK_REWARD=1.5         # TP distance must be >= 1.5x the SL distance
SCALE_OUT_ENABLED=true      # bank partial profit at +1R
SCALE_OUT_R_MULTIPLE=1.0    # trigger the scale-out at 1x the initial stop distance
SCALE_OUT_FRACTION=0.5      # sell 50% of the position at the trigger
```

Position sizing uses **fixed-fractional risk**: `qty = (equity × RISK_PER_TRADE) ÷ (entry − stop)`. A wide 2×ATR swing stop and a tight scalp stop therefore both lose exactly 1% of equity when hit — the notional caps (`BALANCE_USAGE_PERCENT`, `MAX_SYMBOL_ALLOCATION_PERCENT`) remain as secondary ceilings. If the risk-based size falls below the exchange minimum, the trade is skipped rather than up-sized past the risk budget. After a scale-out fires, breakeven (fees covered) locks immediately on the runner.

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
| Stop Loss Multiplier | `1.0× ATR` | `3.0× ATR` | `2.0× ATR` |
| Take Profit Multiplier | `2.0× ATR` | `3.5× ATR` | `4.0× ATR` |
| Min TP Floor (`MIN_TP_PERCENT`) | `0.08%` | `0.15%` | `0.30%` |
| Trailing Stop Activation | `+0.5%` | `+1.5%` | `+3.0%` |
| Trailing Stop Callback | `0.2%` | `0.5%` | `1.2%` |
| Swing Lookback | `3` | `5` | `8` |
| Max Hold Time | `1 hour` | `8 hours` | `24 hours` |

---

## 🏃 Running the Bot (PM2 Supervision)

`ecosystem.config.cjs` launches two supervised processes:

| App name | Purpose |
|---|---|
| `ultimate-bot` | Core 5-factor trading engine (`main.py`) |
| `bot-web-monitor` | Web API + dashboard server (`status.py --web 3000`) |

```bash
cd /path/to/ultimate-bot
pm2 start ecosystem.config.cjs
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

# Option 2 — supervised 24/7 via PM2 (already in ecosystem.config.cjs)
pm2 start ecosystem.config.cjs
```

Then open `http://YOUR_VPS_IP:3000`. When a compiled `./dist` exists next to `status.py`, it serves the React dashboard **with full `npx serve -s dist` parity** — SPA fallback for client-side routes, clean-URL directory redirects (301), ETag/`304` revalidation, immutable caching for content-hashed `/assets/*`, gzip compression, HTTP `Range` support and HTTP/1.1 keep-alive on a multi-threaded `ThreadingHTTPServer` (several viewers can poll simultaneously without blocking each other). No Node.js, `npx serve` or reverse proxy is required on the VPS.

**Realtime transport (React + WebSocket + Python):** the dashboard first opens a WebSocket to `ws(s)://<host>:3000/ws` and receives pushed status snapshots every second plus engine log lines as they are written — no polling round-trips. If the upgrade is unavailable (restrictive proxy, old backend), it falls back to HTTP polling of `/api/status` every 2.5s automatically; the connection badge shows `WS LIVE` vs `HTTP POLL`. The standalone fallback dashboard uses the same WS-first strategy. Control commands (`/api/control`, `/api/config`) remain HTTP POSTs by design — they are idempotent and safe to retry.

If no compiled `dist/` is found, `status.py --web` falls back to a built-in standalone dark-mode dashboard that includes a **Performance & Risk section** (win rate with W/L/B breakdown, profit factor, total realized PnL, average win/loss and the win/loss streak monitor) alongside the balance cards, market scanner, active positions and recent orders.

> **Win-rate consistency**: wins, losses and breakevens are counted from **SELL exit orders that recorded a realized PnL** — never from BUY entries or un-filled orders — and the `win_rate` shown is `wins ÷ closed`. Partial-exit legs (recorded on `CANCELED` SELL orders) are included, so the numbers always reconcile with the engine's own streak and cooldown state.

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
14. **Fixed-Fractional Risk Sizing** — every entry is sized from the entry-to-stop distance (`RISK_PER_TRADE`, default 1% of equity), so stop width can never silently inflate per-trade risk; notional caps act only as secondary ceilings.
15. **Regime Alignment & R:R Gate** — BUYs are blocked when the MTF trend is DOWN (no knife-catching), and entries below `MIN_RISK_REWARD` reward-to-risk are widened or skipped.
16. **Scale-Out Discipline** — 50% of the position is banked at +1R (`SCALE_OUT_*`), breakeven locks immediately on the runner, and the remainder rides to the full take-profit — converting marginal win rates into positive expectancy.

---

## 🧪 Smoke Test

`smoke_test.py` boots the real engine end-to-end against an **isolated temporary database** (your `data/trading.db`, `.env` and logs are never touched) and verifies:

1. The engine boots and initializes the SQLite schema + `paper_balance` risk state.
2. The single-instance lock is acquired.
3. A second engine instance is rejected (`Another instance is already running`).
4. The web monitor serves `/api/status` with **consistent** win/loss stats (`closed = W + L + B`), reports `RUNNING`, and provably reads the isolated temp DB (API numbers match a direct SQL query).
5. SIGTERM shuts the engine down **cleanly** — exit code 0, `Shutdown complete.` in the log, no `Task was destroyed` warnings, lock released.

```bash
cd /path/to/ultimate-bot
./venv/bin/python3 smoke_test.py    # exit 0 = all checks passed
```

It can also be run from the repo root via `npm run smoke`. Requires network access to Binance (the engine fetches `exchangeInfo` at boot) and a free `/tmp/ultimate_bot.lock` (stop any running engine first).

---

## 🔬 Backtesting (Prove It Before You Trade It)

`backtest.py` replays **real** historical Binance klines through the live engine's **own** `SignalGenerator.decide()` — the exact code that trades real money, so there is zero drift between what is tested and what trades. Trade management is identical to the engine: R:R gate, `MIN_TP_PERCENT` floor, gap-aware stops, trailing stop, fee-aware breakeven lock, +1R scale-out, 0.1%/leg taker fees on both legs, 1% risk sizing with notional caps and the daily drawdown breaker.

```bash
cd ultimate-bot
./venv/bin/python3 backtest.py --symbol BTCUSDT --preset day --pages 4          # ~20 days of 5m data
./venv/bin/python3 backtest.py --symbol BTCUSDT --preset day --pages 4 --disable-bb  # A/B the Bollinger gate
./venv/bin/python3 backtest.py --symbol ETHUSDT --preset swing --pages 4 --threshold 5
```

| Flag | Purpose |
|---|---|
| `--symbol` / `--preset` | Market + preset (default `BTCUSDT` / `day`) |
| `--pages N` | Days of history (1 page ≈ 5 days on 5m) |
| `--threshold` / `--sl` / `--tp` / `--min-tp` / `--cooldown-bars` / `--bb-pctb` / `--scale-frac` | Override any strategy parameter |
| `--disable-bb` | Turn the Bollinger stretch gate off for A/B comparison |
| `--adx-min X` | Research gate: skip entries when LTF ADX(14) < X (chop filter) |
| `--vol-mult X` | Research gate: require signal-bar volume ≥ X × its 20-bar average |
| `--bb-lower X` | Research gate: skip entries with Bollinger %B ≤ X (falling-knife filter) |
| `--be-r X` / `--trail-r X` | Research: trigger breakeven/trailing at R-multiples instead of fixed % |
| `--max-hold S` | Research: override `MAX_HOLD_TIME` (seconds) |
| `--maker-tp` | Research: TP exits pay maker fee (0.02%, OCO limit leg) instead of taker 0.1% |
| `--quiet` | One-line summary instead of full JSON (for sweeps) |

**Measured results (BTCUSDT 5m, 20 days, net of 0.2% round-trip fees):**

| Config | Trades | Win rate | Profit factor | Expectancy |
|---|---|---|---|---|
| Old defaults (1.2×/2.4× ATR, 0.5% TP floor) | 151 | 12.6% | 0.09 | −0.98 R |
| **New defaults (3.0×/3.5× ATR, 0.15% floor) + 36-bar cooldown** | 22 | **50.0%** | **0.79** | **−0.09 R** |
| New defaults, no cooldown | 35 | 45.7% | 0.49 | −0.27 R |
| Old defaults, Bollinger gate disabled | 257 | 10.5% | 0.10 | — |

**What the backtest proved (and what changed as a result):**

1. **The old day preset's 0.5% `MIN_TP_PERCENT` floor made the TP ~8× wider than the ATR stop.** A nominal 1:2 bracket actually realized as ~1:8, so 87% of trades died at −1R. Lowering the floor to 0.15% and widening the stop to 3× ATR balanced the bracket: win rate 12.6% → 50%, PF 0.09 → 0.79. These are now the shipped defaults.
2. **The 36-bar (3h on 5m) post-exit cooldown nearly doubled profit factor** vs no cooldown (0.79 vs 0.49) by skipping revenge-trade churn. `COOLDOWN_LOSS` now defaults to 3h.
3. **The Bollinger stretch gate saves ~4.2% equity over 10 days** — it stays on by default.
4. Threshold 5 (all five factors) trades too rarely on 5m to matter; **threshold 4 remains optimal**.
5. **Expectancy is still slightly negative (−0.09 R)** on this window: the risk framework is sound and the bracket is balanced, but this is **not** a proven positive-edge strategy yet. Keep paper trading and re-run the backtest on fresh data monthly.

**Long-sample edge hunt (the follow-up campaign, ~50–156 day windows):**

On honest long samples the 20-day PF 0.79 does **not** hold (BTC 5m×50d: PF 0.28–0.33; BTC 15m×156d: PF 0.52; ETH 0.37; SOL 0.59). The measured decomposition is decisive: on every asset and timeframe **net loss ≈ total fees, i.e. the gross (pre-fee) edge is ≈ 0** — the signal predicts direction no better than chance, and the cost of trading it is the whole loss. Every signal-side lever was tested and measured:

| Hypothesis | Result | Verdict |
|---|---|---|
| LTF ADX(14) regime gate (18/22/25) | PF 0.28→0.33, expectancy flat | Marginal — not the edge |
| R-based breakeven/trailing triggers | PF 0.52→**0.24** | **Rejected** — early locks get shaken out by noise |
| Volume-confirmation gate (1.5×–3× avg) | PF 0.52→0.45, fewer trades | **Rejected** — loud signal bars *underperform* |
| Max-hold 6h→12/24/48h | PF ≤ 0.53 | Current 24h already optimal |
| Cooldown 0/24/96 bars | PF ≤ 0.53 | Current 36 bars already optimal |
| **Maker-fee TP exits (OCO limit)** | **PF 0.52→0.54, every run improves** | **Adopt** — only lever that helped everywhere |

The structural conclusion: a 5-factor momentum-confluence signal with ~zero gross edge cannot be tuned profitable — the fix is a **different or additional signal** (e.g. higher-timeframe momentum alignment, funding-rate/microstructure filters), not more exit engineering. Meanwhile the fee lever is real money: place TP as an OCO **limit** (maker 0.02%) rather than market (taker 0.1%) — a 40% round-trip fee cut that helps every configuration. Re-run the backtest after **any** parameter change — if a config cannot show PF > 1 over 100+ trades, it does not go live.

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

