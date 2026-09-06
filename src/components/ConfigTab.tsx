import React, { useState } from 'react';
import { 
  Sliders, 
  Save, 
  Copy, 
  Check, 
  RotateCcw, 
  Zap, 
  ShieldAlert, 
  Sparkles,
  Layers,
  Settings2,
  FileText
} from 'lucide-react';
import { BotConfig, StrategyPreset } from '../types';

interface ConfigTabProps {
  config: BotConfig;
  onUpdateConfig: (newConfig: BotConfig) => void;
  onApplyPreset: (preset: StrategyPreset) => void;
}

export const ConfigTab: React.FC<ConfigTabProps> = ({
  config,
  onUpdateConfig,
  onApplyPreset
}) => {
  const [copied, setCopied] = useState(false);
  const [savedNotice, setSavedNotice] = useState(false);

  const generateEnvString = () => {
    return `# =================================================================
# BINANCE API CREDENTIALS
# =================================================================
BINANCE_API_KEY=your_api_key_here
BINANCE_PRIVATE_KEY_PATH=./keys/private_key.pem

# =================================================================
# DATABASE
# =================================================================
DB_PATH=./data/trading.db

# =================================================================
# PRESET MODE
# =================================================================
PRESET=${config.preset}

# =================================================================
# TRADING STRATEGY PARAMETERS
# =================================================================
TIMEFRAME=${config.timeframe}
MTF_TIMEFRAME=${config.mtfTimeframe}
ATR_PERIOD=${config.atrPeriod}
ATR_MULTIPLIER_SL=${config.atrMultiplierSl}
ATR_MULTIPLIER_TP=${config.atrMultiplierTp}
TRAILING_STOP_ACTIVATE=${config.trailingStopActivate}
TRAILING_STOP_CALLBACK=${config.trailingStopCallback}
SWING_LOOKBACK=${config.swingLookback}
MAX_SLIPPAGE_PERCENT=0.5
MIN_TP_PERCENT=0.005
SIGNAL_THRESHOLD=${config.signalThreshold}
SIGNAL_INTERVAL=${config.signalInterval}

# =================================================================
# BALANCE USAGE
# =================================================================
BALANCE_USAGE_PERCENT=${config.balanceUsagePercent}
MAX_SYMBOL_ALLOCATION_PERCENT=${config.maxSymbolAllocationPercent}

# =================================================================
# DYNAMIC SYMBOLS
# =================================================================
DYNAMIC_SYMBOLS=${config.dynamicSymbols}
MAX_SYMBOLS=${config.maxSymbols}
TOP_CANDIDATES=50
MIN_VOLUME_USDT=1000000
MIN_PRICE_CHANGE_PERCENT=0.5
MIN_VOLATILITY_PERCENT=0.3
EXCLUDE_SYMBOLS=USDC,BUSD,UP,DOWN,FDUSD,TUSD,DAI
SYMBOL_REFRESH_INTERVAL=3600

# =================================================================
# ADVANCED TREND DETECTION
# =================================================================
ADX_THRESHOLD=${config.adxThreshold}
ADX_PERIOD=${config.adxPeriod}
Z_SCORE_WEIGHT_VOLUME=0.20
Z_SCORE_WEIGHT_CHANGE=0.20
Z_SCORE_WEIGHT_VOLATILITY=0.20
Z_SCORE_WEIGHT_ADX=0.40
CORRELATION_THRESHOLD=0.70
CORRELATION_PENALTY=0.90
TREND_LOOKBACK=20

# =================================================================
# TRADING PARAMETERS
# =================================================================
STATIC_SYMBOLS=${config.staticSymbols.join(',')}
QUOTE_ASSET=USDT
ORDER_TYPE=MARKET_ONLY
BASE_ORDER_SIZE=0.001
MAX_HOLD_TIME=${config.maxHoldTime}

# =================================================================
# RISK MANAGEMENT
# =================================================================
MAX_DAILY_DRAWDOWN=${config.maxDailyDrawdown}
MAX_LOSS_STREAK=${config.maxLossStreak}
MAX_WIN_STREAK=${config.maxWinStreak}
COOLDOWN_LOSS=${config.cooldownLoss}
COOLDOWN_WIN=${config.cooldownWin}

# =================================================================
# EXECUTION
# =================================================================
ENTRY_TIMEOUT=15

# =================================================================
# WEBHOOK & NOTIFICATION
# =================================================================
DISCORD_WEBHOOK_URL=${config.discordWebhookUrl}
DISCORD_COOLDOWN=30

# =================================================================
# LOGGING
# =================================================================
LOG_LEVEL=${config.logLevel}
LOG_FILE=./logs/trading.log

# =================================================================
# HEALTH CHECK & PERFORMANCE
# =================================================================
HEALTH_CHECK_INTERVAL=60
REST_WEIGHT_LIMIT=1200

# =================================================================
# ENVIRONMENT
# =================================================================
PAPER_TRADE=${config.paperTrade}
USE_TESTNET=${config.useTestnet}
`;
  };

  const handleCopyEnv = () => {
    navigator.clipboard.writeText(generateEnvString());
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleChange = (key: keyof BotConfig, value: any) => {
    onUpdateConfig({
      ...config,
      [key]: value
    });
    setSavedNotice(true);
    setTimeout(() => setSavedNotice(false), 1500);
  };

  return (
    <div className="space-y-6">
      {/* Preset Selector Banner */}
      <div className="bg-slate-800/80 border border-slate-700/60 rounded-xl p-5 shadow-sm">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <div className="flex items-center space-x-2">
              <Zap className="w-5 h-5 text-amber-400" />
              <h2 className="text-base font-bold text-white">Strategy Preset Profiles</h2>
              {savedNotice && (
                <span className="px-2 py-0.5 text-xs font-semibold rounded-full bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">
                  Settings Updated
                </span>
              )}
            </div>
            <p className="text-xs text-slate-400 mt-1">
              Select an optimized operational profile to instantly adjust timeframes, ATR stops, and trailing parameters.
            </p>
          </div>

          <div className="flex items-center space-x-2">
            <button
              onClick={() => onApplyPreset('scalping')}
              className={`px-3.5 py-2 rounded-lg text-xs font-bold transition-all ${
                config.preset === 'scalping'
                  ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-600/30 border border-indigo-400'
                  : 'bg-slate-900/80 text-slate-300 hover:bg-slate-700 border border-slate-700'
              }`}
            >
              Scalping (1m / 15m)
            </button>
            <button
              onClick={() => onApplyPreset('day')}
              className={`px-3.5 py-2 rounded-lg text-xs font-bold transition-all ${
                config.preset === 'day'
                  ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-600/30 border border-indigo-400'
                  : 'bg-slate-900/80 text-slate-300 hover:bg-slate-700 border border-slate-700'
              }`}
            >
              Day Trading (5m / 1h)
            </button>
            <button
              onClick={() => onApplyPreset('swing')}
              className={`px-3.5 py-2 rounded-lg text-xs font-bold transition-all ${
                config.preset === 'swing'
                  ? 'bg-indigo-600 text-white shadow-lg shadow-indigo-600/30 border border-indigo-400'
                  : 'bg-slate-900/80 text-slate-300 hover:bg-slate-700 border border-slate-700'
              }`}
            >
              Swing Trading (15m / 4h)
            </button>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left: Parameter Form */}
        <div className="lg:col-span-7 space-y-5">
          {/* Signal Engine Tuning */}
          <div className="bg-slate-800/80 border border-slate-700/60 rounded-xl p-5 shadow-sm space-y-4">
            <h3 className="text-xs font-bold uppercase tracking-wider text-amber-400 flex items-center space-x-2">
              <Layers className="w-4 h-4" />
              <span>Confluence & Signal Interval</span>
            </h3>

            <div className="space-y-4 text-xs">
              {/* Signal Threshold */}
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label className="font-semibold text-slate-200">
                    Signal Threshold: <span className="text-amber-400 font-bold">{config.signalThreshold} of 5 Bullish Indicators</span>
                  </label>
                  <span className="text-slate-400 text-[11px]">Recommended: 4</span>
                </div>
                <input
                  type="range"
                  min={1}
                  max={5}
                  step={1}
                  value={config.signalThreshold}
                  onChange={e => handleChange('signalThreshold', parseInt(e.target.value))}
                  className="w-full h-2 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-amber-500"
                />
                <p className="text-[11px] text-slate-400 mt-1">
                  Requires at least {config.signalThreshold} out of 5 indicators (HTF Trend, BOS, FVG, CVD, POC) before sending a Market BUY.
                </p>
              </div>

              {/* Signal Interval */}
              <div>
                <div className="flex items-center justify-between mb-1.5">
                  <label className="font-semibold text-slate-200">
                    Signal Check Interval: <span className="text-amber-400 font-bold">{config.signalInterval} seconds</span>
                  </label>
                  <span className="text-slate-400 text-[11px]">Default: 10s</span>
                </div>
                <input
                  type="range"
                  min={3}
                  max={60}
                  step={1}
                  value={config.signalInterval}
                  onChange={e => handleChange('signalInterval', parseInt(e.target.value))}
                  className="w-full h-2 bg-slate-700 rounded-lg appearance-none cursor-pointer accent-amber-500"
                />
              </div>

              {/* Monitored Symbols */}
              <div>
                <label className="font-semibold text-slate-200 block mb-1.5">
                  Static Symbols (comma separated)
                </label>
                <input
                  type="text"
                  value={config.staticSymbols.join(', ')}
                  onChange={e => handleChange('staticSymbols', e.target.value.split(',').map(s => s.trim().toUpperCase()).filter(Boolean))}
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-amber-500 font-mono text-xs"
                />
              </div>
            </div>
          </div>

          {/* ATR Risk & Exit Parameters */}
          <div className="bg-slate-800/80 border border-slate-700/60 rounded-xl p-5 shadow-sm space-y-4">
            <h3 className="text-xs font-bold uppercase tracking-wider text-rose-400 flex items-center space-x-2">
              <ShieldAlert className="w-4 h-4" />
              <span>Risk Management & Dynamic Exits</span>
            </h3>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
              <div>
                <label className="font-semibold text-slate-200 block mb-1">
                  ATR SL Multiplier ({config.atrMultiplierSl}x)
                </label>
                <input
                  type="number"
                  step="0.1"
                  min="0.5"
                  max="5.0"
                  value={config.atrMultiplierSl}
                  onChange={e => handleChange('atrMultiplierSl', parseFloat(e.target.value))}
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-slate-200 font-mono text-xs"
                />
              </div>

              <div>
                <label className="font-semibold text-slate-200 block mb-1">
                  ATR TP Multiplier ({config.atrMultiplierTp}x)
                </label>
                <input
                  type="number"
                  step="0.1"
                  min="1.0"
                  max="10.0"
                  value={config.atrMultiplierTp}
                  onChange={e => handleChange('atrMultiplierTp', parseFloat(e.target.value))}
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-slate-200 font-mono text-xs"
                />
              </div>

              <div>
                <label className="font-semibold text-slate-200 block mb-1">
                  Trailing Activate ({(config.trailingStopActivate * 100).toFixed(1)}%)
                </label>
                <input
                  type="number"
                  step="0.005"
                  min="0.005"
                  max="0.1"
                  value={config.trailingStopActivate}
                  onChange={e => handleChange('trailingStopActivate', parseFloat(e.target.value))}
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-slate-200 font-mono text-xs"
                />
              </div>

              <div>
                <label className="font-semibold text-slate-200 block mb-1">
                  Trailing Callback ({(config.trailingStopCallback * 100).toFixed(1)}%)
                </label>
                <input
                  type="number"
                  step="0.001"
                  min="0.001"
                  max="0.05"
                  value={config.trailingStopCallback}
                  onChange={e => handleChange('trailingStopCallback', parseFloat(e.target.value))}
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-slate-200 font-mono text-xs"
                />
              </div>

              <div>
                <label className="font-semibold text-slate-200 block mb-1">
                  Max Daily Drawdown ({(config.maxDailyDrawdown * 100).toFixed(1)}%)
                </label>
                <input
                  type="number"
                  step="0.01"
                  min="0.01"
                  max="0.25"
                  value={config.maxDailyDrawdown}
                  onChange={e => handleChange('maxDailyDrawdown', parseFloat(e.target.value))}
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-slate-200 font-mono text-xs"
                />
              </div>

              <div>
                <label className="font-semibold text-slate-200 block mb-1">
                  Max Position Allocation ({(config.maxSymbolAllocationPercent * 100).toFixed(0)}%)
                </label>
                <input
                  type="number"
                  step="0.05"
                  min="0.05"
                  max="1.0"
                  value={config.maxSymbolAllocationPercent}
                  onChange={e => handleChange('maxSymbolAllocationPercent', parseFloat(e.target.value))}
                  className="w-full bg-slate-900 border border-slate-700 rounded-lg px-3 py-2 text-slate-200 font-mono text-xs"
                />
              </div>
            </div>
          </div>
        </div>

        {/* Right: Live .env Output */}
        <div className="lg:col-span-5 bg-slate-900 border border-slate-800 rounded-xl overflow-hidden shadow-xl flex flex-col h-[620px]">
          <div className="p-4 bg-slate-850 bg-slate-800/60 border-b border-slate-800 flex items-center justify-between">
            <div className="flex items-center space-x-2">
              <FileText className="w-4 h-4 text-amber-400" />
              <span className="text-xs font-bold text-white font-mono">.env (Live Generator)</span>
            </div>

            <button
              onClick={handleCopyEnv}
              className="flex items-center space-x-1.5 px-3 py-1.5 rounded-md text-xs font-semibold bg-slate-700 text-slate-200 hover:bg-slate-600 transition-colors"
            >
              {copied ? (
                <>
                  <Check className="w-3.5 h-3.5 text-emerald-400" />
                  <span>Copied</span>
                </>
              ) : (
                <>
                  <Copy className="w-3.5 h-3.5" />
                  <span>Copy .env</span>
                </>
              )}
            </button>
          </div>

          <div className="flex-1 p-4 overflow-auto font-mono text-xs text-slate-300 bg-slate-950/70 leading-relaxed scrollbar-thin">
            <pre>
              <code>{generateEnvString()}</code>
            </pre>
          </div>
        </div>
      </div>
    </div>
  );
};
