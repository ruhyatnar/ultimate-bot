import React, { useState } from 'react';
import { 
  TrendingUp, 
  TrendingDown, 
  Shield, 
  DollarSign, 
  Crosshair, 
  Clock, 
  ArrowUpRight, 
  ArrowDownRight,
  Sparkles,
  Zap,
  PauseCircle
} from 'lucide-react';
import { 
  ActiveTrade, 
  ClosedTrade, 
  MarketSymbolData, 
  BotConfig, 
  StrategyPreset,
  CandidateSymbol,
  PushResult 
} from '../types';
import { TuningControlBar } from './TuningControlBar';
import { DynamicScreener } from './DynamicScreener';
import { SymbolDetailModal } from './SymbolDetailModal';
import { VpsSyncModal } from './VpsSyncModal';

interface LiveDashboardProps {
  equity: number;
  dailyRealizedPnl: number;
  unrealizedPnl: number;
  activeTrades: ActiveTrade[];
  closedTrades: ClosedTrade[];
  symbolsData: MarketSymbolData[];
  candidates: CandidateSymbol[];
  config: BotConfig;
  onUpdateConfig: (newConfig: BotConfig) => void;
  onApplyPreset: (preset: StrategyPreset) => void;
  onCloseTrade: (symbol: string, reason: string) => void;
  onCloseAllTrades: () => void;
  onTriggerManualBuy: (symbol: string) => void;
  onSimulateConfluenceBoost: (symbol: string) => void;
  onToggleSymbolSelect: (symbol: string) => void;
  useLiveBinanceFeed: boolean;
  onToggleLiveBinanceFeed: () => void;
  winStreak: number;
  lossStreak: number;
  dataSource?: 'vps' | 'simulator';
  vpsRiskAvailable?: boolean;
  isLossCooldown?: boolean;
  cooldownEndsAt?: number;
  vpsConnected?: boolean;
  onPushConfigToVps?: () => Promise<PushResult>;
  vpsPushResult?: PushResult | null;
  controlPaused?: boolean;
  onToggleVpsPause?: () => void;
}

export const LiveDashboard: React.FC<LiveDashboardProps> = ({
  equity,
  dailyRealizedPnl,
  unrealizedPnl,
  activeTrades,
  closedTrades,
  symbolsData,
  candidates,
  config,
  onUpdateConfig,
  onApplyPreset,
  onCloseTrade,
  onCloseAllTrades,
  onTriggerManualBuy,
  onSimulateConfluenceBoost,
  onToggleSymbolSelect,
  useLiveBinanceFeed,
  onToggleLiveBinanceFeed,
  winStreak,
  lossStreak,
  dataSource = 'vps',
  vpsRiskAvailable = false,
  isLossCooldown = false,
  cooldownEndsAt = 0,
  vpsConnected = false,
  onPushConfigToVps,
  vpsPushResult = null,
  controlPaused = false,
  onToggleVpsPause
}) => {
  const [inspectedSymbol, setInspectedSymbol] = useState<string | null>(null);
  const [showVpsSync, setShowVpsSync] = useState<boolean>(false);

  const totalPnl = dailyRealizedPnl + unrealizedPnl;
  const drawdownUsed = Math.max(0, -totalPnl) / (equity > 0 ? equity : 1000);
  const drawdownLimit = config.maxDailyDrawdown;
  const drawdownPct = Math.min(100, (drawdownUsed / drawdownLimit) * 100);

  const winningTrades = closedTrades.filter(t => t.pnl > 0);
  const winRate = closedTrades.length > 0 
    ? (winningTrades.length / closedTrades.length) * 100 
    : 0;

  const grossProfit = winningTrades.reduce((acc, t) => acc + t.pnl, 0);
  const grossLoss = Math.abs(closedTrades.filter(t => t.pnl < 0).reduce((acc, t) => acc + t.pnl, 0));
  const profitFactor = grossLoss > 0 ? (grossProfit / grossLoss).toFixed(2) : grossProfit > 0 ? 'MAX' : '0.00';

  const inspectedData = inspectedSymbol 
    ? symbolsData.find(s => s.symbol === inspectedSymbol) || {
        symbol: inspectedSymbol,
        name: inspectedSymbol,
        price: 100,
        priceChange24h: 0,
        high24h: 105,
        low24h: 95,
        volume24h: 5000000,
        factors: {
          htfTrend: 'UP',
          bos: 'BULLISH',
          fvg: 1,
          cvd: 120,
          poc: 98,
          currentPrice: 100,
          bullishScore: 4,
          bearishScore: 0,
          signal: 'BUY',
          atr: 1.5,
          adx: 28,
          reason: 'Confluence aligned'
        },
        sparkline: [98, 99, 100],
        inCooldown: false
      }
    : null;

  const showServerEquity = dataSource === 'vps' && !vpsRiskAvailable;
  const equityLabel = showServerEquity
    ? 'Server Equity'
    : config.paperTrade
      ? 'Simulated Paper Equity'
      : 'Live Spot Equity';

  return (
    <div className="space-y-6">
      {/* Loss-Streak Cooldown Banner (mirrors COOLDOWN_LOSS in the Python engine) */}
      {isLossCooldown && (
        <div className="flex items-center justify-between p-3 rounded-lg bg-rose-950/50 border border-rose-500/40 animate-pulse">
          <div className="flex items-center space-x-2 text-xs text-rose-200">
            <PauseCircle className="w-4 h-4 text-rose-400" />
            <span>
              <strong>Trading Paused — Loss-Streak Cooldown.</strong> Entries blocked until {new Date(cooldownEndsAt).toLocaleTimeString()} (COOLDOWN_LOSS).
            </span>
          </div>
        </div>
      )}

      {/* Interactive Quick Tuner Bar */}
      <TuningControlBar
        config={config}
        onUpdateConfig={onUpdateConfig}
        onApplyPreset={onApplyPreset}
        onCloseAllTrades={onCloseAllTrades}
        onSimulateConfluenceBoost={onSimulateConfluenceBoost}
        onOpenVpsSync={() => setShowVpsSync(true)}
        useLiveBinanceFeed={useLiveBinanceFeed}
        onToggleLiveBinanceFeed={onToggleLiveBinanceFeed}
        activeSymbols={symbolsData.map(s => s.symbol)}
        activeTradesCount={activeTrades.length}
        vpsConnected={vpsConnected}
        controlPaused={controlPaused}
        onToggleVpsPause={onToggleVpsPause}
      />

      {/* Risk & Performance Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Total Equity (simulator or server-synced) */}
        <div className="bg-slate-800/80 border border-slate-700/60 rounded-xl p-4 shadow-sm relative overflow-hidden">
          <div className="flex items-center justify-between text-xs text-slate-400 font-medium">
            <span>{equityLabel}</span>
            <DollarSign className="w-4 h-4 text-emerald-400" />
          </div>
          {showServerEquity ? (
            <div className="mt-2">
              <span className="text-2xl font-bold tracking-tight text-slate-500">—</span>
              <p className="mt-2 text-[11px] text-slate-500 leading-snug">
                No risk state in trading.db yet. Equity appears after the engine persists its first risk snapshot.
              </p>
            </div>
          ) : (
            <>
              <div className="mt-2 flex items-baseline space-x-2">
                <span className="text-2xl font-bold tracking-tight text-white">
                  ${equity.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
                </span>
                <span className="text-xs text-slate-400">USDT</span>
              </div>
              <div className="mt-2 flex items-center justify-between text-xs">
                <span className="text-slate-400">Capital Active:</span>
                <span className="text-slate-300 font-semibold">
                  {(config.balanceUsagePercent * 100).toFixed(0)}% (${(equity * config.balanceUsagePercent).toFixed(1)})
                </span>
              </div>
            </>
          )}
        </div>

        {/* Daily PnL & Floating */}
        <div className="bg-slate-800/80 border border-slate-700/60 rounded-xl p-4 shadow-sm">
          <div className="flex items-center justify-between text-xs text-slate-400 font-medium">
            <span>Daily Net PnL (Real + Unr)</span>
            {totalPnl >= 0 ? (
              <TrendingUp className="w-4 h-4 text-emerald-400" />
            ) : (
              <TrendingDown className="w-4 h-4 text-rose-400" />
            )}
          </div>
          <div className="mt-2 flex items-baseline space-x-2">
            <span className={`text-2xl font-bold tracking-tight ${totalPnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
              {totalPnl >= 0 ? '+' : ''}${totalPnl.toFixed(2)}
            </span>
            <span className={`text-xs font-semibold ${totalPnl >= 0 ? 'text-emerald-500' : 'text-rose-500'}`}>
              ({totalPnl >= 0 ? '+' : ''}{((totalPnl / (equity - totalPnl || 1)) * 100).toFixed(2)}%)
            </span>
          </div>
          <div className="mt-2 flex items-center justify-between text-xs text-slate-400">
            <span>Realized: <b className="text-slate-200">${dailyRealizedPnl.toFixed(2)}</b></span>
            <span>Floating: <b className={unrealizedPnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}>${unrealizedPnl.toFixed(2)}</b></span>
          </div>
        </div>

        {/* Daily Drawdown Watchdog */}
        <div className="bg-slate-800/80 border border-slate-700/60 rounded-xl p-4 shadow-sm">
          <div className="flex items-center justify-between text-xs text-slate-400 font-medium">
            <span>Daily Drawdown Circuit Breaker</span>
            <Shield className="w-4 h-4 text-amber-400" />
          </div>
          <div className="mt-2 flex items-baseline justify-between">
            <span className="text-2xl font-bold tracking-tight text-white">
              {(drawdownUsed * 100).toFixed(2)}%
            </span>
            <span className="text-xs text-slate-400">
              Limit: <strong className="text-amber-300">{(drawdownLimit * 100).toFixed(1)}%</strong>
            </span>
          </div>
          <div className="mt-3 w-full bg-slate-700/60 rounded-full h-2 overflow-hidden">
            <div 
              className={`h-full transition-all duration-300 ${
                drawdownPct > 75 ? 'bg-rose-500' : drawdownPct > 40 ? 'bg-amber-500' : 'bg-emerald-500'
              }`}
              style={{ width: `${Math.max(4, drawdownPct)}%` }}
            />
          </div>
        </div>

        {/* Win Rate & Streaks */}
        <div className="bg-slate-800/80 border border-slate-700/60 rounded-xl p-4 shadow-sm">
          <div className="flex items-center justify-between text-xs text-slate-400 font-medium">
            <span>Performance & Streaks</span>
            <Sparkles className="w-4 h-4 text-purple-400" />
          </div>
          <div className="mt-2 flex items-baseline space-x-2">
            <span className="text-2xl font-bold tracking-tight text-white">
              {winRate.toFixed(1)}%
            </span>
            <span className="text-xs text-slate-400">
              PF: <strong className="text-slate-200">{profitFactor}</strong>
            </span>
          </div>
          <div className="mt-2 flex items-center justify-between text-xs text-slate-400">
            <span>Win Streak: <b className="text-emerald-400">{winStreak}</b>/{config.maxWinStreak}</span>
            <span>Loss Streak: <b className="text-rose-400">{lossStreak}</b>/{config.maxLossStreak}</span>
          </div>
        </div>
      </div>

      {/* Dynamic Symbols Screener (Active when dynamicSymbols=true) */}
      {config.dynamicSymbols && candidates.length > 0 && (
        <DynamicScreener
          candidates={candidates}
          config={config}
          onToggleSymbolSelect={onToggleSymbolSelect}
          onInspectSymbol={(sym) => setInspectedSymbol(sym)}
          onTriggerManualBuy={onTriggerManualBuy}
        />
      )}

      {/* Active Watchlist Market Tickers */}
      <div className="bg-slate-800/60 border border-slate-700/60 rounded-xl p-4">
        <div className="flex items-center justify-between mb-3">
          <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center space-x-2">
            <Crosshair className="w-3.5 h-3.5 text-amber-400" />
            <span>Monitored Symbols ({symbolsData.length})</span>
            <span className="text-[10px] lowercase text-slate-500 font-normal">
              ({config.dynamicSymbols ? 'top momentum screener' : 'static watchlist'})
            </span>
          </h2>
          <span className="text-xs text-slate-500">
            Scan loop: <strong className="text-slate-300">{config.signalInterval}s</strong> • Confluence threshold: <strong className="text-indigo-400">{config.signalThreshold}/5</strong>
          </span>
        </div>

        {symbolsData.length === 0 ? (
          <div className="py-8 px-4 text-center bg-slate-900/40 rounded-lg border border-dashed border-slate-700/60 flex flex-col items-center justify-center space-y-2">
            <div className="w-6 h-6 rounded-full border-2 border-amber-500/30 border-t-amber-400 animate-spin" />
            <p className="text-sm font-medium text-slate-300">Synchronizing Monitored Pairs & Technical Indicators...</p>
            <p className="text-xs text-slate-400">Loading multi-timeframe candle data for {config.staticSymbols?.join(', ') || 'monitored pairs'}.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3">
            {symbolsData.map(sym => {
            const isBullishTrigger = sym.factors.bullishScore >= config.signalThreshold;
            const hasActiveTrade = activeTrades.some(t => t.symbol === sym.symbol);

            return (
              <div 
                key={sym.symbol} 
                className={`p-3.5 rounded-lg border transition-all ${
                  isBullishTrigger && !hasActiveTrade
                    ? 'bg-emerald-950/20 border-emerald-500/40 shadow-sm shadow-emerald-900/20'
                    : 'bg-slate-850 bg-slate-900/50 border-slate-700/50'
                }`}
              >
                <div className="flex items-start justify-between">
                  <div>
                    <div className="flex items-center space-x-2">
                      <span className="font-bold text-sm text-white">{sym.symbol}</span>
                      {hasActiveTrade && (
                        <span className="px-1.5 py-0.5 text-[10px] font-semibold rounded bg-amber-500/20 text-amber-300 border border-amber-500/30">
                          Active
                        </span>
                      )}
                      {sym.inCooldown && (
                        <span className="px-1.5 py-0.5 text-[10px] font-semibold rounded bg-rose-500/20 text-rose-300 border border-rose-500/30">
                          Cooldown
                        </span>
                      )}
                    </div>
                    <div className="text-xs text-slate-400 mt-0.5">{sym.name}</div>
                  </div>

                  <div className="text-right">
                    <div className="font-mono text-sm font-bold text-slate-100">
                      ${sym.price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: sym.price < 10 ? 4 : 2 })}
                    </div>
                    <div className={`text-xs font-semibold flex items-center justify-end space-x-0.5 ${
                      sym.priceChange24h >= 0 ? 'text-emerald-400' : 'text-rose-400'
                    }`}>
                      {sym.priceChange24h >= 0 ? <ArrowUpRight className="w-3 h-3" /> : <ArrowDownRight className="w-3 h-3" />}
                      <span>{sym.priceChange24h >= 0 ? '+' : ''}{sym.priceChange24h.toFixed(2)}%</span>
                    </div>
                  </div>
                </div>

                {/* Factors Score Bar */}
                <div className="mt-3 pt-2.5 border-t border-slate-700/50 flex items-center justify-between text-xs">
                  <div className="flex items-center space-x-1.5">
                    <span className="text-slate-400">Bullish:</span>
                    <span className={`font-bold px-1.5 py-0.2 rounded text-[11px] ${
                      sym.factors.bullishScore >= config.signalThreshold 
                        ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30' 
                        : 'bg-slate-800 text-slate-300'
                    }`}>
                      {sym.factors.bullishScore}/5
                    </span>
                  </div>

                  <div className="flex items-center space-x-1">
                    <button
                      id={`inspect-card-${sym.symbol}`}
                      onClick={() => setInspectedSymbol(sym.symbol)}
                      className="text-[11px] px-2 py-0.5 rounded font-medium bg-slate-800 text-slate-300 hover:text-white hover:bg-slate-700 transition-colors"
                      title="Inspect 5 factors & calculate order"
                    >
                      Inspect
                    </button>
                    {!hasActiveTrade && !sym.inCooldown && (
                      <button
                        id={`manual-buy-${sym.symbol}`}
                        onClick={() => onTriggerManualBuy(sym.symbol)}
                        title="Force instant market buy simulation"
                        className="text-[11px] px-2 py-0.5 rounded font-medium bg-indigo-600/30 text-indigo-200 border border-indigo-500/40 hover:bg-indigo-600 hover:text-white transition-colors"
                      >
                        Instant Buy
                      </button>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
      </div>

      {/* Active Trades Table */}
      <div className="bg-slate-800/80 border border-slate-700/60 rounded-xl overflow-hidden shadow-sm">
        <div className="p-4 border-b border-slate-700/60 flex items-center justify-between">
          <div className="flex items-center space-x-2">
            <Zap className="w-4 h-4 text-amber-400" />
            <h2 className="font-bold text-sm text-white">Active Positions (Market-Only)</h2>
            <span className="px-2 py-0.5 text-xs font-semibold rounded-full bg-slate-700 text-slate-300">
              {activeTrades.length} / {config.maxSymbols} Max
            </span>
          </div>
          <span className="text-xs text-slate-400 hidden sm:inline">
            Trailing Stop callback: <strong className="text-slate-200">{(config.trailingStopCallback * 100).toFixed(1)}%</strong> • Breakeven at: <strong className="text-slate-200">+1.0%</strong>
          </span>
        </div>

        {activeTrades.length === 0 ? (
          <div className="p-8 text-center">
            <Clock className="w-8 h-8 text-slate-500 mx-auto mb-2 opacity-50" />
            <p className="text-sm font-medium text-slate-300">No active trades currently open</p>
            <p className="text-xs text-slate-500 mt-1 max-w-md mx-auto">
              The bot continuously evaluates 5 confluence indicators across your monitored pairs. Trades enter automatically via market orders when confluence exceeds {config.signalThreshold}/5.
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-xs text-left">
              <thead className="bg-slate-900/60 text-slate-400 font-semibold uppercase tracking-wider border-b border-slate-700/50">
                <tr>
                  <th className="py-3 px-4">Symbol / Side</th>
                  <th className="py-3 px-4">Entry / Current</th>
                  <th className="py-3 px-4">Position Size</th>
                  <th className="py-3 px-4">Stop Loss (ATR)</th>
                  <th className="py-3 px-4">Take Profit (ATR)</th>
                  <th className="py-3 px-4">Safety Locks</th>
                  <th className="py-3 px-4">Unrealized PnL</th>
                  <th className="py-3 px-4 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-700/50">
                {activeTrades.map((trade, idx) => {
                  const pnlColor = trade.unrealizedPnl >= 0 ? 'text-emerald-400' : 'text-rose-400';
                  const slDistance = ((trade.currentPrice - trade.stopPrice) / trade.currentPrice) * 100;
                  const tpDistance = ((trade.takeProfit - trade.currentPrice) / trade.currentPrice) * 100;

                  return (
                    <tr key={`active_trade_${trade.id || trade.symbol}_${trade.entryTime || idx}`} className="hover:bg-slate-700/20 transition-colors">
                      <td className="py-3.5 px-4">
                        <div className="font-bold text-slate-100 flex items-center space-x-1.5">
                          <span>{trade.symbol}</span>
                          <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                            {trade.side}
                          </span>
                        </div>
                        <div className="text-[11px] text-slate-400 mt-0.5">
                          {Math.round((Date.now() - trade.entryTime) / 1000)}s held
                        </div>
                      </td>

                      <td className="py-3.5 px-4 font-mono">
                        <div className="text-slate-300">In: ${trade.entryPrice.toFixed(2)}</div>
                        <div className="font-bold text-slate-100">Now: ${trade.currentPrice.toFixed(2)}</div>
                      </td>

                      <td className="py-3.5 px-4 font-mono">
                        <div className="text-slate-200 font-semibold">{trade.quantity.toFixed(4)}</div>
                        <div className="text-slate-400 text-[11px]">${trade.notional.toFixed(2)} USDT</div>
                      </td>

                      <td className="py-3.5 px-4 font-mono">
                        <div className="text-rose-400 font-semibold">${trade.stopPrice.toFixed(2)}</div>
                        <div className="text-[11px] text-slate-400">-{slDistance.toFixed(2)}% away</div>
                      </td>

                      <td className="py-3.5 px-4 font-mono">
                        <div className="text-emerald-400 font-semibold">${trade.takeProfit.toFixed(2)}</div>
                        <div className="text-[11px] text-slate-400">+{tpDistance.toFixed(2)}% away</div>
                      </td>

                      <td className="py-3.5 px-4">
                        <div className="flex flex-col space-y-1">
                          <span className={`inline-flex items-center space-x-1 text-[10px] font-semibold px-1.5 py-0.5 rounded ${
                            trade.trailingActive 
                              ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30' 
                              : 'bg-slate-700/40 text-slate-400'
                          }`}>
                            <span>Trailing: {trade.trailingActive ? 'ACTIVE' : 'OFF'}</span>
                          </span>
                          <span className={`inline-flex items-center space-x-1 text-[10px] font-semibold px-1.5 py-0.5 rounded ${
                            trade.breakevenActivated 
                              ? 'bg-blue-500/20 text-blue-300 border border-blue-500/30' 
                              : 'bg-slate-700/40 text-slate-400'
                          }`}>
                            <span>Breakeven: {trade.breakevenActivated ? 'LOCKED' : 'OFF'}</span>
                          </span>
                        </div>
                      </td>

                      <td className="py-3.5 px-4 font-mono">
                        <div className={`font-bold text-sm ${pnlColor}`}>
                          {trade.unrealizedPnl >= 0 ? '+' : ''}${trade.unrealizedPnl.toFixed(2)}
                        </div>
                        <div className={`text-[11px] font-semibold ${pnlColor}`}>
                          {trade.unrealizedPnlPct >= 0 ? '+' : ''}{trade.unrealizedPnlPct.toFixed(2)}%
                        </div>
                      </td>

                      <td className="py-3.5 px-4 text-right">
                        <button
                          id={`close-trade-${trade.symbol}`}
                          onClick={() => onCloseTrade(trade.symbol, 'MANUAL')}
                          className="px-2.5 py-1 rounded text-xs font-semibold bg-rose-600/20 text-rose-300 border border-rose-500/30 hover:bg-rose-600 hover:text-white transition-colors"
                        >
                          Market Close
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Closed Trades History */}
      <div className="bg-slate-800/80 border border-slate-700/60 rounded-xl overflow-hidden shadow-sm">
        <div className="p-4 border-b border-slate-700/60 flex items-center justify-between">
          <h2 className="font-bold text-sm text-white flex items-center space-x-2">
            <Clock className="w-4 h-4 text-slate-400" />
            <span>Recent Completed Trades</span>
          </h2>
          <span className="text-xs text-slate-400">
            Total Closed: <strong className="text-slate-200">{closedTrades.length}</strong>
          </span>
        </div>

        {closedTrades.length === 0 ? (
          <div className="p-6 text-center text-xs text-slate-500">
            No closed trades yet in this session.
          </div>
        ) : (
          <div className="overflow-x-auto max-h-60 overflow-y-auto">
            <table className="w-full text-xs text-left">
              <thead className="bg-slate-900/60 text-slate-400 uppercase font-semibold text-[11px] sticky top-0">
                <tr>
                  <th className="py-2.5 px-4">Symbol</th>
                  <th className="py-2.5 px-4">Side</th>
                  <th className="py-2.5 px-4">Entry / Exit</th>
                  <th className="py-2.5 px-4">Exit Reason</th>
                  <th className="py-2.5 px-4 text-right">PnL (USDT)</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-700/50">
                {closedTrades.slice(-8).reverse().map((trade, idx) => (
                  <tr key={`closed_trade_${trade.id || trade.symbol}_${trade.exitTime || idx}`} className="hover:bg-slate-700/20">
                    <td className="py-2.5 px-4 font-bold text-slate-200">{trade.symbol}</td>
                    <td className="py-2.5 px-4">
                      <span className="px-1.5 py-0.5 text-[10px] font-bold rounded bg-emerald-500/10 text-emerald-400">
                        {trade.side}
                      </span>
                    </td>
                    <td className="py-2.5 px-4 font-mono text-slate-300">
                      ${trade.entryPrice.toFixed(2)} → ${trade.exitPrice.toFixed(2)}
                    </td>
                    <td className="py-2.5 px-4">
                      <span className={`px-2 py-0.5 text-[10px] font-semibold rounded ${
                        trade.exitReason === 'TAKE_PROFIT' 
                          ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                          : trade.exitReason === 'TRAILING_STOP'
                          ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                          : 'bg-rose-500/20 text-rose-300 border border-rose-500/30'
                      }`}>
                        {trade.exitReason.replace('_', ' ')}
                      </span>
                    </td>
                    <td className="py-2.5 px-4 text-right font-mono font-bold">
                      <span className={trade.pnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}>
                        {trade.pnl >= 0 ? '+' : ''}${trade.pnl.toFixed(2)} ({trade.pnlPct >= 0 ? '+' : ''}{trade.pnlPct.toFixed(2)}%)
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {/* Symbol Detail Inspection Modal */}
      {inspectedSymbol && inspectedData && (
        <SymbolDetailModal
          symbolData={inspectedData}
          config={config}
          equity={equity}
          onClose={() => setInspectedSymbol(null)}
          onTriggerManualBuy={onTriggerManualBuy}
        />
      )}

      {/* VPS Sync Modal */}
      {showVpsSync && (
        <VpsSyncModal
          config={config}
          onClose={() => setShowVpsSync(false)}
          vpsConnected={vpsConnected}
          onApplyToVps={onPushConfigToVps}
          lastPushResult={vpsPushResult}
        />
      )}
    </div>
  );
};
