import { BotConfig } from '../types';

/** Taker fee per leg on Binance Spot (0.10%). Round-trip = 0.20%.
 *  All paper-trade PnL MUST net this out so results match live expectations. */
export const TAKER_FEE_RATE = 0.001;

/** Binance Spot MIN_NOTIONAL floor — orders below this are rejected live. */
export const MIN_NOTIONAL_USDT = 10;

/** Fee-aware breakeven multiplier: covers 0.2% round-trip fees + 0.05% cushion. */
export const BREAKEVEN_FEE_MULTIPLIER = 1.0025;

/**
 * Single source of truth for the bot's .env file.
 * Used by the Strategy & Config tab, the VPS Sync modal, and the bundled
 * `.env` file shipped in the downloadable ZIP — so all three always match.
 */
export function generateEnvString(config: BotConfig, apiKey: string = 'your_binance_api_key_here'): string {
  return `# =================================================================
# BINANCE ULTIMATE BOT — TUNED CONFIGURATION
# Generated via Interactive Web Monitor
# =================================================================

# --- Trading Mode ---
# SAFETY DEFAULT: 'true' = zero-risk paper simulation with real-time market data.
# The engine will NOT boot into live mode unless this is explicitly 'false'.
# Set to 'false' ONLY after completing the full live-readiness checklist (README).
PAPER_TRADE=${config.paperTrade}
USE_TESTNET=${config.useTestnet}

# --- Binance Credentials ---
# ⚠️ Placeholders below are for NEW setups only. If you are pushing this over an
# EXISTING VPS deployment, preserve your current BINANCE_API_KEY / BINANCE_API_SECRET
# (the web monitor's POST /api/config whitelist never touches credentials, and the
# engine requires the real key to boot in live mode).
BINANCE_API_KEY=${apiKey}
BINANCE_PRIVATE_KEY_PATH=./keys/private_key.pem

# --- Preset Strategy Profile ---
PRESET=${config.preset}

# --- Technical Parameters ---
TIMEFRAME=${config.timeframe}
MTF_TIMEFRAME=${config.mtfTimeframe}
ATR_PERIOD=${config.atrPeriod}
ATR_MULTIPLIER_SL=${config.atrMultiplierSl}
ATR_MULTIPLIER_TP=${config.atrMultiplierTp}
TRAILING_STOP_ACTIVATE=${config.trailingStopActivate}
TRAILING_STOP_CALLBACK=${config.trailingStopCallback}
SWING_LOOKBACK=${config.swingLookback}
MAX_HOLD_TIME=${config.maxHoldTime}

# --- Confluence & Signal Engine ---
SIGNAL_THRESHOLD=${config.signalThreshold}
SIGNAL_INTERVAL=${config.signalInterval}

# --- Risk & Portfolio Limits ---
BALANCE_USAGE_PERCENT=${config.balanceUsagePercent}
MAX_SYMBOL_ALLOCATION_PERCENT=${config.maxSymbolAllocationPercent}
MAX_DAILY_DRAWDOWN=${config.maxDailyDrawdown}
MAX_LOSS_STREAK=${config.maxLossStreak}
MAX_WIN_STREAK=${config.maxWinStreak}
COOLDOWN_LOSS=${config.cooldownLoss}
COOLDOWN_WIN=${config.cooldownWin}
MAX_SLIPPAGE_PERCENT=0.5
MIN_TP_PERCENT=0.005

# --- Symbols Configuration ---
DYNAMIC_SYMBOLS=${config.dynamicSymbols}
MAX_SYMBOLS=${config.maxSymbols}
STATIC_SYMBOLS=${config.staticSymbols.join(',')}
QUOTE_ASSET=USDT
EXCLUDE_SYMBOLS=USDC,BUSD,UP,DOWN,FDUSD,TUSD,DAI

# --- Dynamic Screener & ADX ---
ADX_THRESHOLD=${config.adxThreshold}
ADX_PERIOD=${config.adxPeriod}
TOP_CANDIDATES=50
MIN_VOLUME_USDT=1000000
Z_SCORE_WEIGHT_VOLUME=0.20
Z_SCORE_WEIGHT_CHANGE=0.20
Z_SCORE_WEIGHT_VOLATILITY=0.20
Z_SCORE_WEIGHT_ADX=0.40
CORRELATION_THRESHOLD=0.70
CORRELATION_PENALTY=0.90
TREND_LOOKBACK=20

# --- Database & Webhooks ---
DB_PATH=./data/trading.db
DISCORD_WEBHOOK_URL=${config.discordWebhookUrl}
DISCORD_COOLDOWN=30
LOG_LEVEL=${config.logLevel}
LOG_FILE=./logs/trading.log
HEALTH_CHECK_INTERVAL=60
REST_WEIGHT_LIMIT=1200
ENTRY_TIMEOUT=15

# --- Wallet Safety ---
# If false, existing spot balances in your wallet are left completely untouched
AUTO_LIQUIDATE_ORPHANS=false
`;
}

/** Compute the effective per-trade allocation: min(total-usage, per-symbol cap) with 1% fee buffer. */
export function effectiveAllocation(config: BotConfig, equity: number): number {
  return Math.min(equity * config.balanceUsagePercent, equity * config.maxSymbolAllocationPercent) * 0.99;
}
