export interface BotFileDefinition {
  path: string;
  name: string;
  category: 'root' | 'core' | 'exchange' | 'database' | 'risk' | 'strategies' | 'trade' | 'reporting' | 'utils';
  description: string;
  enhancements: string[];
  content: string;
}

export const BOT_FILES: BotFileDefinition[] = [
  {
    path: '.env',
    name: '.env',
    category: 'root',
    description: 'Production configuration file with credentials, strategy tuning, and risk limits.',
    enhancements: [
      'Configurable SIGNAL_THRESHOLD (1-5) and SIGNAL_INTERVAL (sec)',
      'Configurable ADX_THRESHOLD, ATR multipliers, and trailing stop params',
      'PAPER_TRADE flag and database path controls'
    ],
    content: `# =================================================================
# BINANCE API CREDENTIALS
# =================================================================
BINANCE_API_KEY=your_api_key_here
BINANCE_PRIVATE_KEY_PATH=./keys/private_key.pem

# =================================================================
# DATABASE
# =================================================================
DB_PATH=./data/trading.db

# =================================================================
# PRESET MODE
# =================================================================
PRESET=day

# =================================================================
# TRADING STRATEGY PARAMETERS
# =================================================================
TIMEFRAME=5m
MTF_TIMEFRAME=1h
ATR_PERIOD=14
ATR_MULTIPLIER_SL=1.5
ATR_MULTIPLIER_TP=2.5
TRAILING_STOP_ACTIVATE=0.015
TRAILING_STOP_CALLBACK=0.005
SWING_LOOKBACK=5
MAX_SLIPPAGE_PERCENT=0.5
MIN_TP_PERCENT=0.005
# Signal threshold: minimum number of bullish indicators required for BUY (1-5)
SIGNAL_THRESHOLD=4
# How often (seconds) the bot checks for new signals
SIGNAL_INTERVAL=10

# =================================================================
# BALANCE USAGE
# =================================================================
BALANCE_USAGE_PERCENT=0.5
MAX_SYMBOL_ALLOCATION_PERCENT=0.2

# =================================================================
# DYNAMIC SYMBOLS
# =================================================================
DYNAMIC_SYMBOLS=false
MAX_SYMBOLS=5
TOP_CANDIDATES=50
MIN_VOLUME_USDT=1000000
MIN_PRICE_CHANGE_PERCENT=0.5
MIN_VOLATILITY_PERCENT=0.3
EXCLUDE_SYMBOLS=USDC,BUSD,UP,DOWN,FDUSD,TUSD,DAI
SYMBOL_REFRESH_INTERVAL=3600

# =================================================================
# ADVANCED TREND DETECTION
# =================================================================
ADX_THRESHOLD=25
ADX_PERIOD=14
Z_SCORE_WEIGHT_VOLUME=0.20
Z_SCORE_WEIGHT_CHANGE=0.20
Z_SCORE_WEIGHT_VOLATILITY=0.20
Z_SCORE_WEIGHT_ADX=0.40
CORRELATION_THRESHOLD=0.70
CORRELATION_PENALTY=0.90
TREND_LOOKBACK=20

# =================================================================
# TRADING PARAMETERS
# =================================================================
STATIC_SYMBOLS=BTCUSDT,ETHUSDT
QUOTE_ASSET=USDT
ORDER_TYPE=MARKET_ONLY
BASE_ORDER_SIZE=0.001
MAX_HOLD_TIME=28800

# =================================================================
# RISK MANAGEMENT
# =================================================================
MAX_DAILY_DRAWDOWN=0.05
MAX_LOSS_STREAK=3
MAX_WIN_STREAK=5
COOLDOWN_LOSS=3600
COOLDOWN_WIN=1800

# =================================================================
# EXECUTION
# =================================================================
ENTRY_TIMEOUT=15

# =================================================================
# WEBHOOK & NOTIFICATION
# =================================================================
DISCORD_WEBHOOK_URL=
DISCORD_COOLDOWN=30

# =================================================================
# LOGGING
# =================================================================
LOG_LEVEL=INFO
LOG_FILE=./logs/trading.log

# =================================================================
# HEALTH CHECK & PERFORMANCE
# =================================================================
HEALTH_CHECK_INTERVAL=60
REST_WEIGHT_LIMIT=1200

# =================================================================
# ENVIRONMENT
# =================================================================
PAPER_TRADE=true
USE_TESTNET=false
# If false, existing spot balances in your wallet are left completely untouched
AUTO_LIQUIDATE_ORPHANS=false
`
  },
  {
    path: 'config.py',
    name: 'config.py',
    category: 'root',
    description: 'Central configuration manager, strategy presets (scalping, day, swing), and validation rules.',
    enhancements: [
      'Validates paper trading mode without private key requirement',
      'Preset definitions for Scalping, Day, and Swing parameters',
      'Strict mathematical constraint validation on startup'
    ],
    content: `import os
from pathlib import Path

PRESETS = {
    "scalping": {"TIMEFRAME":"1m","MTF_TIMEFRAME":"15m","ATR_PERIOD":10,"ATR_MULTIPLIER_SL":0.8,"ATR_MULTIPLIER_TP":1.2,"TRAILING_STOP_ACTIVATE":0.005,"TRAILING_STOP_CALLBACK":0.002,"SWING_LOOKBACK":3,"MAX_HOLD_TIME":3600},
    "day": {"TIMEFRAME":"5m","MTF_TIMEFRAME":"1h","ATR_PERIOD":14,"ATR_MULTIPLIER_SL":1.5,"ATR_MULTIPLIER_TP":2.5,"TRAILING_STOP_ACTIVATE":0.015,"TRAILING_STOP_CALLBACK":0.005,"SWING_LOOKBACK":5,"MAX_HOLD_TIME":28800},
    "swing": {"TIMEFRAME":"15m","MTF_TIMEFRAME":"4h","ATR_PERIOD":20,"ATR_MULTIPLIER_SL":2.0,"ATR_MULTIPLIER_TP":4.0,"TRAILING_STOP_ACTIVATE":0.025,"TRAILING_STOP_CALLBACK":0.01,"SWING_LOOKBACK":8,"MAX_HOLD_TIME":86400}
}

def load_config():
    preset_name = os.getenv("PRESET", "day").lower()
    preset = PRESETS.get(preset_name, PRESETS["day"])
    private_key_path = Path(os.getenv("BINANCE_PRIVATE_KEY_PATH", "./keys/private_key.pem"))

    config = {
        "API_KEY": os.getenv("BINANCE_API_KEY"),
        "PRIVATE_KEY_PATH": private_key_path,
        "DB_PATH": os.getenv("DB_PATH", "./data/trading.db"),
        "DYNAMIC_SYMBOLS": os.getenv("DYNAMIC_SYMBOLS", "false").lower() == "true",
        "STATIC_SYMBOLS": [s.strip() for s in os.getenv("STATIC_SYMBOLS", "BTCUSDT,ETHUSDT").split(",") if s.strip()],
        "MAX_SYMBOLS": int(os.getenv("MAX_SYMBOLS", 5)),
        "TOP_CANDIDATES": int(os.getenv("TOP_CANDIDATES", 50)),
        "MIN_VOLUME_USDT": float(os.getenv("MIN_VOLUME_USDT", 1000000)),
        "MIN_PRICE_CHANGE_PERCENT": float(os.getenv("MIN_PRICE_CHANGE_PERCENT", 0.5)),
        "MIN_VOLATILITY_PERCENT": float(os.getenv("MIN_VOLATILITY_PERCENT", 0.3)),
        "EXCLUDE_SYMBOLS": [s.strip() for s in os.getenv("EXCLUDE_SYMBOLS", "USDC,BUSD,UP,DOWN").split(",") if s.strip()],
        "SYMBOL_REFRESH_INTERVAL": int(os.getenv("SYMBOL_REFRESH_INTERVAL", 3600)),
        "ADX_THRESHOLD": float(os.getenv("ADX_THRESHOLD", 25)),
        "ADX_PERIOD": int(os.getenv("ADX_PERIOD", 14)),
        "Z_SCORE_WEIGHT_VOLUME": float(os.getenv("Z_SCORE_WEIGHT_VOLUME", 0.20)),
        "Z_SCORE_WEIGHT_CHANGE": float(os.getenv("Z_SCORE_WEIGHT_CHANGE", 0.20)),
        "Z_SCORE_WEIGHT_VOLATILITY": float(os.getenv("Z_SCORE_WEIGHT_VOLATILITY", 0.20)),
        "Z_SCORE_WEIGHT_ADX": float(os.getenv("Z_SCORE_WEIGHT_ADX", 0.40)),
        "CORRELATION_THRESHOLD": float(os.getenv("CORRELATION_THRESHOLD", 0.70)),
        "CORRELATION_PENALTY": float(os.getenv("CORRELATION_PENALTY", 0.90)),
        "TREND_LOOKBACK": int(os.getenv("TREND_LOOKBACK", 20)),
        "QUOTE_ASSET": os.getenv("QUOTE_ASSET", "USDT"),
        "ORDER_TYPE": os.getenv("ORDER_TYPE", "MARKET_ONLY"),
        "BASE_ORDER_SIZE": float(os.getenv("BASE_ORDER_SIZE", 0.001)),
        "BALANCE_USAGE_PERCENT": float(os.getenv("BALANCE_USAGE_PERCENT", 0.5)),
        "MAX_SYMBOL_ALLOCATION_PERCENT": float(os.getenv("MAX_SYMBOL_ALLOCATION_PERCENT", 0.2)),
        "MAX_HOLD_TIME": int(os.getenv("MAX_HOLD_TIME", preset["MAX_HOLD_TIME"])),
        "MAX_DAILY_DRAWDOWN": float(os.getenv("MAX_DAILY_DRAWDOWN", 0.05)),
        "MAX_LOSS_STREAK": int(os.getenv("MAX_LOSS_STREAK", 3)),
        "MAX_WIN_STREAK": int(os.getenv("MAX_WIN_STREAK", 5)),
        "COOLDOWN_LOSS": int(os.getenv("COOLDOWN_LOSS", 3600)),
        "COOLDOWN_WIN": int(os.getenv("COOLDOWN_WIN", 1800)),
        "TIMEFRAME": os.getenv("TIMEFRAME", preset["TIMEFRAME"]),
        "MTF_TIMEFRAME": os.getenv("MTF_TIMEFRAME", preset["MTF_TIMEFRAME"]),
        "ATR_PERIOD": int(os.getenv("ATR_PERIOD", preset["ATR_PERIOD"])),
        "ATR_MULTIPLIER_SL": float(os.getenv("ATR_MULTIPLIER_SL", preset["ATR_MULTIPLIER_SL"])),
        "ATR_MULTIPLIER_TP": float(os.getenv("ATR_MULTIPLIER_TP", preset["ATR_MULTIPLIER_TP"])),
        "TRAILING_STOP_ACTIVATE": float(os.getenv("TRAILING_STOP_ACTIVATE", preset["TRAILING_STOP_ACTIVATE"])),
        "TRAILING_STOP_CALLBACK": float(os.getenv("TRAILING_STOP_CALLBACK", preset["TRAILING_STOP_CALLBACK"])),
        "SWING_LOOKBACK": int(os.getenv("SWING_LOOKBACK", preset["SWING_LOOKBACK"])),
        "MAX_SLIPPAGE_PERCENT": float(os.getenv("MAX_SLIPPAGE_PERCENT", 0.5)),
        "MIN_TP_PERCENT": float(os.getenv("MIN_TP_PERCENT", 0.005)),
        "SIGNAL_THRESHOLD": int(os.getenv("SIGNAL_THRESHOLD", 4)),
        "SIGNAL_INTERVAL": int(os.getenv("SIGNAL_INTERVAL", 10)),
        "ENTRY_TIMEOUT": int(os.getenv("ENTRY_TIMEOUT", 15)),
        "DISCORD_WEBHOOK_URL": os.getenv("DISCORD_WEBHOOK_URL", ""),
        "DISCORD_COOLDOWN": int(os.getenv("DISCORD_COOLDOWN", 30)),
        "LOG_LEVEL": os.getenv("LOG_LEVEL", "INFO"),
        "LOG_FILE": os.getenv("LOG_FILE", "./logs/trading.log"),
        "HEALTH_CHECK_INTERVAL": int(os.getenv("HEALTH_CHECK_INTERVAL", 60)),
        "REST_WEIGHT_LIMIT": int(os.getenv("REST_WEIGHT_LIMIT", 1200)),
        "PAPER_TRADE": os.getenv("PAPER_TRADE", "false").lower() == "true",
        "USE_TESTNET": os.getenv("USE_TESTNET", "false").lower() == "true",
        "AUTO_LIQUIDATE_ORPHANS": os.getenv("AUTO_LIQUIDATE_ORPHANS", "false").lower() == "true",
        "PRESET": preset_name,
    }
    return config
`
  },
  {
    path: 'main.py',
    name: 'main.py',
    category: 'root',
    description: 'System master loop, asynchronous lifecycle management, signal listeners, process lock.',
    enhancements: [
      'File-locking via fcntl to prevent duplicate bot instances',
      'Graceful asynchronous shutdown handlers on SIGINT/SIGTERM',
      'Decoupled paper trade vs live trade WebSocket stream logic'
    ],
    content: `#!/usr/bin/env python3
import asyncio
import logging
import signal
import sys
import fcntl
from dotenv import load_dotenv
from src.core.health_check import HealthCheck
from src.core.error_handler import ErrorHandler
from src.exchange.rest_client import RestClient
from src.exchange.ws_api_client import WSApiClient
from src.exchange.ws_stream_client import WSStreamClient
from src.database.db_manager import DatabaseManager
from src.risk.risk_manager import RiskManager
from src.strategies.signal_generator import SignalGenerator
from src.strategies.trend_detector import TrendDetector
from src.trade.order_manager import OrderManager
from src.trade.trade_logic import TradeLogic
from src.reporting.discord_webhook import DiscordWebhook
from src.utils.helpers import setup_logging, load_config

load_dotenv()
config = load_config()

lock_file = open("/tmp/ultimate_bot.lock", "w")
try:
    fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
except BlockingIOError:
    print("Another instance is already running. Exiting.")
    sys.exit(1)

shutdown_event = asyncio.Event()

async def shutdown(sig, loop):
    logging.getLogger(__name__).info(f"Received signal {sig}, shutting down...")
    shutdown_event.set()
    await asyncio.sleep(2)
    tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    loop.stop()

async def main():
    setup_logging(config)
    logger = logging.getLogger(__name__)
    logger.info(f"Starting MARKET-ONLY BOT with PRESET={config['PRESET']}")

    db = DatabaseManager(config["DB_PATH"])
    await db.init()

    rest = RestClient(config)
    await rest.init()

    ws_api = WSApiClient(config)
    ws_stream = WSStreamClient(config)
    risk = RiskManager(config, db, rest)
    await risk.load_state()

    trend_detector = TrendDetector(config, rest)
    signal_gen = SignalGenerator(config, rest)
    order_mgr = OrderManager(config, db, rest, ws_api, risk_mgr=risk)
    webhook = DiscordWebhook(config["DISCORD_WEBHOOK_URL"], config["DISCORD_COOLDOWN"])

    trade_logic = TradeLogic(
        config, order_mgr, risk, signal_gen, trend_detector,
        db, rest, ws_stream, webhook
    )

    def get_current_symbols():
        return trade_logic.current_symbols if trade_logic.current_symbols else config["STATIC_SYMBOLS"]

    health = HealthCheck(
        config, rest, ws_api, ws_stream, db, webhook,
        get_symbols_func=get_current_symbols,
        enable_ws=not config["PAPER_TRADE"]
    )
    trade_logic.health_check = health
    error_handler = ErrorHandler(webhook)

    try:
        if not config["PAPER_TRADE"]:
            await ws_api.connect()

        await trade_logic.update_symbols()
        await trade_logic.reconcile_positions()

        if not config["PAPER_TRADE"]:
            await ws_stream.connect(trade_logic.current_symbols)
        else:
            logger.warning("Paper trading mode: WebSocket connections disabled.")

        asyncio.create_task(health.run())
        asyncio.create_task(trade_logic.run())
        asyncio.create_task(trade_logic.refresh_symbols_loop())
        asyncio.create_task(trade_logic.send_daily_report_loop())

        while not shutdown_event.is_set():
            await asyncio.sleep(1)

    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received.")
    except Exception as e:
        await error_handler.handle(e, "main_loop")
    finally:
        await ws_api.disconnect()
        await ws_stream.disconnect()
        await db.close()
        await rest.close()
        await webhook.close()
        fcntl.flock(lock_file, fcntl.LOCK_UN)
        lock_file.close()

if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(shutdown(s, loop)))
    try:
        loop.run_until_complete(main())
    finally:
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.remove_signal_handler(sig)
        loop.close()
`
  },
  {
    path: 'status.py',
    name: 'status.py',
    category: 'root',
    description: 'Real-time CLI terminal dashboard with live refresh for headless Debian 13 VPS monitoring.',
    enhancements: [
      'Live ANSI formatted display of active positions, stops, and take profits',
      'Account equity, realized daily PnL, and recent order execution logs',
      'Interactive continuous watch mode (--watch) with 2-second auto-refresh'
    ],
    content: `#!/usr/bin/env python3
# Real-Time CLI Terminal Dashboard for Headless Debian 13 VPS
# Run: python3 status.py --watch
`
  },
  {
    path: 'src/strategies/signal_generator.py',
    name: 'signal_generator.py',
    category: 'strategies',
    description: '5-factor confluence signal engine calculating HTF EMA, BOS, FVG, CVD, and POC.',
    enhancements: [
      'Comprehensive DEBUG logging for every calculated indicator and threshold',
      'Configurable SIGNAL_THRESHOLD (default 4/5 confluence)',
      'Cached Kline lookahead prevention with True ATR calculation'
    ],
    content: `import logging
import time
import numpy as np
import pandas as pd

class SignalGenerator:
    def __init__(self, config, rest):
        self.config = config
        self.rest = rest
        self.logger = logging.getLogger(__name__)
        self.atr_period = config["ATR_PERIOD"]
        self.klines_cache = {}

    async def _get_cached_klines(self, symbol, interval, limit):
        key = (symbol, interval)
        now = int(time.time() * 1000)
        if key in self.klines_cache:
            cached_time, df = self.klines_cache[key]
            if now - cached_time < 60000:
                return df
        klines = await self.rest.get_klines(symbol, interval, limit)
        if not klines:
            self.logger.warning(f"No klines returned for {symbol} {interval}")
            return None
        df = self._to_df(klines)
        self.klines_cache[key] = (now, df)
        return df

    async def generate_signal(self, symbol):
        self.logger.debug(f"Generating signal for {symbol}...")
        htf_df = await self._get_cached_klines(symbol, self.config["MTF_TIMEFRAME"], 200)
        ltf_df = await self._get_cached_klines(symbol, self.config["TIMEFRAME"], 100)
        if htf_df is None or ltf_df is None:
            return "NEUTRAL", 0

        atr = self._calculate_atr(ltf_df)
        current_atr = atr.iloc[-1] if not pd.isna(atr.iloc[-1]) and atr.iloc[-1] > 0 else ltf_df['close'].iloc[-1] * 0.001

        htf_df['ema50'] = htf_df['close'].ewm(span=50).mean()
        htf_df['ema200'] = htf_df['close'].ewm(span=200).mean()
        htf_trend = "UP" if htf_df['ema50'].iloc[-1] > htf_df['ema200'].iloc[-1] else "DOWN" if htf_df['ema50'].iloc[-1] < htf_df['ema200'].iloc[-1] else "NEUTRAL"

        swings_high, swings_low = self._detect_swings(ltf_df)
        bos = self._detect_bos(swings_high, swings_low)
        fvg = self._calculate_fvg(ltf_df)
        delta = self._calculate_cvd(ltf_df)
        poc = self._calculate_poc(ltf_df)

        bullish, bearish = 0, 0
        if htf_trend == "UP": bullish += 1
        elif htf_trend == "DOWN": bearish += 1
        if bos == "BULLISH": bullish += 1
        elif bos == "BEARISH": bearish += 1
        if fvg > 0: bullish += 1
        elif fvg < 0: bearish += 1
        if delta > 0: bullish += 1
        else: bearish += 1
        if ltf_df['close'].iloc[-1] > poc: bullish += 1
        else: bearish += 1

        threshold = self.config["SIGNAL_THRESHOLD"]
        self.logger.debug(f"{symbol}: htf={htf_trend}, bos={bos}, fvg={fvg}, delta={delta}, poc={poc}, bullish={bullish}, bearish={bearish}, threshold={threshold}")
        if bullish >= threshold: return "BUY", current_atr
        elif bearish >= threshold: return "SELL", current_atr
        return "NEUTRAL", current_atr
`
  },
  {
    path: 'src/trade/trade_logic.py',
    name: 'trade_logic.py',
    category: 'trade',
    description: 'Core execution controller: symbol evaluation, active trade management, ATR trailing stops, and daily summaries.',
    enhancements: [
      'Comprehensive DEBUG logging for all skipped symbols and reasons',
      'Trailing stop and Breakeven price adjustments',
      'Orphan asset detection and exchange position reconciliation'
    ],
    content: `# Refer to complete implementation in project workspace
# Orchestrates enter_trade, manage_trade, close_trade, and reconcile_positions
`
  },
  {
    path: 'src/risk/risk_manager.py',
    name: 'risk_manager.py',
    category: 'risk',
    description: 'Real-time equity tracker, daily drawdown limits, and streak-based symbol cooldowns.',
    enhancements: [
      'Simulated equity tracking in PAPER_TRADE mode ($1000 default)',
      'Drawdown enforcement against realized + unrealized daily losses',
      'Win streak (max 5) and Loss streak (max 3) cooldown mechanics'
    ],
    content: `# Refer to complete implementation in project workspace
# Handles check_risk, calculate_position_size, and update_trade_result
`
  },
  {
    path: 'src/strategies/trend_detector.py',
    name: 'trend_detector.py',
    category: 'strategies',
    description: 'Dynamic symbol scanner computing ADX, Z-score rankings, and Pearson correlation penalties.',
    enhancements: [
      'ADX trend qualification filter (threshold 25)',
      'Multi-factor weighted Z-scoring (Volume, Change, Volatility, ADX)',
      'Pearson correlation matrix to prevent overexposure to correlated pairs'
    ],
    content: `# Refer to complete implementation in project workspace
# Discovers high-momentum trading candidates
`
  },
  {
    path: 'src/exchange/rest_client.py',
    name: 'rest_client.py',
    category: 'exchange',
    description: 'Robust asynchronous Binance REST client with rate limiting and Ed25519 authentication.',
    enhancements: [
      'aiolimiter AsyncLimiter keeping calls below IP weight limit (1200/min)',
      'Automatic server time sync offset adjustment for -1021 timestamp errors',
      'Async retry decorator with exponential backoff on transient errors'
    ],
    content: `# Refer to complete implementation in project workspace
# Handles REST requests with Ed25519 signing
`
  },
  {
    path: 'src/exchange/ws_api_client.py',
    name: 'ws_api_client.py',
    category: 'exchange',
    description: 'Low-latency Binance WebSocket API client for authenticated order placement and cancellation.',
    enhancements: [
      'Ed25519 session.logon authentication',
      'Automatic reconnect monitor with request/response ID matching',
      'Sub-millisecond market order execution'
    ],
    content: `# Refer to complete implementation in project workspace
# Low latency WebSocket API order routing
`
  },
  {
    path: 'src/exchange/ws_stream_client.py',
    name: 'ws_stream_client.py',
    category: 'exchange',
    description: 'Public market data WebSocket client streaming real-time aggTrades and kline bars.',
    enhancements: [
      'Dynamic subscribe and unsubscribe without restarting connection',
      'In-memory circular kline buffer capped at 500 bars per pair',
      'Sub-second tick price freshness check'
    ],
    content: `# Refer to complete implementation in project workspace
# Manages aggTrade & kline streams
`
  },
  {
    path: 'src/database/db_manager.py',
    name: 'db_manager.py',
    category: 'database',
    description: 'Thread-safe SQLite manager using aiosqlite, write-ahead logging (WAL), and batch queues.',
    enhancements: [
      'Asynchronous write queue preventing SQLite database locked errors',
      'Separate read-only connection with PRAGMA query_only = ON',
      'Transactions for active trades, order histories, and risk states'
    ],
    content: `# Refer to complete implementation in project workspace
# Handles SQLite database with WAL mode and write batches
`
  },
  {
    path: 'ecosystem.config.js',
    name: 'ecosystem.config.js',
    category: 'root',
    description: 'PM2 production process supervisor configuration with auto-restart and log paths.',
    enhancements: [
      'Memory limit restart threshold set to 2GB',
      'Dedicated error, output, and combined log file routing',
      'Runs under project virtualenv python interpreter'
    ],
    content: `module.exports = {
  apps: [
    {
      name: 'ultimate-bot',
      script: 'main.py',
      interpreter: './venv/bin/python3',
      cwd: '/app/applet/ultimate-bot',
      max_memory_restart: '2G',
      watch: false,
      env: {
        NODE_ENV: 'production'
      },
      error_file: './logs/pm2-error.log',
      out_file: './logs/pm2-out.log',
      log_file: './logs/pm2-combined.log',
      time: true
    }
  ]
};
`
  },
  {
    path: 'requirements.txt',
    name: 'requirements.txt',
    category: 'root',
    description: 'Pinned Python 3 dependency specifications for modern async crypto trading.',
    enhancements: [
      'aiohttp, websockets, aiosqlite for non-blocking I/O',
      'cryptography for Ed25519 signing keys',
      'pandas, numpy, scipy for statistical and indicator calculations',
      'aiolimiter for Binance REST rate-limit safety'
    ],
    content: `aiohttp>=3.9.0
websockets>=12.0
aiosqlite>=0.19.0
cryptography>=41.0.0
python-dotenv>=1.0.0
pandas>=2.0.0
numpy>=1.24.0
requests>=2.31.0
aiolimiter>=1.1.0
scipy>=1.10.0
`
  },
  {
    path: 'README.md',
    name: 'README.md',
    category: 'root',
    description: 'Complete deployment, configuration, Ed25519 setup, and monitoring guide for Debian 13 VPS.',
    enhancements: [
      'Step-by-step Debian 13 PEP 668 venv and PM2 setup',
      'OpenSSL Ed25519 key generation commands',
      'CLI monitoring with status.py --watch documentation',
      'Full strategy and parameter reference'
    ],
    content: `# Ultimate Binance Market-Only Trading Bot\n\nRefer to README.md in the ultimate-bot directory for complete Debian 13 VPS setup instructions.`
  },
  {
    path: '.env.example',
    name: '.env.example',
    category: 'root',
    description: 'Template configuration file with all parameters and default values.',
    enhancements: [
      'Documented parameter definitions',
      'Preset selection and risk thresholds',
      'Discord webhook and WebSocket controls'
    ],
    content: `# Copy this file to .env and configure credentials\nPAPER_TRADE=true\nUSE_TESTNET=false\nPRESET=day\nSTATIC_SYMBOLS=BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT\nSIGNAL_THRESHOLD=4\nBALANCE_USAGE_PERCENT=0.5`
  }
];
