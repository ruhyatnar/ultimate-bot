# 🚀 Ultimate Binance Market-Only Trading Bot

A production-grade, algorithmic trading bot designed specifically for **Binance Spot Trading** with **Market-Only Execution**, **5-Factor Smart Money Confluence Strategy**, **Strict Risk & Drawdown Management**, and **Ed25519 Asymmetric Cryptography**.

Engineered for **Debian 13 (Trixie) CLI-only VPS** environments with zero GUI overhead, complete PEP 668 compliance, process supervision via PM2, and a terminal live dashboard (`status.py`).

---

## 📑 Table of Contents
1. [Core Features & Architecture](#-core-features--architecture)
2. [5-Factor Confluence Strategy](#-5-factor-confluence-strategy)
3. [Professional Trader Audit: Paper vs. Live Trading](#-professional-trader-audit-paper-vs-live-trading)
4. [Live Readiness Checklist & Safety Protocols](#-live-readiness-checklist--safety-protocols)
5. [Connecting Real Bot Data to Web Monitor (`status.py` & `npx serve`)](#-connecting-real-bot-data-to-web-monitor)
6. [VPS Prerequisites (Debian 13 CLI & Ubuntu)](#-vps-prerequisites-debian-13-cli--ubuntu)
7. [Installation & Setup](#-installation--setup)
8. [Ed25519 Asymmetric API Key Setup](#-ed25519-asymmetric-api-key-setup)
9. [Configuration Reference (`.env`)](#-configuration-reference-env)
10. [Strategy Presets (Scalping, Day, Swing)](#-strategy-presets)
11. [Running the Bot (PM2 Supervision)](#-running-the-bot-pm2-supervision)
12. [Real-Time Monitoring (CLI, PM2, & Web Server)](#-real-time-monitoring)
13. [Interactive Web Operations Center & Tunability](#-interactive-web-operations-center--tunability)
14. [Troubleshooting & Emergency Procedures](#-troubleshooting--emergency-procedures)

---

## ⚡ Core Features & Architecture

- **100% Market Orders Only**: Zero maker orders, zero orphaned limit orders. Positions enter and exit immediately with slippage guards.
- **Ed25519 Signing**: Employs asymmetric cryptography (`ed25519`) rather than HMAC-SHA256, eliminating shared secret risk and matching Binance's modern institutional security standard.
- **Multi-Stream WebSockets**: Public WebSocket streaming for real-time tick prices with zero REST weight consumption, supplemented by Binance WebSocket API v3 for live trade routing.
- **SQLite State Machine**: ACID-compliant transactional persistence (`data/trading.db`) tracking orders, trades, realized PnL, drawdowns, and loss streaks with WAL mode.
- **Debian 13 & PEP 668 Native**: Runs cleanly inside an isolated Python virtual environment (`python3-venv`) without polluting system packages.
- **PM2 Process Supervision**: Auto-restart on crash, memory threshold capping (2 GB), rotating log files, and zero downtime.
- **Unified Terminal & Web Monitor**: Built-in `status.py` serves both an `htop`-style live terminal dashboard and an embedded HTTP REST API (`/api/status`) for the interactive web dashboard.

---

## 🎯 5-Factor Confluence Strategy

The bot executes a `BUY` order only when multiple independent technical factors align simultaneously (configured by `SIGNAL_THRESHOLD`, default: **4 of 5**):

1. **Multi-Timeframe Trend Alignment (HTF)**:
   - Current timeframe (e.g. 5m) confirmed against Higher Timeframe (e.g. 1h).
   - Fast EMA (9) must be above Slow EMA (21), and price above 200 EMA.
2. **Break of Structure (BOS)**:
   - Price must break above recent swing high with volume expansion, confirming buyer dominance.
3. **Fair Value Gap (FVG)**:
   - Detects 3-candle price imbalances where buyers aggressively displaced price without opposing liquidity.
4. **Order Flow CVD (Cumulative Volume Delta)**:
   - Aggressor market buy volume must exceed sell volume over the lookback window.
5. **Volume Point of Control (POC)**:
   - Current price must trade above the highest volume node of the session, treating it as support.

---

## 📊 Professional Trader Audit: Paper vs. Live Trading

As an algorithmic cryptocurrency trading engine, understanding the fundamental differences between **Paper Trading** and **Live Spot Trading** is critical:

| Dimension | Paper Trading (`PAPER_TRADE=true`) | Live Spot Trading (`PAPER_TRADE=false`) |
|---|---|---|
| **Capital Risk** | $0 (Simulated virtual USDT balance) | Real assets on Binance Spot account |
| **Order Execution** | Synthetic fills at current market bid/ask | Sent via WebSocket API / REST to Binance matching engine |
| **Taker Fees** | Simulated (now incorporates 0.10% taker fee per leg) | Deducted in BNB or asset by Binance (0.075% - 0.10%) |
| **Slippage & Depth** | Assumes instantaneous full fill at ticker price | Depends on order book liquidity depth & spread |
| **Exchange Constraints** | Ignored | Strictly enforced: `LOT_SIZE`, `PRICE_FILTER`, `MIN_NOTIONAL` ($10 USDT) |
| **Account Permissions** | Requires no API keys or can run offline | Requires Ed25519 API key with Spot Trading enabled |

### Potential Issues Identified & Fixed:

1. **Fee Drag & Net PnL Miscalculation (FIXED)**:
   - *Previous Issue*: Standard paper trading often calculates gross PnL $(Exit - Entry) \times Qty$, making a strategy appear profitable when exchange fees actually make it negative.
   - *Fix Implemented*: `trade_logic.py` now calculates **Net Realized PnL** after deducting **0.1% taker fees on both entry and exit legs** ($0.2\%$ round-trip), ensuring live and paper metrics are realistic.

2. **Orphan Orders on Symbol Exit (FIXED)**:
   - *Previous Issue*: In live spot trading, if a stop-loss or take-profit trigger fires while another order for the symbol remains open on Binance, an unexpected fill could occur later.
   - *Fix Implemented*: `trade_logic.py:close_trade` now triggers an orphan cleanup request (`DELETE /api/v3/openOrders`) for the symbol whenever a position is closed.

3. **Database Concurrency & Locking Conflicts (FIXED)**:
   - *Previous Issue*: If the main trading bot (`main.py`) writes to `data/trading.db` while `status.py` or the web monitor queries it, SQLite could throw `database is locked`.
   - *Fix Implemented*: `status.py` connects with URI read-only mode (`mode:ro`), WAL mode, and a 10-second busy timeout.

4. **Minimum Notional Value ($10 USDT rule)**:
   - *Safety Rule*: Binance requires spot orders to have a total value of at least **$10 USDT** (`MIN_NOTIONAL`). If your allocated balance per trade is under $10, Binance will reject the order.
   - *Recommendation*: Maintain an account balance of at least **$50 - $100 USDT** so that each position (e.g. 20% allocation = $20) cleanly exceeds $10.

---

## 🛡️ Live Readiness Checklist & Safety Protocols

Before switching `PAPER_TRADE=false` in `.env`, run through this mandatory checklist:

- [ ] **1. API Key Permissions**:
  - Go to Binance **API Management**.
  - Ensure **"Enable Reading"** and **"Enable Spot & Margin Trading"** are checked.
  - **CRITICAL**: Ensure **"Enable Withdrawals" is UNCHECKED (DISABLED)**. The bot never needs withdrawal permissions.
- [ ] **2. IP Access Restriction**:
  - In Binance API Management, select **"Restrict access to trusted IPs only"**.
  - Enter your Tencent Cloud VPS public IP address.
- [ ] **3. Ed25519 Private Key**:
  - Verify `keys/private_key.pem` exists on your VPS with permissions `chmod 600 keys/private_key.pem`.
  - The matching public key must be registered on Binance API Management.
- [ ] **4. BNB Fee Deduction (Recommended)**:
  - Keep 0.05 BNB in your spot wallet and enable "Use BNB for fees" on Binance for a 25% trading fee discount.
- [ ] **5. Run Paper Trading for 24-48 Hours First**:
  - Keep `PAPER_TRADE=true` running for at least 1-2 days to observe confluence signals, ATR trailing stops, and daily drawdown resets in real market conditions.
- [ ] **6. Set Conservative Initial Risk**:
  - Recommended for first live week:
    - `MAX_SYMBOLS=2`
    - `BALANCE_USAGE_PERCENT=0.30` (use 30% of portfolio)
    - `MAX_SYMBOL_ALLOCATION_PERCENT=0.15` (15% per symbol)
    - `MAX_DAILY_DRAWDOWN=0.03` (halt trading if daily loss reaches 3%)

---

## 🌐 Connecting Real Bot Data to Web Monitor

### Why `status.py --watch` and `npx serve` showed different data previously:
1. `status.py --watch` queries the **actual SQLite database (`data/trading.db`)** written by your Python bot process.
2. `npx serve` runs the React single-page frontend. When launched without a backend connection, the frontend previously ran a client-side **simulation sandbox** with mock simulated trades.

### The Solution: 100% Real-Time VPS Synchronization
We updated `status.py` to serve both the terminal dashboard AND an embedded REST API (`/api/status`) on port 3000, and integrated the **Live VPS Connection Bar** directly into the web dashboard!

### How to Launch the Web Monitor on Your VPS:

#### Option 1: Native Python Web Server (Recommended - Zero Node/npm Build Needed)
Run `status.py` with the `--web` flag:
```bash
cd ~/ultimate-bot
./venv/bin/python3 status.py --web 3000
```
*Note: If your VPS previously gave `unrecognized arguments: --web 3000`, it means your VPS was running an older `status.py`. Update `status.py` using git pull or copy the updated file, and it will run smoothly.*

#### Option 2: 24/7 PM2 Supervision (Recommended for Production)
The updated `ecosystem.config.js` runs both the trading bot and the web monitor under PM2 supervision:
```bash
cd ~/ultimate-bot
pm2 start ecosystem.config.js
pm2 save
```
This launches:
- `ultimate-bot`: The core 5-factor trading engine (`main.py`)
- `bot-web-monitor`: The web API and dashboard server (`status.py --web 3000`)

#### Option 3: Static React Production Server (`npx serve`)
```bash
cd ~/ultimate-bot
npx serve -s dist -l 3000
```
When running via `npx serve`, the frontend automatically polls `http://localhost:3000/api/status` or allows you to enter your remote VPS IP in the **VPS Connection Bar**!

### Interactive Control API (Tune & Operate from the Web)

`status.py --web` is not read-only — the web dashboard can operate the live engine:

| Endpoint | Method | Purpose |
|---|---|---|
| `/api/status` | GET | Full snapshot: process state, SQLite trades/orders/risk, tunable config, engine pause state |
| `/api/logs?lines=120` | GET | Tail the real `logs/trading.log` so the web Debug Console mirrors the engine |
| `/api/control` | POST | `{"action": "pause" \| "resume" \| "close_all" \| "close_symbol", "symbol": "..."}` |
| `/api/config` | POST | `{"env_file": "<generated .env content>"}` — merges whitelisted tunable keys into `.env` and reloads via `pm2 reload ultimate-bot` |

How it works:
- The engine watches `data/engine_control.json` (configurable via `CONTROL_FILE`). `pause` blocks **new entries** while open positions keep being managed (stops/TP/trailing stay armed); `close_all` / `close_symbol` execute once via a deduplicated `command_id`.
- `/api/config` only accepts a **whitelist** of tuning keys — credentials (`BINANCE_API_KEY`, private key path, `DISCORD_WEBHOOK_URL`) are never writable from the browser, and the merge preserves all other lines.
- The dashboard exposes these as **Pause Engine / Resume**, **Close All**, **Push to VPS**, and the live log stream — no SSH needed for routine tuning.

### Remote Browser Access:
1. Open port 3000 in your **Tencent Cloud VPS Security Group** (Inbound rule: Protocol TCP, Port 3000, Source 0.0.0.0/0).
2. Visit `http://YOUR_VPS_IP:3000` in your web browser.
3. The top banner will indicate: **● Live VPS Synced** with real-time latency, active positions from `trading.db`, live PnL, and win streaks!
4. You can toggle between **"Live VPS Bot"** (real data) and **"Strategy Simulator"** (local testing sandbox) at any time.

| # | Factor | Indicator / Model | Signal Condition |
|---|---|---|---|
| **1** | **Multi-Timeframe Trend** | Dual EMA (20 & 50) on Higher TF + Execution TF | Price > EMA20 > EMA50 on both timeframes |
| **2** | **Market Structure BOS** | Swing High/Low Fractal Extrema | Break of Structure (higher swing highs + higher swing lows) |
| **3** | **Fair Value Gap (FVG)** | 3-Candle Smart Money Imbalance | Bullish price gap: Candle 3 Low > Candle 1 High |
| **4** | **Order Flow CVD** | Cumulative Volume Delta (20 bars) | Positive taker buy volume dominance (`CVD > 0`) |
| **5** | **Volume Profile POC** | Point of Control (Volume Bins) | Price trades above maximum volume cluster (support) |

Exits are managed dynamically via:
- **ATR-Based Stop Loss**: Dynamic volatility cushion (`ATR_MULTIPLIER_SL`).
- **Take Profit (1:1.67+ Risk/Reward)**: Scaled volatility target (`ATR_MULTIPLIER_TP`).
- **Dynamic Trailing Stop**: Activated once trade enters profit, locks in gains as price rises.
- **Breakeven Shift**: Moves stop loss to entry price + fees once initial threshold is reached.
- **Max Hold Time Timeout**: Prevents stagnant capital tie-up.

---

## 🧪 Paper Trading vs. Live Trading

| Feature | Paper Trading (`PAPER_TRADE=true`) | Live Trading (`PAPER_TRADE=false`) |
|---|---|---|
| **Real Funds at Risk** | ❌ None ($0 risk, simulated $1,000 equity) | ⚠️ Real Binance Spot balance |
| **Market Data** | ✅ Real-time public Binance WebSocket | ✅ Real-time public Binance WebSocket |
| **Order Placement** | Simulated instantly with actual market price | Real execution via Binance WebSocket API / REST |
| **Exchange Filters** | Sanitized against `LOT_SIZE` & `MIN_NOTIONAL` | Sanitized against `LOT_SIZE` & `MIN_NOTIONAL` |
| **API Keys Required** | ❌ No API key or Ed25519 key needed | ✅ API Key + Ed25519 Private Key required |
| **Database & Dashboard** | ✅ Logged to `trading.db` and `status.py` | ✅ Logged to `trading.db` and `status.py` |

> 💡 **Recommendation**: Run the bot in **Paper Trading mode for at least 24–48 hours** to verify market dynamics and signal triggers on your VPS before switching to live funds.

---

## 🚦 Live Trading Readiness Checklist

Before flipping `PAPER_TRADE=false`, ensure every item on this institutional pre-flight checklist is verified:

- [ ] **1. Binance API Key Permissions**:
  - `Enable Reading`: **Checked**
  - `Enable Spot & Margin Trading`: **Checked**
  - `Enable Withdrawals`: **UNCHECKED (CRITICAL: NEVER enable withdrawals for a trading bot)**
  - `IP Access Restriction`: **Restrict access to trusted IPs only** (Enter your Debian VPS static IP)
- [ ] **2. Ed25519 Key Registration**:
  - Asymmetric Ed25519 public key copied to Binance API Management (`cat keys/public_key.pem`).
  - Private key stored locally on VPS with strict permissions (`chmod 600 keys/private_key.pem`).
- [ ] **3. Account Balance & Fee Deduction**:
  - Maintain a small balance of **BNB** (~$10–$20) with "Using BNB for fees" turned ON in Binance account settings to receive the 25% fee discount.
  - *Fallback Safety*: If BNB is not held, the bot's auto-clamping logic automatically adjusts SELL quantities so fee deductions in base assets never trigger `-2010 Insufficient Balance`.
- [ ] **4. Sufficient Quote Capital**:
  - Minimum USDT balance: at least $25–$50 (to clear Binance `MIN_NOTIONAL` of $5–$10 across multiple open positions). Recommended minimum: $100+ USDT.
- [ ] **5. System Clock Synchronization**:
  - Run `timedatectl status` on your Debian VPS to ensure NTP synchronization is active.
- [ ] **6. Initial Live Test with Scaled Down Allocation**:
  - For your first live run, set `BALANCE_USAGE_PERCENT=0.10` (10% equity) and `MAX_SYMBOL_ALLOCATION_PERCENT=0.05` (5% per trade) to observe live order routing before scaling up.

---

## 🔧 Hardened Safeguards & Architecture Highlights

The codebase has undergone a quantitative trading audit with several critical protections:

1. **Universal WebSocket Compatibility (`ClientConnection.state`)**:
   - Modern `websockets` (v12.0+ on Debian 13) replaced `.closed` with the `.state` enum (`State.OPEN`). The bot's connection health check handles both modern and legacy protocols with zero exceptions.
2. **Fee-Aware Breakeven Stop**:
   - Standard breakeven stops (`entry_price`) lose money due to taker fees (0.1% entry + 0.1% exit = 0.20%). The bot moves the stop to `entry_price * 1.0025` (+0.25%), ensuring fee coverage and a true net breakeven.
3. **Base-Asset Fee Auto-Clamping on Exits**:
   - When exiting spot positions without BNB fee discounts, Binance deducts the 0.1% fee from the acquired base asset. The exit order manager automatically checks available free base asset balance before issuing market SELL orders, eliminating `-2010 (Insufficient Balance)` rejections.
4. **Free Quote Balance Safeguard**:
   - Position sizing caps allocations against real-time free USDT balance (`free_quote * 0.99`), providing a 1% safety buffer for taker fees and intra-second price slippage.
5. **Statistical Candle Lookback**:
   - Expanded historical candle fetch to 100+ bars so Dual EMA (20 & 50) and ADX (14) calculations have sufficient lookback history to compute real-time trend direction accurately.
6. **Zero Dead Code**:
   - Verified with AST static analysis: zero unused imports, zero orphaned routines, and full type safety across all strategy, risk, exchange, and database modules.

1. **Debian 13 (Trixie)** minimal server installation.
2. Root or `sudo` shell access.
3. Stable outbound internet access to Binance endpoints.
4. Static Public IP (recommended for whitelisting on Binance).

---

## 📦 Installation & Setup

### Step 1: System Packages & Dependencies
```bash
sudo apt-get update && sudo apt-get upgrade -y
sudo apt-get install -y python3 python3-venv python3-pip git curl openssl
```

### Step 2: Install Node.js & PM2 (Process Supervisor)
```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs
sudo npm install -g pm2
```

### Step 3: Set Up Project & Python Virtual Environment (PEP 668 Compliant)
Debian 13 prohibits installing pip packages globally. Create a dedicated virtual environment:

```bash
# Navigate to project directory
cd /path/to/ultimate-bot

# Create isolated Python virtual environment
python3 -m venv venv

# Activate venv and install dependencies
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
deactivate
```

---

## 🔑 Ed25519 Asymmetric API Key Setup

Binance supports Ed25519 asymmetric keys for high-speed, cryptographically secure trade authorization.

### 1. Generate Ed25519 Key Pair on your VPS:
```bash
cd /path/to/ultimate-bot
mkdir -p keys
chmod 700 keys

# Generate Ed25519 private key
openssl genpkey -algorithm Ed25519 -out keys/private_key.pem
chmod 600 keys/private_key.pem

# Extract corresponding public key
openssl pkey -in keys/private_key.pem -pubout -out keys/public_key.pem
```

### 2. View and Copy Your Public Key:
```bash
cat keys/public_key.pem
```
It looks like this:
```
-----BEGIN PUBLIC KEY-----
MCowBQYDK2VwAyEA...
-----END PUBLIC KEY-----
```

### 3. Register on Binance:
1. Log in to [Binance.com](https://www.binance.com) and go to **API Management**.
2. Click **Create API** ➔ Select **Self-Generated (Ed25519)**.
3. Paste the contents of `keys/public_key.pem`.
4. Copy the generated **API Key**.
5. Enable **Enable Spot & Margin Trading** (Keep "Permit Withdrawals" **DISABLED**).
6. Under **IP Access Restriction**, select **Restrict access to trusted IPs only** and enter your VPS static IP.

---

## ⚙️ Configuration Reference (`.env`)

Copy the example configuration:
```bash
cp .env.example .env
nano .env
```

### Essential Settings:
```ini
# Trading Mode
PAPER_TRADE=true           # Set 'false' for live trading
USE_TESTNET=false

# Binance Credentials (Required if PAPER_TRADE=false)
BINANCE_API_KEY=your_actual_binance_api_key
BINANCE_PRIVATE_KEY_PATH=./keys/private_key.pem

# Preset Strategy Mode
PRESET=day                 # Options: scalping, day, swing

# Monitored Pairs
STATIC_SYMBOLS=BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT
DYNAMIC_SYMBOLS=false      # Set true to dynamically screen top momentum pairs
QUOTE_ASSET=USDT

# Confluence & Execution
SIGNAL_THRESHOLD=4         # 4 of 5 indicators must confirm BUY (range: 1-5)
SIGNAL_INTERVAL=10         # Analyze symbols every 10 seconds

# Risk & Capital Protection
BALANCE_USAGE_PERCENT=0.5          # Max 50% total balance active
MAX_SYMBOL_ALLOCATION_PERCENT=0.2  # Max 20% balance per individual trade
MAX_DAILY_DRAWDOWN=0.05            # Emergency stop at 5% daily loss
MAX_LOSS_STREAK=3                  # Cooldown after 3 consecutive losses
COOLDOWN_LOSS=3600                 # 1-hour cooldown after loss streak

# Optional Discord Alerts
DISCORD_WEBHOOK_URL=https://discord.com/api/webhooks/...
```

---

## 📊 Strategy Presets

The bot includes three calibrated presets:

| Setting | Scalping (`scalping`) | Day Trading (`day`) | Swing Trading (`swing`) |
|---|---|---|---|
| **Execution Timeframe** | `1m` | `5m` | `15m` |
| **Higher Timeframe (HTF)** | `15m` | `1h` | `4h` |
| **ATR Period** | `10` | `14` | `20` |
| **Stop Loss Multiplier** | `0.8x ATR` | `1.5x ATR` | `2.0x ATR` |
| **Take Profit Multiplier** | `1.2x ATR` | `2.5x ATR` | `4.0x ATR` |
| **Trailing Stop Activation**| `+0.5%` | `+1.5%` | `+2.5%` |
| **Trailing Stop Callback** | `0.2%` | `0.5%` | `1.0%` |
| **Max Hold Time** | 1 Hour | 8 Hours | 24 Hours |

To switch presets, change `PRESET=day` in `.env` and restart the bot.

---

## 🏃 Running the Bot (PM2 Supervision)

The project includes a production `ecosystem.config.js` configured for your virtual environment:

### Start the Bot:
```bash
pm2 start ecosystem.config.js
```

### Save PM2 Process List on System Reboot:
```bash
pm2 save
pm2 startup
```

### Useful PM2 Management Commands:
```bash
pm2 status                  # Check process status and uptime
pm2 logs ultimate-bot       # Stream live log output
pm2 restart ultimate-bot    # Gracefully restart the bot
pm2 stop ultimate-bot       # Stop trading engine
pm2 reload ultimate-bot     # Zero-downtime reload
```

---

## 🖥️ Real-Time Monitoring (`status.py`)

Run the terminal-based live dashboard anytime on your Debian VPS:

```bash
# Single snapshot
./venv/bin/python3 status.py

# Continuous live-refreshing terminal dashboard (refreshes every 2 seconds)
./venv/bin/python3 status.py --watch
```

### Dashboard View:
```
========================================================================
 BINANCE ULTIMATE BOT — LIVE CLI TERMINAL DASHBOARD 
========================================================================
  Engine Status : ● RUNNING (Lock active)    Preset : DAY    Mode : LIVE PRODUCTION
  System Time   : 2026-09-06 06:45:00 UTC    Monitored Symbols : BTCUSDT,ETHUSDT
------------------------------------------------------------------------
 ACCOUNT & RISK OVERVIEW
  Daily PnL        : +$14.25 USDT

 ACTIVE POSITIONS (1)
  SYMBOL     SIDE   ENTRY        QTY        STOP         TP           BE   
  ----------------------------------------------------------------------
  BTCUSDT    BUY    64250.0000   0.0150     63850.0000   65200.0000   NO   

 RECENT ORDERS & FILLS (LAST 5)
  TIME                SYMBOL     SIDE   PRICE      QTY        STATUS    
  ----------------------------------------------------------------------
  2026-09-06 06:42:15 BTCUSDT    BUY    64250.00   0.0150     FILLED    
  2026-09-06 05:10:02 ETHUSDT    SELL   3450.20    0.2800     FILLED    
------------------------------------------------------------------------
  Press Ctrl+C to exit monitor. Run 'pm2 logs ultimate-bot' for debug streams.
========================================================================
```

---

## 💻 Interactive Web Monitoring & Parameter Tuning

The bot includes a web-based operations center that bridges live data visualization with real-time parameter tuning and direct VPS synchronization.

### 🌟 Key Web Capabilities

1. **Interactive Strategy Tuning Bar**:
   - **Hot-Swap Presets**: Switch instantly between `Scalping` (1m/15m), `Day` (5m/1h), and `Swing` (15m/4h) with 1 click.
   - **Confluence Threshold Slider**: Adjust the required confluence score (1/5 to 5/5). 
     - `4/5` is the optimal recommended standard.
     - `5/5` enforces ultra-conservative entries (all 5 smart money factors must confirm).
     - `2-3/5` enables higher frequency trading during high-momentum markets.
   - **Capital & Position Sizing Tuners**: Adjust total portfolio balance utilization (10% to 100%) and maximum single-symbol allocation (5% to 50%) via live interactive sliders.
   - **Scan Interval & Max Positions**: Control how often candidate symbols are evaluated (2s to 30s) and the maximum concurrent positions permitted (1 to 6).

2. **Dynamic Momentum Screener (`DYNAMIC_SYMBOLS=true`)**:
   - Automatically tracks and evaluates candidates (e.g. BTC, ETH, SOL, BNB, NEAR, AVAX, SUI, DOGE, LINK, OP).
   - Computes multi-factor composite Z-Scores:
     $$\text{Z-Score} = 0.20 \times Z(\text{Volume}) + 0.20 \times Z(\text{24h Change}) + 0.20 \times Z(\text{Volatility}) + 0.40 \times Z(\text{ADX})$$
   - Displays real-time ranking, 24h volume, volatility, and ADX trend strength.
   - Allows pinning or curating the active trading basket directly from the web interface.

3. **Symbol Deep-Dive & Order Calculator Modal**:
   - Click **Inspect** on any symbol to view a detailed breakdown of all 5 confluence factors:
     - Multi-Timeframe Trend (Dual EMA)
     - Market Structure (BOS Higher Highs/Lows)
     - Fair Value Gap (FVG Imbalance)
     - Order Flow CVD (Cumulative Volume Delta)
     - Volume Point of Control (POC Support)
   - Calculated SL, TP, Trailing Stop triggers, and a real-time order sizing calculator with `MIN_NOTIONAL` validation.
   - **Instant Market Buy**: Manually execute a simulated buy order on any coin.

4. **Testing & Inflow Simulator**:
   - Use the **Simulate Inflow Event** button to test the confluence engine by injecting a synthetic institutional buyer volume spike (+1.5% candle jump, 6x volume, positive CVD) into any symbol to observe signal evaluation and trade execution in real time.

5. **Emergency Liquidation**:
   - In volatile conditions, click the **Emergency Close All** button to immediately market-close all open positions.

6. **1-Click VPS Sync (`Sync to VPS .env`)**:
   - Click the **Sync to VPS .env** button in the web header to generate an optimized `.env` file reflecting your tuned settings.
   - Copy the 1-click command and paste it directly into your VPS SSH terminal:
     ```bash
     cat << 'EOF' > .env
     # (Tuned configuration auto-pasted here)
     EOF
     pm2 reload ultimate-bot
     ./venv/bin/python3 status.py
     ```
   - **Zero Downtime**: PM2 reloads the configuration in memory while preserving existing active positions and database records.

---

## 🛡️ Risk Management & Safety Mechanisms

1. **Single Instance Lock**: File lock (`/tmp/ultimate_bot.lock`) prevents multiple accidental instances from executing conflicting orders.
2. **Daily Drawdown Circuit Breaker**: If daily losses reach `MAX_DAILY_DRAWDOWN` (e.g. 5%), new trades are halted until the UTC midnight reset.
3. **Consecutive Loss Streak Protection**: After 3 consecutive losses on a symbol, that pair enters a 60-minute cooling period to prevent revenge-trading during bad market regimes.
4. **Exchange Position Reconciliation**: On startup and periodically, positions are reconciled with Binance spot account balances to ensure consistency.
5. **Rate Limiting Protection**: REST requests are automatically throttled by `AsyncLimiter` within the 1,200 weight/min ceiling to prevent 429 IP bans.
6. **Lot Size & Min Notional Sanitization**: Every order is mathematically quantized against Binance's `stepSize`, `minQty`, and `minNotional` filters.

---

## 🚨 Troubleshooting & Emergency Procedures

### Emergency Stop (Close all active trades):
```bash
# 1. Stop the bot process immediately
pm2 stop ultimate-bot

# 2. Check active positions
./venv/bin/python3 status.py

# 3. If you wish to manually close open positions, use the Binance Mobile/Web app
```

### "Another instance is already running":
If the bot crashed unexpectedly and left a stale lock file:
```bash
rm -f /tmp/ultimate_bot.lock
pm2 restart ultimate-bot
```

### Timestamp Synchronization Error (`-1021`):
The bot automatically synchronizes with Binance server time. If your VPS clock drifts significantly:
```bash
sudo timedatectl set-ntp on
sudo systemctl restart systemd-timesyncd
```

### Discord Alerts not Arriving:
Verify that `DISCORD_WEBHOOK_URL` in `.env` is populated with a valid Discord Webhook URL. If blank, Discord alerts are cleanly silenced without interrupting trade execution.
