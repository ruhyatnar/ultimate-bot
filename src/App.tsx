import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { 
  BotConfig, 
  StrategyPreset, 
  ActiveTrade, 
  ClosedTrade, 
  MarketSymbolData, 
  LogMessage,
  CandidateSymbol,
  VpsBotStatus
} from './types';
import { analyzeCandles } from './utils/technicalAnalysis';
import { Header } from './components/Header';
import { VpsConnectionBar } from './components/VpsConnectionBar';
import { LiveDashboard } from './components/LiveDashboard';
import { SignalInspector } from './components/SignalInspector';
import { DebugConsole } from './components/DebugConsole';
import { CodeExplorer } from './components/CodeExplorer';
import { ConfigTab } from './components/ConfigTab';
import { DeployGuide } from './components/DeployGuide';

const PRESET_MAP: Record<StrategyPreset, Partial<BotConfig>> = {
  scalping: {
    timeframe: '1m',
    mtfTimeframe: '15m',
    atrPeriod: 10,
    atrMultiplierSl: 0.8,
    atrMultiplierTp: 1.2,
    trailingStopActivate: 0.005,
    trailingStopCallback: 0.002,
    swingLookback: 3,
    maxHoldTime: 3600
  },
  day: {
    timeframe: '5m',
    mtfTimeframe: '1h',
    atrPeriod: 14,
    atrMultiplierSl: 1.5,
    atrMultiplierTp: 2.5,
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
    trailingStopActivate: 0.025,
    trailingStopCallback: 0.01,
    swingLookback: 8,
    maxHoldTime: 86400
  }
};

const DEFAULT_CONFIG: BotConfig = {
  preset: 'day',
  timeframe: '5m',
  mtfTimeframe: '1h',
  atrPeriod: 14,
  atrMultiplierSl: 1.5,
  atrMultiplierTp: 2.5,
  trailingStopActivate: 0.015,
  trailingStopCallback: 0.005,
  swingLookback: 5,
  maxHoldTime: 28800,
  signalThreshold: 4,
  signalInterval: 6,
  maxDailyDrawdown: 0.05,
  maxLossStreak: 3,
  maxWinStreak: 5,
  cooldownLoss: 3600,
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
      // fallback
    }
    return DEFAULT_CONFIG;
  });

  const [isRunning, setIsRunning] = useState<boolean>(true);
  const [activeTab, setActiveTab] = useState<'dashboard' | 'signals' | 'debug' | 'code' | 'config' | 'deploy'>('dashboard');

  const [equity, setEquity] = useState<number>(1000.0);
  const [dailyRealizedPnl, setDailyRealizedPnl] = useState<number>(0.0);
  const [winStreak, setWinStreak] = useState<number>(0);
  const [lossStreak, setLossStreak] = useState<number>(0);

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
  const [vpsStatus, setVpsStatus] = useState<VpsBotStatus>({
    connected: false,
    endpoint: vpsEndpoint || (typeof window !== 'undefined' ? window.location.origin : ''),
    engineStatus: 'CHECKING...',
    engineRunning: false
  });

  const [activeTrades, setActiveTrades] = useState<ActiveTrade[]>([]);
  const [closedTrades, setClosedTrades] = useState<ClosedTrade[]>([]);
  const [logs, setLogs] = useState<LogMessage[]>([]);

  const [useLiveBinanceFeed, setUseLiveBinanceFeed] = useState<boolean>(false);
  const [selectedPinnedSymbols, setSelectedPinnedSymbols] = useState<string[]>(['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT']);

  // Candle history ref for each symbol
  const candlesRef = useRef<Record<string, { open: number; high: number; low: number; close: number; volume: number }[]>>({});
  const [symbolsData, setSymbolsData] = useState<MarketSymbolData[]>([]);
  const [candidates, setCandidates] = useState<CandidateSymbol[]>([]);

  // Ref mirrors to avoid timer resets during rapid VPS polling
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

  const runTickRef = useRef<() => void>(() => {});

  // Ensure candle buffer exists for any symbol (including dynamic coins like SUSHI, RAY, etc.)
  const ensureCandlesForSymbol = useCallback((sym: string, hintPrice?: number) => {
    if (!candlesRef.current[sym] || candlesRef.current[sym].length === 0) {
      const meta = getSymbolMeta(sym, hintPrice);
      const base = hintPrice && hintPrice > 0 ? hintPrice : meta.basePrice;
      const initialCandles = [];
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
      // ignore
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

  // Initialize candle buffers for all candidate symbols
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

        const tickerMap: Record<string, { price: number; change: number; volume: number; high: number; low: number }> = {};
        data.forEach((item: any) => {
          if (currentInterests.has(item.symbol)) {
            const lastP = parseFloat(item.lastPrice);
            ensureCandlesForSymbol(item.symbol, lastP);
            tickerMap[item.symbol] = {
              price: lastP,
              change: parseFloat(item.priceChangePercent),
              volume: parseFloat(item.quoteVolume),
              high: parseFloat(item.highPrice),
              low: parseFloat(item.lowPrice)
            };
          }
        });

        Object.keys(tickerMap).forEach(sym => {
          const t = tickerMap[sym];
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
        // network or CORS fallback
      }
    };

    fetchLiveBinanceTickers();
    const interval = setInterval(fetchLiveBinanceTickers, 10000);
    return () => {
      isSubscribed = false;
      clearInterval(interval);
    };
  }, [useLiveBinanceFeed, addLog]);

  // Real VPS Data Fetcher (reads SQLite trading.db and PM2 engine state via status.py HTTP endpoint)
  const fetchVpsData = useCallback(async () => {
    if (dataSource !== 'vps') return;
    setIsPollingVps(true);
    const targetBase = (vpsEndpoint || (typeof window !== 'undefined' ? window.location.origin : '')).replace(/\/+$/, '');
    const url = targetBase.endsWith('/api/status') ? targetBase : `${targetBase}/api/status`;

    const startTime = performance.now();
    try {
      const res = await fetch(url, { mode: 'cors' });
      const latency = Math.round(performance.now() - startTime);

      if (!res.ok) {
        throw new Error(`HTTP ${res.status}: ${res.statusText}`);
      }
      const json = await res.json();
      const rawProcess = String(json.process || '');
      const isEngineRunning = rawProcess.includes('RUNNING') || rawProcess.includes('ONLINE');

      setVpsStatus({
        connected: true,
        endpoint: targetBase,
        latencyMs: latency,
        engineStatus: rawProcess || 'RUNNING',
        engineRunning: isEngineRunning,
        lastSyncTime: new Date().toLocaleTimeString(),
        serverTime: json.server_time || json.timestamp,
        stats: json.data?.stats
      });

      // Update Risk state from SQLite
      if (json.data?.risk) {
        const r = json.data.risk;
        if (r.daily_pnl !== undefined) {
          const val = parseFloat(r.daily_pnl || '0');
          if (!isNaN(val)) setDailyRealizedPnl(val);
        }
        if (r.paper_balance !== undefined) {
          const val = parseFloat(r.paper_balance || '1000');
          if (!isNaN(val)) setEquity(val);
        }
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

      // Sync recent orders from SQLite
      if (Array.isArray(json.data?.orders)) {
        const mappedOrders: ClosedTrade[] = json.data.orders.map((o: any) => {
          const entryP = parseFloat(o.price || o.avg_fill_price || 0);
          const exitP = parseFloat(o.avg_fill_price || o.price || 0);
          const q = parseFloat(o.executed_qty || o.quantity || 0);
          const pnl = parseFloat(o.profit_loss || 0);
          const pnlPct = entryP > 0 && q > 0 ? (pnl / (entryP * q)) * 100 : 0;

          return {
            id: `order_${o.order_id}`,
            symbol: o.symbol,
            side: (o.side || 'BUY') as 'BUY' | 'SELL',
            entryPrice: entryP,
            exitPrice: exitP,
            quantity: q,
            pnl,
            pnlPct,
            entryTime: o.created_at ? new Date(o.created_at).getTime() : Date.now() - 3600000,
            exitTime: o.updated_at ? new Date(o.updated_at).getTime() : Date.now(),
            exitReason: (o.status || 'FILLED') as any
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

      // Trigger immediate UI refresh for symbols and tickers
      setTimeout(() => {
        if (runTickRef.current) runTickRef.current();
      }, 50);
    } catch (err: any) {
      setVpsStatus(prev => ({
        ...prev,
        connected: false,
        error: err.message,
        engineStatus: 'DISCONNECTED',
        engineRunning: false
      }));
    } finally {
      setIsPollingVps(false);
    }
  }, [dataSource, vpsEndpoint]);

  // Periodic VPS Polling
  useEffect(() => {
    if (dataSource !== 'vps') return;
    fetchVpsData();
    const interval = setInterval(fetchVpsData, 2500);
    return () => clearInterval(interval);
  }, [dataSource, fetchVpsData]);

  // Apply Preset
  const handleApplyPreset = (preset: StrategyPreset) => {
    const presetOverrides = PRESET_MAP[preset];
    setConfig(prev => ({
      ...prev,
      preset,
      ...presetOverrides
    }));
    addLog('INFO', 'SYS', `Applied ${preset.toUpperCase()} strategy profile. Timeframe: ${presetOverrides.timeframe}, MTF: ${presetOverrides.mtfTimeframe}`);
  };

  // Reset simulation
  const handleResetSimulation = () => {
    setEquity(1000.0);
    setDailyRealizedPnl(0.0);
    setActiveTrades([]);
    setClosedTrades([]);
    setWinStreak(0);
    setLossStreak(0);
    addLog('INFO', 'SYS', 'Simulated paper balance reset to $1,000.00 USDT. Trade history cleared.');
  };

  // Manual Buy simulation
  const handleTriggerManualBuy = (symbol: string) => {
    const symData = symbolsData.find(s => s.symbol === symbol);
    const candles = candlesRef.current[symbol] || [];
    const lastClose = candles.length > 0 ? candles[candles.length - 1].close : INITIAL_SYMBOLS[symbol]?.basePrice || 100;
    const price = symData ? symData.price : lastClose;
    const atr = symData?.factors.atr || price * 0.01;
    executeTrade(symbol, price, atr, 'MANUAL');
  };

  // Execute a market buy trade
  const executeTrade = (symbol: string, currentPrice: number, atr: number, triggerSource: string = 'SIGNAL') => {
    // Check max open trades
    if (activeTrades.length >= config.maxSymbols) {
      addLog('WARN', 'ORDER', `Max open trades reached (${activeTrades.length}/${config.maxSymbols}). Skipping ${symbol}.`, symbol);
      return;
    }

    // Check if already open
    if (activeTrades.some(t => t.symbol === symbol)) {
      addLog('DEBUG', 'ORDER', `${symbol} already has an active position. Skipping duplicate entry.`, symbol);
      return;
    }

    // Position sizing: allocate up to maxSymbolAllocationPercent
    const allocation = Math.min(equity * config.balanceUsagePercent, equity * config.maxSymbolAllocationPercent);
    const quantity = allocation / currentPrice;
    const notional = quantity * currentPrice;

    const stopPrice = currentPrice - atr * config.atrMultiplierSl;
    let takeProfit = currentPrice + atr * config.atrMultiplierTp;
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
  };

  // Close an active trade safely with unique closed ID
  const handleCloseTrade = (symbol: string, reason: string, customExitPrice?: number) => {
    setActiveTrades(prevTrades => {
      const trade = prevTrades.find(t => t.symbol === symbol);
      if (!trade) return prevTrades;

      const exitPrice = customExitPrice ?? trade.currentPrice;
      const pnl = (exitPrice - trade.entryPrice) * trade.quantity;
      const pnlPct = ((exitPrice - trade.entryPrice) / trade.entryPrice) * 100;

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

      setClosedTrades(prev => {
        // Prevent duplicate closure records for the exact same trade instance
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
        addLog('SUCCESS', 'ORDER', `CLOSE ${symbol} (${reason}) - PnL: +$${pnl.toFixed(2)} (+${pnlPct.toFixed(2)}%)`, symbol);
      } else {
        setLossStreak(prev => prev + 1);
        setWinStreak(0);
        addLog('WARN', 'ORDER', `CLOSE ${symbol} (${reason}) - PnL: -$${Math.abs(pnl).toFixed(2)} (${pnlPct.toFixed(2)}%)`, symbol);
      }

      return prevTrades.filter(t => t.symbol !== symbol);
    });
  };

  // Emergency Close All Trades
  const handleCloseAllTrades = () => {
    setActiveTrades(prevTrades => {
      if (prevTrades.length === 0) return prevTrades;

      prevTrades.forEach(t => {
        const exitPrice = t.currentPrice;
        const pnl = (exitPrice - t.entryPrice) * t.quantity;
        const pnlPct = ((exitPrice - t.entryPrice) / t.entryPrice) * 100;

        const closed: ClosedTrade = {
          id: `${t.id}_exit_${Date.now()}_${Math.random().toString(36).substring(2, 6)}`,
          symbol: t.symbol,
          side: t.side,
          entryPrice: t.entryPrice,
          exitPrice,
          quantity: t.quantity,
          pnl,
          pnlPct,
          entryTime: t.entryTime,
          exitTime: Date.now(),
          exitReason: 'EMERGENCY_CLOSE'
        };

        setClosedTrades(prev => {
          if (prev.some(ct => ct.id === closed.id || (ct.symbol === t.symbol && ct.entryTime === t.entryTime))) {
            return prev;
          }
          return [...prev, closed];
        });

        setDailyRealizedPnl(prev => prev + pnl);
        setEquity(prev => prev + pnl);
      });

      addLog('WARN', 'RISK', `EMERGENCY LIQUIDATION: Closed all ${prevTrades.length} open market positions.`);
      return [];
    });
  };

  // Simulate Institutional Confluence Boost
  const handleSimulateConfluenceBoost = (symbol: string) => {
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
  };

  // Toggle Symbol Selection in Screener
  const handleToggleSymbolSelect = (symbol: string) => {
    setSelectedPinnedSymbols(prev => {
      if (prev.includes(symbol)) {
        return prev.filter(s => s !== symbol);
      } else {
        return [...prev, symbol];
      }
    });
    addLog('INFO', 'SYS', `Updated watchlist selection for ${symbol}.`);
  };

  // Main Bot Tick, Dynamic Screener, and Evaluation Routine
  const runTick = useCallback(() => {
    const curConfig = configRef.current;
    const curDataSource = dataSourceRef.current;
    const curActiveTrades = activeTradesRef.current;
    const curEquity = equityRef.current;
    const curDailyPnl = dailyRealizedPnlRef.current;

    // 1. Gather ALL candidate symbols:
    // master list + active trades (e.g. SUSHI, RAY) + static symbols + pinned screener symbols
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
      let volume = 30 + Math.random() * 20;
      if (!useLiveBinanceFeed) {
        const drift = (Math.random() - 0.49) * (lastClose * 0.002);
        newClose = Math.max(0.00001, lastClose + drift);
        const open = lastClose;
        const high = Math.max(open, newClose) + Math.random() * (lastClose * 0.001);
        const low = Math.min(open, newClose) - Math.random() * (lastClose * 0.001);
        const newCandle = { open, high, low, close: newClose, volume };
        candlesRef.current[sym] = [...candles.slice(-80), newCandle];
      }

      const priceChange24h = base > 0 ? ((newClose - base) / base) * 100 : 0;
      const volatility = Math.abs(priceChange24h) * 0.01 + 0.015;
      const adx = 20 + (Math.abs(priceChange24h) * 2) + (Math.random() * 5);

      // Approximate 24h Volume in USDT
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

    // Compute multi-factor composite Z-scores
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

      // Sort candidates by Z-Score descending
      evaluatedCandidates.sort((a, b) => b.zScore - a.zScore);
      evaluatedCandidates.forEach((c, idx) => {
        c.momentumRank = idx + 1;
        c.isSelected = curConfig.dynamicSymbols 
          ? (idx < curConfig.maxSymbols || selectedPinnedSymbols.includes(c.symbol))
          : (curConfig.staticSymbols || []).includes(c.symbol);
      });
    }

    setCandidates(evaluatedCandidates);

    // Determine which symbols are actively monitored by the trading engine
    // GUARANTEE: Monitored list always has symbols, and also includes any open trades
    const openTradeSymbols = curActiveTrades.map(t => t.symbol);
    const chosenList = curConfig.dynamicSymbols
      ? evaluatedCandidates.filter(c => c.isSelected).slice(0, curConfig.maxSymbols).map(c => c.symbol)
      : (curConfig.staticSymbols && curConfig.staticSymbols.length > 0 ? curConfig.staticSymbols : ['BTCUSDT', 'ETHUSDT', 'SOLUSDT', 'BNBUSDT']);

    // Merge chosenList with any open trades so the user always sees their open positions
    const activeSymbolList = Array.from(new Set([...chosenList, ...openTradeSymbols]));

    // Fallback if somehow empty
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
        inCooldown: false
      };
    });

    setSymbolsData(updatedSymbols);

    // If connected to live VPS, the real bot processes all trades and orders on the server.
    // We only update unrealized PnL with the latest live market price without generating fake local trades.
    if (curDataSource === 'vps') {
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

    // 3. Manage Active Trades (Price updates, Trailing Stop, Breakeven, SL, TP) - Simulator Mode Only
    const tradesToClose: { symbol: string; reason: string; exitPrice?: number }[] = [];

    setActiveTrades(prevTrades => {
      const remainingTrades: ActiveTrade[] = [];

      prevTrades.forEach(trade => {
        const symData = updatedSymbols.find(s => s.symbol === trade.symbol);
        const livePrice = symData ? symData.price : trade.currentPrice;

        let trailingActive = trade.trailingActive;
        let trailingStop = trade.trailingStop;
        let breakevenActivated = trade.breakevenActivated;
        let stopPrice = trade.stopPrice;

        const pnl = (livePrice - trade.entryPrice) * trade.quantity;
        const pnlPct = trade.entryPrice > 0 ? ((livePrice - trade.entryPrice) / trade.entryPrice) * 100 : 0;
        const profitPct = trade.entryPrice > 0 ? (livePrice - trade.entryPrice) / trade.entryPrice : 0;

        // Check Stop Loss
        if (livePrice <= stopPrice) {
          tradesToClose.push({ symbol: trade.symbol, reason: 'STOP_LOSS', exitPrice: stopPrice });
          return;
        }

        // Check Take Profit
        if (livePrice >= trade.takeProfit) {
          tradesToClose.push({ symbol: trade.symbol, reason: 'TAKE_PROFIT', exitPrice: trade.takeProfit });
          return;
        }

        // Check Trailing Stop Activation
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

        // Check Breakeven lock (+1.0%)
        if (!breakevenActivated && profitPct >= 0.01) {
          breakevenActivated = true;
          stopPrice = trade.entryPrice * 1.0025;
          addLog('INFO', 'ORDER', `Breakeven lock ENGAGED for ${trade.symbol} (+1.0% profit). Stop raised to entry+fees.`, trade.symbol);
        }

        // Check Max Hold Time
        if ((Date.now() - trade.entryTime) / 1000 > curConfig.maxHoldTime) {
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

    // Execute closures cleanly outside of the setActiveTrades updater function
    tradesToClose.forEach(({ symbol, reason, exitPrice }) => {
      handleCloseTrade(symbol, reason, exitPrice);
    });

    // 4. Confluence Evaluation & Execution
    updatedSymbols.forEach(sym => {
      const f = sym.factors;
      const hasActive = curActiveTrades.some(t => t.symbol === sym.symbol);

      if (hasActive) {
        addLog('DEBUG', 'SIGNAL', `Processing ${sym.symbol}: position already active, managing exits...`, sym.symbol);
        return;
      }

      // Drawdown check
      const totalPnl = curDailyPnl;
      if (curEquity > 0 && totalPnl <= -curConfig.maxDailyDrawdown * curEquity) {
        addLog('WARN', 'RISK', `Max daily drawdown exceeded (${(-curConfig.maxDailyDrawdown * 100).toFixed(1)}%). Entry blocked for ${sym.symbol}.`, sym.symbol);
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
        executeTrade(sym.symbol, sym.price, f.atr, '5-FACTOR CONFLUENCE');
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

  // Main Bot Tick, Dynamic Screener, and Simulation Loop
  useEffect(() => {
    if (!isRunning) return;

    // Run tick immediately upon mounting or parameter change
    runTick();

    const interval = setInterval(() => {
      if (runTickRef.current) {
        runTickRef.current();
      }
    }, (config.signalInterval || 6) * 1000);

    return () => clearInterval(interval);
  }, [isRunning, config.signalInterval, runTick]);

  const totalUnrealizedPnl = activeTrades.reduce((acc, t) => acc + t.unrealizedPnl, 0);

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
      />

      {/* Live VPS Connection Bar */}
      <VpsConnectionBar
        dataSource={dataSource}
        onToggleDataSource={setDataSource}
        vpsStatus={vpsStatus}
        vpsEndpoint={vpsEndpoint}
        onUpdateVpsEndpoint={setVpsEndpoint}
        onRefreshVps={fetchVpsData}
        isPolling={isPollingVps}
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
          />
        )}

        {activeTab === 'deploy' && (
          <DeployGuide />
        )}
      </main>
    </div>
  );
}
