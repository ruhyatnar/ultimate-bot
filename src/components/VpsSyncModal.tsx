import React, { useState } from 'react';
import { 
  X, 
  Copy, 
  Check, 
  Terminal, 
  Server, 
  FileText, 
  RefreshCw, 
  AlertCircle,
  Sparkles,
  ArrowRight
} from 'lucide-react';
import { BotConfig } from '../types';

interface VpsSyncModalProps {
  config: BotConfig;
  onClose: () => void;
}

export const VpsSyncModal: React.FC<VpsSyncModalProps> = ({ config, onClose }) => {
  const [copiedScript, setCopiedScript] = useState<boolean>(false);
  const [copiedEnv, setCopiedEnv] = useState<boolean>(false);

  const generateEnvContent = () => {
    return `# =================================================================
# BINANCE ULTIMATE BOT — TUNED CONFIGURATION
# Generated via Interactive Web Monitor
# =================================================================

# --- Trading Mode ---
PAPER_TRADE=${config.paperTrade}
USE_TESTNET=${config.useTestnet}

# --- Binance Credentials ---
BINANCE_API_KEY=your_binance_api_key_here
BINANCE_PRIVATE_KEY_PATH=./keys/private_key.pem

# --- Preset Strategy Profile ---
PRESET=${config.preset}

# --- Technical Parameters ---
TIMEFRAME=${config.timeframe}
MTF_TIMEFRAME=${config.mtfTimeframe}
ATR_PERIOD=${config.atrPeriod}
ATR_MULTIPLIER_SL=${config.atrMultiplierSl}
ATR_MULTIPLIER_TP=${config.atrMultiplierTp}
TRAILING_STOP_ACTIVATE=${config.trailingStopActivate}
TRAILING_STOP_CALLBACK=${config.trailingStopCallback}
SWING_LOOKBACK=${config.swingLookback}
MAX_HOLD_TIME=${config.maxHoldTime}

# --- Confluence & Signal Engine ---
SIGNAL_THRESHOLD=${config.signalThreshold}
SIGNAL_INTERVAL=${config.signalInterval}

# --- Risk & Portfolio Limits ---
BALANCE_USAGE_PERCENT=${config.balanceUsagePercent}
MAX_SYMBOL_ALLOCATION_PERCENT=${config.maxSymbolAllocationPercent}
MAX_DAILY_DRAWDOWN=${config.maxDailyDrawdown}
MAX_LOSS_STREAK=${config.maxLossStreak}
MAX_WIN_STREAK=${config.maxWinStreak}
COOLDOWN_LOSS=${config.cooldownLoss}
COOLDOWN_WIN=${config.cooldownWin}

# --- Symbols Configuration ---
DYNAMIC_SYMBOLS=${config.dynamicSymbols}
MAX_SYMBOLS=${config.maxSymbols}
STATIC_SYMBOLS=${config.staticSymbols.join(',')}
QUOTE_ASSET=USDT
EXCLUDE_SYMBOLS=USDC,BUSD,UP,DOWN,FDUSD,TUSD,DAI

# --- Dynamic Screener & ADX ---
ADX_THRESHOLD=${config.adxThreshold}
ADX_PERIOD=${config.adxPeriod}
TOP_CANDIDATES=50
MIN_VOLUME_USDT=1000000

# --- Database & Webhooks ---
DB_PATH=./data/trading.db
DISCORD_WEBHOOK_URL=${config.discordWebhookUrl}
LOG_LEVEL=${config.logLevel}
`;
  };

  const bashCommand = `cat << 'EOF' > .env
${generateEnvContent()}EOF
pm2 reload ultimate-bot
./venv/bin/python3 status.py`;

  const handleCopyBash = () => {
    navigator.clipboard.writeText(bashCommand);
    setCopiedScript(true);
    setTimeout(() => setCopiedScript(false), 2000);
  };

  const handleCopyEnv = () => {
    if (navigator.clipboard) {
      navigator.clipboard.writeText(generateEnvContent());
    }
    setCopiedEnv(true);
    setTimeout(() => setCopiedEnv(false), 2000);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-950/80 backdrop-blur-sm animate-in fade-in">
      <div className="bg-slate-900 border border-slate-700 rounded-2xl w-full max-w-3xl overflow-hidden shadow-2xl flex flex-col max-h-[85vh]">
        {/* Header */}
        <div className="p-5 border-b border-slate-800 flex items-center justify-between">
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 rounded-xl bg-purple-500/10 border border-purple-500/30 flex items-center justify-center text-purple-400">
              <Server className="w-5 h-5" />
            </div>
            <div>
              <h3 className="font-bold text-base text-white">VPS Sync & Export Center</h3>
              <p className="text-xs text-slate-400">
                Apply web-tuned parameters directly to your Debian 13 VPS with zero downtime.
              </p>
            </div>
          </div>
          <button
            id="close-vps-sync-btn"
            onClick={onClose}
            className="p-1.5 rounded-lg text-slate-400 hover:text-white hover:bg-slate-800 transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="p-5 space-y-4 overflow-y-auto flex-1 text-xs">
          {/* Workflow Step Explanation */}
          <div className="bg-slate-800/60 p-4 rounded-xl border border-slate-700/60">
            <div className="font-semibold text-slate-200 mb-2 flex items-center space-x-1.5">
              <Sparkles className="w-4 h-4 text-amber-400" />
              <span>How Web-Tuned Parameters Sync to Your Debian 13 VPS</span>
            </div>
            <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-slate-300">
              <div className="bg-slate-900/60 p-2.5 rounded-lg border border-slate-800">
                <span className="font-bold text-amber-400 block mb-1">1. Tune Interactively</span>
                Adjust Preset, Confluence Threshold, or Dynamic Symbols in this web monitor.
              </div>
              <div className="bg-slate-900/60 p-2.5 rounded-lg border border-slate-800">
                <span className="font-bold text-purple-400 block mb-1">2. Run Sync Command</span>
                Paste the 1-click command into your SSH terminal inside <code className="text-purple-300">ultimate-bot/</code>.
              </div>
              <div className="bg-slate-900/60 p-2.5 rounded-lg border border-slate-800">
                <span className="font-bold text-emerald-400 block mb-1">3. Zero Downtime</span>
                PM2 reloads the process with the new configuration while preserving open positions.
              </div>
            </div>
          </div>

          {/* 1-Click SSH Command */}
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <span className="font-semibold text-slate-300 flex items-center space-x-1.5">
                <Terminal className="w-3.5 h-3.5 text-emerald-400" />
                <span>1-Click SSH Command (Overwrite .env & Graceful Reload)</span>
              </span>
              <button
                id="copy-ssh-command-btn"
                onClick={handleCopyBash}
                className="flex items-center space-x-1 px-2.5 py-1 rounded bg-indigo-600/30 text-indigo-200 border border-indigo-500/40 hover:bg-indigo-600 hover:text-white transition-colors"
              >
                {copiedScript ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                <span>{copiedScript ? 'Copied to Clipboard!' : 'Copy Full Command'}</span>
              </button>
            </div>
            <pre className="bg-slate-950 p-3 rounded-lg border border-slate-800 text-emerald-400 font-mono text-[11px] overflow-x-auto select-all">
              {bashCommand}
            </pre>
          </div>

          {/* Raw .env preview */}
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <span className="font-semibold text-slate-300 flex items-center space-x-1.5">
                <FileText className="w-3.5 h-3.5 text-slate-400" />
                <span>Generated .env File Content</span>
              </span>
              <button
                id="copy-env-btn"
                onClick={handleCopyEnv}
                className="text-slate-400 hover:text-white flex items-center space-x-1"
              >
                {copiedEnv ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
                <span>{copiedEnv ? 'Copied' : 'Copy .env only'}</span>
              </button>
            </div>
            <pre className="bg-slate-950 p-3 rounded-lg border border-slate-800 text-slate-300 font-mono text-[11px] max-h-48 overflow-y-auto">
              {generateEnvContent()}
            </pre>
          </div>
        </div>

        {/* Footer */}
        <div className="p-4 border-t border-slate-800 bg-slate-900/60 flex items-center justify-between text-xs text-slate-400">
          <span>Target Directory: <code>/path/to/ultimate-bot</code></span>
          <button
            id="done-vps-sync-btn"
            onClick={onClose}
            className="px-4 py-1.5 rounded-lg font-semibold bg-slate-800 text-slate-200 hover:bg-slate-700 transition-colors"
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
};
