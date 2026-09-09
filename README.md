# 🚀 Ultimate Binance Market-Only Trading Bot — Operations Center

A production-grade **Binance Spot** trading engine with **market-only execution**, a **5-factor Smart Money confluence strategy** (HTF trend, Break of Structure, Fair Value Gap, Cumulative Volume Delta, Volume POC), **strict risk & drawdown management**, and **Ed25519 asymmetric cryptography** — paired with an interactive **web operations center** for live monitoring, parameter tuning, and 1-click VPS sync.

```
├── ultimate-bot/          # The audited Python trading engine (Debian 13 / PEP 668 / PM2)
│   ├── main.py            # Async engine entrypoint (signal loop, exits, reconciliation)
│   ├── status.py          # CLI dashboard + embedded web monitor / control API
│   ├── config.py          # .env loader, presets, boot-time validation
│   ├── ecosystem.config.cjs# PM2: runs engine AND web monitor
│   ├── .env.example       # Annotated template for every config key
│   └── src/               # exchange / strategy / risk / trade / database / reporting modules
├── src/                   # React + Vite web dashboard (Strategy Simulator + VPS ops center)
└── metadata.json          # Applet metadata
```

Full documentation and step-by-step Debian 13 VPS instructions live in **[ultimate-bot/README.md](./ultimate-bot/README.md)**.

> **Smoke test**: `npm run smoke` (or `ultimate-bot/venv/bin/python3 ultimate-bot/smoke_test.py`) boots the engine against an isolated temp DB and verifies boot, single-instance locking, second-instance rejection, web-monitor stats consistency, and clean SIGTERM shutdown — all without touching your real `trading.db`.

### Recent correctness & safety fixes

- **Win/loss & win-rate accounting** — the dashboard previously counted every recent order (including BUY entries with zero PnL) as a "closed trade", diluting the win rate. Closed trades are now derived from SELL exit orders only, and the VPS dashboard prefers the engine's full-history aggregates, so displayed wins/losses always match the win rate.
- **Partial-exit PnL counted** — partial-exit legs (persisted as `CANCELED` SELL orders with a realized PnL) are now included in the monitor's stats, the CLI dashboard, the daily Discord report and the web UI, matching the engine's own streak/cooldown accounting.
- **Live-mode startup crash fixed** — the WebSocket API client was missing `import os`, raising `NameError` at boot whenever an Ed25519 private key was configured for live trading.
- **Web monitor hardening** — percent-encoded path-traversal attempts (`..%2f`, `%2e%2e`) are rejected before any file is read; unknown paths return 404 instead of serving the dashboard HTML.
- **Live screener integrity** — the React dashboard no longer overwrites the engine-scanned candidates with locally simulated momentum rankings while synced to a VPS.
- **Credential-safe VPS sync** — the 1-click SSH `.env` sync now backs up the existing `.env` first and warns that credentials must be preserved (the browser push path already applies a whitelist that never touches credentials).
- **Graceful shutdown hang fixed** — the engine previously hung forever on SIGINT/SIGTERM (the signal handler cancelled `main()` mid-cleanup and stopped the loop, leaving a torn-down WebSocket awaited indefinitely), which wedged `pm2 reload/restart` and kept the single-instance lock held. Signals now only flag a shutdown event; `main()` stops the loops, cancels background tasks, and tears down connections with bounded timeouts (verified live: clean exit in ~5s, lock released).

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

# 5. Build the React dashboard (run from the REPO ROOT, not ultimate-bot/)
cd ..
npm install
npm run build        # outputs to ./dist at the repo root

# 6. Launch engine + web monitor under PM2 supervision (run from ultimate-bot/)
cd ultimate-bot
pm2 start ecosystem.config.cjs
pm2 save

# 7. Monitor in real time
./venv/bin/python3 status.py --watch        # terminal dashboard
./venv/bin/python3 status.py --web 3000     # web monitor / API (http://YOUR_VPS_IP:3000)
```

> **Which folder?** The repo has two layers: the **repo root** is the React dashboard project (npm/vite) — `npm run build`/`npm run dev` run there and emit `dist/`. The **`ultimate-bot/` folder** is the Python trading engine — venv, `.env`, `main.py`, `status.py` and PM2 all live and run there. `status.py --web` automatically picks up the compiled UI from `../dist`, so you never need `npx serve` or a second server.

---

## 🌐 Interactive Web Operations Center

Run the React dashboard (`npm run dev`, or serve the compiled `dist/` next to `status.py`), then:

- **Live VPS Bot Sync**: point the dashboard at your VPS (`http://IP:3000`) to stream the real engine state from SQLite — active positions, orders, equity, daily PnL, win/loss streaks, scanned candidates, and the engine's own log file. No fake local balances are shown for the live server.
- **Engine-Exact Performance Stats**: in VPS mode the Performance card uses the engine's own SQLite aggregates — win rate, wins/losses/breakevens, profit factor, average win/loss, total realized PnL and streaks — instead of recomputing from a short window of recent orders. Only SELL exit orders with realized PnL are ever counted as closed trades, so the win/loss numbers always match the engine's win rate.
- **Comprehensive `status.py` Fallback Dashboard**: when no compiled `dist/` is present, `status.py --web` serves an upgraded standalone dashboard with a full performance section (win rate with W/L/B breakdown, profit factor, total realized PnL, average win/loss, and streak monitor) in addition to balance, scanner, positions and orders.
- **Full `npx serve -s dist` Parity in One Python File**: with a compiled `dist/` present, `status.py --web` serves the React dashboard with SPA fallback, clean-URL redirects, ETag/304 revalidation, immutable caching for hashed assets, gzip compression, HTTP Range support and HTTP/1.1 keep-alive on a multi-threaded server — no Node.js or reverse proxy needed on the VPS.
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
- **Professional risk model**: fixed-fractional 1% risk-per-trade sizing (entry→stop distance), regime-alignment gate (never long a downtrend), minimum 1.5 R:R entry filter, CVD noise floor, and +1R partial scale-out with a breakeven-locked runner.
- Daily drawdown circuit breaker, per-symbol win/loss streak cooldowns, exchange position reconciliation, and single-instance locking.
- WAL-mode SQLite with a batched async write queue and read-only monitor access.
- PM2 supervision of both the engine and the web monitor (`ecosystem.config.cjs`).

For technical indicator definitions, full `.env` reference, presets, and the live-readiness checklist, see **[ultimate-bot/README.md](./ultimate-bot/README.md)**.
