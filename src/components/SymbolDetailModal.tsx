import React, { useState } from 'react';
import { 
  X, 
  Activity, 
  TrendingUp, 
  TrendingDown, 
  Shield, 
  Crosshair, 
  Zap, 
  CheckCircle2, 
  XCircle, 
  DollarSign, 
  Calculator,
  ArrowRight
} from 'lucide-react';
import { MarketSymbolData, BotConfig } from '../types';

interface SymbolDetailModalProps {
  symbolData: MarketSymbolData;
  config: BotConfig;
  equity: number;
  onClose: () => void;
  onTriggerManualBuy: (symbol: string) => void;
}

export const SymbolDetailModal: React.FC<SymbolDetailModalProps> = ({
  symbolData,
  config,
  equity,
  onClose,
  onTriggerManualBuy
}) => {
  const f = symbolData.factors;
  const price = symbolData.price;
  const atr = f.atr || price * 0.01;

  const stopLoss = price - atr * config.atrMultiplierSl;
  let takeProfit = price + atr * config.atrMultiplierTp;
  const minTpDist = price * 0.005;
  if (takeProfit - price < minTpDist) {
    takeProfit = price + minTpDist;
  }

  const trailingTrigger = price * (1 + config.trailingStopActivate);
  const breakevenTrigger = price * 1.01;

  // Sizing estimation
  const defaultAlloc = Math.min(equity * config.balanceUsagePercent, equity * config.maxSymbolAllocationPercent);
  const [customAllocation, setCustomAllocation] = useState<number>(Math.round(defaultAlloc));
  const estimatedQuantity = customAllocation / price;
  const minNotionalValid = customAllocation >= 10.0;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-in fade-in">
      <div className="bg-slate-900 border border-slate-700/80 rounded-2xl w-full max-w-2xl overflow-hidden shadow-2xl">
        {/* Modal Header */}
        <div className="p-5 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 rounded-xl bg-indigo-500/10 border border-indigo-500/30 flex items-center justify-center text-indigo-400 font-bold text-base">
              {symbolData.symbol.substring(0, 3)}
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <h3 className="font-bold text-lg text-white">{symbolData.symbol}</h3>
                <span className={`px-2 py-0.5 text-xs font-semibold rounded ${
                  symbolData.priceChange24h >= 0 ? 'bg-emerald-500/10 text-emerald-400' : 'bg-rose-500/10 text-rose-400'
                }`}>
                  {symbolData.priceChange24h >= 0 ? '+' : ''}{symbolData.priceChange24h.toFixed(2)}%
                </span>
              </div>
              <p className="text-xs text-slate-400">{symbolData.name} • Binance Spot Market</p>
            </div>
          </div>

          <div className="flex items-center space-x-4">
            <div className="text-right">
              <div className="text-xs text-slate-400">Current Market Price</div>
              <div className="text-lg font-mono font-bold text-slate-100">
                ${price.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: price < 10 ? 4 : 2 })}
              </div>
            </div>
            <button
              id="close-modal-btn"
              onClick={onClose}
              className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Modal Body */}
        <div className="p-5 space-y-5 max-h-[80vh] overflow-y-auto">
          {/* Confluence Rating & Summary */}
          <div className={`p-4 rounded-xl border flex items-center justify-between ${
            f.bullishScore >= config.signalThreshold
              ? 'bg-emerald-950/30 border-emerald-500/40 text-emerald-200'
              : 'bg-slate-800/60 border-slate-700/60 text-slate-300'
          }`}>
            <div>
              <div className="flex items-center space-x-2">
                <span className="text-xs uppercase tracking-wider font-semibold text-slate-400">Confluence Status</span>
                <span className={`px-2 py-0.5 rounded text-xs font-bold ${
                  f.bullishScore >= config.signalThreshold
                    ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                    : 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                }`}>
                  {f.bullishScore >= config.signalThreshold ? 'READY TO BUY' : 'WAITING FOR CONFLUENCE'}
                </span>
              </div>
              <p className="text-xs text-slate-300 mt-1">
                {f.bullishScore >= config.signalThreshold 
                  ? `All ${f.bullishScore}/5 necessary smart money factors aligned. Market order execution permitted.`
                  : f.skippedReason || `Currently at ${f.bullishScore}/5 factors. Need >= ${config.signalThreshold}/5.`}
              </p>
            </div>
            <div className="text-right shrink-0 ml-4">
              <div className="text-3xl font-bold font-mono">
                {f.bullishScore}<span className="text-slate-500 text-lg">/5</span>
              </div>
              <div className="text-[10px] text-slate-400">Target &gt;= {config.signalThreshold}</div>
            </div>
          </div>

          {/* 5-Factor Radar Matrix */}
          <div>
            <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-3 flex items-center space-x-1.5">
              <Activity className="w-3.5 h-3.5 text-indigo-400" />
              <span>5-Factor Indicator Alignment</span>
            </h4>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 text-xs">
              {/* Factor 1: HTF Trend */}
              <div className="bg-slate-800/60 p-3 rounded-lg border border-slate-700/50 flex items-center justify-between">
                <div>
                  <div className="font-semibold text-slate-200">1. Multi-Timeframe Trend</div>
                  <div className="text-[11px] text-slate-400 mt-0.5">EMA 20 &gt; EMA 50 on {config.mtfTimeframe}</div>
                </div>
                <div className="flex items-center space-x-1.5 font-bold">
                  {f.htfTrend === 'UP' ? (
                    <span className="text-emerald-400 flex items-center space-x-1">
                      <CheckCircle2 className="w-4 h-4" />
                      <span>Bullish</span>
                    </span>
                  ) : (
                    <span className="text-slate-400 flex items-center space-x-1">
                      <XCircle className="w-4 h-4 text-slate-500" />
                      <span>{f.htfTrend}</span>
                    </span>
                  )}
                </div>
              </div>

              {/* Factor 2: Market Structure BOS */}
              <div className="bg-slate-800/60 p-3 rounded-lg border border-slate-700/50 flex items-center justify-between">
                <div>
                  <div className="font-semibold text-slate-200">2. Market Structure (BOS)</div>
                  <div className="text-[11px] text-slate-400 mt-0.5">Fractal Higher Highs & Lows</div>
                </div>
                <div className="flex items-center space-x-1.5 font-bold">
                  {f.bos === 'BULLISH' ? (
                    <span className="text-emerald-400 flex items-center space-x-1">
                      <CheckCircle2 className="w-4 h-4" />
                      <span>BOS Confirmed</span>
                    </span>
                  ) : (
                    <span className="text-slate-400 flex items-center space-x-1">
                      <XCircle className="w-4 h-4 text-slate-500" />
                      <span>{f.bos}</span>
                    </span>
                  )}
                </div>
              </div>

              {/* Factor 3: Fair Value Gap */}
              <div className="bg-slate-800/60 p-3 rounded-lg border border-slate-700/50 flex items-center justify-between">
                <div>
                  <div className="font-semibold text-slate-200">3. Fair Value Gap (FVG)</div>
                  <div className="text-[11px] text-slate-400 mt-0.5">3-Candle Smart Money Imbalance</div>
                </div>
                <div className="flex items-center space-x-1.5 font-bold">
                  {f.fvg > 0 ? (
                    <span className="text-emerald-400 flex items-center space-x-1">
                      <CheckCircle2 className="w-4 h-4" />
                      <span>Bullish Gap</span>
                    </span>
                  ) : (
                    <span className="text-slate-400 flex items-center space-x-1">
                      <XCircle className="w-4 h-4 text-slate-500" />
                      <span>{f.fvg < 0 ? 'Bearish Gap' : 'No Gap'}</span>
                    </span>
                  )}
                </div>
              </div>

              {/* Factor 4: Cumulative Volume Delta */}
              <div className="bg-slate-800/60 p-3 rounded-lg border border-slate-700/50 flex items-center justify-between">
                <div>
                  <div className="font-semibold text-slate-200">4. Order Flow CVD Delta</div>
                  <div className="text-[11px] text-slate-400 mt-0.5">Taker Net Buy Volume Domination</div>
                </div>
                <div className="flex items-center space-x-1.5 font-bold">
                  {f.cvd > 0 ? (
                    <span className="text-emerald-400 flex items-center space-x-1">
                      <CheckCircle2 className="w-4 h-4" />
                      <span>Inflow (+{f.cvd.toFixed(1)})</span>
                    </span>
                  ) : (
                    <span className="text-slate-400 flex items-center space-x-1">
                      <XCircle className="w-4 h-4 text-slate-500" />
                      <span>Outflow ({f.cvd.toFixed(1)})</span>
                    </span>
                  )}
                </div>
              </div>

              {/* Factor 5: Volume Point of Control */}
              <div className="bg-slate-800/60 p-3 rounded-lg border border-slate-700/50 sm:col-span-2 flex items-center justify-between">
                <div>
                  <div className="font-semibold text-slate-200">5. Volume Point of Control (POC)</div>
                  <div className="text-[11px] text-slate-400 mt-0.5">Trading above POC support cluster (${f.poc.toFixed(2)})</div>
                </div>
                <div className="flex items-center space-x-1.5 font-bold">
                  {price >= f.poc ? (
                    <span className="text-emerald-400 flex items-center space-x-1">
                      <CheckCircle2 className="w-4 h-4" />
                      <span>Above POC Support</span>
                    </span>
                  ) : (
                    <span className="text-slate-400 flex items-center space-x-1">
                      <XCircle className="w-4 h-4 text-slate-500" />
                      <span>Below POC Resistance</span>
                    </span>
                  )}
                </div>
              </div>
            </div>
          </div>

          {/* Planned Trade Levels */}
          <div className="bg-slate-800/40 p-4 rounded-xl border border-slate-700/60 space-y-3">
            <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400 flex items-center space-x-1.5">
              <Crosshair className="w-3.5 h-3.5 text-amber-400" />
              <span>Simulated Execution & Exit Levels</span>
            </h4>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-xs font-mono">
              <div className="bg-slate-900/70 p-2.5 rounded-lg border border-slate-800">
                <span className="text-slate-400 block text-[10px]">Entry Price</span>
                <span className="text-slate-100 font-bold">${price.toFixed(2)}</span>
              </div>
              <div className="bg-slate-900/70 p-2.5 rounded-lg border border-slate-800">
                <span className="text-rose-400 block text-[10px]">Stop Loss ({config.atrMultiplierSl}x ATR)</span>
                <span className="text-rose-400 font-bold">${stopLoss.toFixed(2)}</span>
              </div>
              <div className="bg-slate-900/70 p-2.5 rounded-lg border border-slate-800">
                <span className="text-emerald-400 block text-[10px]">Take Profit ({config.atrMultiplierTp}x ATR)</span>
                <span className="text-emerald-400 font-bold">${takeProfit.toFixed(2)}</span>
              </div>
              <div className="bg-slate-900/70 p-2.5 rounded-lg border border-slate-800">
                <span className="text-amber-400 block text-[10px]">Trailing At (+{(config.trailingStopActivate * 100).toFixed(1)}%)</span>
                <span className="text-amber-400 font-bold">${trailingTrigger.toFixed(2)}</span>
              </div>
            </div>
          </div>

          {/* Interactive Order Calculator */}
          <div className="bg-slate-800/60 p-4 rounded-xl border border-slate-700/60">
            <h4 className="text-xs font-semibold uppercase tracking-wider text-slate-400 mb-2 flex items-center space-x-1.5">
              <Calculator className="w-3.5 h-3.5 text-sky-400" />
              <span>Tunable Order Size Calculator</span>
            </h4>
            <div className="flex flex-wrap items-center gap-3 text-xs">
              <div className="flex-1 min-w-[180px]">
                <label className="text-[10px] text-slate-400 block mb-1">Simulated Allocation (USDT)</label>
                <div className="flex items-center space-x-2">
                  <input
                    id="input-custom-allocation"
                    type="number"
                    min="10"
                    max={equity}
                    value={customAllocation}
                    onChange={(e) => setCustomAllocation(Math.max(10, parseFloat(e.target.value) || 10))}
                    className="bg-slate-900 border border-slate-700 rounded px-2.5 py-1.5 text-slate-100 font-mono w-32"
                  />
                  <span className="text-slate-400">
                    ≈ <strong className="text-slate-200 font-mono">{estimatedQuantity.toFixed(4)}</strong> {symbolData.symbol.replace('USDT', '')}
                  </span>
                </div>
              </div>

              <div className="text-right">
                <button
                  id={`modal-instant-buy-${symbolData.symbol}`}
                  onClick={() => {
                    onTriggerManualBuy(symbolData.symbol);
                    onClose();
                  }}
                  className="flex items-center space-x-1.5 px-4 py-2 rounded-lg font-bold bg-indigo-600 text-white hover:bg-indigo-500 shadow-md shadow-indigo-600/20 transition-all"
                >
                  <Zap className="w-4 h-4" />
                  <span>Instant Market Buy</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
