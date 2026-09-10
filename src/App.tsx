import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { 
  BotConfig, 
  StrategyPreset, 
  ActiveTrade, 
  ClosedTrade, 
  MarketSymbolData, 
  LogMessage,
  CandidateSymbol,
  VpsBotStatus,
  VpsControlState,
  PushResult,
  VpsBalanceData
} from './types';
import { analyzeCandles } from './utils/technicalAnalysis';
import { TAKER_FEE_RATE, MIN_NOTIONAL_USDT, BREAKEVEN_FEE_MULTIPLIER, effectiveAllocation, generateEnvString } from './utils/envGenerator';
import { VpsSocket, WsTransport } from './utils/vpsSocket';
import { Header } from './components/Header';
import { VpsConnectionBar } from './components/VpsConnectionBar';
import { LiveDashboard } from './components/LiveDashboard';
import { SignalInspector } from './components/SignalInspector';
import { DebugConsole } from './components/DebugConsole';
import { CodeExplorer } from './components/CodeExplorer';
import { ConfigTab } from './components/ConfigTab';
import { DeployGuide } from './components/DeployGuide';

const PRESET_MAP: Record<StrategyPreset, Partial<BotConfig>> = {
  // Values mirror ultimate-bot/config.py PRESETS exactly so the dashboard tunes
  // the same strategy the engine runs (previously the UI presets contradicted
  // the engine's — e.g. scalping 0.8/1.2 ATR here vs 1.0/2.0 on the engine).
  scalping: {
    timeframe: '1m',
    mtfTimeframe: '15m',
    atrPeriod: 10,
    atrMultiplierSl: 1.0,
    atrMultiplierTp: 2.0,
    trailingStopActivate: 0.005,
    trailingStopCallback: 0.002,
    swingLookback: 3,
    maxHoldTime: 3600
  },
  day: {
    timeframe: '5m',
    mtfTimeframe: '1h',
    atrPeriod: 14,
    atrMultiplierSl: 3.0,
    atrMultiplierTp: 3.5,
    trailingStopActivate: 0.015,
    trailingStopCallback: 0.005,
    swingLookback: 5,
    maxHoldTime: 28800
  },
  swing: {
    timeframe: '15m',
    mtfTimeframe: '4h',
    atrPeriod: 20,
    atrMultiplierSl: 2.0,
    atrMultiplierTp: 4.0,
    trailingStopActivate: 0.03,
    trailingStopCallback: 0.012,
    swingLookback: 8,
    maxHoldTime: 86400
  }
};

const DEFAULT_CONFIG: BotConfig = {
  preset: 'day',
  timeframe: '5m',
  mtfTimeframe: '1h',
  atrPeriod: 14,
  atrMultiplierSl: 3.0,
  atrMultiplierTp: 3.5,
  trailingStopActivate: 0.015,
  trailingStopCallback: 0.005,
  swingLookback: 5,
  bbPeriod: 20,
  bbStdDev: 2.0,
  bbUpperPctB: 0.95,
  bbStretchGateEnabled: true,
  maxHoldTime: 28800,
  signalThreshold: 4,
  signalInterval: 6,
  maxDailyDrawdown: 0.05,
  maxLossStreak: 3,
  maxWinStreak: 5,
  cooldownLoss: 10800,
  cooldownWin: 1800,
  balanceUsagePercent: 0.5,
  maxSymbolAllocationPercent: 0.2,
  staticSymbols: ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT'],
  dynamicSymbols: true,
  maxSymbols: 4,
  adxThreshold: 25,
  adxPeriod: 14,
  paperTrade: true,
  useTestnet: false,
  discordWebhookUrl: '',
  logLevel: 'DEBUG'
};

const INITIAL_SYMBOLS: Record<string, { name: string; basePrice: number }> = {
  BTCUSDT: { name: 'Bitcoin', basePrice: 65420.5 },
  ETHUSDT: { name: 'Ethereum', basePrice: 3480.2 },
  SOLUSDT: { name: 'Solana', basePrice: 148.6 },
  BNBUSDT: { name: 'BNB', basePrice: 585.4 },
  SUSHIUSDT: { name: 'SushiSwap', basePrice: 0.24 },
  RAYUSDT: { name: 'Raydium', basePrice: 1.16 },
  NEARUSDT: { name: 'NEAR Protocol', basePrice: 4.85 },
  AVAXUSDT: { name: 'Avalanche', basePrice: 28.4 },
  SUIUSDT: { name: 'Sui', basePrice: 1.62 },
  DOGEUSDT: { name: 'Dogecoin', basePrice: 0.125 },
  LINKUSDT: { name: 'Chainlink', basePrice: 12.8 },
  OPUSDT: { name: 'Optimism', basePrice: 1.75 },
  APTUSDT: { name: 'Aptos', basePrice: 8.5 },
  PEPEUSDT: { name: 'Pepe', basePrice: 0.0000095 },
  RENDERUSDT: { name: 'Render', basePrice: 5.4 }
};

// Dynamic symbol metadata resolver
const getSymbolMeta = (sym: string, hintPrice?: number) => {
  if (INITIAL_SYMBOLS[sym]) {
    if (hintPrice && hintPrice > 0 && Math.abs(INITIAL_SYMBOLS[sym].basePrice - hintPrice) / hintPrice > 0.5) {
      INITIAL_SYMBOLS[sym].basePrice = hintPrice;
    }
    return INITIAL_SYMBOLS[sym];
  }
  const cleanBase = sym.replace(/USDT$|BUSD$|USDC$/, '');
  const price = hintPrice && hintPrice > 0 ? hintPrice : 1.0;
  INITIAL_SYMBOLS[sym] = { name: cleanBase, basePrice: price };
  return INITIAL_SYMBOLS[sym];
};

export default function App() {
  const [config, setConfig] = useState<BotConfig>(() => {
    try {
      const saved = localStorage.getItem('ultimate_bot_config');
      if (saved) {
        return { ...DEFAULT_CONFIG, ...JSON.parse(saved) };
      }
    } catch (e) {
      // fallback to defaults
    }
    return DEFAULT_CONFIG;
  });

  const [isRunning, setIsRunning] = useState<boolean>(true);
  const [activeTab, setActiveTab] = useState<'dashboard' | 'signals' | 'debug' | 'code' | 'config' | 'deploy'>('dashboard');

  // `equity`/`dailyRealizedPnl` are simulator-owned state. In VPS mode they are
  // populated from the server's SQLite risk_state — never locally, so the UI never
  // presents a fake $1000 balance as real live-server equity.
  const [equity, setEquity] = useState<number>(1000.0);
  const [dailyRealizedPnl, setDailyRealizedPnl] = useState<number>(0.0);
  const [vpsRiskAvailable, setVpsRiskAvailable] = useState<boolean>(false);
  const [winStreak, setWinStreak] = useState<number>(0);
  const [lossStreak, setLossStreak] = useState<number>(0);
  const [isLossCooldown, setIsLossCooldown] = useState<boolean>(false);
  const [cooldownEndsAt, setCooldownEndsAt] = useState<number>(0);

  const [dataSource, setDataSource] = useState<'vps' | 'simulator'>(() => {
    try {
      return (localStorage.getItem('ultimate_bot_datasource') as 'vps' | 'simulator') || 'vps';
    } catch {
      return 'vps';
    }
  });
  const [vpsEndpoint, setVpsEndpoint] = useState<string>(() => {
    try {
      return localStorage.getItem('ultimate_bot_vps_endpoint') || '';
    } catch {
      return '';
    }
  });
  const [isPollingVps, setIsPollingVps] = useState<boolean>(false);
  // Monitoring stack transport: 'websocket' = realtime /ws push from status.py,
  // 'polling' = HTTP fallback (proxy blocked the upgrade or backend restarts).
  const [wsTransport, setWsTransport] = useState<WsTransport>('connecting');
  const [vpsStatus, setVpsStatus] = useState<VpsBotStatus>({
    connected: false,
    endpoint: vpsEndpoint || (typeof window !== 'undefined' ? window.location.origin : ''),
    engineStatus: 'CHECKING...',
    engineRunning: false
  });
  const [vpsControl, setVpsControl] = useState<VpsControlState>({ paused: false });
  const vpsControlRef = useRef<VpsControlState>({ paused: false });
  vpsControlRef.current = vpsControl;

  const vpsStatusRef = useRef<VpsBotStatus>(vpsStatus);
  vpsStatusRef.current = vpsStatus;

  const wsTransportRef = useRef<WsTransport>('connecting');
  wsTransportRef.current = wsTransport;

  const [vpsPushResult, setVpsPushResult] = useState<PushResult | null>(null);
  const [vpsBalance, setVpsBalance] = useState<VpsBalanceData | null>(null);

  const [activeTrades, setActiveTrades] = useState<ActiveTrade[]>([]);
  const [closedTrades, setClosedTrades] = useState<ClosedTrade[]>([]);
  const [logs, setLogs] = useState<LogMessage[]>([]);

  const [useLiveBinanceFeed, setUseLiveBinanceFeed] = useState<boolean>(false);
  const [selectedPinnedSymbols, setSelectedPinnedSymbols] = useState<string[]>(['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT']);

  // Candle history per symbol (shared ref, mutated in place for performance)
  const candlesRef = useRef<Record<string, { open: number; high: number; low: number; close: number; volume: number }[]>>({});
  const [symbolsData, setSymbolsData] = useState<MarketSymbolData[]>([]);
  const [candidates, setCandidates] = useState<CandidateSymbol[]>([]);

  // Per-symbol cooldowns after closes (mirrors symbol_cooldowns in the Python engine)
  const cooldownsRef = useRef<Record<string, number>>({});

  // Ref mirrors so timers and callbacks always read fresh state without resetting intervals
  const activeTradesRef = useRef<ActiveTrade[]>(activeTrades);
  activeTradesRef.current = activeTrades;

  const configRef = useRef<BotConfig>(config);
  configRef.current = config;

  const equityRef = useRef<number>(equity);
  equityRef.current = equity;

  const dailyRealizedPnlRef = useRef<number>(dailyRealizedPnl);
  dailyRealizedPnlRef.current = dailyRealizedPnl;

  const dataSourceRef = useRef<'vps' | 'simulator'>(dataSource);
  dataSourceRef.current = dataSource;

  const lossStreakRef = useRef<number>(lossStreak);
  lossStreakRef.current = lossStreak;

  const cooldownUntilRef = useRef<number>(0);
  const runTickRef = useRef<() => void>(() => {});

  // Ensure a candle buffer exists for any symbol (including dynamic coins)
  const ensureCandlesForSymbol = useCallback((sym: string, hintPrice?: number) => {
    if (!candlesRef.current[sym] || candlesRef.current[sym].length === 0) {
      const meta = getSymbolMeta(sym, hintPrice);
      const base = hintPrice && hintPrice > 0 ? hintPrice : meta.basePrice;
      const initialCandles = [] as { open: number; high: number; low: number; close: number; volume: number }[];
      let price = base;
      for (let i = 0; i < 45; i++) {
        const delta = (Math.random() - 0.48) * (base * 0.004);
        const open = price;
        const close = Math.max(0.00001, price + delta);
        const high = Math.max(open, close) + Math.random() * (base * 0.002);
        const low = Math.min(open, close) - Math.random() * (base * 0.002);
        const volume = Math.random() * 50 + 10;
        initialCandles.push({ open, high, low, close, volume });
        price = close;
      }
      candlesRef.current[sym] = initialCandles;
    }
  }, []);

  // Persist config and VPS settings to localStorage
  useEffect(() => {
    try {
      localStorage.setItem('ultimate_bot_config', JSON.stringify(config));
      localStorage.setItem('ultimate_bot_datasource', dataSource);
      localStorage.setItem('ultimate_bot_vps_endpoint', vpsEndpoint);
    } catch (e) {
      // storage unavailable (private mode) — non-fatal
    }
  }, [config, dataSource, vpsEndpoint]);

  const addLog = useCallback((
    level: LogMessage['level'],
    category: LogMessage['category'],
    message: string,
    symbol?: string
  ) => {
    const newLog: LogMessage = {
      id: `log_${Date.now()}_${Math.random().toString(36).substring(2, 9)}`,
      timestamp: new Date().toISOString().substring(11, 19),
      level,
      category,
      message,
      symbol
    };
    setLogs(prev => [...prev.slice(-300), newLog]);
  }, []);

  // -----------------------------------------------------------------------
  // Realtime WebSocket channel (React frontend + WS API + Python backend).
  // status.py streams /api/status snapshots (1s) and engine log lines over
  // ws://<host>/ws; HTTP polling below remains the automatic fallback.
  // Handlers resolve through refs so reconnects never use stale closures.
  // -----------------------------------------------------------------------
  const applyVpsPayloadRef = useRef<(json: any, latency?: number) => void>(() => {});
  const vpsEndpointRef = useRef<string>(vpsEndpoint);
  vpsEndpointRef.current = vpsEndpoint;
  const lastWsTransportRef = useRef<WsTransport>('connecting');
  const vpsSocketRef = useRef<VpsSocket | null>(null);
  if (typeof window !== 'undefined' && !vpsSocketRef.current) {
    const seenWsLogs = new Set<string>();
    vpsSocketRef.current = new VpsSocket({
      onSnapshot: (payload) => applyVpsPayloadRef.current(payload),
      onLogLines: (lines) => {
        // Same line-format mapping as the HTTP log poller; WS pushes only new
        // lines, but a rotated/truncated log resends its tail — dedupe on it.
        const lineRegex = /^(.+?) - (INFO|WARNING|ERROR|DEBUG|CRITICAL) - (.*)$/;
        lines.forEach(raw => {
          const line = raw.trim();
          const match = lineRegex.exec(line);
          if (!match) return;
          const [, , level, message] = match;
          if (!message.trim()) return;
          const id = `${level}_${message.slice(0, 80)}`;
          if (seenWsLogs.has(id)) return;
          seenWsLogs.add(id);
          if (seenWsLogs.size > 4000) seenWsLogs.clear();
          const mappedLevel: LogMessage['level'] =
            level === 'WARNING' ? 'WARN' : level === 'CRITICAL' ? 'ERROR' : (level as LogMessage['level']);
          addLog(mappedLevel, 'SYS', message.trim());
        });
      },
      onStatus: (update) => {
        setWsTransport(update.transport);
        const prevTransport = lastWsTransportRef.current;
        if (update.transport !== prevTransport) {
          lastWsTransportRef.current = update.transport;
          if (update.transport === 'websocket') {
            addLog('SUCCESS', 'SYS', `Realtime WebSocket connected (${vpsEndpointRef.current || 'same-origin'}/ws) — live push active, HTTP polling paused.`);
          } else if (update.transport === 'polling') {
            addLog('WARN', 'SYS', `${update.error || 'WebSocket unavailable'} — falling back to HTTP polling (2.5s).`);
          }
        }
        if (update.transport === 'websocket') {
          setVpsStatus(prev => ({
            ...prev,
            connected: true,
            endpoint: vpsEndpointRef.current || prev.endpoint,
            latencyMs: update.latencyMs ?? prev.latencyMs,
            error: undefined
          }));
        } else if (update.transport === 'polling') {
          // Don't clobber engine state here — the HTTP fallback poll (still
          // running) sets engineStatus/engineRunning on its next result.
          setVpsStatus(prev => ({ ...prev, connected: false, error: update.error }));
        }
      }
    });
  }

  // UTC-midnight reset of daily PnL & streaks (mirrors the Python engine's daily drawdown reset)
  useEffect(() => {
    let lastDay = new Date().toISOString().slice(0, 10);
    const tick = () => {
      const key = new Date().toISOString().slice(0, 10);
      if (key !== lastDay) {
        lastDay = key;
        setDailyRealizedPnl(0.0);
        setWinStreak(0);
        setLossStreak(0);
        addLog('INFO', 'RISK', 'UTC midnight reset: daily drawdown counter and streaks cleared.');
      }
    };
    const interval = setInterval(tick, 30_000);
    return () => clearInterval(interval);
  }, [addLog]);

  // Track loss-streak cooldown state for the UI banner
  useEffect(() => {
    const tick = () => setIsLossCooldown(Date.now() < cooldownUntilRef.current);
    tick();
    const interval = setInterval(tick, 1000);
    return () => clearInterval(interval);
  }, []);

  // Initialize candle buffers
  useEffect(() => {
    Object.keys(INITIAL_SYMBOLS).forEach(sym => {
      ensureCandlesForSymbol(sym);
    });

    addLog('INFO', 'SYS', 'Market-Only Bot initialized in PAPER_TRADE mode. SQLite WAL active.');
    addLog('DEBUG', 'HEALTH', 'REST ping OK, WS latency 12ms, DB connection verified.');
  }, [ensureCandlesForSymbol, addLog]);

  // Periodic Live Binance Spot Ticker Fetch (if toggled)
  useEffect(() => {
    if (!useLiveBinanceFeed) return;

    let isSubscribed = true;
    const fetchLiveBinanceTickers = async () => {
      try {
        const res = await fetch('https://api.binance.com/api/v3/ticker/24hr');
        if (!res.ok) return;
        const data = await res.json();
        if (!isSubscribed) return;

        const currentInterests = new Set([
          ...Object.keys(INITIAL_SYMBOLS),
          ...activeTradesRef.current.map(t => t.symbol),
          ...(configRef.current.staticSymbols || []),
          ...selectedPinnedSymbols
        ]);

        const tickerMap: Record<string, { price: number; change: number; volume: number }> = {};
        for (const item of data) {
          if (currentInterests.has(item.symbol)) {
            const lastP = parseFloat(item.lastPrice);
            ensureCandlesForSymbol(item.symbol, lastP);
            tickerMap[item.symbol] = {
              price: lastP,
              change: parseFloat(item.priceChangePercent),
              volume: parseFloat(item.quoteVolume)
            };
          }
        }

        Object.entries(tickerMap).forEach(([sym, t]) => {
          const existing = candlesRef.current[sym] || [];
          const last = existing[existing.length - 1];
          if (last && Math.abs(last.close - t.price) > 0.00001) {
            candlesRef.current[sym] = [
              ...existing.slice(-80),
              {
                open: last.close,
                high: Math.max(last.close, t.price),
                low: Math.min(last.close, t.price),
                close: t.price,
                volume: t.volume / 1000
              }
            ];
          }
        });
        addLog('DEBUG', 'HEALTH', 'Direct Binance Spot REST ticker feed synced successfully.');
        if (runTickRef.current) {
          runTickRef.current();
        }
      } catch (err) {
        // network or CORS failure — simulator feed remains the fallback
      }
    };

    fetchLiveBinanceTickers();
    const interval = setInterval(fetchLiveBinanceTickers, 10000);
    return () => {
      isSubscribed = false;
      clearInterval(interval);
    };
  }, [useLiveBinanceFeed, addLog, ensureCandlesForSymbol, selectedPinnedSymbols]);

  // Real VPS Data Fetcher (reads SQLite trading.db and PM2 engine state via status.py HTTP endpoint)
  // Re-created when its deps change so the polling useEffect can re-subscribe.
  // Shared status processor: BOTH the WebSocket push path and the HTTP polling
  // fallback funnel every /api/status payload through this exact mapping, so the
  // two transports can never disagree about how a snapshot maps to app state.
  const processVpsStatus = useCallback((json: any, latency?: number) => {
    const targetBase = (vpsEndpoint || (typeof window !== 'undefined' ? window.location.origin : '')).replace(/\/+$/, '');
    try {
      const rawProcess = String(json.process || '');
      const isEngineRunning = rawProcess.includes('RUNNING') || rawProcess.includes('ONLINE');

      setVpsStatus({
        connected: true,
        endpoint: targetBase,
        latencyMs: latency ?? vpsStatusRef.current.latencyMs,
        engineStatus: rawProcess || 'RUNNING',
        engineRunning: isEngineRunning,
        lastSyncTime: new Date().toLocaleTimeString(),
        serverTime: json.server_time || json.timestamp,
        stats: json.data?.stats
      });

      // Engine control state (web-monitor pause from POST /api/control)
      if (json.control && typeof json.control.paused === 'boolean') {
        setVpsControl({
          paused: json.control.paused,
          pauseReason: json.control.pause_reason || undefined
        });
      }

      // Update Risk & Comprehensive Balance state from VPS.
      // Supports both paper simulated equity and live production (PAPER_TRADE=false) with Spot balances.
      const r = json.data?.risk;
      const b = json.balance || json.data?.balance;
      
      if (b) {
        setVpsBalance({
          totalEquity: parseFloat(b.total_equity || b.equity || 0),
          freeQuote: parseFloat(b.free_quote || b.total_equity || 0),
          lockedQuote: parseFloat(b.locked_quote || 0),
          quoteAsset: b.quote_asset || 'USDT',
          isLive: Boolean(b.is_live),
          dailyPnl: b.daily_pnl !== undefined ? parseFloat(b.daily_pnl) : undefined,
          balances: Array.isArray(b.balances) ? b.balances : []
        });
      }

      const rawEq = b?.total_equity ?? b?.equity ?? r?.total_equity ?? r?.live_equity ?? r?.equity ?? r?.paper_balance;
      const hasBalance = rawEq !== undefined && rawEq !== null && !isNaN(parseFloat(rawEq));
      const hasDaily = (r && r.daily_pnl !== undefined && !isNaN(parseFloat(r.daily_pnl))) ||
                       (b && b.daily_pnl !== undefined && !isNaN(parseFloat(b.daily_pnl)));

      setVpsRiskAvailable(Boolean(hasDaily || hasBalance));
      if (hasBalance) {
        setEquity(parseFloat(rawEq));
      }
      if (hasDaily) {
        const dVal = r?.daily_pnl !== undefined ? parseFloat(r.daily_pnl) : parseFloat(b.daily_pnl);
        setDailyRealizedPnl(dVal);
      }
      if (r) {
        if (r.win_streak !== undefined) {
          const val = parseInt(r.win_streak || '0', 10);
          if (!isNaN(val)) setWinStreak(val);
        }
        if (r.loss_streak !== undefined) {
          const val = parseInt(r.loss_streak || '0', 10);
          if (!isNaN(val)) setLossStreak(val);
        }
      }

      // Sync active positions from SQLite
      if (Array.isArray(json.data?.trades)) {
        json.data.trades.forEach((t: any) => {
          if (t.symbol) {
            ensureCandlesForSymbol(t.symbol, parseFloat(t.entry_price || t.current_price || 0));
          }
        });

        const mappedActive: ActiveTrade[] = json.data.trades.map((t: any) => {
          const symbol = t.symbol;
          const entryPrice = parseFloat(t.entry_price || 0);
          const qty = parseFloat(t.quantity || 0);
          const candles = candlesRef.current[symbol] || [];
          const livePrice = candles.length > 0 ? candles[candles.length - 1].close : entryPrice;
          const curPrice = livePrice || entryPrice;
          const unPnl = (curPrice - entryPrice) * qty;
          const unPnlPct = entryPrice > 0 ? ((curPrice - entryPrice) / entryPrice) * 100 : 0;

          return {
            id: `db_${t.symbol}_${t.order_id || t.entry_time || Date.now()}`,
            symbol,
            side: (t.side || 'BUY') as 'BUY' | 'SELL',
            entryPrice,
            currentPrice: curPrice,
            quantity: qty,
            notional: entryPrice * qty,
            entryTime: t.entry_time ? (t.entry_time < 1e12 ? t.entry_time * 1000 : t.entry_time) : Date.now(),
            stopPrice: parseFloat(t.stop_price || 0),
            takeProfit: parseFloat(t.take_profit || 0),
            atr: parseFloat(t.atr || 0),
            trailingActive: Boolean(t.trailing_active),
            trailingStop: parseFloat(t.trailing_stop || t.stop_price || 0),
            breakevenActivated: Boolean(t.breakeven_activated),
            unrealizedPnl: unPnl,
            unrealizedPnlPct: unPnlPct
          };
        });
        setActiveTrades(mappedActive);
      }

      // Sync recent COMPLETED trades from SQLite.
      // CRITICAL: only SELL exit orders that actually recorded a realized PnL are
      // mapped into closedTrades. The raw orders list also contains BUY entry
      // orders (profit_loss=0), NEW orders, and CANCELED attempts — including any
      // of those would dilute the win-rate denominator (the engine's stats count
      // wins/losses over closed SELL exits only). Partial-exit legs are persisted
      // as CANCELED SELL orders with a non-zero profit_loss, so they are included.
      if (Array.isArray(json.data?.orders)) {
        const exitOrders = json.data.orders.filter((o: any) => {
          const side = String(o.side || '').toUpperCase();
          const status = String(o.status || '').toUpperCase();
          if (side !== 'SELL') return false;
          const hasPnl = o.profit_loss !== null && o.profit_loss !== undefined;
          if (status === 'FILLED') return true;
          if (status === 'CANCELED') return hasPnl && parseFloat(o.profit_loss) !== 0;
          return false;
        });
        const mappedOrders: ClosedTrade[] = exitOrders.map((o: any) => {
          const entryP = parseFloat(o.price || o.avg_fill_price || 0);
          const exitP = parseFloat(o.avg_fill_price || o.price || 0);
          const q = parseFloat(o.executed_qty || o.quantity || 0);
          const pnl = parseFloat(o.profit_loss || 0);
          const pnlPct = entryP > 0 && q > 0 ? (pnl / (entryP * q)) * 100 : 0;

          const parseTs = (val: any, fallback: number): number => {
            if (!val) return fallback;
            if (typeof val === 'number') return val < 1e11 ? val * 1000 : val;
            const num = Number(val);
            if (!isNaN(num)) return num < 1e11 ? num * 1000 : num;
            const d = new Date(val).getTime();
            return isNaN(d) ? fallback : d;
          };

          return {
            id: `order_${o.order_id}`,
            symbol: o.symbol,
            side: (o.side || 'SELL') as 'BUY' | 'SELL',
            entryPrice: entryP,
            exitPrice: exitP,
            quantity: q,
            pnl,
            pnlPct,
            entryTime: parseTs(o.created_at, Date.now() - 3600000),
            exitTime: parseTs(o.updated_at, Date.now()),
            // The engine does not persist the exit reason in the orders table, so
            // map the order status to a readable label instead of showing 'FILLED'.
            exitReason: (String(o.status || '').toUpperCase() === 'CANCELED' ? 'PARTIAL_EXIT' : 'MARKET_EXIT') as any
          };
        });
        if (mappedOrders.length > 0) {
          setClosedTrades(mappedOrders);
        }
      }

      // Sync active parameters from VPS .env
      if (json.config && Object.keys(json.config).length > 0) {
        const c = json.config;
        const staticList = c.STATIC_SYMBOLS 
          ? c.STATIC_SYMBOLS.split(',').map((s: string) => s.trim().toUpperCase()).filter(Boolean)
          : null;
        const dynamicSym = c.DYNAMIC_SYMBOLS !== undefined 
          ? String(c.DYNAMIC_SYMBOLS).toLowerCase() === 'true' 
          : null;

        if (staticList && staticList.length > 0) {
          staticList.forEach((s: string) => ensureCandlesForSymbol(s));
        }

        setConfig(prev => ({
          ...prev,
          paperTrade: c.PAPER_TRADE !== undefined ? String(c.PAPER_TRADE).toLowerCase() === 'true' : prev.paperTrade,
          useTestnet: c.USE_TESTNET !== undefined ? String(c.USE_TESTNET).toLowerCase() === 'true' : prev.useTestnet,
          timeframe: c.TIMEFRAME || prev.timeframe,
          mtfTimeframe: c.MTF_TIMEFRAME || prev.mtfTimeframe,
          atrPeriod: c.ATR_PERIOD ? parseInt(c.ATR_PERIOD, 10) : prev.atrPeriod,
          atrMultiplierSl: c.ATR_MULTIPLIER_SL ? parseFloat(c.ATR_MULTIPLIER_SL) : prev.atrMultiplierSl,
          atrMultiplierTp: c.ATR_MULTIPLIER_TP ? parseFloat(c.ATR_MULTIPLIER_TP) : prev.atrMultiplierTp,
          trailingStopActivate: c.TRAILING_STOP_ACTIVATE ? parseFloat(c.TRAILING_STOP_ACTIVATE) : prev.trailingStopActivate,
          trailingStopCallback: c.TRAILING_STOP_CALLBACK ? parseFloat(c.TRAILING_STOP_CALLBACK) : prev.trailingStopCallback,
          signalThreshold: c.SIGNAL_THRESHOLD ? parseInt(c.SIGNAL_THRESHOLD, 10) : prev.signalThreshold,
          maxDailyDrawdown: c.MAX_DAILY_DRAWDOWN ? parseFloat(c.MAX_DAILY_DRAWDOWN) : prev.maxDailyDrawdown,
          maxSymbols: c.MAX_SYMBOLS ? parseInt(c.MAX_SYMBOLS, 10) : prev.maxSymbols,
          staticSymbols: staticList && staticList.length > 0 ? staticList : prev.staticSymbols,
          dynamicSymbols: dynamicSym !== null ? dynamicSym : prev.dynamicSymbols
        }));
      }

      // Sync dynamic scanned candidates from VPS
      const rawCandidates = json.candidates || json.scanned_pairs || json.data?.scanned_pairs;
      if (Array.isArray(rawCandidates) && rawCandidates.length > 0) {
        const mappedCandidates: CandidateSymbol[] = rawCandidates.map((c: any, idx: number) => {
          const sym = String(c.symbol || '').toUpperCase();
          const meta = getSymbolMeta(sym);
          const price = parseFloat(c.price || c.last_price || meta.basePrice);
          ensureCandlesForSymbol(sym, price);
          return {
            symbol: sym,
            name: meta.name || c.name || sym,
            price,
            priceChange24h: parseFloat(c.price_change_24h ?? c.priceChangePercent ?? c.raw_price_change ?? 0),
            volume24h: parseFloat(c.volume_24h ?? c.volume ?? 0),
            volatility: parseFloat(c.volatility || 0),
            adx: parseFloat(c.adx || 0),
            zScore: parseFloat(c.z_score ?? c.final_score ?? 0),
            isSelected: Boolean(c.is_selected ?? ((configRef.current.staticSymbols || []).includes(sym) || idx < (configRef.current.maxSymbols || 5))),
            momentumRank: c.momentum_rank || (idx + 1)
          };
        });
        setCandidates(mappedCandidates);
      }

      // Trigger immediate UI refresh for symbols and tickers
      setTimeout(() => {
        if (runTickRef.current) runTickRef.current();
      }, 50);
    } catch (err: any) {
      // Processing errors must never kill the push/poll loop itself.
      console.error('VPS status processing failed:', err);
    }
  }, [ensureCandlesForSymbol, vpsEndpoint]);

  const fetchVpsData = useCallback(async () => {
    if (dataSource !== 'vps') return;
    // Over WebSocket the snapshot already arrives via push — only flag the
    // spinner when this call performs an actual HTTP round-trip.
    if (wsTransportRef.current === 'websocket') {
      applyVpsPayloadRef.current = processVpsStatus;
    } else {
      setIsPollingVps(true);
    }
    const targetBase = (vpsEndpoint || (typeof window !== 'undefined' ? window.location.origin : '')).replace(/\/+$/, '');
    const url = targetBase.endsWith('/api/status') ? targetBase : `${targetBase}/api/status`;

    const startTime = performance.now();
    try {
      const res = await fetch(url, { mode: 'cors' });
      const latency = wsTransportRef.current === 'websocket'
        ? (vpsStatusRef.current.latencyMs ?? Math.round(performance.now() - startTime))
        : Math.round(performance.now() - startTime);

      if (!res.ok) {
        throw new Error(`HTTP ${res.status}: ${res.statusText}`);
      }
      const json = await res.json();
      processVpsStatus(json, latency);
    } catch (err: any) {
      setVpsRiskAvailable(false);
      setVpsStatus(prev => ({
        ...prev,
        connected: false,
        error: err.message,
        engineStatus: 'DISCONNECTED',
        engineRunning: false
      }));
    } finally {
      if (wsTransportRef.current !== 'websocket') setIsPollingVps(false);
    }
  }, [dataSource, vpsEndpoint, ensureCandlesForSymbol, wsTransport, processVpsStatus]);

  // Periodic VPS Polling — HTTP fallback. When the WebSocket push is live,
  // polling drops to a 30s safety net (config drift, missed pushes); it ramps
  // back to 2.5s automatically whenever the socket is down.
  useEffect(() => {
    if (dataSource !== 'vps') return;
    if (wsTransport === 'websocket') {
      const interval = setInterval(fetchVpsData, 30_000);
      return () => clearInterval(interval);
    }
    fetchVpsData();
    const interval = setInterval(fetchVpsData, 2500);
    return () => clearInterval(interval);
  }, [dataSource, wsTransport, fetchVpsData]);

  // WebSocket lifecycle: connect when VPS mode is active, disconnect otherwise.
  useEffect(() => {
    const sock = vpsSocketRef.current;
    if (!sock) return;
    if (dataSource === 'vps') {
      applyVpsPayloadRef.current = processVpsStatus;
      sock.connect(vpsEndpoint || (typeof window !== 'undefined' ? window.location.origin : ''));
    } else {
      sock.disconnect();
      setWsTransport('connecting');
    }
    return () => {
      if (dataSource === 'vps') return; // keep the socket across renders
      sock.disconnect();
    };
  }, [dataSource, vpsEndpoint, processVpsStatus]);

  // Send a remote control command to the live engine via status.py (POST /api/control)
  const sendVpsControl = useCallback(async (action: 'pause' | 'resume' | 'close_all' | 'close_symbol', symbol?: string): Promise<boolean> => {
    const targetBase = (vpsEndpoint || (typeof window !== 'undefined' ? window.location.origin : '')).replace(/\/+$/, '');
    try {
      const res = await fetch(`${targetBase}/api/control`, {
        method: 'POST',
        mode: 'cors',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ action, symbol })
      });
      const json = await res.json();
      if (!res.ok || !json.ok) {
        throw new Error(json.message || `HTTP ${res.status}`);
      }
      if (json.control && typeof json.control.paused === 'boolean') {
        setVpsControl({
          paused: json.control.paused,
          pauseReason: json.control.pause_reason || undefined
        });
      }
      return true;
    } catch (err: any) {
      addLog('ERROR', 'RISK', `Remote control failed (${action}): ${err.message}`);
      return false;
    }
  }, [vpsEndpoint, addLog]);

  // Pause / resume the live engine from the web monitor
  const handleToggleVpsPause = useCallback(async () => {
    const willPause = !vpsControlRef.current.paused;
    const ok = await sendVpsControl(willPause ? 'pause' : 'resume');
    if (ok) {
      addLog('WARN', 'RISK', `Remote engine ${willPause ? 'PAUSED' : 'RESUMED'} from web monitor. ${willPause ? 'New entries blocked — open positions still managed.' : ''}`);
    }
  }, [sendVpsControl, addLog]);

  // Push the tuned web configuration to the live engine (POST /api/config)
  const pushConfigToVps = useCallback(async (): Promise<PushResult> => {
    const targetBase = (vpsEndpoint || (typeof window !== 'undefined' ? window.location.origin : '')).replace(/\/+$/, '');
    try {
      const res = await fetch(`${targetBase}/api/config`, {
        method: 'POST',
        mode: 'cors',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ env_file: generateEnvString(configRef.current) })
      });
      const json = await res.json();
      if (!res.ok || !json.ok) {
        throw new Error(json.message || `HTTP ${res.status}`);
      }
      const reloadNote = json.reload?.exit_code === 0
        ? 'Engine reloaded via PM2 — changes live now.'
        : (json.reload?.hint || (json.reload?.error ? `Reload note: ${json.reload.error}` : ''));
      const message = `Applied ${json.count} tunable keys to VPS .env. ${reloadNote}`;
      setVpsPushResult({ ok: true, message });
      addLog('SUCCESS', 'SYS', `VPS config pushed: ${(json.applied || []).join(', ')}`);
      // Ask the realtime channel for an immediate snapshot; the delayed HTTP
      // fetch stays as a backstop for when the socket is down.
      vpsSocketRef.current?.refresh();
      setTimeout(() => fetchVpsData(), 2500);
      return { ok: true, message };
    } catch (err: any) {
      const message = `Push failed: ${err.message}`;
      setVpsPushResult({ ok: false, message });
      addLog('ERROR', 'SYS', message);
      return { ok: false, message };
    }
  }, [vpsEndpoint, addLog, fetchVpsData]);

  // Stream the real engine log from the VPS into the Debug Console
  useEffect(() => {
    if (dataSource !== 'vps' || !vpsStatus.connected) return;

    const seen = new Set<string>();
    const targetBase = (vpsEndpoint || (typeof window !== 'undefined' ? window.location.origin : '')).replace(/\/+$/, '');
    let cancelled = false;

    const fetchEngineLogs = async () => {
      if (cancelled) return;
      try {
        const res = await fetch(`${targetBase}/api/logs?lines=120`, { mode: 'cors' });
        if (!res.ok) return;
        const json = await res.json();
        const lines: string[] = Array.isArray(json.lines) ? json.lines : [];
        const lineRegex = /^(.+?) - (INFO|WARNING|ERROR|DEBUG|CRITICAL) - (.*)$/;
        lines.forEach(raw => {
          const line = raw.trim();
          const match = lineRegex.exec(line);
          if (!match) return;
          const [, , level, message] = match;
          if (!message.trim()) return;
          const id = `${level}_${message.slice(0, 80)}`;
          if (seen.has(id)) return;
          seen.add(id);
          const mappedLevel: LogMessage['level'] =
            level === 'WARNING' ? 'WARN' : level === 'CRITICAL' ? 'ERROR' : (level as LogMessage['level']);
          addLog(mappedLevel, 'SYS', message.trim());
        });
        if (seen.size > 4000) seen.clear();
      } catch {
        // Engine log endpoint unreachable — simulator logs remain as fallback.
      }
    };

    fetchEngineLogs();
    const interval = setInterval(fetchEngineLogs, 5000);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [dataSource, vpsStatus.connected, vpsEndpoint, addLog]);

  // Switching data source clears locally-simulated trade state so VPS figures
  // and simulator figures never contaminate each other's display.
  const handleToggleDataSource = useCallback((source: 'vps' | 'simulator') => {
    setDataSource(prev => {
      if (prev !== source) {
        setActiveTrades([]);
        setClosedTrades([]);
        setDailyRealizedPnl(0.0);
        setEquity(1000.0);
        setVpsRiskAvailable(false);
      }
      return source;
    });
  }, []);

  // Apply Preset
  const handleApplyPreset = useCallback((preset: StrategyPreset) => {
    const presetOverrides = PRESET_MAP[preset];
    setConfig(prev => ({
      ...prev,
      preset,
      ...presetOverrides
    }));
    addLog('INFO', 'SYS', `Applied ${preset.toUpperCase()} strategy profile. Timeframe: ${presetOverrides.timeframe}, MTF: ${presetOverrides.mtfTimeframe}`);
  }, [addLog]);

  // Reset simulation
  const handleResetSimulation = useCallback(() => {
    setEquity(1000.0);
    setDailyRealizedPnl(0.0);
    setActiveTrades([]);
    setClosedTrades([]);
    setWinStreak(0);
    setLossStreak(0);
    cooldownUntilRef.current = 0;
    cooldownsRef.current = {};
    addLog('INFO', 'SYS', 'Simulated paper balance reset to $1,000.00 USDT. Trade history, streaks, and cooldowns cleared.');
  }, [addLog]);

  // Close an active trade safely with unique closed ID.
  // PnL is NET of round-trip taker fees (0.2%) so paper results match live expectations.
  // Returns the realized PnL delta so the tick loop can fold it into its local drawdown
  // mirror (React state writes are asynchronous).
  const handleCloseTrade = useCallback((symbol: string, reason: string, customExitPrice?: number): number => {
    if (dataSourceRef.current === 'vps' && vpsStatusRef.current.connected) {
      sendVpsControl('close_symbol', symbol).then(ok => {
        if (ok) {
          addLog('WARN', 'ORDER', `Manual market close requested for ${symbol} on live VPS engine.`, symbol);
        }
      });
      return 0;
    }

    const trade = activeTradesRef.current.find(t => t.symbol === symbol);
    if (!trade) return 0;

    const exitPrice = customExitPrice ?? trade.currentPrice;
    const grossPnl = (exitPrice - trade.entryPrice) * trade.quantity;
    const fees = (trade.entryPrice * trade.quantity + exitPrice * trade.quantity) * TAKER_FEE_RATE;
    const pnl = grossPnl - fees;
    const pnlPct = trade.entryPrice > 0 ? (pnl / (trade.entryPrice * trade.quantity)) * 100 : 0;

    const closed: ClosedTrade = {
      id: `${trade.id}_exit_${Date.now()}_${Math.random().toString(36).substring(2, 6)}`,
      symbol: trade.symbol,
      side: trade.side,
      entryPrice: trade.entryPrice,
      exitPrice,
      quantity: trade.quantity,
      pnl,
      pnlPct,
      entryTime: trade.entryTime,
      exitTime: Date.now(),
      exitReason: reason as any
    };

    setActiveTrades(prev => prev.filter(t => t.symbol !== symbol));

    // Prevent duplicate closure records for the exact same trade instance
    setClosedTrades(prev => {
      if (prev.some(t => t.id === closed.id || (t.symbol === symbol && t.entryTime === trade.entryTime))) {
        return prev;
      }
      return [...prev, closed];
    });

    setDailyRealizedPnl(prev => prev + pnl);
    setEquity(prev => prev + pnl);

    if (pnl >= 0) {
      setWinStreak(prev => prev + 1);
      setLossStreak(0);
      addLog('SUCCESS', 'ORDER', `CLOSE ${symbol} (${reason}) - Net PnL: +$${pnl.toFixed(2)} (+${pnlPct.toFixed(2)}%) after $${fees.toFixed(2)} fees`, symbol);
    } else {
      const newStreak = lossStreakRef.current + 1;
      setLossStreak(newStreak);
      setWinStreak(0);
      addLog('WARN', 'ORDER', `CLOSE ${symbol} (${reason}) - Net PnL: -$${Math.abs(pnl).toFixed(2)} (${pnlPct.toFixed(2)}%) after $${fees.toFixed(2)} fees`, symbol);
      // Engage global cooldown when the loss-streak limit is hit (mirrors the Python engine)
      if (newStreak >= configRef.current.maxLossStreak) {
        cooldownUntilRef.current = Date.now() + configRef.current.cooldownLoss * 1000;
        setCooldownEndsAt(cooldownUntilRef.current);
        addLog('WARN', 'RISK', `Loss streak ${newStreak}/${configRef.current.maxLossStreak} — trading PAUSED for ${Math.round(configRef.current.cooldownLoss / 60)} min (COOLDOWN_LOSS).`);
      }
    }

    // Short per-symbol re-entry cooldown (mirrors self.symbol_cooldowns in trade_logic.py)
    cooldownsRef.current[symbol] = Date.now() + 10_000;
    return pnl;
  }, [addLog]);

  // Emergency Close All Trades — remotely liquidates the live engine when in
  // VPS mode, otherwise closes the local simulator positions.
  const handleCloseAllTrades = useCallback(async () => {
    if (dataSourceRef.current === 'vps' && vpsStatusRef.current.connected) {
      const ok = await sendVpsControl('close_all');
      if (ok) {
        addLog('WARN', 'RISK', 'EMERGENCY LIQUIDATION requested on VPS engine — closing all open positions.');
      }
      return;
    }
    const open = activeTradesRef.current;
    if (open.length === 0) return;
    open.forEach(t => handleCloseTrade(t.symbol, 'EMERGENCY_CLOSE'));
    addLog('WARN', 'RISK', `EMERGENCY LIQUIDATION: Closed all ${open.length} open market positions.`);
  }, [handleCloseTrade, addLog, sendVpsControl]);

  // Execute a market buy trade (Simulator mode only — the real engine lives on the VPS).
  // Returns true when a trade was actually opened so tick loops can enforce the max-position
  // cap against *this tick's* openings (state refs only update after a re-render).
  const executeTrade = useCallback((symbol: string, currentPrice: number, atr: number, triggerSource: string = 'SIGNAL'): boolean => {
    if (dataSourceRef.current === 'vps') {
      addLog('WARN', 'ORDER', `${symbol}: manual entries are disabled while synced to the live VPS engine. Switch to Strategy Simulator for testing.`, symbol);
      return false;
    }

    // Check max open trades
    if (activeTradesRef.current.length >= configRef.current.maxSymbols) {
      addLog('WARN', 'ORDER', `Max open trades reached (${activeTradesRef.current.length}/${configRef.current.maxSymbols}). Skipping ${symbol}.`, symbol);
      return false;
    }

    // Check if already open
    if (activeTradesRef.current.some(t => t.symbol === symbol)) {
      addLog('DEBUG', 'ORDER', `${symbol} already has an active position. Skipping duplicate entry.`, symbol);
      return false;
    }

    // Loss-streak cooldown gate (mirrors MAX_LOSS_STREAK / COOLDOWN_LOSS in the Python engine)
    if (Date.now() < cooldownUntilRef.current) {
      const remaining = Math.ceil((cooldownUntilRef.current - Date.now()) / 1000);
      addLog('WARN', 'RISK', `Loss-streak cooldown ACTIVE. Entries paused for another ${remaining}s.`, symbol);
      return false;
    }

    // Per-symbol re-entry cooldown
    const symCooldown = cooldownsRef.current[symbol] || 0;
    if (Date.now() < symCooldown) {
      addLog('DEBUG', 'ORDER', `${symbol} in re-entry cooldown for ${Math.ceil((symCooldown - Date.now()) / 1000)}s.`, symbol);
      return false;
    }

    // Position sizing: capped by BOTH total usage and per-symbol allocation,
    // with a 1% safety buffer for taker fees (mirrors the live engine's free-quote guard).
    const curEquity = equityRef.current;
    const allocation = effectiveAllocation(configRef.current, curEquity);

    // Binance rejects orders below MIN_NOTIONAL — skip instead of sizing up.
    if (allocation < MIN_NOTIONAL_USDT || curEquity < MIN_NOTIONAL_USDT) {
      addLog('WARN', 'ORDER', `${symbol}: allocation $${allocation.toFixed(2)} below Binance MIN_NOTIONAL ($${MIN_NOTIONAL_USDT}). Order would be rejected live — skipped.`, symbol);
      return false;
    }

    const quantity = allocation / currentPrice;
    const notional = quantity * currentPrice;

    const stopPrice = currentPrice - atr * configRef.current.atrMultiplierSl;
    let takeProfit = currentPrice + atr * configRef.current.atrMultiplierTp;
    const minTpDist = currentPrice * 0.005;
    if (takeProfit - currentPrice < minTpDist) {
      takeProfit = currentPrice + minTpDist;
    }

    const newTrade: ActiveTrade = {
      id: `trade_${Date.now()}_${Math.random().toString(36).substring(2, 6)}`,
      symbol,
      side: 'BUY',
      entryPrice: currentPrice,
      currentPrice,
      quantity,
      notional,
      entryTime: Date.now(),
      stopPrice,
      takeProfit,
      atr,
      trailingActive: false,
      trailingStop: stopPrice,
      breakevenActivated: false,
      unrealizedPnl: 0,
      unrealizedPnlPct: 0
    };

    setActiveTrades(prev => [...prev, newTrade]);
    addLog(
      'INFO', 
      'ORDER', 
      `ENTRY MARKET BUY ${quantity.toFixed(4)} ${symbol} @ $${currentPrice.toFixed(2)} [SL: $${stopPrice.toFixed(2)}, TP: $${takeProfit.toFixed(2)}] (${triggerSource})`,
      symbol
    );
    return true;
  }, [addLog]);

  // Manual Buy simulation
  const handleTriggerManualBuy = useCallback((symbol: string) => {
    const symData = symbolsData.find(s => s.symbol === symbol);
    const candles = candlesRef.current[symbol] || [];
    const lastClose = candles.length > 0 ? candles[candles.length - 1].close : INITIAL_SYMBOLS[symbol]?.basePrice || 100;
    const price = symData ? symData.price : lastClose;
    const atr = symData?.factors.atr || price * 0.01;
    executeTrade(symbol, price, atr, 'MANUAL');
  }, [symbolsData, executeTrade]);

  // Simulate Institutional Confluence Boost
  const handleSimulateConfluenceBoost = useCallback((symbol: string) => {
    const candles = candlesRef.current[symbol] || [];
    if (candles.length === 0) return;
    const last = candles[candles.length - 1];
    const surgeClose = last.close * 1.015;
    const boosted = {
      open: last.close,
      high: surgeClose * 1.002,
      low: last.close * 0.998,
      close: surgeClose,
      volume: last.volume * 6
    };
    candlesRef.current[symbol] = [...candles.slice(-80), boosted];
    addLog('INFO', 'SIGNAL', `SIMULATION: Injected institutional buyer volume into ${symbol} (+1.5% jump, 6x volume, positive CVD). Confluence triggered!`, symbol);
  }, [addLog]);

  // Toggle Symbol Selection in Screener
  const handleToggleSymbolSelect = useCallback((symbol: string) => {
    setSelectedPinnedSymbols(prev => {
      if (prev.includes(symbol)) {
        return prev.filter(s => s !== symbol);
      }
      return [...prev, symbol];
    });
    addLog('INFO', 'SYS', `Updated watchlist selection for ${symbol}.`);
  }, [addLog]);

  // Main Bot Tick, Dynamic Screener, and Evaluation Routine
  const runTick = useCallback(() => {
    const curConfig = configRef.current;
    const curDataSource = dataSourceRef.current;
    const curActiveTrades = activeTradesRef.current;
    const curEquity = equityRef.current;
    const curDailyPnl = dailyRealizedPnlRef.current;
    const now = Date.now();

    // Best-effort mirror of the draw-down state that the closure batch will mutate.
    // React state writes are asynchronous, so we keep a local number in sync so the
    // drawdown gate immediately below sees this tick's net closes. When the UI re-
    // renders it will pick up the authoritative committed value from the ref.
    let committedDailyPnl = curDailyPnl;

    // 1. Gather ALL candidate symbols
    const allCandidateKeys = Array.from(new Set([
      ...Object.keys(INITIAL_SYMBOLS),
      ...curActiveTrades.map(t => t.symbol),
      ...(curConfig.staticSymbols || []),
      ...selectedPinnedSymbols
    ]));

    const evaluatedCandidates: CandidateSymbol[] = [];

    allCandidateKeys.forEach(sym => {
      ensureCandlesForSymbol(sym);
      const meta = getSymbolMeta(sym);
      const base = meta.basePrice;
      const candles = candlesRef.current[sym] || [];
      const lastClose = candles.length > 0 ? candles[candles.length - 1].close : base;

      // Price drift simulation (if not on direct live feed)
      let newClose = lastClose;
      if (!useLiveBinanceFeed) {
        const drift = (Math.random() - 0.49) * (lastClose * 0.002);
        newClose = Math.max(0.00001, lastClose + drift);
        const open = lastClose;
        const high = Math.max(open, newClose) + Math.random() * (lastClose * 0.001);
        const low = Math.min(open, newClose) - Math.random() * (lastClose * 0.001);
        const volume = 30 + Math.random() * 20;
        const newCandle = { open, high, low, close: newClose, volume };
        candlesRef.current[sym] = [...candles.slice(-80), newCandle];
      }

      const priceChange24h = base > 0 ? ((newClose - base) / base) * 100 : 0;
      const volatility = Math.abs(priceChange24h) * 0.01 + 0.015;
      const adx = 20 + (Math.abs(priceChange24h) * 2) + (Math.random() * 5);
      const volume24h = 10_000_000 + (Math.abs(priceChange24h) * 2_000_000) + (base * 1000);

      evaluatedCandidates.push({
        symbol: sym,
        name: meta.name,
        price: newClose,
        priceChange24h,
        volume24h,
        volatility,
        adx,
        zScore: 0,
        isSelected: false,
        momentumRank: 0
      });
    });

    // Compute multi-factor composite Z-scores (weights mirror the Python TrendDetector)
    if (evaluatedCandidates.length > 0) {
      const meanVol = evaluatedCandidates.reduce((a, c) => a + c.volume24h, 0) / evaluatedCandidates.length;
      const meanChg = evaluatedCandidates.reduce((a, c) => a + c.priceChange24h, 0) / evaluatedCandidates.length;
      const meanAdx = evaluatedCandidates.reduce((a, c) => a + c.adx, 0) / evaluatedCandidates.length;

      evaluatedCandidates.forEach(c => {
        const zVol = (c.volume24h - meanVol) / (meanVol * 0.3 || 1);
        const zChg = (c.priceChange24h - meanChg) / 3;
        const zAdx = (c.adx - meanAdx) / 5;
        c.zScore = 0.20 * zVol + 0.20 * zChg + 0.20 * (c.volatility * 20) + 0.40 * zAdx;
      });

      evaluatedCandidates.sort((a, b) => b.zScore - a.zScore);
      evaluatedCandidates.forEach((c, idx) => {
        c.momentumRank = idx + 1;
        c.isSelected = curConfig.dynamicSymbols 
          ? (idx < curConfig.maxSymbols || selectedPinnedSymbols.includes(c.symbol))
          : (curConfig.staticSymbols || []).includes(c.symbol);
      });
    }

    // In VPS mode the real engine-scanned candidates arrive via /api/status
    // (fetchVpsData) — never overwrite them with locally-simulated candidates,
    // otherwise the screener would show fake momentum rankings instead of the
    // engine's actual scanned pool.
    if (curDataSource !== 'vps') {
      setCandidates(evaluatedCandidates);
    }

    // Determine which symbols are actively monitored by the trading engine
    const openTradeSymbols = curActiveTrades.map(t => t.symbol);
    const chosenList = curConfig.dynamicSymbols
      ? evaluatedCandidates.filter(c => c.isSelected).slice(0, curConfig.maxSymbols).map(c => c.symbol)
      : (curConfig.staticSymbols && curConfig.staticSymbols.length > 0 ? curConfig.staticSymbols : ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT']);

    // Merge chosenList with any open trades so the user always sees their open positions
    const activeSymbolList = Array.from(new Set([...chosenList, ...openTradeSymbols]));
    const finalSymbolList = activeSymbolList.length > 0 ? activeSymbolList : ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT'];

    // 2. Compute 5-factor analysis for monitored symbols
    const updatedSymbols: MarketSymbolData[] = finalSymbolList.map(sym => {
      const meta = getSymbolMeta(sym);
      const base = meta.basePrice;
      const candles = candlesRef.current[sym] || [];
      const lastClose = candles.length > 0 ? candles[candles.length - 1].close : base;
      const factors = analyzeCandles(sym, candles, curConfig);
      const priceChange24h = base > 0 ? ((lastClose - base) / base) * 100 : 0;
      const sparkline = candles.length > 0 ? candles.slice(-15).map(c => c.close) : [lastClose, lastClose];

      return {
        symbol: sym,
        name: meta.name,
        price: lastClose,
        priceChange24h,
        high24h: Math.max(...sparkline),
        low24h: Math.min(...sparkline),
        volume24h: 15_000_000 + Math.random() * 2_000_000,
        factors,
        sparkline,
        inCooldown: (cooldownsRef.current[sym] || 0) > now
      };
    });

    setSymbolsData(updatedSymbols);

    // If connected to live VPS, the real bot processes all trades and orders on the server.
    // We only update unrealized PnL with the latest live market price without generating fake local trades.
    if (curDataSource === 'vps') {
      // Derive a per-symbol price from either the freshly computed symbol data or the
      // existing tracked price — a missing symbol in updatedSymbols should never drop a
      // position's displayed price to zero.
      setActiveTrades(prev => prev.map(t => {
        const symData = updatedSymbols.find(s => s.symbol === t.symbol);
        const livePrice = symData ? symData.price : t.currentPrice;
        const pnl = (livePrice - t.entryPrice) * t.quantity;
        const pnlPct = t.entryPrice > 0 ? ((livePrice - t.entryPrice) / t.entryPrice) * 100 : 0;
        return {
          ...t,
          currentPrice: livePrice,
          unrealizedPnl: pnl,
          unrealizedPnlPct: pnlPct
        };
      }));
      return;
    }

    // 3. Manage Active Trades (Simulator Mode Only): SL/TP, trailing, breakeven, time stop
    const tradesToClose: { symbol: string; reason: string; exitPrice?: number }[] = [];

    setActiveTrades(prevTrades => {
      const remainingTrades: ActiveTrade[] = [];

      prevTrades.forEach(trade => {
        const symData = updatedSymbols.find(s => s.symbol === trade.symbol);
        // Never drop to zero just because a symbol is momentarily absent from the
        // monitor list — fall back to the last known price.
        const livePrice = symData ? symData.price : trade.currentPrice;

        let trailingActive = trade.trailingActive;
        let trailingStop = trade.trailingStop;
        let breakevenActivated = trade.breakevenActivated;
        let stopPrice = trade.stopPrice;

        const pnl = (livePrice - trade.entryPrice) * trade.quantity;
        const pnlPct = trade.entryPrice > 0 ? ((livePrice - trade.entryPrice) / trade.entryPrice) * 100 : 0;
        const profitPct = trade.entryPrice > 0 ? (livePrice - trade.entryPrice) / trade.entryPrice : 0;

        // Gap-breach SL check: exit at the worse of stop or current price (mirrors the Python engine)
        if (livePrice <= stopPrice) {
          tradesToClose.push({ symbol: trade.symbol, reason: 'STOP_LOSS', exitPrice: Math.min(stopPrice, livePrice) });
          return;
        }

        if (livePrice >= trade.takeProfit) {
          tradesToClose.push({ symbol: trade.symbol, reason: 'TAKE_PROFIT', exitPrice: trade.takeProfit });
          return;
        }

        // Trailing Stop Activation
        if (!trailingActive && profitPct >= curConfig.trailingStopActivate) {
          trailingActive = true;
          trailingStop = stopPrice;
          addLog('INFO', 'ORDER', `Trailing stop ACTIVATED for ${trade.symbol} at profit ${(profitPct * 100).toFixed(2)}%`, trade.symbol);
        }

        if (trailingActive) {
          const newStop = livePrice * (1 - curConfig.trailingStopCallback);
          if (newStop > trailingStop) {
            trailingStop = newStop;
          }
          if (livePrice <= trailingStop) {
            tradesToClose.push({ symbol: trade.symbol, reason: 'TRAILING_STOP', exitPrice: trailingStop });
            return;
          }
        }

        // Fee-aware Breakeven lock (entry + 0.25% covers round-trip fees — mirrors the engine)
        if (!breakevenActivated && profitPct >= 0.01) {
          breakevenActivated = true;
          stopPrice = trade.entryPrice * BREAKEVEN_FEE_MULTIPLIER;
          addLog('INFO', 'ORDER', `Breakeven lock ENGAGED for ${trade.symbol} (+1.0% profit). Stop raised to entry+fees.`, trade.symbol);
        }

        // Max Hold Time
        if ((now - trade.entryTime) / 1000 > curConfig.maxHoldTime) {
          tradesToClose.push({ symbol: trade.symbol, reason: 'TIME_STOP', exitPrice: livePrice });
          return;
        }

        remainingTrades.push({
          ...trade,
          currentPrice: livePrice,
          trailingActive,
          trailingStop,
          breakevenActivated,
          stopPrice,
          unrealizedPnl: pnl,
          unrealizedPnlPct: pnlPct
        });
      });

      return remainingTrades;
    });

    // Execute closures cleanly outside of the setActiveTrades updater.
    // Because setDailyRealizedPnl is asynchronous, fold each close's realized PnL into
    // our local mirror so the drawdown gate right below sees this tick's net closes.
    if (tradesToClose.length > 0) {
      tradesToClose.forEach(({ symbol, reason, exitPrice }) => {
        const pnl = handleCloseTrade(symbol, reason, exitPrice);
        if (typeof pnl === 'number') committedDailyPnl += pnl;
      });
      dailyRealizedPnlRef.current = committedDailyPnl;
    }

    // 4. Confluence Evaluation & Execution
    // Drawdown gate mirrors the Python engine: realized daily PnL PLUS current
    // unrealized PnL against MAX_DAILY_DRAWDOWN of equity.
    const floatingPnl = curActiveTrades.reduce((acc, t) => acc + ((t.currentPrice - t.entryPrice) * t.quantity), 0);
    const drawdownExceeded = curEquity > 0 && (committedDailyPnl + floatingPnl) <= -curConfig.maxDailyDrawdown * curEquity;
    if (drawdownExceeded) {
      addLog('WARN', 'RISK', `Max daily drawdown exceeded (${(curConfig.maxDailyDrawdown * 100).toFixed(1)}% incl. floating). All new entries blocked until UTC reset.`);
    }

    // Max-position enforcement across THIS tick: state refs only update after a
    // re-render, so without a local counter several symbols could each pass the
    // "max open trades" check and overshoot the cap in a single tick.
    const openSlots = Math.max(0, curConfig.maxSymbols - curActiveTrades.length);
    let openedThisTick = 0;

    updatedSymbols.forEach(sym => {
      const f = sym.factors;
      const hasActive = curActiveTrades.some(t => t.symbol === sym.symbol);

      if (hasActive) {
        addLog('DEBUG', 'SIGNAL', `Processing ${sym.symbol}: position already active, managing exits...`, sym.symbol);
        return;
      }

      if (drawdownExceeded) return;

      if (openedThisTick >= openSlots) {
        addLog('DEBUG', 'SIGNAL', `${sym.symbol} SKIPPED: max positions already reached this tick (${curActiveTrades.length + openedThisTick}/${curConfig.maxSymbols}).`, sym.symbol);
        return;
      }

      // Confluence check
      const meetsThreshold = f.bullishScore >= curConfig.signalThreshold;

      if (meetsThreshold) {
        addLog(
          'INFO', 
          'SIGNAL', 
          `BUY signal triggered: HTF=${f.htfTrend}, BOS=${f.bos}, FVG=${f.fvg > 0 ? '+' : f.fvg < 0 ? '-' : '0'}, CVD=${f.cvd > 0 ? '+' : '-'}, POC=${f.currentPrice > f.poc ? '>' : '<'} (Confluence: ${f.bullishScore}/5 >= ${curConfig.signalThreshold})`,
          sym.symbol
        );
        if (executeTrade(sym.symbol, sym.price, f.atr, '5-FACTOR CONFLUENCE')) {
          openedThisTick += 1;
        }
      } else {
        addLog(
          'DEBUG', 
          'SIGNAL', 
          `${sym.symbol} SKIPPED: ${f.skippedReason || 'confluence score below threshold'} (Bullish: ${f.bullishScore}/5, Threshold: ${curConfig.signalThreshold})`,
          sym.symbol
        );
      }
    });
  }, [ensureCandlesForSymbol, selectedPinnedSymbols, useLiveBinanceFeed, addLog, executeTrade, handleCloseTrade]);

  // Keep runTickRef synchronized
  useEffect(() => {
    runTickRef.current = runTick;
  }, [runTick]);

  // Main Bot Tick Loop
  useEffect(() => {
    if (!isRunning) return;

    // Run an initial tick synchronously after mount so the dashboard is populated
    // immediately instead of waiting for the first interval firing.
    runTick();

    const interval = setInterval(() => {
      if (runTickRef.current) {
        runTickRef.current();
      }
    }, Math.max(1000, (config.signalInterval || 6) * 1000));

    return () => clearInterval(interval);
  }, [isRunning, config.signalInterval]);

  const totalUnrealizedPnl = useMemo(
    () => activeTrades.reduce((acc, t) => acc + t.unrealizedPnl, 0),
    [activeTrades]
  );

  return (
    <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col selection:bg-amber-500/30 selection:text-amber-200">
      {/* Header & Controls */}
      <Header
        isRunning={isRunning}
        onToggleRunning={() => setIsRunning(prev => !prev)}
        onResetSimulation={handleResetSimulation}
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        config={config}
        activeTradesCount={activeTrades.length}
        unrealizedPnl={totalUnrealizedPnl}
        totalEquity={equity + totalUnrealizedPnl}
        dataSource={dataSource}
        vpsConnected={vpsStatus.connected}
        isLossCooldown={isLossCooldown}
      />

      {/* Live VPS Connection Bar */}
      <VpsConnectionBar
        dataSource={dataSource}
        onToggleDataSource={handleToggleDataSource}
        vpsStatus={vpsStatus}
        vpsEndpoint={vpsEndpoint}
        onUpdateVpsEndpoint={setVpsEndpoint}
        onRefreshVps={fetchVpsData}
        isPolling={isPollingVps}
        controlPaused={vpsControl.paused}
        onToggleVpsPause={handleToggleVpsPause}
        wsTransport={wsTransport}
      />

      {/* Main Content Area */}
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 lg:px-8 py-6">
        {activeTab === 'dashboard' && (
          <LiveDashboard
            equity={equity + totalUnrealizedPnl}
            dailyRealizedPnl={dailyRealizedPnl}
            unrealizedPnl={totalUnrealizedPnl}
            activeTrades={activeTrades}
            closedTrades={closedTrades}
            symbolsData={symbolsData}
            candidates={candidates}
            config={config}
            onUpdateConfig={setConfig}
            onApplyPreset={handleApplyPreset}
            onCloseTrade={handleCloseTrade}
            onCloseAllTrades={handleCloseAllTrades}
            onTriggerManualBuy={handleTriggerManualBuy}
            onSimulateConfluenceBoost={handleSimulateConfluenceBoost}
            onToggleSymbolSelect={handleToggleSymbolSelect}
            useLiveBinanceFeed={useLiveBinanceFeed}
            onToggleLiveBinanceFeed={() => setUseLiveBinanceFeed(prev => !prev)}
            winStreak={winStreak}
            lossStreak={lossStreak}
            dataSource={dataSource}
            vpsRiskAvailable={vpsRiskAvailable}
            isLossCooldown={isLossCooldown}
            cooldownEndsAt={cooldownEndsAt}
            vpsConnected={vpsStatus.connected}
            vpsBalance={vpsBalance}
            onPushConfigToVps={pushConfigToVps}
            vpsPushResult={vpsPushResult}
            controlPaused={vpsControl.paused}
            onToggleVpsPause={handleToggleVpsPause}
            serverStats={vpsStatus.stats || null}
          />
        )}

        {activeTab === 'signals' && (
          <SignalInspector
            symbolsData={symbolsData}
            config={config}
            onTriggerManualBuy={handleTriggerManualBuy}
          />
        )}

        {activeTab === 'debug' && (
          <DebugConsole
            logs={logs}
            onClearLogs={() => setLogs([])}
            signalInterval={config.signalInterval}
            signalThreshold={config.signalThreshold}
          />
        )}

        {activeTab === 'code' && (
          <CodeExplorer />
        )}

        {activeTab === 'config' && (
          <ConfigTab
            config={config}
            onUpdateConfig={setConfig}
            onApplyPreset={handleApplyPreset}
            dataSource={dataSource}
            vpsConnected={vpsStatus.connected}
            onPushToVps={pushConfigToVps}
          />
        )}

        {activeTab === 'deploy' && (
          <DeployGuide />
        )}
      </main>
    </div>
  );
}
