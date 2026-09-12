import logging
import time
import numpy as np
import pandas as pd

class SignalGenerator:
    # Cap the kline cache so dynamic screening over hundreds of symbols cannot grow
    # memory without bound on long VPS runs. Evicts the oldest entries (FIFO) once
    # the cap is hit; entries also expire after 60s via the timestamp check below.
    KLINE_CACHE_MAX_ENTRIES = 64

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
        while len(self.klines_cache) > self.KLINE_CACHE_MAX_ENTRIES:
            oldest_key = next(iter(self.klines_cache))
            self.klines_cache.pop(oldest_key, None)
        return df

    async def generate_signal(self, symbol):
        self.logger.debug(f"Generating signal for {symbol}...")
        htf_df = await self._get_cached_klines(symbol, self.config["MTF_TIMEFRAME"], 200)
        ltf_df = await self._get_cached_klines(symbol, self.config["TIMEFRAME"], 100)
        if htf_df is None or ltf_df is None:
            return "NEUTRAL", 0
        rsi_df = None
        if self.config.get("STRATEGY_MODE") == "rsi_dip":
            # Real RSI-TF candles: Wilder RSI needs ~3x its period of samples to
            # converge — 250 x 15m buckets is converged, whereas grouping the
            # 100-bar 5m window yields only ~25 buckets and a biased RSI that
            # almost never reaches the oversold trigger.
            rsi_df = await self._get_cached_klines(symbol, self.config["RSI_TIMEFRAME"], 250)
            if rsi_df is None:
                return "NEUTRAL", 0
        return self.decide(htf_df, ltf_df, rsi_df=rsi_df, symbol=symbol)

    def decide(self, htf_df, ltf_df, rsi_df=None, symbol: str = ""):
        """Pure decision core: score the confluence factors on the given frames
        and return (signal, current_atr). Shared verbatim by the LIVE engine
        (via generate_signal) and the BACKTEST bar-replay (backtest.py) — one
        strategy definition, zero drift between what is backtested and what
        trades real money. rsi_df (RSI_TIMEFRAME candles) is only used by the
        rsi_dip strategy mode."""
        if self.config.get("STRATEGY_MODE") == "rsi_dip":
            return self._decide_rsi_dip(htf_df, ltf_df, rsi_df=rsi_df, symbol=symbol)
        return self._decide_confluence(htf_df, ltf_df, symbol)

    def _decide_rsi_dip(self, htf_df, ltf_df, rsi_df=None, symbol: str = ""):
        """swing_rsi strategy mode: daily-regime filter + RSI pullback trigger.

        Backtest-proven (2026-09-10, ~113 days, $22 equity, fees + minNotional
        modeled): NEARUSDT +52.4% (PF 2.11, WR 55.3%), 6/9 alt pairs positive;
        see README changelog. Rules:

          1. REGIME (htf_df = daily candles): last COMPLETED day closed above
             its EMA-50 and EMA-50 is rising over REGIME_SLOPE_DAYS. If the
             last htf row is today's partial candle (same UTC day as the last
             ltf bar) it is dropped first — the regime never peeks at an
             unfinished day.
          2. TRIGGER (ltf_df = execution-TF candles): RSI(RSI_PERIOD) computed
             on RSI_TIMEFRAME (15m) bucket closes. BUY when RSI < RSI_OVERSOLD
             and turning up (rsi > previous bucket's rsi) — 'buy the dip, not
             the top'. The in-progress 15m bucket is excluded so the reading
             matches the backtest's completed-bucket convention.

        Exits are handled by the % bracket (SL_PERCENT / TP_PERCENT) — this
        mode ignores ATR bracket math by design (the tested edge used fixed
        -2% / +4% levels).
        """
        current_atr = self._calculate_atr(ltf_df)
        current_atr = current_atr.iloc[-1] if not pd.isna(current_atr.iloc[-1]) and current_atr.iloc[-1] > 0 else ltf_df['close'].iloc[-1] * 0.001

        # ---- 1) daily regime on completed candles only ----
        htf = htf_df.copy()
        ltf_last_day = int(ltf_df['open_time'].iloc[-1]) // 86_400_000
        if len(htf) and int(htf['open_time'].iloc[-1]) // 86_400_000 == ltf_last_day:
            htf = htf.iloc[:-1]                      # drop today's partial daily candle
        regime_ema = int(self.config.get("REGIME_EMA", 50))
        slope_days = int(self.config.get("REGIME_SLOPE_DAYS", 3))
        if len(htf) < max(regime_ema + slope_days + 5, 20):
            self.logger.debug(f"{symbol}: rsi_dip regime not ready ({len(htf)} daily candles < {regime_ema + slope_days + 5}).")
            return "NEUTRAL", current_atr
        ema50 = htf['close'].ewm(span=regime_ema, adjust=False).mean()
        regime_up = bool(htf['close'].iloc[-1] > ema50.iloc[-1]
                         and ema50.iloc[-1] > ema50.iloc[-1 - slope_days])
        if not regime_up:
            self.logger.debug(f"{symbol}: rsi_dip regime DOWN/flat — no long entries.")
            return "NEUTRAL", current_atr

        # ---- 2) RSI pullback trigger ----
        rsi_period = int(self.config.get("RSI_PERIOD", 14))
        oversold = float(self.config.get("RSI_OVERSOLD", 40))
        bucket_ms = int(self.config.get("RSI_TIMEFRAME_MS", 900_000))   # 15m default
        tf_ms = {"1m": 60_000, "3m": 180_000, "5m": 300_000, "15m": 900_000,
                 "30m": 1_800_000, "1h": 3_600_000}.get(self.config.get("TIMEFRAME", "5m"), 300_000)
        ltf_close_ms = int(ltf_df['open_time'].iloc[-1]) + tf_ms
        rsi_source = str(self.config.get("RSI_SOURCE", "htf")).lower()
        if rsi_source == "ltf":
            # intraday_rsi convention (backtest-proven): RSI(period) computed on
            # the EXECUTION-TF close series (every 5m bar) and SAMPLED at the
            # last completed bar of each RSI_TIMEFRAME bucket — '1h RSI(7) on
            # 5m closes, read at :55'. NOTE: this is NOT RSI on hourly closes
            # (that would be a ~7-hour lookback); the proven signal has a
            # ~35-minute lookback read once per hour.
            l = ltf_df.copy()
            l['bucket'] = l['open_time'].astype('int64') // bucket_ms
            # NOTE: no bucket-completion filter here. The LTF window already
            # contains only CLOSED 5m bars ending at the signal bar, so the
            # current bucket's last bar IS the completed read (the :55 bar
            # when firing). Filtering bars by open_time+bucket_ms would keep
            # only the current bucket's :00 bar and sample RSI 55min stale.
            r_series = self._rsi_wilder(l['close'], rsi_period)
            l = l.assign(_rsi=r_series.values)
            rsi = l.groupby('bucket')['_rsi'].last()
            rsi_last, rsi_prev = rsi.iloc[-1], rsi.iloc[-2]
            if pd.isna(rsi_last) or pd.isna(rsi_prev):
                return "NEUTRAL", current_atr
            self.logger.debug(
                f"{symbol}: rsi_dip regime UP, RSI(ltf)={rsi_last:.1f} (prev {rsi_prev:.1f}, "
                f"oversold<{oversold})")
            # Fire ONCE per bucket: the last completed bucket must close exactly
            # at this signal bar's close (fresh bucket — no re-triggering).
            last_bucket_close = int(rsi.index[-1]) * bucket_ms + bucket_ms
            if last_bucket_close != ltf_close_ms:
                return "NEUTRAL", current_atr
            if rsi_last < oversold and rsi_last > rsi_prev:
                return "BUY", current_atr
            return "NEUTRAL", current_atr
        if rsi_df is not None and len(rsi_df):
            r = rsi_df.copy()
        else:
            # Degraded fallback: derive buckets from the LTF window (few samples,
            # RSI biased — callers should provide rsi_df whenever possible).
            r = ltf_df.copy()
        r['bucket'] = r['open_time'].astype('int64') // bucket_ms
        # A bucket is complete iff its close time <= the LTF signal bar's close.
        r = r[r['open_time'].astype('int64') + bucket_ms <= ltf_close_ms]
        c15 = r.groupby('bucket')['close'].last()
        if len(c15) < rsi_period + 2:
            self.logger.debug(f"{symbol}: rsi_dip RSI not ready ({len(c15)} buckets < {rsi_period + 2}).")
            return "NEUTRAL", current_atr
        delta = c15.diff()
        gain = delta.clip(lower=0).ewm(alpha=1.0 / rsi_period, adjust=False).mean()
        loss = (-delta.clip(upper=0)).ewm(alpha=1.0 / rsi_period, adjust=False).mean()
        rs = gain / loss.replace(0, np.nan)
        rsi = 100 - 100 / (1 + rs)
        rsi_last, rsi_prev = rsi.iloc[-1], rsi.iloc[-2]
        if pd.isna(rsi_last) or pd.isna(rsi_prev):
            return "NEUTRAL", current_atr
        self.logger.debug(
            f"{symbol}: rsi_dip regime UP, RSI={rsi_last:.1f} (prev {rsi_prev:.1f}, "
            f"oversold<{oversold})")
        # Fire ONCE per dip bucket: the last completed bucket must have closed
        # exactly at this signal bar's close (fresh bucket). Without this, the
        # (rsi_last > rsi_prev) comparison stays true for every 5m bar of the
        # whole 15m bucket and re-triggers after each exit.
        last_bucket_close = int(c15.index[-1]) * bucket_ms + bucket_ms
        if last_bucket_close != ltf_close_ms:
            return "NEUTRAL", current_atr
        if rsi_last < oversold and rsi_last > rsi_prev:
            return "BUY", current_atr
        return "NEUTRAL", current_atr

    def _rsi_wilder(self, close, period):
        """Wilder RSI on a close series (alpha = 1/period), zero-loss bars pin to 100.
        Matches the research-lab RSI formula exactly (rsi_dip proven edge)."""
        delta = close.diff()
        gain = delta.clip(lower=0).ewm(alpha=1.0 / period, adjust=False).mean()
        loss = (-delta.clip(upper=0)).ewm(alpha=1.0 / period, adjust=False).mean()
        rs = gain / loss.replace(0, np.nan)
        out = 100 - 100 / (1 + rs)
        out[loss == 0] = 100.0
        return out

    def _decide_confluence(self, htf_df, ltf_df, symbol: str = ""):
        atr = self._calculate_atr(ltf_df)
        current_atr = atr.iloc[-1] if not pd.isna(atr.iloc[-1]) and atr.iloc[-1] > 0 else ltf_df['close'].iloc[-1] * 0.001

        htf_df['ema50'] = htf_df['close'].ewm(span=50, adjust=False).mean()
        htf_df['ema200'] = htf_df['close'].ewm(span=200, adjust=False).mean()
        ema50_last = htf_df['ema50'].iloc[-1]
        ema200_last = htf_df['ema200'].iloc[-1]
        if pd.isna(ema50_last) or pd.isna(ema200_last):
            htf_trend = "NEUTRAL"
        elif ema50_last > ema200_last:
            htf_trend = "UP"
        elif ema50_last < ema200_last:
            htf_trend = "DOWN"
        else:
            htf_trend = "NEUTRAL"

        swings_high, swings_low = self._detect_swings(ltf_df)
        current_price = ltf_df['close'].iloc[-1]
        bos = self._detect_bos(swings_high, swings_low, current_price)
        fvg = self._calculate_fvg(ltf_df)
        delta = self._calculate_cvd(ltf_df)
        poc = self._calculate_poc(ltf_df)
        pct_b = self._calculate_bollinger_pct_b(ltf_df)

        bullish, bearish = 0, 0
        if htf_trend == "UP": bullish += 1
        elif htf_trend == "DOWN": bearish += 1
        if bos == "BULLISH": bullish += 1
        elif bos == "BEARISH": bearish += 1
        if fvg > 0: bullish += 1
        elif fvg < 0: bearish += 1
        if delta > 0: bullish += 1
        elif delta < 0: bearish += 1
        if ltf_df['close'].iloc[-1] > poc: bullish += 1
        elif ltf_df['close'].iloc[-1] < poc: bearish += 1

        threshold = self.config["SIGNAL_THRESHOLD"]
        self.logger.debug(f"{symbol}: htf={htf_trend}, bos={bos}, fvg={fvg}, delta={delta}, poc={poc}, bullish={bullish}, bearish={bearish}, threshold={threshold}")

        # Regime alignment gate (professional filter): never catch falling knives.
        # A BUY requires the higher-timeframe trend to be UP or at worst NEUTRAL —
        # a 4/5 bullish score while the HTF trend is DOWN is exactly the setup that
        # bleeds accounts (long into distribution). The same applies mirrored for
        # shorts, keeping the logic symmetric even though spot mode is long-only.
        if bullish >= threshold and htf_trend == "DOWN":
            self.logger.debug(f"{symbol}: BUY score {bullish}>={threshold} blocked — HTF trend is DOWN (regime misalignment).")
            return "NEUTRAL", current_atr
        if bearish >= threshold and htf_trend == "UP":
            self.logger.debug(f"{symbol}: SELL score {bearish}>={threshold} blocked — HTF trend is UP (regime misalignment).")
            return "NEUTRAL", current_atr

        # Bollinger overextension gate: all five confluence factors are momentum/
        # continuation signals, so the stack's blind spot is buying a vertical,
        # overextended candle that mean-reverts into the ATR stop before TP fires.
        # A %B reading >= BB_UPPER_PCT_B (default 0.95) means price closed at/above
        # the upper band — statistically stretched. Skipping those entries protects
        # the expectancy without touching SIGNAL_THRESHOLD semantics (1-5).
        if self.config.get("BB_STRETCH_GATE_ENABLED", True) and bullish >= threshold and pct_b >= float(self.config.get("BB_UPPER_PCT_B", 0.95)):
            self.logger.debug(
                f"{symbol}: BUY score {bullish}>={threshold} blocked — Bollinger overextended "
                f"(%B={pct_b:.2f} >= {self.config.get('BB_UPPER_PCT_B', 0.95)}); waiting for a pullback entry."
            )
            return "NEUTRAL", current_atr

        if bullish >= threshold: return "BUY", current_atr
        elif bearish >= threshold: return "SELL", current_atr
        return "NEUTRAL", current_atr

    def _to_df(self, klines):
        df = pd.DataFrame(klines, columns=['open_time','open','high','low','close','volume','close_time','quote_volume','trades','taker_buy_base','taker_buy_quote','ignore'])
        for col in ['open','high','low','close','volume','quote_volume','taker_buy_base','taker_buy_quote']:
            df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0)
        return df

    def _calculate_atr(self, df):
        high_low = df['high'] - df['low']
        high_close = (df['high'] - df['close'].shift()).abs()
        low_close = (df['low'] - df['close'].shift()).abs()
        tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        return tr.rolling(self.atr_period, min_periods=1).mean()

    def _detect_swings(self, df):
        highs, lows = df['high'].values, df['low'].values
        lookback = self.config["SWING_LOOKBACK"]
        if lookback < 2:
            return [], []
        swing_highs, swing_lows = [], []
        for i in range(lookback, len(df) - 1):
            start = max(0, i - lookback)
            end = min(len(df), i + lookback + 1)
            window_high = max(highs[start:end])
            window_low = min(lows[start:end])
            if highs[i] == window_high:
                if not swing_highs or swing_highs[-1][0] < i - 1:
                    swing_highs.append((i, highs[i]))
            if lows[i] == window_low:
                if not swing_lows or swing_lows[-1][0] < i - 1:
                    swing_lows.append((i, lows[i]))
        return swing_highs, swing_lows

    def _detect_bos(self, swing_highs, swing_lows, current_price=None):
        if not swing_highs or not swing_lows: return "NEUTRAL"
        # Real-time Break of Structure: price actively breaking prior swing high
        if current_price and len(swing_highs) >= 1 and current_price > swing_highs[-1][1]:
            return "BULLISH"
        if len(swing_highs) < 2 or len(swing_lows) < 2: return "NEUTRAL"
        if swing_highs[-1][1] > swing_highs[-2][1] and swing_lows[-1][1] > swing_lows[-2][1]: return "BULLISH"
        if swing_highs[-1][1] < swing_highs[-2][1] and swing_lows[-1][1] < swing_lows[-2][1]: return "BEARISH"
        return "NEUTRAL"

    def _calculate_fvg(self, df):
        # Require at least 4 candles so the 3-candle window (-4, -3, -2) is available
        # and we never index into a too-short frame.
        if len(df) < 4: return 0
        # Use last closed candles (df.iloc[-4], -3, -2) to prevent false signals from
        # the unclosed forming candle's fluctuating high/low.
        c1, _, c3 = df.iloc[-4], df.iloc[-3], df.iloc[-2]
        threshold = 0.0005 * df['close'].iloc[-1]
        # Bullish FVG: Candle 3's low is strictly higher than Candle 1's high
        if c3['low'] > c1['high'] and (c3['low'] - c1['high']) > threshold: return 1
        # Bearish FVG: Candle 3's high is strictly lower than Candle 1's low
        if c3['high'] < c1['low'] and (c1['low'] - c3['high']) > threshold: return -1
        return 0

    def _calculate_bollinger_pct_b(self, df):
        """Bollinger Bands %B position gauge: (close − lower) / (upper − lower).

        0.5 = at the midline, 1.0 = at the upper band, >1.0 = above it. Bands are
        computed from BB_PERIOD CLOSED candles (stable, no forming-candle noise)
        but the position is evaluated against the LIVE close — entries execute at
        the live price, so an intrabar spike into the upper band must be caught,
        not just one that already closed there. Returns 0.5 (midline — never
        blocks) when there is not enough data or the band width collapses, so the
        gate only ever blocks genuinely stretched entries.
        """
        try:
            period = int(self.config.get("BB_PERIOD", 20))
            std_dev = float(self.config.get("BB_STD_DEV", 2.0))
            closed = df.iloc[:-1]  # bands exclude the unclosed forming candle
            if len(closed) < period:
                return 0.5
            window = closed['close'].iloc[-period:]
            mid = float(window.mean())
            sd = float(window.std(ddof=0))
            if not np.isfinite(sd) or sd <= 0:
                return 0.5
            upper = mid + std_dev * sd
            lower = mid - std_dev * sd
            width = upper - lower
            if width <= 0:
                return 0.5
            close = float(df['close'].iloc[-1])  # live/forming close = entry price
            return (close - lower) / width
        except Exception as e:
            self.logger.debug(f"Bollinger %B calculation failed: {e}")
            return 0.5

    def _calculate_cvd(self, df):
        """Normalized CVD direction with a noise floor.

        A raw taker-buy minus taker-sell sum treats a ±0.1% imbalance the same as a
        strong 2% one-way flow, giving low-quality confluence points. Normalizing by
        total quoted volume and requiring a minimum directional share before
        counting the factor keeps this factor meaningful.
        """
        if 'taker_buy_quote' not in df.columns or 'quote_volume' not in df.columns: return 0.0
        recent = df.iloc[-20:]
        if len(recent) < 10: return 0.0
        buy_vol = float(recent['taker_buy_quote'].sum())
        total_vol = float(recent['quote_volume'].sum())
        if total_vol <= 0: return 0.0
        buy_share = buy_vol / total_vol  # 0.5 = perfectly balanced flow
        # Require at least a 55/45 directional skew before counting as confluence.
        if buy_share >= 0.55: return 1.0
        if buy_share <= 0.45: return -1.0
        return 0.0

    def _calculate_poc(self, df):
        recent = df.iloc[-20:]
        if len(recent) < 10: return df['close'].iloc[-1]
        min_price, max_price = recent['low'].min(), recent['high'].max()
        if min_price == max_price: return recent['close'].iloc[-1]
        bins = np.linspace(min_price, max_price, 11)
        indices = np.clip(np.digitize(recent['close'], bins, right=False) - 1, 0, 9)
        vol_by_bin = [0]*10
        for i, idx in enumerate(indices):
            vol_by_bin[idx] += recent.iloc[i]['volume']
        poc_idx = np.argmax(vol_by_bin)
        return bins[poc_idx] + (bins[1] - bins[0]) / 2
