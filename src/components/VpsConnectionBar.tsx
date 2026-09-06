import React, { useState } from 'react';
import { 
  Server, 
  Wifi, 
  WifiOff, 
  RefreshCw, 
  Settings2, 
  CheckCircle2, 
  AlertTriangle, 
  ExternalLink,
  ShieldCheck,
  Cpu,
  Database
} from 'lucide-react';
import { VpsBotStatus } from '../types';

interface VpsConnectionBarProps {
  dataSource: 'vps' | 'simulator';
  onToggleDataSource: (source: 'vps' | 'simulator') => void;
  vpsStatus: VpsBotStatus;
  vpsEndpoint: string;
  onUpdateVpsEndpoint: (url: string) => void;
  onRefreshVps: () => void;
  isPolling: boolean;
}

export const VpsConnectionBar: React.FC<VpsConnectionBarProps> = ({
  dataSource,
  onToggleDataSource,
  vpsStatus,
  vpsEndpoint,
  onUpdateVpsEndpoint,
  onRefreshVps,
  isPolling
}) => {
  const [showConfigModal, setShowConfigModal] = useState<boolean>(false);
  const [inputUrl, setInputUrl] = useState<string>(vpsEndpoint);
  const [testResult, setTestResult] = useState<{ success?: boolean; message?: string } | null>(null);
  const [isTesting, setIsTesting] = useState<boolean>(false);

  const handleTestConnection = async () => {
    setIsTesting(true);
    setTestResult(null);
    const targetUrl = (inputUrl || window.location.origin).replace(/\/+$/, '');
    const testEndpoint = targetUrl.endsWith('/api/status') ? targetUrl : `${targetUrl}/api/status`;

    try {
      const startTime = performance.now();
      const res = await fetch(testEndpoint, { mode: 'cors' });
      const elapsed = Math.round(performance.now() - startTime);

      if (!res.ok) {
        throw new Error(`HTTP ${res.status}: ${res.statusText}`);
      }
      const data = await res.json();
      setTestResult({
        success: true,
        message: `Connected successfully! Latency: ${elapsed}ms | Engine: ${data.process || 'OK'} | Trades in DB: ${data.data?.trades?.length ?? 0}`
      });
    } catch (err: any) {
      setTestResult({
        success: false,
        message: `Connection failed: ${err.message}. Make sure status.py --web 3000 is running on your VPS and port 3000 is allowed in your Tencent Cloud firewall.`
      });
    } finally {
      setIsTesting(false);
    }
  };

  const handleSaveEndpoint = () => {
    onUpdateVpsEndpoint(inputUrl.trim());
    setShowConfigModal(false);
    onRefreshVps();
  };

  return (
    <div className="bg-slate-950/90 border-b border-slate-800 px-4 py-2 sm:px-6 lg:px-8 text-xs">
      <div className="max-w-7xl mx-auto flex flex-wrap items-center justify-between gap-3">
        {/* Source Mode Toggle */}
        <div className="flex items-center space-x-2">
          <span className="text-slate-400 font-medium hidden sm:inline">Data Source:</span>
          <div className="inline-flex rounded-lg bg-slate-900 p-0.5 border border-slate-800">
            <button
              id="source-vps-btn"
              onClick={() => onToggleDataSource('vps')}
              className={`flex items-center space-x-1.5 px-3 py-1 rounded-md transition-all font-medium ${
                dataSource === 'vps'
                  ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Server className="w-3.5 h-3.5" />
              <span>Live VPS Bot Sync</span>
              {dataSource === 'vps' && vpsStatus.connected && (
                <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
              )}
            </button>
            <button
              id="source-sim-btn"
              onClick={() => onToggleDataSource('simulator')}
              className={`flex items-center space-x-1.5 px-3 py-1 rounded-md transition-all font-medium ${
                dataSource === 'simulator'
                  ? 'bg-indigo-500/20 text-indigo-300 border border-indigo-500/40 shadow-sm'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              <Cpu className="w-3.5 h-3.5" />
              <span>Strategy Simulator</span>
            </button>
          </div>
        </div>

        {/* Live Status Indicators */}
        <div className="flex items-center space-x-3 sm:space-x-4">
          {dataSource === 'vps' ? (
            <>
              <div className="flex items-center space-x-2">
                {vpsStatus.connected ? (
                  <span className="inline-flex items-center space-x-1 text-emerald-400 bg-emerald-950/60 border border-emerald-800/60 px-2 py-0.5 rounded-full font-medium">
                    <Wifi className="w-3 h-3" />
                    <span>VPS Online</span>
                    {vpsStatus.latencyMs !== undefined && (
                      <span className="text-slate-400 font-normal text-[10px]">({vpsStatus.latencyMs}ms)</span>
                    )}
                  </span>
                ) : (
                  <span className="inline-flex items-center space-x-1 text-rose-400 bg-rose-950/60 border border-rose-800/60 px-2 py-0.5 rounded-full font-medium">
                    <WifiOff className="w-3 h-3" />
                    <span>VPS Disconnected</span>
                  </span>
                )}
              </div>

              {/* Engine process badge */}
              <div className="hidden md:flex items-center space-x-1.5 text-slate-300 bg-slate-900 border border-slate-800 px-2 py-0.5 rounded-md">
                <span className="text-slate-400">Process:</span>
                <span className={vpsStatus.engineRunning ? 'text-emerald-400 font-semibold' : 'text-amber-400 font-semibold'}>
                  {vpsStatus.engineStatus || 'Checking...'}
                </span>
              </div>

              {/* Sync timestamp */}
              {vpsStatus.lastSyncTime && (
                <span className="text-slate-400 text-[11px] hidden lg:inline">
                  Last Sync: {vpsStatus.lastSyncTime}
                </span>
              )}

              {/* Manual refresh button */}
              <button
                id="refresh-vps-btn"
                onClick={onRefreshVps}
                disabled={isPolling}
                title="Force refresh database status"
                className="p-1 rounded bg-slate-900 border border-slate-800 text-slate-300 hover:text-white hover:bg-slate-800 transition-colors"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${isPolling ? 'animate-spin text-amber-400' : ''}`} />
              </button>

              {/* Connection setup button */}
              <button
                id="config-endpoint-btn"
                onClick={() => {
                  setInputUrl(vpsEndpoint);
                  setTestResult(null);
                  setShowConfigModal(true);
                }}
                className="flex items-center space-x-1 px-2 py-1 rounded bg-slate-900 border border-slate-800 text-slate-300 hover:text-white hover:bg-slate-800 transition-colors"
              >
                <Settings2 className="w-3.5 h-3.5 text-slate-400" />
                <span className="hidden sm:inline">VPS Endpoint</span>
              </button>
            </>
          ) : (
            <div className="flex items-center space-x-2 text-slate-400 text-[11px]">
              <span className="w-2 h-2 rounded-full bg-indigo-400 animate-ping" />
              <span>Forward-testing simulator running locally with simulated execution.</span>
            </div>
          )}
        </div>
      </div>

      {/* VPS Endpoint Settings Modal */}
      {showConfigModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm">
          <div className="bg-slate-900 border border-slate-800 rounded-xl max-w-lg w-full p-6 shadow-2xl space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-slate-800">
              <div className="flex items-center space-x-2">
                <Server className="w-5 h-5 text-emerald-400" />
                <h3 className="text-base font-semibold text-white">Connect Real Bot (VPS)</h3>
              </div>
              <button
                onClick={() => setShowConfigModal(false)}
                className="text-slate-400 hover:text-white text-lg font-bold"
              >
                ✕
              </button>
            </div>

            <div className="space-y-3 text-slate-300">
              <p className="text-xs text-slate-400 leading-relaxed">
                Enter your VPS IP and port where <code className="text-amber-400">status.py --web 3000</code> or PM2 is running.
                If you are serving the web dashboard directly from the VPS, leave this empty or use <code className="text-amber-400">/api</code>.
              </p>

              <div>
                <label className="block text-xs font-medium text-slate-300 mb-1">
                  VPS Bot Server URL
                </label>
                <input
                  type="text"
                  value={inputUrl}
                  onChange={(e) => setInputUrl(e.target.value)}
                  placeholder="e.g. http://100.96.0.8:3000 or leave empty for current host"
                  className="w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-sm text-white font-mono placeholder-slate-600 focus:outline-none focus:border-emerald-500"
                />
              </div>

              {testResult && (
                <div
                  className={`p-3 rounded-lg text-xs border ${
                    testResult.success
                      ? 'bg-emerald-950/60 border-emerald-800 text-emerald-300'
                      : 'bg-rose-950/60 border-rose-800 text-rose-300'
                  }`}
                >
                  <div className="flex items-start space-x-2">
                    {testResult.success ? (
                      <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
                    ) : (
                      <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
                    )}
                    <span>{testResult.message}</span>
                  </div>
                </div>
              )}

              <div className="bg-slate-950 p-3 rounded-lg border border-slate-800/80 space-y-1 text-[11px] text-slate-400">
                <div className="font-semibold text-slate-300 flex items-center space-x-1">
                  <Database className="w-3.5 h-3.5 text-amber-400" />
                  <span>How Real VPS Data Works:</span>
                </div>
                <p>1. On your VPS, run: <code className="text-amber-300">./venv/bin/python3 status.py --web 3000</code></p>
                <p>2. Ensure port 3000 is open in Tencent Cloud Security Group (Inbound TCP: 3000).</p>
                <p>3. The web dashboard will automatically read SQLite <code className="text-emerald-300">trading.db</code> active trades, daily PnL, win streaks, and orders in real-time!</p>
              </div>
            </div>

            <div className="flex items-center justify-between pt-3 border-t border-slate-800">
              <button
                type="button"
                onClick={handleTestConnection}
                disabled={isTesting}
                className="px-3.5 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 text-xs font-semibold flex items-center space-x-1.5 transition-colors"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${isTesting ? 'animate-spin' : ''}`} />
                <span>{isTesting ? 'Testing...' : 'Test Connection'}</span>
              </button>

              <div className="flex space-x-2">
                <button
                  type="button"
                  onClick={() => setShowConfigModal(false)}
                  className="px-3 py-1.5 rounded-lg text-slate-400 hover:text-white text-xs"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  onClick={handleSaveEndpoint}
                  className="px-4 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-semibold transition-colors shadow-sm"
                >
                  Save & Connect
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
