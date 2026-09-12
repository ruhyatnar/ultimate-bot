import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env HERE — not only in main.py — so backtest.py, status.py, soak and
# test harnesses all see the same configuration as the live engine. An explicit
# path keeps this deterministic regardless of the caller's working directory.
# Existing process-env vars still win (override=False default), so CLI research
# overrides keep working.
load_dotenv(Path(__file__).resolve().parent / ".env")

PRESETS = {
    # Scalping: 1m entries, tight 1.0x/2.0x ATR bracket (R:R 2.0), fast trailing.
    # Tight stops demand HTF alignment — confluence gate stays at 4/5.
    # NOTE: NOT yet validated by backtest — paper-trade before live use.
    "scalping": {"TIMEFRAME":"1m","MTF_TIMEFRAME":"15m","ATR_PERIOD":10,"ATR_MULTIPLIER_SL":1.0,"ATR_MULTIPLIER_TP":2.0,"TRAILING_STOP_ACTIVATE":0.005,"TRAILING_STOP_CALLBACK":0.002,"SWING_LOOKBACK":3,"MAX_HOLD_TIME":3600,"MIN_TP_PERCENT":0.0008},
    # Day trading: 5m entries. Backtest-proven (BTCUSDT, 20d, 2026-08/09):
    # a wide 3.0x-ATR stop with a low 0.15% TP floor (balanced bracket)
    # lifted win rate 12.6% -> 50% and profit factor 0.09 -> 0.79 vs the old
    # 1.2x/2.4x + 0.5%-floor setup, whose floor made TP ~8x the stop so nearly
    # every trade resolved as a -1R stop-out. TP 3.5x keeps R:R > 1 while
    # satisfying the TP > SL validation.
    "day": {"TIMEFRAME":"5m","MTF_TIMEFRAME":"1h","ATR_PERIOD":14,"ATR_MULTIPLIER_SL":3.0,"ATR_MULTIPLIER_TP":3.5,"TRAILING_STOP_ACTIVATE":0.015,"TRAILING_STOP_CALLBACK":0.005,"SWING_LOOKBACK":5,"MAX_HOLD_TIME":28800,"MIN_TP_PERCENT":0.0015},
    # Swing: 15m entries, 2.0x SL / 4.0x TP (R:R 2.0), trailing later (3%) so
    # multi-day runners keep their room. Backtest on 15m data was negative for
    # ALL configs (the strategy's HTF trend gate filters too little on 15m);
    # floor lowered proportionally to keep the bracket balanced.
    "swing": {"TIMEFRAME":"15m","MTF_TIMEFRAME":"4h","ATR_PERIOD":20,"ATR_MULTIPLIER_SL":2.0,"ATR_MULTIPLIER_TP":4.0,"TRAILING_STOP_ACTIVATE":0.03,"TRAILING_STOP_CALLBACK":0.012,"SWING_LOOKBACK":8,"MAX_HOLD_TIME":86400,"MIN_TP_PERCENT":0.003},
    # swing_rsi: backtest-proven small-account strategy (2026-09-10, ~113 days,
    # $22 equity, fees + $10 minNotional modeled): NEARUSDT +52.4% (PF 2.11,
    # WR 55.3%, 38 trades, max DD 6.5%); 6/9 alt pairs positive. Daily-EMA50
    # regime gate + 15m RSI<40 dip trigger; FIXED % bracket (SL -2% / TP +4%,
    # TP as resting OCO limit = maker fee). ATR multipliers below are % of
    # price in this mode; scale-out is disabled (the tested edge had none).
    "swing_rsi": {"TIMEFRAME":"5m","MTF_TIMEFRAME":"1d","ATR_PERIOD":14,"ATR_MULTIPLIER_SL":0.02,"ATR_MULTIPLIER_TP":0.04,"TRAILING_STOP_ACTIVATE":0.05,"TRAILING_STOP_CALLBACK":0.01,"SWING_LOOKBACK":5,"MAX_HOLD_TIME":604800,"MIN_TP_PERCENT":0.04,"STRATEGY_MODE":"rsi_dip","SL_PERCENT":0.02,"TP_PERCENT":0.04,"RSI_PERIOD":14,"RSI_OVERSOLD":40.0,"RSI_TIMEFRAME":"15m","REGIME_EMA":50,"REGIME_SLOPE_DAYS":3,"COOLDOWN_LOSS":86400,"COOLDOWN_WIN":86400,"MAX_TRADES_PER_DAY":3},
    # intraday_rsi: backtest-proven intraday variant (2026-09-11, 174 days, $22
    # equity, honest taker/maker fees + $10 minNotional, same-UTC-day close):
    # NEARUSDT +45.7% (PF 1.94, WR 51.7%, 58 trades, max DD 9.4%); all three
    # 58-day sub-windows positive (+19.6/+15.6/+5.4%); all 9 parameter-
    # neighborhood configs positive; +32% with 10bps slippage stress. Daily-
    # EMA50 regime + 1h RSI(7)<40 dip trigger; % bracket (SL -1.2% / TP +3%,
    # TP as OCO limit = maker fee); max 1 entry/day; position force-closed at
    # UTC day end (CLOSE_AT_UTC_DAY_END); breakeven lock OFF (would exit the
    # intraday trade before TP). Edge is PAIR-CONCENTRATED: 9-pair rotation
    # was only +14.6% (PF 1.07) — run with STATIC_SYMBOLS=NEARUSDT.
    "intraday_rsi": {"TIMEFRAME":"5m","MTF_TIMEFRAME":"1d","ATR_PERIOD":14,"ATR_MULTIPLIER_SL":0.012,"ATR_MULTIPLIER_TP":0.03,"TRAILING_STOP_ACTIVATE":0.05,"TRAILING_STOP_CALLBACK":0.01,"SWING_LOOKBACK":5,"MAX_HOLD_TIME":84600,"MIN_TP_PERCENT":0.03,"STRATEGY_MODE":"rsi_dip","SL_PERCENT":0.012,"TP_PERCENT":0.03,"RSI_PERIOD":7,"RSI_OVERSOLD":40.0,"RSI_TIMEFRAME":"1h","RSI_SOURCE":"ltf","REGIME_EMA":50,"REGIME_SLOPE_DAYS":3,"COOLDOWN_LOSS":86400,"COOLDOWN_WIN":86400,"MAX_TRADES_PER_DAY":1,"BREAKEVEN_ENABLED":False,"CLOSE_AT_UTC_DAY_END":True}
}

def load_config():
    preset_name = os.getenv("PRESET", "day").lower()
    preset = PRESETS.get(preset_name, PRESETS["day"])
    private_key_path = Path(os.getenv("BINANCE_PRIVATE_KEY_PATH", "./keys/private_key.pem"))

    config = {
        "API_KEY": os.getenv("BINANCE_API_KEY"),
        "API_SECRET": os.getenv("BINANCE_API_SECRET"),
        "PRIVATE_KEY_PATH": private_key_path,
        "DB_PATH": os.getenv("DB_PATH", "./data/trading.db"),
        "CONTROL_FILE": os.getenv("CONTROL_FILE", "./data/engine_control.json"),
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
        "BALANCE_USAGE_PERCENT": float(os.getenv("BALANCE_USAGE_PERCENT", 0.5)),
        "MAX_SYMBOL_ALLOCATION_PERCENT": float(os.getenv("MAX_SYMBOL_ALLOCATION_PERCENT", 0.2)),
        "MAX_HOLD_TIME": int(os.getenv("MAX_HOLD_TIME", preset["MAX_HOLD_TIME"])),
        "RISK_PER_TRADE": float(os.getenv("RISK_PER_TRADE", 0.01)),
        "MIN_RISK_REWARD": float(os.getenv("MIN_RISK_REWARD", 1.5)),
        # swing_rsi preset was proven WITHOUT scale-out; other presets keep the
        # historical default. An explicit SCALE_OUT_ENABLED env always wins.
        "SCALE_OUT_ENABLED": os.getenv("SCALE_OUT_ENABLED",
                                       "false" if preset.get("STRATEGY_MODE") == "rsi_dip" else "true").lower() == "true",
        # rsi_dip RSI series source:
        #   'htf' = RSI computed on dedicated RSI_TIMEFRAME candle closes
        #           (swing_rsi's proven 15m-candle convention).
        #   'ltf' = RSI computed on execution-TF closes, sampled at the LAST
        #           bar of each RSI_TIMEFRAME bucket (intraday_rsi's proven
        #           convention: RSI(7) on 5m closes read at :55).
        "RSI_SOURCE": os.getenv("RSI_SOURCE", preset.get("RSI_SOURCE", "htf")).lower(),
        "SCALE_OUT_R_MULTIPLE": float(os.getenv("SCALE_OUT_R_MULTIPLE", 1.0)),
        "SCALE_OUT_FRACTION": float(os.getenv("SCALE_OUT_FRACTION", 0.5)),
        "MAX_DAILY_DRAWDOWN": float(os.getenv("MAX_DAILY_DRAWDOWN", 0.05)),
        "MAX_LOSS_STREAK": int(os.getenv("MAX_LOSS_STREAK", 3)),
        "MAX_WIN_STREAK": int(os.getenv("MAX_WIN_STREAK", 5)),
        "COOLDOWN_LOSS": int(os.getenv("COOLDOWN_LOSS", preset.get("COOLDOWN_LOSS", 10800))),
        "COOLDOWN_WIN": int(os.getenv("COOLDOWN_WIN", preset.get("COOLDOWN_WIN", 1800))),
        "MAX_TRADES_PER_DAY": int(os.getenv("MAX_TRADES_PER_DAY", preset.get("MAX_TRADES_PER_DAY", 0))),
        "TIMEFRAME": os.getenv("TIMEFRAME", preset["TIMEFRAME"]),
        "MTF_TIMEFRAME": os.getenv("MTF_TIMEFRAME", preset["MTF_TIMEFRAME"]),
        "ATR_PERIOD": int(os.getenv("ATR_PERIOD", preset["ATR_PERIOD"])),
        "ATR_MULTIPLIER_SL": float(os.getenv("ATR_MULTIPLIER_SL", preset["ATR_MULTIPLIER_SL"])),
        "ATR_MULTIPLIER_TP": float(os.getenv("ATR_MULTIPLIER_TP", preset["ATR_MULTIPLIER_TP"])),
        "TRAILING_STOP_ACTIVATE": float(os.getenv("TRAILING_STOP_ACTIVATE", preset["TRAILING_STOP_ACTIVATE"])),
        "TRAILING_STOP_CALLBACK": float(os.getenv("TRAILING_STOP_CALLBACK", preset["TRAILING_STOP_CALLBACK"])),
        "SWING_LOOKBACK": int(os.getenv("SWING_LOOKBACK", preset["SWING_LOOKBACK"])),
        "STRATEGY_MODE": os.getenv("STRATEGY_MODE", preset.get("STRATEGY_MODE", "confluence")).lower(),
        "SL_PERCENT": float(os.getenv("SL_PERCENT", preset.get("SL_PERCENT", 0.02))),
        "TP_PERCENT": float(os.getenv("TP_PERCENT", preset.get("TP_PERCENT", 0.04))),
        "RSI_PERIOD": int(os.getenv("RSI_PERIOD", preset.get("RSI_PERIOD", 14))),
        "RSI_OVERSOLD": float(os.getenv("RSI_OVERSOLD", preset.get("RSI_OVERSOLD", 40.0))),
        "RSI_TIMEFRAME": os.getenv("RSI_TIMEFRAME", preset.get("RSI_TIMEFRAME", "15m")),
        # Bucket size (ms) for the rsi_dip RSI series. Derived from RSI_TIMEFRAME
        # by default; an explicit RSI_TIMEFRAME_MS in .env overrides the map so
        # the variable is genuinely tunable (nonstandard timeframes supported).
        "RSI_TIMEFRAME_MS": int(os.getenv("RSI_TIMEFRAME_MS") or {"1m": 60_000, "3m": 180_000, "5m": 300_000,
                             "15m": 900_000, "30m": 1_800_000, "1h": 3_600_000}.get(
            os.getenv("RSI_TIMEFRAME", preset.get("RSI_TIMEFRAME", "15m")), 900_000)),
        "REGIME_EMA": int(os.getenv("REGIME_EMA", preset.get("REGIME_EMA", 50))),
        "REGIME_SLOPE_DAYS": int(os.getenv("REGIME_SLOPE_DAYS", preset.get("REGIME_SLOPE_DAYS", 3))),
        # Fee-aware breakeven lock (+1% profit -> stop to entry*1.0025). The
        # intraday_rsi edge was proven WITHOUT it (BE exits before the +3% TP),
        # so presets can disable it; an explicit env var always wins.
        "BREAKEVEN_ENABLED": os.getenv("BREAKEVEN_ENABLED",
                                       "true" if preset.get("BREAKEVEN_ENABLED", True) else "false").lower() == "true",
        # intraday_rsi: force-close open positions at the UTC day end (research
        # exits every trade the same day it opens). Explicit env var wins.
        "CLOSE_AT_UTC_DAY_END": os.getenv("CLOSE_AT_UTC_DAY_END",
                                          "true" if preset.get("CLOSE_AT_UTC_DAY_END", False) else "false").lower() == "true",
        "BB_PERIOD": int(os.getenv("BB_PERIOD", 20)),
        "BB_STD_DEV": float(os.getenv("BB_STD_DEV", 2.0)),
        "BB_UPPER_PCT_B": float(os.getenv("BB_UPPER_PCT_B", 0.95)),
        "BB_STRETCH_GATE_ENABLED": os.getenv("BB_STRETCH_GATE_ENABLED", "true").lower() == "true",
        "MAX_SLIPPAGE_PERCENT": float(os.getenv("MAX_SLIPPAGE_PERCENT", 0.5)),
        "MIN_TP_PERCENT": float(os.getenv("MIN_TP_PERCENT", preset.get("MIN_TP_PERCENT", 0.0015))),
        "SIGNAL_THRESHOLD": int(os.getenv("SIGNAL_THRESHOLD", 4)),
        "SIGNAL_INTERVAL": int(os.getenv("SIGNAL_INTERVAL", 10)),
        "ENTRY_TIMEOUT": int(os.getenv("ENTRY_TIMEOUT", 15)),
        "DISCORD_WEBHOOK_URL": os.getenv("DISCORD_WEBHOOK_URL", ""),
        "DISCORD_COOLDOWN": int(os.getenv("DISCORD_COOLDOWN", 30)),
        "LOG_LEVEL": os.getenv("LOG_LEVEL", "INFO"),
        "LOG_FILE": os.getenv("LOG_FILE", "./logs/trading.log"),
        "HEALTH_CHECK_INTERVAL": int(os.getenv("HEALTH_CHECK_INTERVAL", 60)),
        "REST_WEIGHT_LIMIT": int(os.getenv("REST_WEIGHT_LIMIT", 1200)),
        "PAPER_TRADE": os.getenv("PAPER_TRADE", "true").lower() == "true",
        "USE_TESTNET": os.getenv("USE_TESTNET", "false").lower() == "true",
        "AUTO_LIQUIDATE_ORPHANS": os.getenv("AUTO_LIQUIDATE_ORPHANS", "false").lower() == "true",
        "ORPHAN_ADOPT_WINDOW_HOURS": int(os.getenv("ORPHAN_ADOPT_WINDOW_HOURS", "48")),
        "PRESET": preset_name,
    }

    # Validations
    if not config["PAPER_TRADE"] and not config["API_KEY"]:
        raise ValueError("BINANCE_API_KEY is required for live trading.")
    if not isinstance(config["SIGNAL_INTERVAL"], int) or config["SIGNAL_INTERVAL"] < 1:
        raise ValueError("SIGNAL_INTERVAL must be a positive integer (>= 1 second).")
    if not isinstance(config["MAX_SYMBOLS"], int) or config["MAX_SYMBOLS"] < 1:
        raise ValueError("MAX_SYMBOLS must be a positive integer (>= 1).")
    if not isinstance(config["TOP_CANDIDATES"], int) or config["TOP_CANDIDATES"] < 1:
        raise ValueError("TOP_CANDIDATES must be a positive integer (>= 1).")
    if not isinstance(config["SYMBOL_REFRESH_INTERVAL"], int) or config["SYMBOL_REFRESH_INTERVAL"] < 60:
        raise ValueError("SYMBOL_REFRESH_INTERVAL must be at least 60 seconds.")
    if not isinstance(config["ENTRY_TIMEOUT"], int) or config["ENTRY_TIMEOUT"] < 5:
        raise ValueError("ENTRY_TIMEOUT must be at least 5 seconds.")
    if not isinstance(config["HEALTH_CHECK_INTERVAL"], int) or config["HEALTH_CHECK_INTERVAL"] < 5:
        raise ValueError("HEALTH_CHECK_INTERVAL must be at least 5 seconds.")
    if not isinstance(config["REST_WEIGHT_LIMIT"], int) or config["REST_WEIGHT_LIMIT"] < 1:
        raise ValueError("REST_WEIGHT_LIMIT must be a positive integer.")
    if not isinstance(config["DISCORD_COOLDOWN"], int) or config["DISCORD_COOLDOWN"] < 0:
        raise ValueError("DISCORD_COOLDOWN must be a non-negative integer.")
    if not isinstance(config["LOG_LEVEL"], str) or config["LOG_LEVEL"].upper() not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ValueError("LOG_LEVEL must be one of DEBUG/INFO/WARNING/ERROR/CRITICAL.")
    if not isinstance(config["MAX_SLIPPAGE_PERCENT"], (int, float)) or not (0 < config["MAX_SLIPPAGE_PERCENT"] <= 10.0):
        raise ValueError("MAX_SLIPPAGE_PERCENT must be between 0 (exclusive) and 10.0 (percent).")
    if not isinstance(config["MIN_TP_PERCENT"], (int, float)) or config["MIN_TP_PERCENT"] < 0:
        raise ValueError("MIN_TP_PERCENT must be non-negative.")
    if not isinstance(config["BALANCE_USAGE_PERCENT"], (int, float)) or not (0 < config["BALANCE_USAGE_PERCENT"] <= 1):
        raise ValueError("BALANCE_USAGE_PERCENT must be between 0 (exclusive) and 1.")
    if not isinstance(config["MAX_SYMBOL_ALLOCATION_PERCENT"], (int, float)) or not (0 < config["MAX_SYMBOL_ALLOCATION_PERCENT"] <= 1):
        raise ValueError("MAX_SYMBOL_ALLOCATION_PERCENT must be between 0 (exclusive) and 1.")
    if not isinstance(config["MAX_DAILY_DRAWDOWN"], (int, float)) or not (0 < config["MAX_DAILY_DRAWDOWN"] <= 1):
        raise ValueError("MAX_DAILY_DRAWDOWN must be between 0 (exclusive) and 1.")
    if not isinstance(config["SIGNAL_THRESHOLD"], int) or not (1 <= config["SIGNAL_THRESHOLD"] <= 5):
        raise ValueError("SIGNAL_THRESHOLD must be an integer between 1 and 5.")
    if not isinstance(config["MAX_LOSS_STREAK"], int) or config["MAX_LOSS_STREAK"] < 1:
        raise ValueError("MAX_LOSS_STREAK must be a positive integer.")
    if not isinstance(config["MAX_WIN_STREAK"], int) or config["MAX_WIN_STREAK"] < 1:
        raise ValueError("MAX_WIN_STREAK must be a positive integer.")
    if not isinstance(config["COOLDOWN_LOSS"], int) or config["COOLDOWN_LOSS"] < 0:
        raise ValueError("COOLDOWN_LOSS must be a non-negative integer.")
    if not isinstance(config["COOLDOWN_WIN"], int) or config["COOLDOWN_WIN"] < 0:
        raise ValueError("COOLDOWN_WIN must be a non-negative integer.")
    if not isinstance(config["MAX_TRADES_PER_DAY"], int) or config["MAX_TRADES_PER_DAY"] < 0:
        raise ValueError("MAX_TRADES_PER_DAY must be a non-negative integer (0 = unlimited).")
    if not isinstance(config["ADX_THRESHOLD"], (int, float)) or not (0 <= config["ADX_THRESHOLD"] <= 100):
        raise ValueError("ADX_THRESHOLD must be between 0 and 100.")
    if not isinstance(config["ADX_PERIOD"], int) or config["ADX_PERIOD"] < 1:
        raise ValueError("ADX_PERIOD must be a positive integer.")
    if not isinstance(config["TREND_LOOKBACK"], int) or config["TREND_LOOKBACK"] < 1:
        raise ValueError("TREND_LOOKBACK must be a positive integer.")
    if not isinstance(config["Z_SCORE_WEIGHT_VOLUME"], (int, float)) or not (0 <= config["Z_SCORE_WEIGHT_VOLUME"] <= 1):
        raise ValueError("Z_SCORE_WEIGHT_VOLUME must be between 0 and 1.")
    if not isinstance(config["Z_SCORE_WEIGHT_CHANGE"], (int, float)) or not (0 <= config["Z_SCORE_WEIGHT_CHANGE"] <= 1):
        raise ValueError("Z_SCORE_WEIGHT_CHANGE must be between 0 and 1.")
    if not isinstance(config["Z_SCORE_WEIGHT_VOLATILITY"], (int, float)) or not (0 <= config["Z_SCORE_WEIGHT_VOLATILITY"] <= 1):
        raise ValueError("Z_SCORE_WEIGHT_VOLATILITY must be between 0 and 1.")
    if not isinstance(config["Z_SCORE_WEIGHT_ADX"], (int, float)) or not (0 <= config["Z_SCORE_WEIGHT_ADX"] <= 1):
        raise ValueError("Z_SCORE_WEIGHT_ADX must be between 0 and 1.")
    if not isinstance(config["CORRELATION_THRESHOLD"], (int, float)) or not (0 <= config["CORRELATION_THRESHOLD"] <= 1):
        raise ValueError("CORRELATION_THRESHOLD must be between 0 and 1.")
    if not isinstance(config["CORRELATION_PENALTY"], (int, float)) or not (0 < config["CORRELATION_PENALTY"] <= 1):
        raise ValueError("CORRELATION_PENALTY must be between 0 (exclusive) and 1.")
    if not isinstance(config["MIN_VOLUME_USDT"], (int, float)) or config["MIN_VOLUME_USDT"] < 0:
        raise ValueError("MIN_VOLUME_USDT must be non-negative.")
    if not isinstance(config["MIN_PRICE_CHANGE_PERCENT"], (int, float)) or config["MIN_PRICE_CHANGE_PERCENT"] < 0:
        raise ValueError("MIN_PRICE_CHANGE_PERCENT must be non-negative.")
    if not isinstance(config["MIN_VOLATILITY_PERCENT"], (int, float)) or config["MIN_VOLATILITY_PERCENT"] < 0:
        raise ValueError("MIN_VOLATILITY_PERCENT must be non-negative.")
    if not isinstance(config["ATR_PERIOD"], int) or config["ATR_PERIOD"] < 1:
        raise ValueError("ATR_PERIOD must be a positive integer.")
    if not isinstance(config["ATR_MULTIPLIER_SL"], (int, float)) or config["ATR_MULTIPLIER_SL"] <= 0:
        raise ValueError("ATR_MULTIPLIER_SL must be positive.")
    if not isinstance(config["ATR_MULTIPLIER_TP"], (int, float)) or config["ATR_MULTIPLIER_TP"] <= config["ATR_MULTIPLIER_SL"]:
        raise ValueError("ATR_MULTIPLIER_TP must be greater than ATR_MULTIPLIER_SL.")
    if config["STRATEGY_MODE"] == "rsi_dip":
        if not (0 < config["SL_PERCENT"] < config["TP_PERCENT"] <= 1):
            raise ValueError("SL_PERCENT/TP_PERCENT: need 0 < SL_PERCENT < TP_PERCENT <= 1.")
        if not isinstance(config["RSI_PERIOD"], int) or config["RSI_PERIOD"] < 2:
            raise ValueError("RSI_PERIOD must be an integer >= 2.")
        if not (0 < config["RSI_OVERSOLD"] < 100):
            raise ValueError("RSI_OVERSOLD must be between 0 and 100 (exclusive).")
        if not isinstance(config["REGIME_EMA"], int) or config["REGIME_EMA"] < 2:
            raise ValueError("REGIME_EMA must be an integer >= 2.")
        if not isinstance(config["REGIME_SLOPE_DAYS"], int) or config["REGIME_SLOPE_DAYS"] < 1:
            raise ValueError("REGIME_SLOPE_DAYS must be a positive integer.")
    if not isinstance(config["TRAILING_STOP_ACTIVATE"], (int, float)) or not (0 < config["TRAILING_STOP_ACTIVATE"] <= 1):
        raise ValueError("TRAILING_STOP_ACTIVATE must be between 0 (exclusive) and 1.")
    if not isinstance(config["TRAILING_STOP_CALLBACK"], (int, float)) or not (0 <= config["TRAILING_STOP_CALLBACK"] < config["TRAILING_STOP_ACTIVATE"]):
        raise ValueError("TRAILING_STOP_CALLBACK must be non-negative and less than TRAILING_STOP_ACTIVATE.")
    if not isinstance(config["SWING_LOOKBACK"], int) or config["SWING_LOOKBACK"] < 2:
        raise ValueError("SWING_LOOKBACK must be at least 2.")
    if not isinstance(config["BB_PERIOD"], int) or config["BB_PERIOD"] < 2:
        raise ValueError("BB_PERIOD must be a positive integer >= 2.")
    if not isinstance(config["BB_STD_DEV"], (int, float)) or config["BB_STD_DEV"] <= 0:
        raise ValueError("BB_STD_DEV must be positive.")
    if not isinstance(config["BB_UPPER_PCT_B"], (int, float)) or not (0 < config["BB_UPPER_PCT_B"] <= 1.5):
        raise ValueError("BB_UPPER_PCT_B must be between 0 (exclusive) and 1.5 (values > 1 allow overbought entries; not recommended).")
    if not isinstance(config["MAX_HOLD_TIME"], int) or config["MAX_HOLD_TIME"] < 60:
        raise ValueError("MAX_HOLD_TIME must be at least 60 seconds.")
    if not isinstance(config["RISK_PER_TRADE"], (int, float)) or not (0 < config["RISK_PER_TRADE"] <= 0.1):
        raise ValueError("RISK_PER_TRADE must be between 0 (exclusive) and 0.1 (10% of equity per trade — do not go higher).")
    if not isinstance(config["MIN_RISK_REWARD"], (int, float)) or config["MIN_RISK_REWARD"] < 1.0:
        raise ValueError("MIN_RISK_REWARD must be at least 1.0 (TP distance vs SL distance).")
    if not (0 < config["SCALE_OUT_FRACTION"] < 1):
        raise ValueError("SCALE_OUT_FRACTION must be between 0 (exclusive) and 1 (exclusive).")
    if config["SCALE_OUT_R_MULTIPLE"] <= 0:
        raise ValueError("SCALE_OUT_R_MULTIPLE must be positive (1.0 = take profit at 1x the stop distance).")
    if config["SCALE_OUT_R_MULTIPLE"] >= config["ATR_MULTIPLIER_TP"] / config["ATR_MULTIPLIER_SL"]:
        raise ValueError("SCALE_OUT_R_MULTIPLE must be below the preset's full R:R (TP/SL multiple) so the runner leg still has room.")
    if not config["STATIC_SYMBOLS"] and not config["DYNAMIC_SYMBOLS"]:
        raise ValueError("At least one symbol must be provided.")
    if not config["PAPER_TRADE"]:
        has_pem = private_key_path and private_key_path.exists()
        has_secret = bool(config.get("API_SECRET"))
        if not has_pem and not has_secret:
            raise ValueError(
                f"Live trading requires either BINANCE_API_SECRET (for standard HMAC-SHA256) "
                f"or BINANCE_PRIVATE_KEY_PATH (for Ed25519; file not found at {private_key_path})."
            )
    if config["PAPER_TRADE"]:
        # Even in paper mode, validate that any non-default paths point at plausible files
        # so a mis-typed DB_PATH or LOG_FILE is caught early rather than mid-run.
        if config.get("DB_PATH") and not config["DB_PATH"].endswith(".db"):
            raise ValueError("DB_PATH should end with .db (e.g. ./data/trading.db).")
        if config.get("LOG_FILE") and not config["LOG_FILE"].endswith(".log"):
            raise ValueError("LOG_FILE should end with .log (e.g. ./logs/trading.log).")
        if config.get("CONTROL_FILE") and not config["CONTROL_FILE"].endswith(".json"):
            raise ValueError("CONTROL_FILE should end with .json (e.g. ./data/engine_control.json).")

    return config
