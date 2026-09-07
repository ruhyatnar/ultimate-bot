import React from 'react';
import { 
  Play, 
  Pause, 
  RotateCcw, 
  Sliders, 
  Terminal, 
  Activity, 
  FileCode2, 
  BookOpen, 
  Zap,
  TrendingUp
} from 'lucide-react';
import { BotConfig } from '../types';

interface HeaderProps {
  isRunning: boolean;
  onToggleRunning: () => void;
  onResetSimulation: () => void;
  activeTab: 'dashboard' | 'signals' | 'debug' | 'code' | 'config' | 'deploy';
  setActiveTab: (tab: 'dashboard' | 'signals' | 'debug' | 'code' | 'config' | 'deploy') => void;
  config: BotConfig;
  activeTradesCount: number;
  unrealizedPnl: number;
  totalEquity: number;
  dataSource?: 'vps' | 'simulator';
  vpsConnected?: boolean;
  isLossCooldown?: boolean;
}

export const Header: React.FC<HeaderProps> = ({
  isRunning,
  onToggleRunning,
  onResetSimulation,
  activeTab,
  setActiveTab,
  config,
  activeTradesCount,
  unrealizedPnl,
  totalEquity,
  dataSource = 'vps',
  vpsConnected = false,
  isLossCooldown = false
}) => {
  return (
    <header className="bg-slate-900 border-b border-slate-800 sticky top-0 z-30">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          {/* Logo & Brand */}
          <div className="flex items-center space-x-3">
            <div className="w-10 h-10 rounded-xl bg-amber-500/10 border border-amber-500/30 flex items-center justify-center text-amber-400 shadow-sm shadow-amber-500/10">
              <Zap className="w-5 h-5 fill-amber-400/20" />
            </div>
            <div>
              <div className="flex items-center space-x-2">
                <span className="text-lg font-bold tracking-tight text-white">Binance Bot Monitor</span>
                {dataSource === 'vps' ? (
                  <span className={`px-2 py-0.5 text-xs font-semibold rounded-full border ${
                    vpsConnected 
                      ? 'bg-emerald-500/15 text-emerald-400 border-emerald-500/30'
                      : 'bg-rose-500/15 text-rose-400 border-rose-500/30'
                  }`}>
                    {vpsConnected ? '● Live VPS Synced' : '○ VPS Offline'}
                  </span>
                ) : (
                  <span className="px-2 py-0.5 text-xs font-semibold rounded-full bg-indigo-500/15 text-indigo-300 border border-indigo-500/30">
                    Simulator Sandbox
                  </span>
                )}
                <span className={`px-2 py-0.5 text-xs font-semibold rounded-full border ${
                  config.paperTrade 
                    ? 'bg-sky-500/10 text-sky-400 border-sky-500/20' 
                    : 'bg-emerald-500/10 text-emerald-400 border-emerald-500/20'
                }`}>
                  {config.paperTrade ? 'Paper Mode' : 'LIVE SPOT'}
                </span>
                {isLossCooldown && (
                  <span className="px-2 py-0.5 text-xs font-semibold rounded-full bg-rose-500/15 text-rose-400 border border-rose-500/30 animate-pulse">
                    ⏸ Cooldown
                  </span>
                )}
                <span className="px-2 py-0.5 text-xs font-semibold rounded-full bg-slate-800 text-slate-300 border border-slate-700 capitalize hidden sm:inline">
                  {config.preset}
                </span>
              </div>
              <p className="text-xs text-slate-400 hidden sm:block">
                Tencent Cloud VPS Sync • SQLite Database • 5-Factor Confluence • Dynamic ATR
              </p>
            </div>
          </div>

          {/* Quick Metrics Bar */}
          <div className="hidden lg:flex items-center space-x-5 px-4 py-1.5 rounded-lg bg-slate-800/60 border border-slate-700/60 text-xs">
            <div>
              <span className="text-slate-400">Equity: </span>
              <span className="font-bold text-slate-100">${totalEquity.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</span>
            </div>
            <div className="w-px h-3.5 bg-slate-700" />
            <div>
              <span className="text-slate-400">Unrealized: </span>
              <span className={`font-bold ${unrealizedPnl >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                {unrealizedPnl >= 0 ? '+' : ''}${unrealizedPnl.toFixed(2)}
              </span>
            </div>
            <div className="w-px h-3.5 bg-slate-700" />
            <div>
              <span className="text-slate-400">Active Trades: </span>
              <span className="font-bold text-amber-300">{activeTradesCount}</span>
              <span className="text-slate-500">/{config.maxSymbols}</span>
            </div>
          </div>

          {/* Engine Controls */}
          <div className="flex items-center space-x-2">
            <button
              id="bot-toggle-btn"
              onClick={onToggleRunning}
              className={`flex items-center space-x-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold transition-all shadow-sm ${
                isRunning
                  ? 'bg-amber-500/15 text-amber-300 border border-amber-500/30 hover:bg-amber-500/25'
                  : 'bg-emerald-600 text-white hover:bg-emerald-500 shadow-emerald-600/20'
              }`}
            >
              {isRunning ? (
                <>
                  <Pause className="w-3.5 h-3.5" />
                  <span>Pause Engine</span>
                </>
              ) : (
                <>
                  <Play className="w-3.5 h-3.5 fill-white" />
                  <span>Run Bot</span>
                </>
              )}
            </button>

            <button
              id="bot-reset-btn"
              onClick={onResetSimulation}
              title="Reset paper simulation balance & history"
              className="p-1.5 text-slate-400 hover:text-slate-200 hover:bg-slate-800 rounded-lg border border-slate-700/50 transition-colors"
            >
              <RotateCcw className="w-3.5 h-3.5" />
            </button>
          </div>
        </div>

        {/* Tab Navigation */}
        <div className="flex items-center space-x-1 overflow-x-auto py-2 border-t border-slate-800/80 scrollbar-none">
          <button
            id="tab-dashboard"
            onClick={() => setActiveTab('dashboard')}
            className={`flex items-center space-x-2 px-3 py-1.5 rounded-md text-xs font-medium whitespace-nowrap transition-colors ${
              activeTab === 'dashboard'
                ? 'bg-slate-800 text-white border border-slate-700 shadow-sm'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
            }`}
          >
            <TrendingUp className="w-3.5 h-3.5 text-amber-400" />
            <span>Trading Desk</span>
          </button>

          <button
            id="tab-signals"
            onClick={() => setActiveTab('signals')}
            className={`flex items-center space-x-2 px-3 py-1.5 rounded-md text-xs font-medium whitespace-nowrap transition-colors ${
              activeTab === 'signals'
                ? 'bg-slate-800 text-white border border-slate-700 shadow-sm'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
            }`}
          >
            <Activity className="w-3.5 h-3.5 text-indigo-400" />
            <span>5-Factor Confluence</span>
          </button>

          <button
            id="tab-debug"
            onClick={() => setActiveTab('debug')}
            className={`flex items-center space-x-2 px-3 py-1.5 rounded-md text-xs font-medium whitespace-nowrap transition-colors ${
              activeTab === 'debug'
                ? 'bg-slate-800 text-white border border-slate-700 shadow-sm'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
            }`}
          >
            <Terminal className="w-3.5 h-3.5 text-emerald-400" />
            <span>Debug Log (Skipped Symbols)</span>
          </button>

          <button
            id="tab-code"
            onClick={() => setActiveTab('code')}
            className={`flex items-center space-x-2 px-3 py-1.5 rounded-md text-xs font-medium whitespace-nowrap transition-colors ${
              activeTab === 'code'
                ? 'bg-slate-800 text-white border border-slate-700 shadow-sm'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
            }`}
          >
            <FileCode2 className="w-3.5 h-3.5 text-sky-400" />
            <span>Project Code & ZIP</span>
          </button>

          <button
            id="tab-config"
            onClick={() => setActiveTab('config')}
            className={`flex items-center space-x-2 px-3 py-1.5 rounded-md text-xs font-medium whitespace-nowrap transition-colors ${
              activeTab === 'config'
                ? 'bg-slate-800 text-white border border-slate-700 shadow-sm'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
            }`}
          >
            <Sliders className="w-3.5 h-3.5 text-purple-400" />
            <span>Strategy & .env Config</span>
          </button>

          <button
            id="tab-deploy"
            onClick={() => setActiveTab('deploy')}
            className={`flex items-center space-x-2 px-3 py-1.5 rounded-md text-xs font-medium whitespace-nowrap transition-colors ${
              activeTab === 'deploy'
                ? 'bg-slate-800 text-white border border-slate-700 shadow-sm'
                : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/50'
            }`}
          >
            <BookOpen className="w-3.5 h-3.5 text-orange-400" />
            <span>VPS Deployment Guide</span>
          </button>
        </div>
      </div>
    </header>
  );
};
