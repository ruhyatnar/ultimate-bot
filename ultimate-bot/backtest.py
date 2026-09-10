#!/usr/bin/env python3
"""Backtest engine for the Ultimate Binance Bot strategy.

Proves (or disproves) the strategy's expectancy on REAL historical Binance
klines by replaying closed bars through the LIVE engine's own decision core
(SignalGenerator.decide) — the exact code the engine trades with, so there is
zero drift between what is backtested and what trades real money.

Trade management mirrors trade_logic.py:
  - SL = entry − ATR×ATR_MULTIPLIER_SL, TP = entry + max(ATR×ATR_MULTIPLIER_TP, MIN_TP_PERCENT)
  - R:R gate: TP widened to MIN_RISK_REWARD × stop distance (reject if impossible)
  - Bollinger stretch gate + HTF regime gate (inside SignalGenerator.decide)
  - Trailing stop: activates at TRAILING_STOP_ACTIVATE, trails by TRAILING_STOP_CALLBACK
  - Breakeven lock at +1% (entry × 1.0025, fees covered) — same 0.0025 multiplier
  - Scale-out at +1R (measured against the INITIAL stop) for SCALE_OUT_FRACTION
  - Taker fees both legs (0.1% × 2) netted from every trade's PnL
  - 1R fixed-fractional position sizing (RISK_PER_TRADE of current equity)
  - Daily drawdown circuit breaker (MAX_DAILY_DRAWDOWN) — same rule as live

Usage:
  ./venv/bin/python3 backtest.py                        # BTCUSDT day preset, 3×500 5m bars
  ./venv/bin/python3 backtest.py --symbol ETHUSDT --preset swing
  ./venv/bin/python3 backtest.py --pages 10 --days 30   # more history (10 × 1000 bars)

Exit code 0 = backtest ran (regardless of profitability), 2 = could not run.
"""
import argparse
import asyncio
import json
import sys
import time
import urllib.request
from datetime import datetime, timezone

import numpy as np
import pandas as pd

sys.path.insert(0, __file__.rsplit("/", 1)[0])

from config import load_config, PRESETS  # noqa: E402
from src.strategies.signal_generator import SignalGenerator  # noqa: E402

BASE_URL = "https://api.binance.com"
TAKER_FEE = 0.001            # 0.1% per leg, matching the engine's fee model
MAKER_FEE = 0.0002           # 0.02% Binance spot maker fee (OCO TP limit leg)
BE_MULTIPLIER = 1.0025       # breakeven lock: entry × 1.0025 (matches trade_logic.py)


def fetch_klines(symbol, interval, limit, end_time=None):
    query = f"symbol={symbol}&interval={interval}&limit={min(limit, 1000)}"
    if end_time:
        query += f"&endTime={int(end_time)}"
    url = f"{BASE_URL}/api/v3/klines?{query}"
    req = urllib.request.Request(url, headers={"User-Agent": "BacktestEngine/1.0"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        return json.loads(resp.read().decode("utf-8"))


_KLINE_CACHE = {}   # (symbol, interval, pages, end_time) -> rows; repeated sweeps skip refetching

def fetch_history(symbol, interval, pages, end_time=None):
    """Walk backwards `pages` requests of up to 1000 bars each (cached per process)."""
    key = (symbol, interval, pages, end_time)
    if key in _KLINE_CACHE:
        return _KLINE_CACHE[key]
    all_rows = []
    cursor = end_time
    for _ in range(pages):
        rows = fetch_klines(symbol, interval, 1000, end_time=cursor)
        if not rows:
            break
        all_rows = rows + all_rows
        cursor = rows[0][0] - 1
        if len(rows) < 1000:
            break
    _KLINE_CACHE[key] = all_rows
    return all_rows


def to_df(rows):
    import pandas as pd
    df = pd.DataFrame(rows, columns=["open_time", "open", "high", "low", "close", "volume",
                                     "close_time", "quote_volume", "trades", "taker_buy_base",
                                     "taker_buy_quote", "ignore"])
    for col in ["open", "high", "low", "close", "volume", "quote_volume", "taker_buy_quote"]:
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0.0)
    df["open_time"] = pd.to_numeric(df["open_time"], errors="coerce")
    return df


def _compute_adx(df, period=14):
    """ADX(period) over the window (Wilder smoothing). Returns the last value or None."""
    try:
        high, low, close = df["high"], df["low"], df["close"]
        if len(df) < period * 2 + 2:
            return None
        up = high.diff()
        down = -low.diff()
        plus_dm = pd.Series(np.where((up > down) & (up > 0), up, 0.0), index=df.index)
        minus_dm = pd.Series(np.where((down > up) & (down > 0), down, 0.0), index=df.index)
        tr = pd.concat([high - low, (high - close.shift()).abs(), (low - close.shift()).abs()], axis=1).max(axis=1)
        # Wilder smoothing = EMA with alpha = 1/period
        atr_s = tr.ewm(alpha=1.0 / period, adjust=False).mean()
        plus_di = 100 * plus_dm.ewm(alpha=1.0 / period, adjust=False).mean() / atr_s
        minus_di = 100 * minus_dm.ewm(alpha=1.0 / period, adjust=False).mean() / atr_s
        denom = (plus_di + minus_di).replace(0.0, np.nan)
        dx = 100 * (plus_di - minus_di).abs() / denom
        adx = dx.ewm(alpha=1.0 / period, adjust=False).mean()
        val = float(adx.iloc[-1])
        return val if np.isfinite(val) else None
    except Exception:
        return None


def run_backtest(symbol, preset_name, pages, end_time=None, quiet=False, disable_bb=False,
                 threshold=None, sl_mult=None, tp_mult=None, scale_frac=None, bb_pctb=None,
                 cooldown_bars=None, min_tp=None, bb_lower=None, adx_min=None,
                 vol_mult=None, be_r=None, trail_r=None, max_hold=None, maker_tp=False):
    cfg = load_config()
    cfg["TIMEFRAME"] = PRESETS[preset_name]["TIMEFRAME"]
    cfg["MTF_TIMEFRAME"] = PRESETS[preset_name]["MTF_TIMEFRAME"]
    cfg["ATR_PERIOD"] = PRESETS[preset_name]["ATR_PERIOD"]
    cfg["ATR_MULTIPLIER_SL"] = PRESETS[preset_name]["ATR_MULTIPLIER_SL"]
    cfg["ATR_MULTIPLIER_TP"] = PRESETS[preset_name]["ATR_MULTIPLIER_TP"]
    cfg["TRAILING_STOP_ACTIVATE"] = PRESETS[preset_name]["TRAILING_STOP_ACTIVATE"]
    cfg["TRAILING_STOP_CALLBACK"] = PRESETS[preset_name]["TRAILING_STOP_CALLBACK"]
    cfg["SWING_LOOKBACK"] = PRESETS[preset_name]["SWING_LOOKBACK"]
    cfg["MAX_HOLD_TIME"] = PRESETS[preset_name]["MAX_HOLD_TIME"]
    cfg["MIN_TP_PERCENT"] = PRESETS[preset_name].get("MIN_TP_PERCENT", cfg["MIN_TP_PERCENT"])
    # Strategy-research overrides — applied AFTER the preset block so they win
    # (None = keep the preset/env value; used by sweeps and CLI flags).
    if disable_bb:
        cfg["BB_STRETCH_GATE_ENABLED"] = False   # A/B: measure the gate's value
    if threshold is not None: cfg["SIGNAL_THRESHOLD"] = int(threshold)
    if sl_mult is not None: cfg["ATR_MULTIPLIER_SL"] = float(sl_mult)
    if tp_mult is not None: cfg["ATR_MULTIPLIER_TP"] = float(tp_mult)
    if scale_frac is not None: cfg["SCALE_OUT_FRACTION"] = float(scale_frac)
    if bb_pctb is not None: cfg["BB_UPPER_PCT_B"] = float(bb_pctb)
    if min_tp is not None: cfg["MIN_TP_PERCENT"] = float(min_tp)
    if bb_lower is not None: cfg["BB_LOWER_PCT_B"] = float(bb_lower)   # research: falling-knife gate
    if adx_min is not None: cfg["LTF_ADX_MIN"] = float(adx_min)         # research: execution-TF regime gate
    if vol_mult is not None: cfg["SIGNAL_VOL_MULT"] = float(vol_mult)   # research: signal-bar volume confirmation
    if be_r is not None: cfg["BE_TRIGGER_R"] = float(be_r)             # research: R-based breakeven trigger
    if trail_r is not None: cfg["TRAIL_ACTIVATE_R"] = float(trail_r)   # research: R-based trailing trigger
    if max_hold is not None: cfg["MAX_HOLD_TIME"] = float(max_hold)    # research: time-stop override (seconds)
    cfg["MAKER_TP"] = bool(maker_tp)                                   # research: TP leg pays maker (0.02%) not taker

    import logging
    logging.disable(logging.CRITICAL)
    sg = SignalGenerator(cfg, rest=None)

    tf_ms = {"1m": 60_000, "3m": 180_000, "5m": 300_000, "15m": 900_000,
             "1h": 3_600_000, "4h": 14_400_000}.get(cfg["TIMEFRAME"], 300_000)
    # Mirror the live engine: default post-exit cooldown derives from COOLDOWN_LOSS.
    if cooldown_bars is None:
        cooldown_bars = max(0, int(round(cfg["COOLDOWN_LOSS"] * 1000 / tf_ms)))
    htf_ms = {"1m": 60_000, "3m": 180_000, "5m": 300_000, "15m": 900_000,
              "1h": 3_600_000, "4h": 14_400_000}.get(cfg["MTF_TIMEFRAME"], 3_600_000)
    warmup_bars = max(1, htf_ms // tf_ms)
    ltf_bars = 100
    lookback_total = warmup_bars + ltf_bars

    rows = fetch_history(symbol, cfg["TIMEFRAME"], pages, end_time=end_time)
    if len(rows) < lookback_total + 10:
        print(f"NOT ENOUGH DATA: got {len(rows)} bars, need > {lookback_total + 10} "
              f"(HTF window of {warmup_bars} bars + 100-bar LTF window + trades)")
        return None

    df = to_df(rows)
    closes = df["close"].tolist()
    highs = df["high"].tolist()
    lows = df["low"].tolist()
    opens = df["open"].tolist()
    times = df["open_time"].tolist()
    volumes = df["volume"].tolist()
    n = len(df)

    equity = 1000.0
    start_equity = equity
    risk_per_trade = float(cfg.get("RISK_PER_TRADE", 0.01))
    max_daily_dd = float(cfg.get("MAX_DAILY_DRAWDOWN", 0.05))
    threshold = int(cfg["SIGNAL_THRESHOLD"])
    scale_enabled = bool(cfg.get("SCALE_OUT_ENABLED", True))
    scale_r = float(cfg.get("SCALE_OUT_R_MULTIPLE", 1.0))
    scale_frac = float(cfg.get("SCALE_OUT_FRACTION", 0.5))
    min_rr = float(cfg.get("MIN_RISK_REWARD", 1.5))
    min_tp_pct = float(cfg.get("MIN_TP_PERCENT", 0.005))
    max_hold_s = float(cfg["MAX_HOLD_TIME"])   # config unit: SECONDS (matches engine)
    # Notional allocation caps — mirrors RiskManager.calculate_position_size,
    # which takes min(risk-based size, allocation cap). Skipping the cap lets
    # notional explode on tight stops and wildly overstates fee drag.
    alloc_cap_frac = min(float(cfg.get("BALANCE_USAGE_PERCENT", 0.5)),
                         float(cfg.get("MAX_SYMBOL_ALLOCATION_PERCENT", 0.2)))

    position = None
    trades = []          # realized trade records (scale-out legs merged per entry)
    equity_curve = []
    day_key = None
    day_start_equity = equity
    day_blocked = False
    last_exit_i = -10 ** 9   # post-stop cooldown anchor (bars since last exit)

    def record(i, reason, fill_price, qty, entry_price, initial_stop, entry_fees_paid):
        gross = (fill_price - entry_price) * qty
        # OCO take-profit is a LIMIT leg: with --maker-tp it pays the maker rate
        # (0.02% vs 0.1% taker) — models placing the TP as a resting order.
        exit_rate = MAKER_FEE if (reason == "TAKE_PROFIT" and cfg.get("MAKER_TP")) else TAKER_FEE
        fees = entry_fees_paid + fill_price * qty * exit_rate
        return {"entry_time": None, "exit_index": i, "reason": reason,
                "entry_price": entry_price, "exit_price": fill_price, "qty": qty,
                "gross": gross, "fees": fees, "pnl": gross - fees,
                "r": (fill_price - entry_price) / (entry_price - initial_stop)
                     if (entry_price - initial_stop) > 0 else 0.0}

    for i in range(lookback_total, n):
        # ---- daily drawdown circuit breaker (resets each UTC day) ----
        d = datetime.fromtimestamp(times[i] / 1000, tz=timezone.utc).date()
        if d != day_key:
            day_key = d
            day_start_equity = equity
            day_blocked = False
        if day_blocked:
            equity_curve.append(equity)
            continue
        if day_start_equity > 0 and equity - day_start_equity <= -max_daily_dd * day_start_equity:
            day_blocked = True
            equity_curve.append(equity)
            continue

        # ---- manage open position on this bar (SL/TP/trail/BE/scale-out) ----
        if position is not None:
            p = position
            bar_high, bar_low, bar_close, bar_open = highs[i], lows[i], closes[i], opens[i]
            # Conservative intrabar sequence: if both stops are inside the bar,
            # assume the STOP hit first (adverse assumption).
            entry, stop, tp = p["entry"], p["stop"], p["tp"]
            # 1) trailing-stop / stop-loss (gap-aware: gap below stop fills at open)
            stop_level = max(stop, p.get("trailing_stop") or 0)
            stop_level = max(stop_level, entry * BE_MULTIPLIER) if p.get("be") else stop_level
            if stop_level > 0 and bar_low <= stop_level:
                fill = bar_open if bar_open < stop_level else stop_level
                leg = record(i, "TRAIL_STOP" if p.get("trailing_stop") and p["trailing_stop"] >= stop else "STOP_LOSS",
                             fill, p["qty"], entry, p["initial_stop"], p["entry_fee"])
                equity += leg["pnl"]
                merged = p.setdefault("legs", [])
                merged.append(leg)
                trades.append(_merge_legs(p, merged))
                position = None
                last_exit_i = i
            else:
                # 2) take-profit (limit-style fill at TP)
                if bar_high >= tp:
                    leg = record(i, "TAKE_PROFIT", tp, p["qty"], entry, p["initial_stop"], p["entry_fee"])
                    equity += leg["pnl"]
                    p.setdefault("legs", []).append(leg)
                    trades.append(_merge_legs(p, p["legs"]))
                    position = None
                    last_exit_i = i
                else:
                    # 3) scale-out at +1R vs the INITIAL stop
                    if scale_enabled and not p.get("scaled") and p["initial_stop"] < entry:
                        r_mult = (bar_high - entry) / (entry - p["initial_stop"])
                        if r_mult >= scale_r:
                            scale_qty = round(p["qty"] * scale_frac, 12)
                            runner_qty = p["qty"] - scale_qty
                            notional = runner_qty * bar_high
                            if scale_qty > 0 and notional >= 5.0:
                                # Live engine market-sells the moment +1R is touched
                                # intrabar, so the fill is the trigger price itself
                                # (capped by the bar's actual high).
                                fill = min(bar_high, entry + (entry - p["initial_stop"]) * scale_r)
                                leg = record(i, "SCALE_OUT", fill, scale_qty, entry, p["initial_stop"], p["entry_fee"])
                                equity += leg["pnl"]
                                p.setdefault("legs", []).append(leg)
                                p["qty"] = runner_qty
                                p["entry_fee"] = p["entry_fee"] * (runner_qty / (runner_qty + scale_qty))
                                p["scaled"] = True
                                # runner becomes risk-free immediately (matches live engine)
                                p["be"] = True
                                p["stop"] = max(p["stop"], entry * BE_MULTIPLIER)
                            else:
                                p["scaled"] = True   # too small to split; manage as one unit
                    # 4) trailing stop update + breakeven lock.
                    #    Default = live engine's %-based triggers. Research flags
                    #    (--be-r / --trail-r) switch triggers to R-multiples of
                    #    the initial stop so the mechanisms are reachable when
                    #    TP sits inside the fixed % thresholds.
                    profit_pct = (bar_close - entry) / entry
                    sl_dist0 = entry - p["initial_stop"]
                    be_r = cfg.get("BE_TRIGGER_R")
                    trail_r = cfg.get("TRAIL_ACTIVATE_R")
                    if sl_dist0 > 0:
                        be_thr = float(be_r) * sl_dist0 / entry if be_r is not None else 0.01
                        trail_thr = float(trail_r) * sl_dist0 / entry if trail_r is not None else float(cfg["TRAILING_STOP_ACTIVATE"])
                    else:
                        be_thr = trail_thr = float("inf")
                    if not p.get("be") and profit_pct >= be_thr:
                        p["be"] = True
                        p["stop"] = max(p["stop"], entry * BE_MULTIPLIER)
                    if not p.get("trailing_active") and profit_pct >= trail_thr:
                        p["trailing_active"] = True
                        p["trailing_stop"] = max(p.get("trailing_stop") or 0, p["stop"])
                    if p.get("trailing_active"):
                        p["trailing_stop"] = max(p.get("trailing_stop") or 0,
                                                 bar_close * (1 - float(cfg["TRAILING_STOP_CALLBACK"])))
                    # 5) time stop
                    entry_ms = p.get("entry_ms") or times[p["entry_index"]]
                    if (times[i] - entry_ms) / 1000.0 > max_hold_s:
                        leg = record(i, "TIME_STOP", bar_close, p["qty"], entry, p["initial_stop"], p["entry_fee"])
                        equity += leg["pnl"]
                        trades.append(_merge_legs(p, p.setdefault("legs", []) + [leg]))
                        position = None
                        last_exit_i = i
            equity_curve.append(equity)
            if position is None:
                continue
            # position still open → no new entry this bar
            equity_curve[-1] = equity
            continue

        # ---- look for a new entry (uses the LIVE engine's decide()) ----
        if i - last_exit_i < cooldown_bars:
            equity_curve.append(equity)
            continue
        htf_start = i - warmup_bars - ltf_bars + 1
        htf_win = df.iloc[htf_start: i + 1]
        if len(htf_win) < ltf_bars:
            equity_curve.append(equity)
            continue
        ltf_win = df.iloc[i - ltf_bars + 1: i + 1]
        # The last bar of ltf_win is the just-closed signal bar (index i).
        signal, atr = sg.decide(htf_win, ltf_win, symbol=symbol)
        if signal != "BUY" or not atr or atr <= 0:
            equity_curve.append(equity)
            continue
        # Research gate (off unless --bb-lower given): skip entries at/below the
        # Bollinger lower band — momentum entries in a falling knife tend to
        # fill at local extremes and stop out before any reversal confirms.
        bb_lower_val = cfg.get("BB_LOWER_PCT_B")
        if bb_lower_val is not None:
            pct_b = sg._calculate_bollinger_pct_b(ltf_win)
            if pct_b <= float(bb_lower_val):
                equity_curve.append(equity)
                continue
        # Research gate (off unless --adx-min given): only trade when the
        # EXECUTION timeframe is actually trending. The 5 factors are local
        # structure/momentum reads that can align inside a 5m chop range;
        # ADX(14) on the LTF window distinguishes trend from range.
        adx_min_val = cfg.get("LTF_ADX_MIN")
        if adx_min_val is not None:
            adx = _compute_adx(ltf_win)
            if adx is None or adx < float(adx_min_val):
                equity_curve.append(equity)
                continue
        # Research gate (off unless --vol-mult given): require the signal bar to
        # carry above-average participation — breakouts on dead tape rarely
        # follow through before the stop is tested.
        vol_mult_val = cfg.get("SIGNAL_VOL_MULT")
        if vol_mult_val is not None:
            v_start = max(0, i - 20)
            v_mean = sum(volumes[v_start:i]) / max(1, i - v_start)
            if v_mean <= 0 or volumes[i] < float(vol_mult_val) * v_mean:
                equity_curve.append(equity)
                continue

        entry = bar_close = closes[i]
        stop = entry - atr * float(cfg["ATR_MULTIPLIER_SL"])
        tp = entry + atr * float(cfg["ATR_MULTIPLIER_TP"])
        if tp - entry < entry * min_tp_pct:
            tp = entry + entry * min_tp_pct
        sl_dist = entry - stop
        if sl_dist <= 0:
            equity_curve.append(equity)
            continue
        if (tp - entry) / sl_dist < min_rr:
            tp = entry + sl_dist * min_rr
        qty_risk = (equity * risk_per_trade) / sl_dist
        qty_cap = (equity * alloc_cap_frac) / entry
        qty = min(qty_risk, qty_cap)   # engine rule: never size above the cap
        position = {
            "entry": entry, "stop": stop, "tp": tp, "qty": qty,
            "initial_stop": stop, "entry_fee": entry * qty * TAKER_FEE,
            "entry_index": i, "entry_ms": times[i],
            "legs": [], "scaled": False, "be": False,
            "trailing_active": False, "trailing_stop": 0.0,
        }
        equity_curve.append(equity)

    # ---- force-close any open position at the last close ----
    if position is not None:
        i = n - 1
        leg = record(i, "END_OF_DATA", closes[i], position["qty"], position["entry"],
                     position["initial_stop"], position["entry_fee"])
        equity += leg["pnl"]
        trades.append(_merge_legs(position, position.setdefault("legs", []) + [leg]))
        equity_curve.append(equity)

    return _summarize(symbol, preset_name, cfg, start_equity, equity, trades,
                      equity_curve, len(rows), quiet)


def _merge_legs(position, legs):
    """Merge scale-out legs into one trade record for honest per-entry stats."""
    pnl = sum(leg["pnl"] for leg in legs)
    fees = sum(leg["fees"] for leg in legs)
    gross = sum(leg["gross"] for leg in legs)
    reasons = "/".join(dict.fromkeys(leg["reason"] for leg in legs))
    qty = sum(leg["qty"] for leg in legs)
    first, last = legs[0], legs[-1]
    return {
        "entry_price": first["entry_price"], "exit_price": last["exit_price"],
        "qty": qty, "gross": gross, "fees": fees, "pnl": pnl,
        "reason": reasons, "r": last["r"], "exit_index": last["exit_index"],
        "entry_index": position["entry_index"], "entry_ms": position["entry_ms"],
    }


def _summarize(symbol, preset_name, cfg, start_equity, equity, trades, curve, n_bars, quiet):
    total = len(trades)
    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] <= 0]
    gross_win = sum(t["pnl"] for t in wins)
    gross_loss = abs(sum(t["pnl"] for t in losses))
    total_fees = sum(t["fees"] for t in trades)
    win_rate = len(wins) / total * 100 if total else 0.0
    pf = (gross_win / gross_loss) if gross_loss > 0 else float("inf") if gross_win > 0 else 0.0
    expectancy = (sum(t["pnl"] for t in trades) / total) if total else 0.0
    avg_r = (sum(t["r"] for t in trades) / total) if total else 0.0
    peak, max_dd = start_equity, 0.0
    for v in curve:
        peak = max(peak, v)
        max_dd = max(max_dd, (peak - v) / peak * 100 if peak > 0 else 0)
    ret_pct = (equity - start_equity) / start_equity * 100

    result = {
        "symbol": symbol, "preset": preset_name, "bars": n_bars,
        "timeframe": cfg["TIMEFRAME"],
        "start_equity": start_equity, "end_equity": round(equity, 2),
        "return_pct": round(ret_pct, 2), "max_drawdown_pct": round(max_dd, 2),
        "trades": total, "wins": len(wins), "losses": len(losses),
        "win_rate": round(win_rate, 1), "profit_factor": round(pf, 2) if pf != float("inf") else None,
        "expectancy_per_trade": round(expectancy, 2),
        "avg_r_multiple": round(avg_r, 2),
        "total_fees": round(total_fees, 2),
    }
    if not quiet:
        print(json.dumps(result, indent=2))
        print("\n  exit reasons:", {r: sum(1 for t in trades if r in t["reason"]) for r in
                                    ("TAKE_PROFIT", "STOP_LOSS", "TRAIL_STOP", "SCALE_OUT", "TIME_STOP")})
    else:
        print(f"  {symbol} {preset_name}: ret={ret_pct:+.2f}% trades={total} wr={win_rate:.0f}% "
              f"pf={pf:.2f} exp={expectancy:+.2f}R fees={total_fees:.1f} dd={max_dd:.1f}%")
    return result


def main():
    parser = argparse.ArgumentParser(description="Strategy backtest on real Binance klines")
    parser.add_argument("--symbol", default="BTCUSDT")
    parser.add_argument("--preset", default="day", choices=list(PRESETS.keys()))
    parser.add_argument("--pages", type=int, default=3, help="number of 1000-bar pages to fetch")
    parser.add_argument("--end", type=int, default=None, help="endTime ms (for reproducible runs)")
    parser.add_argument("--disable-bb", action="store_true", help="A/B test: disable the Bollinger stretch gate")
    parser.add_argument("--threshold", type=int, default=None, help="override SIGNAL_THRESHOLD (1-5)")
    parser.add_argument("--sl", type=float, default=None, help="override ATR_MULTIPLIER_SL")
    parser.add_argument("--tp", type=float, default=None, help="override ATR_MULTIPLIER_TP")
    parser.add_argument("--scale-frac", type=float, default=None, help="override SCALE_OUT_FRACTION")
    parser.add_argument("--bb-pctb", type=float, default=None, help="override BB_UPPER_PCT_B")
    parser.add_argument("--cooldown-bars", type=int, default=None, help="bars to wait after any exit before re-entry (default: derived from COOLDOWN_LOSS)")
    parser.add_argument("--min-tp", type=float, default=None, help="override MIN_TP_PERCENT (TP floor as fraction)")
    parser.add_argument("--bb-lower", type=float, default=None, help="research: skip entries with Bollinger %%B <= this (falling-knife gate)")
    parser.add_argument("--adx-min", type=float, default=None, help="research: skip entries when LTF ADX(14) < this (chop gate)")
    parser.add_argument("--vol-mult", type=float, default=None, help="research: require signal-bar volume >= this multiple of the 20-bar average")
    parser.add_argument("--be-r", type=float, default=None, help="research: breakeven lock triggers at this R-multiple (default: +1%% of price)")
    parser.add_argument("--trail-r", type=float, default=None, help="research: trailing stop activates at this R-multiple (default: TRAILING_STOP_ACTIVATE)")
    parser.add_argument("--max-hold", type=float, default=None, help="research: override MAX_HOLD_TIME in seconds")
    parser.add_argument("--maker-tp", action="store_true", help="research: TP exits pay maker fee 0.02%% (OCO limit leg) instead of taker 0.1%%")
    parser.add_argument("--quiet", action="store_true", help="suppress the per-exit event log")
    args = parser.parse_args()

    print(f"Backtesting {args.symbol} | preset={args.preset} | pages={args.pages} (up to {args.pages * 1000} bars)")
    t0 = time.time()
    result = run_backtest(args.symbol, args.preset, args.pages, end_time=args.end,
                          disable_bb=args.disable_bb, threshold=args.threshold,
                          sl_mult=args.sl, tp_mult=args.tp, scale_frac=args.scale_frac,
                          bb_pctb=args.bb_pctb, cooldown_bars=args.cooldown_bars,
                          min_tp=args.min_tp, bb_lower=args.bb_lower,
                          adx_min=args.adx_min, vol_mult=args.vol_mult,
                          be_r=args.be_r, trail_r=args.trail_r, max_hold=args.max_hold,
                          maker_tp=args.maker_tp, quiet=args.quiet)
    if result is None:
        return 2
    print(f"\nCompleted in {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    sys.exit(main())
