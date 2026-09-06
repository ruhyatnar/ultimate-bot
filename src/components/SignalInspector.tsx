import React from 'react';
import { 
  Activity, 
  TrendingUp, 
  TrendingDown, 
  BarChart2, 
  Layers, 
  Compass, 
  Target,
  CheckCircle,
  XCircle,
  AlertCircle,
  Info
} from 'lucide-react';
import { MarketSymbolData, BotConfig } from '../types';

interface SignalInspectorProps {
  symbolsData: MarketSymbolData[];
  config: BotConfig;
  onTriggerManualBuy: (symbol: string) => void;
}

export const SignalInspector: React.FC<SignalInspectorProps> = ({
  symbolsData,
  config,
  onTriggerManualBuy
}) => {
  return (
    <div className="space-y-6">
      {/* Intro Header */}
      <div className="bg-slate-800/80 border border-slate-700/60 rounded-xl p-5 shadow-sm">
        <div className="flex flex-col md:flex-row md:items-center md:justify-between gap-4">
          <div>
            <div className="flex items-center space-x-2">
              <Activity className="w-5 h-5 text-indigo-400" />
              <h2 className="text-base font-bold text-white">5-Factor Confluence Signal Engine</h2>
              <span className="px-2 py-0.5 text-xs font-semibold rounded-full bg-indigo-500/20 text-indigo-300 border border-indigo-500/30">
                Threshold: {config.signalThreshold}/5
              </span>
            </div>
            <p className="text-xs text-slate-400 mt-1 max-w-2xl">
              Signals require at least <strong>{config.signalThreshold} out of 5 bullish factors</strong> to execute a Market BUY order. All 5 indicators are recalculated on every tick and interval ({config.signalInterval}s).
            </p>
          </div>

          <div className="grid grid-cols-2 sm:grid-cols-3 gap-2 text-xs">
            <div className="bg-slate-900/60 p-2.5 rounded-lg border border-slate-700/50">
              <span className="text-slate-400">LTF Interval:</span>
              <div className="font-bold text-slate-100">{config.timeframe}</div>
            </div>
            <div className="bg-slate-900/60 p-2.5 rounded-lg border border-slate-700/50">
              <span className="text-slate-400">HTF Interval:</span>
              <div className="font-bold text-slate-100">{config.mtfTimeframe}</div>
            </div>
            <div className="bg-slate-900/60 p-2.5 rounded-lg border border-slate-700/50 col-span-2 sm:col-span-1">
              <span className="text-slate-400">ATR Lookback:</span>
              <div className="font-bold text-slate-100">{config.atrPeriod} bars</div>
            </div>
          </div>
        </div>
      </div>

      {/* Symbols Confluence Matrix */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
        {symbolsData.map(sym => {
          const f = sym.factors;
          const meetsThreshold = f.bullishScore >= config.signalThreshold;

          return (
            <div 
              key={sym.symbol} 
              className={`rounded-xl border p-5 transition-all shadow-sm ${
                meetsThreshold
                  ? 'bg-gradient-to-b from-slate-800 to-emerald-950/20 border-emerald-500/40'
                  : 'bg-slate-800/90 border-slate-700/60'
              }`}
            >
              {/* Card Header */}
              <div className="flex items-center justify-between pb-4 border-b border-slate-700/60">
                <div>
                  <div className="flex items-center space-x-2.5">
                    <span className="text-lg font-bold text-white">{sym.symbol}</span>
                    <span className="font-mono text-sm text-slate-300 font-semibold">
                      ${sym.price.toLocaleString('en-US', { minimumFractionDigits: 2 })}
                    </span>
                  </div>
                  <div className="text-xs text-slate-400 mt-0.5">
                    24h Volume: ${(sym.volume24h / 1e6).toFixed(1)}M • ADX: <strong className="text-slate-200">{f.adx.toFixed(1)}</strong>
                  </div>
                </div>

                <div className="flex items-center space-x-2">
                  <div className={`px-3 py-1 rounded-lg text-xs font-bold flex items-center space-x-1.5 ${
                    meetsThreshold
                      ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                      : 'bg-slate-700/50 text-slate-300 border border-slate-600/50'
                  }`}>
                    {meetsThreshold ? (
                      <>
                        <CheckCircle className="w-3.5 h-3.5 text-emerald-400" />
                        <span>BUY TRIGGER ({f.bullishScore}/{config.signalThreshold})</span>
                      </>
                    ) : (
                      <>
                        <XCircle className="w-3.5 h-3.5 text-slate-400" />
                        <span>SKIPPED ({f.bullishScore}/{config.signalThreshold})</span>
                      </>
                    )}
                  </div>
                </div>
              </div>

              {/* 5 Indicator Factor Breakdown */}
              <div className="py-4 space-y-2.5">
                {/* 1. HTF Trend */}
                <div className="flex items-center justify-between p-2.5 rounded-lg bg-slate-900/60 border border-slate-700/40 text-xs">
                  <div className="flex items-center space-x-2">
                    <TrendingUp className="w-4 h-4 text-indigo-400" />
                    <div>
                      <span className="font-semibold text-slate-200">1. HTF Trend (EMA50 / EMA200)</span>
                      <p className="text-[11px] text-slate-400">Trend baseline on {config.mtfTimeframe}</p>
                    </div>
                  </div>
                  <div className="text-right">
                    <span className={`px-2 py-0.5 rounded font-bold text-[11px] ${
                      f.htfTrend === 'UP'
                        ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                        : f.htfTrend === 'DOWN'
                        ? 'bg-rose-500/20 text-rose-300 border border-rose-500/30'
                        : 'bg-slate-700 text-slate-300'
                    }`}>
                      {f.htfTrend}
                    </span>
                    <span className="ml-2 text-slate-400 font-semibold">{f.htfTrend === 'UP' ? '+1 Bull' : '0'}</span>
                  </div>
                </div>

                {/* 2. LTF Break of Structure */}
                <div className="flex items-center justify-between p-2.5 rounded-lg bg-slate-900/60 border border-slate-700/40 text-xs">
                  <div className="flex items-center space-x-2">
                    <Layers className="w-4 h-4 text-amber-400" />
                    <div>
                      <span className="font-semibold text-slate-200">2. Break of Structure (BOS)</span>
                      <p className="text-[11px] text-slate-400">Swing high/low expansion ({config.swingLookback} bar lookback)</p>
                    </div>
                  </div>
                  <div className="text-right">
                    <span className={`px-2 py-0.5 rounded font-bold text-[11px] ${
                      f.bos === 'BULLISH'
                        ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                        : f.bos === 'BEARISH'
                        ? 'bg-rose-500/20 text-rose-300 border border-rose-500/30'
                        : 'bg-slate-700 text-slate-300'
                    }`}>
                      {f.bos}
                    </span>
                    <span className="ml-2 text-slate-400 font-semibold">{f.bos === 'BULLISH' ? '+1 Bull' : '0'}</span>
                  </div>
                </div>

                {/* 3. Fair Value Gap (FVG) */}
                <div className="flex items-center justify-between p-2.5 rounded-lg bg-slate-900/60 border border-slate-700/40 text-xs">
                  <div className="flex items-center space-x-2">
                    <Compass className="w-4 h-4 text-sky-400" />
                    <div>
                      <span className="font-semibold text-slate-200">3. Fair Value Gap (FVG)</span>
                      <p className="text-[11px] text-slate-400">3-bar liquidity displacement gap</p>
                    </div>
                  </div>
                  <div className="text-right">
                    <span className={`px-2 py-0.5 rounded font-bold text-[11px] ${
                      f.fvg > 0
                        ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                        : f.fvg < 0
                        ? 'bg-rose-500/20 text-rose-300 border border-rose-500/30'
                        : 'bg-slate-700 text-slate-300'
                    }`}>
                      {f.fvg > 0 ? '+1 Bull Gap' : f.fvg < 0 ? '-1 Bear Gap' : 'None'}
                    </span>
                    <span className="ml-2 text-slate-400 font-semibold">{f.fvg > 0 ? '+1 Bull' : '0'}</span>
                  </div>
                </div>

                {/* 4. Cumulative Volume Delta (CVD) */}
                <div className="flex items-center justify-between p-2.5 rounded-lg bg-slate-900/60 border border-slate-700/40 text-xs">
                  <div className="flex items-center space-x-2">
                    <BarChart2 className="w-4 h-4 text-purple-400" />
                    <div>
                      <span className="font-semibold text-slate-200">4. Cumulative Volume Delta (CVD)</span>
                      <p className="text-[11px] text-slate-400">Taker buy vs sell aggressive pressure</p>
                    </div>
                  </div>
                  <div className="text-right">
                    <span className={`px-2 py-0.5 rounded font-bold font-mono text-[11px] ${
                      f.cvd > 0
                        ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                        : 'bg-rose-500/20 text-rose-300 border border-rose-500/30'
                    }`}>
                      {f.cvd > 0 ? `+${Math.round(f.cvd)}` : Math.round(f.cvd)}
                    </span>
                    <span className="ml-2 text-slate-400 font-semibold">{f.cvd > 0 ? '+1 Bull' : '0'}</span>
                  </div>
                </div>

                {/* 5. Point of Control (POC) */}
                <div className="flex items-center justify-between p-2.5 rounded-lg bg-slate-900/60 border border-slate-700/40 text-xs">
                  <div className="flex items-center space-x-2">
                    <Target className="w-4 h-4 text-rose-400" />
                    <div>
                      <span className="font-semibold text-slate-200">5. Point of Control (POC)</span>
                      <p className="text-[11px] text-slate-400">POC price: ${f.poc.toFixed(2)} (High Volume Node)</p>
                    </div>
                  </div>
                  <div className="text-right">
                    <span className={`px-2 py-0.5 rounded font-bold text-[11px] ${
                      f.currentPrice > f.poc
                        ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                        : 'bg-rose-500/20 text-rose-300 border border-rose-500/30'
                    }`}>
                      {f.currentPrice > f.poc ? 'Price > POC' : 'Price < POC'}
                    </span>
                    <span className="ml-2 text-slate-400 font-semibold">{f.currentPrice > f.poc ? '+1 Bull' : '0'}</span>
                  </div>
                </div>
              </div>

              {/* Confluence Reason & Debug Output */}
              <div className="pt-3 border-t border-slate-700/60 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 text-xs">
                <div className="flex items-start space-x-1.5 text-slate-400">
                  <Info className="w-4 h-4 text-slate-400 mt-0.5 shrink-0" />
                  <div>
                    <span className="font-semibold text-slate-300">Engine Evaluation: </span>
                    <span className={meetsThreshold ? 'text-emerald-300 font-medium' : 'text-slate-400'}>
                      {meetsThreshold ? f.reason : f.skippedReason || f.reason}
                    </span>
                  </div>
                </div>

                <div className="shrink-0">
                  <button
                    id={`test-buy-${sym.symbol}`}
                    onClick={() => onTriggerManualBuy(sym.symbol)}
                    className="w-full sm:w-auto px-3 py-1 rounded-md text-xs font-semibold bg-indigo-600 text-white hover:bg-indigo-500 transition-colors shadow-sm"
                  >
                    Simulate Signal Trigger
                  </button>
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
