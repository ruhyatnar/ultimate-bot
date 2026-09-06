# 🚀 Ultimate Binance Market-Only Trading Bot

A production-grade, algorithmic trading bot designed specifically for **Binance Spot Trading** with **Market-Only Execution**, **5-Factor Smart Money Confluence Strategy**, **Strict Risk & Drawdown Management**, and **Ed25519 Asymmetric Cryptography**.

Engineered for **Debian 13 (Trixie) CLI-only VPS** environments with zero GUI overhead, complete PEP 668 compliance, process supervision via PM2, and a terminal live dashboard (`status.py`).

Full documentation and step-by-step Debian 13 VPS instructions are available in [ultimate-bot/README.md](./ultimate-bot/README.md).

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

# 4. Configure .env
cp .env.example .env
nano .env

# 5. Launch with PM2 supervision
pm2 start ecosystem.config.js
pm2 save

# 6. Monitor in real-time
./venv/bin/python3 status.py --watch
```

---

## 🌐 Interactive Web Operations Center

In addition to the terminal `status.py` monitor, this project includes an interactive web monitoring dashboard that allows you to:

- **Tune Strategy Parameters in Real Time**: Live sliders for Confluence Threshold (1-5), ATR Multipliers, Capital Allocation %, Scan Interval, and Max Positions.
- **Dynamic Momentum Screener**: Ranked candidates via 4-factor Z-Score (Volume, 24h Change, Volatility, ADX).
- **Symbol Deep-Dive**: Inspect the 5 Smart Money Confluence factors (HTF Dual EMA, BOS, FVG, CVD, POC) for any token.
- **1-Click VPS Sync**: Copy a ready-to-run Bash script that updates `.env` on your Debian 13 VPS and runs `pm2 reload ultimate-bot` with zero downtime.

For full details on technical indicators, risk parameters, and presets, refer to [`ultimate-bot/README.md`](./ultimate-bot/README.md).
