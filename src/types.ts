export type StrategyPreset = 'scalping' | 'day' | 'swing' | 'swing_rsi' | 'intraday_rsi';

export interface BotConfig {
  preset: StrategyPreset;
  timeframe: string;
  mtfTimeframe: string;
  // --- rsi_dip strategy keys (swing_rsi / intraday_rsi presets) ---
  strategyMode: 'rsi_dip' | 'confluence';
  slPercent: number;          // fixed SL bracket, fraction (0.012 = -1.2%)
  tpPercent: number;          // fixed TP bracket, fraction (0.03 = +3%)
  rsiPeriod: number;
  rsiOversold: number;
  rsiTimeframe: string;       // RSI sampling bucket ('15m' swing, '1h' intraday)
  rsiTimeframeMs: number;     // bucket size in ms (derived; explicit wins)
  rsiSource: 'ltf' | 'htf';   // ltf = RSI on 5m closes sampled per bucket (proven)
  regimeEma: number;          // daily EMA span for the regime gate
  regimeSlopeDays: number;    // EMA rising-over-N-days requirement
  maxTradesPerDay: number;    // 0 = unlimited
  breakevenEnabled: boolean;  // +1% BE lock (must stay OFF for intraday_rsi)
  closeAtUtcDayEnd: boolean;  // force-close open positions at UTC day end
  minTpPercent: number;       // TP floor as fraction
  atrPeriod: number;
  atrMultiplierSl: number;
  atrMultiplierTp: number;
  trailingStopActivate: number;
  trailingStopCallback: number;
  swingLookback: number;
  bbPeriod: number;
  bbStdDev: number;
  bbUpperPctB: number;
  bbStretchGateEnabled: boolean;
  maxHoldTime: number; // seconds
  signalThreshold: number; // 1 to 5
  signalInterval: number; // seconds
  maxDailyDrawdown: number; // e.g. 0.05
  maxLossStreak: number;
  maxWinStreak: number;
  cooldownLoss: number; // seconds
  cooldownWin: number; // seconds
  balanceUsagePercent: number;
  maxSymbolAllocationPercent: number;
  staticSymbols: string[];
  dynamicSymbols: boolean;
  maxSymbols: number;
  adxThreshold: number;
  adxPeriod: number;
  paperTrade: boolean;
  useTestnet: boolean;
  discordWebhookUrl: string;
  logLevel: 'DEBUG' | 'INFO' | 'WARNING' | 'ERROR';
}

export interface FactorAnalysis {
  htfTrend: 'UP' | 'DOWN' | 'NEUTRAL';
  bos: 'BULLISH' | 'BEARISH' | 'NEUTRAL';
  fvg: number; // 1 = bullish gap, -1 = bearish gap, 0 = none
  cvd: number; // positive = net buyers, negative = net sellers
  poc: number; // point of control price
  currentPrice: number;
  bullishScore: number;
  bearishScore: number;
  signal: 'BUY' | 'SELL' | 'NEUTRAL';
  atr: number;
  adx: number;
  bollingerPctB: number;
  reason: string;
  skippedReason?: string;
}

export interface ActiveTrade {
  id: string;
  symbol: string;
  side: 'BUY' | 'SELL';
  entryPrice: number;
  currentPrice: number;
  quantity: number;
  notional: number;
  entryTime: number;
  stopPrice: number;
  takeProfit: number;
  atr: number;
  trailingActive: boolean;
  trailingStop: number;
  breakevenActivated: boolean;
  unrealizedPnl: number;
  unrealizedPnlPct: number;
}

export interface ClosedTrade {
  id: string;
  symbol: string;
  side: 'BUY' | 'SELL';
  entryPrice: number;
  exitPrice: number;
  quantity: number;
  pnl: number;
  pnlPct: number;
  entryTime: number;
  exitTime: number;
  exitReason: 'STOP_LOSS' | 'TAKE_PROFIT' | 'TRAILING_STOP' | 'TIME_STOP' | 'MANUAL' | 'EMERGENCY_CLOSE';
}

export interface LogMessage {
  id: string;
  timestamp: string;
  level: 'DEBUG' | 'INFO' | 'WARN' | 'ERROR' | 'SUCCESS';
  category: 'SIGNAL' | 'ORDER' | 'RISK' | 'HEALTH' | 'SYS';
  message: string;
  symbol?: string;
  details?: Record<string, any>;
}

export interface MarketSymbolData {
  symbol: string;
  name: string;
  price: number;
  priceChange24h: number;
  high24h: number;
  low24h: number;
  volume24h: number;
  factors: FactorAnalysis;
  sparkline: number[];
  inCooldown: boolean;
  cooldownEndsAt?: number;
}

export interface CandidateSymbol {
  symbol: string;
  name: string;
  price: number;
  priceChange24h: number;
  volume24h: number;
  volatility: number;
  adx: number;
  zScore: number;
  isSelected: boolean;
  momentumRank: number;
}

export interface VpsBotStatus {
  connected: boolean;
  endpoint: string;
  lastSyncTime?: string;
  latencyMs?: number;
  engineStatus: string;
  engineRunning: boolean;
  error?: string;
  serverTime?: string;
  stats?: {
    total_orders: number;
    closed_trades: number;
    winning_trades: number;
    losing_trades: number;
    breakeven_trades: number;
    total_realized_pnl: number;
    win_rate: number;
    profit_factor: number;
    avg_win: number;
    avg_loss: number;
  };
}

export interface VpsControlState {
  paused: boolean;
  pauseReason?: string;
}

export interface VpsBalanceData {
  totalEquity: number;
  freeQuote: number;
  lockedQuote: number;
  quoteAsset: string;
  isLive: boolean;
  dailyPnl?: number;
  balances?: Array<{
    asset: string;
    free: number;
    locked: number;
    total?: number;
    usd_value?: number;
  }>;
}

export interface PushResult {
  ok: boolean;
  message: string;
}
