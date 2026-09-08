# 🚀 Ultimate Binance Market-Only Trading Bot — Operations Center

A production-grade **Binance Spot** trading engine with **market-only execution**, a **5-factor Smart Money confluence strategy** (HTF trend, Break of Structure, Fair Value Gap, Cumulative Volume Delta, Volume POC), **strict risk & drawdown management**, and **Ed25519 asymmetric cryptography** — paired with an interactive **web operations center** for live monitoring, parameter tuning, and 1-click VPS sync.

```
├── ultimate-bot/          # The audited Python trading engine (Debian 13 / PEP 668 / PM2)
│   ├── main.py            # Async engine entrypoint (signal loop, exits, reconciliation)
│   ├── status.py          # CLI dashboard + embedded web monitor / control API
│   ├── config.py          # .env loader, presets, boot-time validation
│   ├── ecosystem.config.js# PM2: runs engine AND web monitor
│   └── src/               # exchange / strategy / risk / trade / database / reporting modules
├── src/                   # React + Vite web dashboard (Strategy Simulator + VPS ops center)
├── generate_bot.py        # Generates a deployable copy of ultimate-bot/ from the audited tree
└── metadata.json / .env.example  # Applet metadata & host template
```

Full documentation and step-by-step Debian 13 VPS instructions live in **[ultimate-bot/README.md](./ultimate-bot/README.md)**.

---

## ⚡ Quick Start on Debian 13 VPS

```bash
# 1. System packages
sudo apt-get update && sudo apt-get install -y python3 python3-venv python3-pip git curl openssl
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
sudo apt-get install -y nodejs && sudo npm install -g pm2

# 2. Virtual environment setup (PEP 668 compliant)
cd ultimate-bot
python3 -m venv venv
./venv/bin/pip install --upgrade pip
./venv/bin/pip install -r requirements.txt

# 3. Generate Ed25519 Keys for Binance API
mkdir -p keys && chmod 700 keys
openssl genpkey -algorithm Ed25519 -out keys/private_key.pem && chmod 600 keys/private_key.pem
openssl pkey -in keys/private_key.pem -pubout -out keys/public_key.pem
cat keys/public_key.pem

# 4. Configure .env (starts in safe PAPER_TRADE=true mode)
cp .env.example .env
nano .env

# 5. Launch engine + web monitor under PM2 supervision
pm2 start ecosystem.config.js
pm2 save

# 6. Monitor in real time
./venv/bin/python3 status.py --watch        # terminal dashboard
./venv/bin/python3 status.py --web 3000     # web monitor / API (http://YOUR_VPS_IP:3000)
```

---

## 🌐 Interactive Web Operations Center

Run the React dashboard (`npm run dev`, or serve the compiled `dist/` next to `status.py`), then:

- **Live VPS Bot Sync**: point the dashboard at your VPS (`http://IP:3000`) to stream the real engine state from SQLite — active positions, orders, equity, daily PnL, win/loss streaks, scanned candidates, and the engine's own log file. No fake local balances are shown for the live server.
- **Tune Strategy Parameters**: live sliders/presets for Confluence Threshold (1–5), ATR multipliers, trailing-stop levels, capital allocation, scan interval, and max positions.
- **Dynamic Momentum Screener**: ranked candidates via the 4-factor Z-score (Volume, 24h Change, Volatility, ADX) with a correlation penalty — pin or deselect symbols from the trading basket.
- **Symbol Deep-Dive**: inspect all 5 Smart Money confluence factors for any token, plus an order-size calculator with `MIN_NOTIONAL` validation and instant simulated buys.
- **Remote Engine Control**: **Pause/Resume** new entries (open positions stay managed), **Emergency Close All**, and per-symbol **Market Close** straight from the browser via the engine's control-file channel.
- **1-Click VPS .env Sync**: push your tuned configuration to the VPS `.env` (whitelisted keys only — never credentials) and `pm2 reload ultimate-bot` with zero downtime.
- **Project Code & ZIP**: browse every audited engine file or download a byte-identical `ultimate-bot.zip` for deployment.

A **Strategy Simulator** sandbox (forward-tested paper trading with fee-accurate net PnL) is built into the dashboard for testing signals and exits before touching the live engine.

---

## 🔑 Key Features of the Engine

- 100% market orders with slippage guards, filter-exact `LOT_SIZE`/`MIN_NOTIONAL` quantization, and orphan-order cleanup on exit.
- Ed25519-signed REST **and** WebSocket API order routing (HMAC secret supported as a fallback).
- Public WebSocket price stream with automatic REST fallback and gap-breach stop protection on bar lows.
- Net PnL always deducts 0.1% taker fees per leg; fee-aware breakeven lock at entry +0.25%.
- Daily drawdown circuit breaker, per-symbol win/loss streak cooldowns, exchange position reconciliation, and single-instance locking.
- WAL-mode SQLite with a batched async write queue and read-only monitor access.
- PM2 supervision of both the engine and the web monitor (`ecosystem.config.js`).

For technical indicator definitions, full `.env` reference, presets, and the live-readiness checklist, see **[ultimate-bot/README.md](./ultimate-bot/README.md)**.
