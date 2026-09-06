import logging
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
        current_price = ltf_df['close'].iloc[-1]
        bos = self._detect_bos(swings_high, swings_low, current_price)
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
        swing_highs, swing_lows = [], []
        for i in range(lookback, len(df) - 1):
            start = max(0, i - lookback)
            end = min(len(df), i + lookback + 1)
            if highs[i] == max(highs[start:end]):
                if not swing_highs or swing_highs[-1][0] < i - 1:
                    swing_highs.append((i, highs[i]))
            if lows[i] == min(lows[start:end]):
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
        if len(df) < 5: return 0
        # Use last closed candles (df.iloc[-4], -3, -2) to prevent false signals from unclosed candle fluctuations
        c1, c2, c3 = df.iloc[-4], df.iloc[-3], df.iloc[-2]
        threshold = 0.0005 * df['close'].iloc[-1]
        # Bullish FVG: Candle 3's low is strictly higher than Candle 1's high
        if c3['low'] > c1['high'] and (c3['low'] - c1['high']) > threshold: return 1
        # Bearish FVG: Candle 3's high is strictly lower than Candle 1's low
        if c3['high'] < c1['low'] and (c1['low'] - c3['high']) > threshold: return -1
        return 0

    def _calculate_cvd(self, df):
        if 'taker_buy_quote' not in df.columns or 'quote_volume' not in df.columns: return 0.0
        delta = df['taker_buy_quote'] - (df['quote_volume'] - df['taker_buy_quote'])
        val = delta.rolling(20, min_periods=1).sum().iloc[-1]
        return float(val) if not pd.isna(val) else 0.0

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
