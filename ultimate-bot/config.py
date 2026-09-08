import os
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
        "PAPER_TRADE": os.getenv("PAPER_TRADE", "true").lower() == "true",
        "USE_TESTNET": os.getenv("USE_TESTNET", "false").lower() == "true",
        "AUTO_LIQUIDATE_ORPHANS": os.getenv("AUTO_LIQUIDATE_ORPHANS", "false").lower() == "true",
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
    if not isinstance(config["TRAILING_STOP_ACTIVATE"], (int, float)) or not (0 < config["TRAILING_STOP_ACTIVATE"] <= 1):
        raise ValueError("TRAILING_STOP_ACTIVATE must be between 0 (exclusive) and 1.")
    if not isinstance(config["TRAILING_STOP_CALLBACK"], (int, float)) or not (0 <= config["TRAILING_STOP_CALLBACK"] < config["TRAILING_STOP_ACTIVATE"]):
        raise ValueError("TRAILING_STOP_CALLBACK must be non-negative and less than TRAILING_STOP_ACTIVATE.")
    if not isinstance(config["SWING_LOOKBACK"], int) or config["SWING_LOOKBACK"] < 2:
        raise ValueError("SWING_LOOKBACK must be at least 2.")
    if not isinstance(config["MAX_HOLD_TIME"], int) or config["MAX_HOLD_TIME"] < 60:
        raise ValueError("MAX_HOLD_TIME must be at least 60 seconds.")
    if not config["STATIC_SYMBOLS"] and not config["DYNAMIC_SYMBOLS"]:
        raise ValueError("At least one symbol must be provided.")
    if not (0 < config["BALANCE_USAGE_PERCENT"] <= 1):
        raise ValueError("BALANCE_USAGE_PERCENT must be between 0 and 1.")
    if not (0 < config["MAX_DAILY_DRAWDOWN"] <= 1):
        raise ValueError("MAX_DAILY_DRAWDOWN must be between 0 and 1.")
    if config["ATR_PERIOD"] <= 0:
        raise ValueError("ATR_PERIOD must be positive.")
    if config["ATR_MULTIPLIER_TP"] <= config["ATR_MULTIPLIER_SL"]:
        raise ValueError("ATR_MULTIPLIER_TP must be greater than ATR_MULTIPLIER_SL.")
    if config["TRAILING_STOP_CALLBACK"] >= config["TRAILING_STOP_ACTIVATE"]:
        raise ValueError("TRAILING_STOP_CALLBACK must be less than TRAILING_STOP_ACTIVATE.")
    if config["MIN_TP_PERCENT"] < 0:
        raise ValueError("MIN_TP_PERCENT must be non-negative.")
    if not (0 < config["MAX_SYMBOL_ALLOCATION_PERCENT"] <= 1):
        raise ValueError("MAX_SYMBOL_ALLOCATION_PERCENT must be between 0 and 1.")
    if not (1 <= config["SIGNAL_THRESHOLD"] <= 5):
        raise ValueError("SIGNAL_THRESHOLD must be between 1 and 5.")
    if config["SIGNAL_INTERVAL"] < 1:
        raise ValueError("SIGNAL_INTERVAL must be at least 1 second.")
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
