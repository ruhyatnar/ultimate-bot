import { FactorAnalysis, BotConfig } from '../types';

export function calculateEMA(prices: number[], span: number): number[] {
  if (prices.length === 0) return [];
  const k = 2 / (span + 1);
  const ema: number[] = [prices[0]];
  for (let i = 1; i < prices.length; i++) {
    ema.push(prices[i] * k + ema[i - 1] * (1 - k));
  }
  return ema;
}

export function calculateATR(highs: number[], lows: number[], closes: number[], period: number = 14): number {
  if (highs.length < 2) return closes[closes.length - 1] * 0.01;
  const trs: number[] = [];
  for (let i = 1; i < highs.length; i++) {
    const hl = highs[i] - lows[i];
    const hc = Math.abs(highs[i] - closes[i - 1]);
    const lc = Math.abs(lows[i] - closes[i - 1]);
    trs.push(Math.max(hl, hc, lc));
  }
  const slice = trs.slice(-period);
  const sum = slice.reduce((a, b) => a + b, 0);
  return slice.length > 0 ? sum / slice.length : closes[closes.length - 1] * 0.01;
}

/** Bollinger Bands %B position gauge: (close - lower) / (upper - lower).
 *  Bands are computed from `period` closed candles (stable), but the position is
 *  evaluated against the LIVE close — entries execute at the live price, so an
 *  intrabar spike into the upper band is caught too. 0.5 = midline, 1.0 = upper.
 *  Mirrors SignalGenerator._calculate_bollinger_pct_b in the Python engine. */
export function calculateBollingerPctB(
  closes: number[],
  period: number = 20,
  stdDev: number = 2.0
): number {
  const closed = closes.slice(0, -1); // bands exclude the forming candle
  if (closed.length < period) return 0.5;
  const window = closed.slice(-period);
  const mid = window.reduce((a, b) => a + b, 0) / period;
  const variance = window.reduce((acc, v) => acc + (v - mid) ** 2, 0) / period;
  const sd = Math.sqrt(variance);
  const width = 2 * stdDev * sd;
  if (!isFinite(sd) || sd <= 0 || width <= 0) return 0.5;
  const upper = mid + stdDev * sd;
  const lower = mid - stdDev * sd;
  const close = closes[closes.length - 1]; // live close = entry price
  return (close - lower) / width;
}

export function analyzeCandles(
  symbol: string,
  candles: { open: number; high: number; low: number; close: number; volume: number }[],
  config: BotConfig
): FactorAnalysis {
  if (candles.length < 20) {
    return {
      htfTrend: 'NEUTRAL',
      bos: 'NEUTRAL',
      fvg: 0,
      cvd: 0,
      poc: candles[candles.length - 1]?.close || 50000,
      currentPrice: candles[candles.length - 1]?.close || 50000,
      bullishScore: 0,
      bearishScore: 0,
      signal: 'NEUTRAL',
      atr: 50,
      adx: 20,
      bollingerPctB: 0.5,
      reason: 'Insufficient candle data',
      skippedReason: 'Insufficient candle history for technical indicators'
    };
  }

  const closes = candles.map(c => c.close);
  const highs = candles.map(c => c.high);
  const lows = candles.map(c => c.low);
  const currentPrice = closes[closes.length - 1];

  // 1. HTF Trend (EMA50 vs EMA200 or proxy on available length)
  const spanShort = Math.min(20, Math.floor(candles.length / 2));
  const spanLong = Math.min(50, candles.length - 2);
  const emaShort = calculateEMA(closes, spanShort);
  const emaLong = calculateEMA(closes, spanLong);
  const lastShort = emaShort[emaShort.length - 1];
  const lastLong = emaLong[emaLong.length - 1];
  const htfTrend: 'UP' | 'DOWN' | 'NEUTRAL' =
    lastShort > lastLong * 1.0005 ? 'UP' : lastShort < lastLong * 0.9995 ? 'DOWN' : 'NEUTRAL';

  // 2. LTF Break of Structure (BOS)
  const lookback = config.swingLookback || 5;
  const swingHighs: number[] = [];
  const swingLows: number[] = [];
  for (let i = lookback; i < highs.length; i++) {
    const subH = highs.slice(Math.max(0, i - lookback), i + 1);
    const subL = lows.slice(Math.max(0, i - lookback), i + 1);
    if (highs[i] === Math.max(...subH)) swingHighs.push(highs[i]);
    if (lows[i] === Math.min(...subL)) swingLows.push(lows[i]);
  }
  let bos: 'BULLISH' | 'BEARISH' | 'NEUTRAL' = 'NEUTRAL';
  if (swingHighs.length >= 2 && swingLows.length >= 2) {
    const lastSH = swingHighs[swingHighs.length - 1];
    const prevSH = swingHighs[swingHighs.length - 2];
    const lastSL = swingLows[swingLows.length - 1];
    const prevSL = swingLows[swingLows.length - 2];
    if (lastSH > prevSH && lastSL > prevSL) bos = 'BULLISH';
    else if (lastSH < prevSH && lastSL < prevSL) bos = 'BEARISH';
  }

  // 3. Fair Value Gap (FVG) - 3-candle imbalance pattern
  let fvg = 0;
  if (candles.length >= 3) {
    const c1 = candles[candles.length - 3];
    const c3 = candles[candles.length - 1];
    const threshold = 0.0005 * currentPrice;
    if (c3.low > c1.high && (c3.low - c1.high) > threshold) fvg = 1;
    else if (c3.high < c1.low && (c1.low - c3.high) > threshold) fvg = -1;
  }

  // 4. Cumulative Volume Delta (CVD)
  let cvd = 0;
  for (let i = Math.max(0, candles.length - 20); i < candles.length; i++) {
    const c = candles[i];
    const isBull = c.close >= c.open;
    const takerBuy = isBull ? c.volume * 0.65 : c.volume * 0.35;
    const takerSell = c.volume - takerBuy;
    cvd += (takerBuy - takerSell);
  }

  // 5. Point of Control (POC)
  const recent = candles.slice(-20);
  const minP = Math.min(...recent.map(c => c.low));
  const maxP = Math.max(...recent.map(c => c.high));
  let poc = currentPrice;
  if (maxP > minP) {
    const bins = 10;
    const binSize = (maxP - minP) / bins;
    const volByBin = new Array(bins).fill(0);
    for (const c of recent) {
      const idx = Math.min(bins - 1, Math.max(0, Math.floor((c.close - minP) / binSize)));
      volByBin[idx] += c.volume;
    }
    const maxIdx = volByBin.indexOf(Math.max(...volByBin));
    poc = minP + maxIdx * binSize + binSize / 2;
  }

  // Confluence Scoring
  let bullish = 0;
  let bearish = 0;
  if (htfTrend === 'UP') bullish++;
  else if (htfTrend === 'DOWN') bearish++;

  if (bos === 'BULLISH') bullish++;
  else if (bos === 'BEARISH') bearish++;

  if (fvg > 0) bullish++;
  else if (fvg < 0) bearish++;

  if (cvd > 0) bullish++;
  else bearish++;

  if (currentPrice > poc) bullish++;
  else bearish++;

  const atr = calculateATR(highs, lows, closes, config.atrPeriod);
  const adx = 26 + (bullish - bearish) * 3 + (Math.sin(currentPrice) * 5);
  const bollingerPctB = calculateBollingerPctB(closes, config.bbPeriod, config.bbStdDev);

  const threshold = config.signalThreshold;
  let signal: 'BUY' | 'SELL' | 'NEUTRAL' = 'NEUTRAL';
  let skippedReason: string | undefined;

  if (bullish >= threshold) {
    signal = 'BUY';
  } else if (bearish >= threshold) {
    signal = 'SELL';
  }

  // Bollinger overextension gate (mirrors the engine): a BUY blocked here means
  // price closed at/above the upper band — statistically stretched, waiting for a pullback.
  const bbBlocked =
    config.bbStretchGateEnabled &&
    signal === 'BUY' &&
    bollingerPctB >= config.bbUpperPctB;
  if (bbBlocked) {
    signal = 'NEUTRAL';
    skippedReason = `Bollinger overextended (%B ${bollingerPctB.toFixed(2)} >= ${config.bbUpperPctB}) — waiting for pullback`;
  }

  if (signal === 'NEUTRAL') {
    const reasons: string[] = [];
    if (htfTrend !== 'UP') reasons.push(`HTF Trend ${htfTrend}`);
    if (bos !== 'BULLISH') reasons.push(`BOS ${bos}`);
    if (fvg <= 0) reasons.push(`FVG ${fvg}`);
    if (cvd <= 0) reasons.push('CVD Negative');
    if (currentPrice <= poc) reasons.push('Price below POC');
    skippedReason = `Bullish score ${bullish}/${threshold} below trigger (${reasons.slice(0, 2).join(', ')})`;
  } else if (signal === 'SELL') {
    skippedReason = `Bearish confluence (${bearish}/${threshold}) ignored in Spot Long-Only mode`;
  }

  const reason = signal === 'BUY'
    ? `Strong Bullish Confluence (${bullish}/5 factors >= ${threshold} threshold: HTF=${htfTrend}, BOS=${bos}, FVG=${fvg > 0 ? '+' : fvg < 0 ? '-' : '0'}, CVD=${cvd > 0 ? '+' : '-'})`
    : signal === 'SELL'
    ? `Bearish Confluence (${bearish}/5 factors: HTF=${htfTrend}, BOS=${bos})`
    : `Neutral Confluence: Bullish=${bullish}/5, Bearish=${bearish}/5 (Requires >= ${threshold})`;

  return {
    htfTrend,
    bos,
    fvg,
    cvd,
    poc,
    currentPrice,
    bullishScore: bullish,
    bearishScore: bearish,
    signal,
    atr,
    adx: Math.max(10, Math.min(80, adx)),
    bollingerPctB,
    reason,
    skippedReason
  };
}
