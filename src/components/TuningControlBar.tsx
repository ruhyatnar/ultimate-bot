import React, { useState } from 'react';
import { 
  Sliders, 
  Activity, 
  Clock, 
  Percent, 
  Flame, 
  ChevronDown, 
  ChevronUp, 
  Globe, 
  AlertOctagon,
  Sparkles,
  Share2,
  PauseCircle,
  PlayCircle
} from 'lucide-react';
import { BotConfig, StrategyPreset } from '../types';

interface TuningControlBarProps {
  config: BotConfig;
  onUpdateConfig: (newConfig: BotConfig) => void;
  onApplyPreset: (preset: StrategyPreset) => void;
  onCloseAllTrades: () => void;
  onSimulateConfluenceBoost: (symbol: string) => void;
  onOpenVpsSync: () => void;
  useLiveBinanceFeed: boolean;
  onToggleLiveBinanceFeed: () => void;
  activeSymbols: string[];
  activeTradesCount: number;
  vpsConnected?: boolean;
  controlPaused?: boolean;
  onToggleVpsPause?: () => void;
}

export const TuningControlBar: React.FC<TuningControlBarProps> = ({
  config,
  onUpdateConfig,
  onApplyPreset,
  onCloseAllTrades,
  onSimulateConfluenceBoost,
  onOpenVpsSync,
  useLiveBinanceFeed,
  onToggleLiveBinanceFeed,
  activeSymbols,
  activeTradesCount,
  vpsConnected = false,
  controlPaused = false,
  onToggleVpsPause
}) => {
  const [isExpanded, setIsExpanded] = useState<boolean>(false);
  const [selectedBoostSymbol, setSelectedBoostSymbol] = useState<string>(activeSymbols[0] || 'BTCUSDT');
  const [showPanicConfirm, setShowPanicConfirm] = useState<boolean>(false);

  const getThresholdLabel = (val: number) => {
    switch (val) {
      case 1:
      case 2:
        return { label: 'Aggressive / High Frequency', color: 'text-amber-400', bg: 'bg-amber-500/10 border-amber-500/30' };
      case 3:
        return { label: 'Moderate / Standard', color: 'text-sky-400', bg: 'bg-sky-500/10 border-sky-500/30' };
      case 4:
        return { label: 'Recommended (Optimal Confluence)', color: 'text-emerald-400', bg: 'bg-emerald-500/10 border-emerald-500/30' };
      case 5:
        return { label: 'Ultra-Strict (All 5 Must Align)', color: 'text-purple-400', bg: 'bg-purple-500/10 border-purple-500/30' };
      default:
        return { label: `${val}/5 Confluence`, color: 'text-slate-300', bg: 'bg-slate-800 border-slate-700' };
    }
  };

  const thresholdInfo = getThresholdLabel(config.signalThreshold);

  return (
    <div className="bg-slate-900/90 border border-slate-700/70 rounded-xl shadow-lg p-4 transition-all">
      {/* Top Primary Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        {/* Left: Preset Selector */}
        <div className="flex items-center space-x-2">
          <span className="text-xs font-semibold text-slate-400 flex items-center space-x-1.5">
            <Sliders className="w-3.5 h-3.5 text-amber-400" />
            <span>Active Preset:</span>
          </span>
          <div className="inline-flex rounded-lg bg-slate-800 p-1 border border-slate-700/60 text-xs">
            {(['scalping', 'day', 'swing'] as StrategyPreset[]).map((p) => {
              const isSelected = config.preset === p;
              return (
                <button
                  key={p}
                  id={`preset-btn-${p}`}
                  onClick={() => onApplyPreset(p)}
                  className={`px-2.5 py-1 rounded-md font-semibold transition-all capitalize ${
                    isSelected
                      ? 'bg-amber-500 text-slate-950 shadow-sm shadow-amber-500/30'
                      : 'text-slate-400 hover:text-slate-200 hover:bg-slate-700/50'
                  }`}
                >
                  {p === 'scalping' && '⚡ '}
                  {p === 'day' && '📅 '}
                  {p === 'swing' && '🌊 '}
                  {p}
                </button>
              );
            })}
          </div>
        </div>

        {/* Center: Dynamic Mode & Live Feed Badges */}
        <div className="flex items-center space-x-2 text-xs">
          {/* Dynamic / Static Toggle */}
          <button
            id="toggle-dynamic-symbols-btn"
            onClick={() => onUpdateConfig({ ...config, dynamicSymbols: !config.dynamicSymbols })}
            className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-lg border font-medium transition-all ${
              config.dynamicSymbols
                ? 'bg-indigo-500/20 text-indigo-300 border-indigo-500/40 shadow-sm shadow-indigo-500/10'
                : 'bg-slate-800 text-slate-400 border-slate-700 hover:text-slate-200'
            }`}
          >
            <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
            <span>Dynamic Screener: <strong>{config.dynamicSymbols ? 'ON (Top Momentum)' : 'OFF (Static)'}</strong></span>
          </button>

          {/* Binance Live Feed vs Sim */}
          <button
            id="toggle-live-feed-btn"
            onClick={onToggleLiveBinanceFeed}
            className={`flex items-center space-x-1.5 px-3 py-1.5 rounded-lg border font-medium transition-all ${
              useLiveBinanceFeed
                ? 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30'
                : 'bg-slate-800 text-slate-400 border-slate-700 hover:text-slate-200'
            }`}
          >
            <Globe className="w-3.5 h-3.5 text-emerald-400" />
            <span>Feed: <strong>{useLiveBinanceFeed ? 'Binance Live Ticker' : 'Sandbox Sim'}</strong></span>
          </button>
        </div>

        {/* Right: Quick Actions & Expand */}
        <div className="flex items-center space-x-2 ml-auto">
          {/* Remote Engine Pause / Resume (VPS mode only) */}
          {vpsConnected && onToggleVpsPause && (
            <button
              id="vps-pause-toggle-btn"
              onClick={onToggleVpsPause}
              className={`flex items-center space-x-1 px-3 py-1.5 rounded-lg text-xs font-semibold border transition-all shadow-sm ${
                controlPaused
                  ? 'bg-amber-500/20 text-amber-300 border-amber-500/40 hover:bg-amber-500 hover:text-white'
                  : 'bg-slate-800 text-slate-300 border-slate-700 hover:bg-slate-700 hover:text-white'
              }`}
              title={controlPaused ? 'Resume the live engine (entries re-enabled)' : 'Pause new entries on the live engine (open positions stay managed)'}
            >
              {controlPaused ? <PlayCircle className="w-3.5 h-3.5" /> : <PauseCircle className="w-3.5 h-3.5" />}
              <span>{controlPaused ? 'Engine Paused — Resume' : 'Pause Engine'}</span>
            </button>
          )}

          {/* VPS Sync Button */}
          <button
            id="open-vps-sync-btn"
            onClick={onOpenVpsSync}
            className="flex items-center space-x-1 px-3 py-1.5 rounded-lg text-xs font-semibold bg-purple-600/20 text-purple-300 border border-purple-500/40 hover:bg-purple-600 hover:text-white transition-all shadow-sm"
          >
            <Share2 className="w-3.5 h-3.5" />
            <span>Sync to VPS .env</span>
          </button>

          {/* Emergency Panic Button */}
          {activeTradesCount > 0 && (
            <button
              id="panic-close-all-btn"
              onClick={() => setShowPanicConfirm(true)}
              className="flex items-center space-x-1 px-3 py-1.5 rounded-lg text-xs font-semibold bg-rose-600/20 text-rose-300 border border-rose-500/40 hover:bg-rose-600 hover:text-white transition-all shadow-sm"
            >
              <AlertOctagon className="w-3.5 h-3.5" />
              <span>Close All ({activeTradesCount})</span>
            </button>
          )}

          {/* Expand Details Toggle */}
          <button
            id="toggle-tuner-expand-btn"
            onClick={() => setIsExpanded(prev => !prev)}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 border border-slate-700 transition-colors"
            title="Toggle Live Parameter Sliders"
          >
            {isExpanded ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
          </button>
        </div>
      </div>

      {/* Panic Confirmation Banner */}
      {showPanicConfirm && (
        <div className="mt-3 p-3 rounded-lg bg-rose-950/60 border border-rose-500/50 flex items-center justify-between text-xs animate-in fade-in">
          <div className="flex items-center space-x-2 text-rose-200">
            <AlertOctagon className="w-4 h-4 text-rose-400 shrink-0" />
            <span>
              <strong>EMERGENCY LIQUIDATION:</strong> Immediately execute market sell orders for all <strong>{activeTradesCount}</strong> active positions?
            </span>
          </div>
          <div className="flex items-center space-x-2">
            <button
              id="confirm-panic-close-btn"
              onClick={() => {
                onCloseAllTrades();
                setShowPanicConfirm(false);
              }}
              className="px-3 py-1 rounded font-bold bg-rose-600 text-white hover:bg-rose-500 transition-colors"
            >
              Confirm Close All
            </button>
            <button
              id="cancel-panic-close-btn"
              onClick={() => setShowPanicConfirm(false)}
              className="px-3 py-1 rounded font-medium bg-slate-800 text-slate-300 hover:bg-slate-700 transition-colors"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* Expanded Interactive Tuners & Sliders */}
      {isExpanded && (
        <div className="mt-4 pt-4 border-t border-slate-800 grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 text-xs">
          {/* Confluence Threshold Slider */}
          <div className="bg-slate-800/60 p-3 rounded-lg border border-slate-700/50 space-y-2">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-slate-300 flex items-center space-x-1.5">
                <Activity className="w-3.5 h-3.5 text-indigo-400" />
                <span>Confluence Threshold</span>
              </span>
              <span className={`px-2 py-0.5 rounded font-bold text-xs border ${thresholdInfo.bg} ${thresholdInfo.color}`}>
                {config.signalThreshold}/5
              </span>
            </div>
            <input
              id="slider-signal-threshold"
              type="range"
              min="1"
              max="5"
              step="1"
              value={config.signalThreshold}
              onChange={(e) => onUpdateConfig({ ...config, signalThreshold: parseInt(e.target.value) })}
              className="w-full accent-indigo-500 cursor-pointer"
            />
            <div className="text-[11px] text-slate-400 truncate">
              {thresholdInfo.label}
            </div>
          </div>

          {/* Tick Interval & Max Symbols */}
          <div className="bg-slate-800/60 p-3 rounded-lg border border-slate-700/50 space-y-2">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-slate-300 flex items-center space-x-1.5">
                <Clock className="w-3.5 h-3.5 text-amber-400" />
                <span>Scan Interval & Max Pairs</span>
              </span>
              <span className="font-mono text-slate-200 font-bold">
                {config.signalInterval}s • Max {config.maxSymbols}
              </span>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="text-[10px] text-slate-400 block mb-1">Interval (sec)</label>
                <input
                  id="slider-signal-interval"
                  type="range"
                  min="2"
                  max="30"
                  step="1"
                  value={config.signalInterval}
                  onChange={(e) => onUpdateConfig({ ...config, signalInterval: parseInt(e.target.value) })}
                  className="w-full accent-amber-500 cursor-pointer"
                />
              </div>
              <div>
                <label className="text-[10px] text-slate-400 block mb-1">Max Positions</label>
                <input
                  id="slider-max-symbols"
                  type="range"
                  min="1"
                  max="6"
                  step="1"
                  value={config.maxSymbols}
                  onChange={(e) => onUpdateConfig({ ...config, maxSymbols: parseInt(e.target.value) })}
                  className="w-full accent-amber-500 cursor-pointer"
                />
              </div>
            </div>
          </div>

          {/* Risk Allocations (Balance Usage & Single Symbol) */}
          <div className="bg-slate-800/60 p-3 rounded-lg border border-slate-700/50 space-y-2">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-slate-300 flex items-center space-x-1.5">
                <Percent className="w-3.5 h-3.5 text-emerald-400" />
                <span>Capital Allocation</span>
              </span>
              <span className="font-mono text-emerald-400 font-bold">
                {(config.balanceUsagePercent * 100).toFixed(0)}% / Max {(config.maxSymbolAllocationPercent * 100).toFixed(0)}%
              </span>
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="text-[10px] text-slate-400 block mb-1">Total Usage %</label>
                <input
                  id="slider-balance-usage"
                  type="range"
                  min="0.1"
                  max="1.0"
                  step="0.05"
                  value={config.balanceUsagePercent}
                  onChange={(e) => onUpdateConfig({ ...config, balanceUsagePercent: parseFloat(e.target.value) })}
                  className="w-full accent-emerald-500 cursor-pointer"
                />
              </div>
              <div>
                <label className="text-[10px] text-slate-400 block mb-1">Max Per Coin %</label>
                <input
                  id="slider-symbol-allocation"
                  type="range"
                  min="0.05"
                  max="0.5"
                  step="0.05"
                  value={config.maxSymbolAllocationPercent}
                  onChange={(e) => onUpdateConfig({ ...config, maxSymbolAllocationPercent: parseFloat(e.target.value) })}
                  className="w-full accent-emerald-500 cursor-pointer"
                />
              </div>
            </div>
          </div>

          {/* Confluence Event Simulator */}
          <div className="bg-slate-800/60 p-3 rounded-lg border border-slate-700/50 flex flex-col justify-between">
            <div className="flex items-center justify-between">
              <span className="font-semibold text-slate-300 flex items-center space-x-1.5">
                <Flame className="w-3.5 h-3.5 text-orange-400" />
                <span>Simulate Inflow Event</span>
              </span>
              <span className="text-[10px] text-slate-500">Test Trigger</span>
            </div>
            <p className="text-[10px] text-slate-400 mt-1">
              Injects instant CVD buyer surge + FVG gap to trigger live confluence buy.
            </p>
            <div className="mt-2 flex items-center space-x-1.5">
              <select
                id="select-boost-symbol"
                value={selectedBoostSymbol}
                onChange={(e) => setSelectedBoostSymbol(e.target.value)}
                className="bg-slate-900 border border-slate-700 rounded px-2 py-1 text-xs text-slate-200 flex-1"
              >
                {activeSymbols.map((s) => (
                  <option key={s} value={s}>{s}</option>
                ))}
              </select>
              <button
                id="trigger-confluence-boost-btn"
                onClick={() => onSimulateConfluenceBoost(selectedBoostSymbol)}
                className="px-2.5 py-1 rounded bg-orange-500/20 text-orange-300 border border-orange-500/40 hover:bg-orange-500 hover:text-white font-semibold transition-colors"
              >
                Trigger
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
