"use client";

import { TrendingUp, TrendingDown } from "lucide-react";

interface TickerData {
  symbol: string;
  price: number;
  change_pct: number;
  high_24h: number;
  low_24h: number;
  volume_24h: number;
}

interface TickerBarProps {
  ticker: TickerData | null;
  loading?: boolean;
}

function fmt(n: number, decimals = 2): string {
  if (n >= 1000) return n.toLocaleString("en-US", { maximumFractionDigits: 2 });
  return n.toFixed(decimals);
}

function fmtVol(n: number): string {
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(2) + "M";
  if (n >= 1_000) return (n / 1_000).toFixed(2) + "K";
  return n.toFixed(4);
}

export function TickerBar({ ticker, loading }: TickerBarProps) {
  if (loading || !ticker) {
    return (
      <div className="flex items-center gap-6 px-4 py-3 bg-slate-900 border border-slate-800 rounded-xl animate-pulse">
        {[...Array(5)].map((_, i) => (
          <div key={i} className="h-4 w-24 bg-slate-700 rounded" />
        ))}
      </div>
    );
  }

  const isUp = ticker.change_pct >= 0;
  const changeColor = isUp ? "text-green-400" : "text-red-400";
  const TrendIcon = isUp ? TrendingUp : TrendingDown;

  return (
    <div className="px-4 py-3 bg-slate-900 border border-slate-800 rounded-xl">
      {/* 移动端：两行布局 */}
      <div className="flex flex-col gap-1.5 md:hidden">
        <div className="flex items-baseline gap-2">
          <span className={`text-xl font-bold font-mono ${changeColor}`}>
            ${fmt(ticker.price)}
          </span>
          <span className={`flex items-center gap-0.5 text-sm font-medium ${changeColor}`}>
            <TrendIcon className="w-3 h-3" />
            {isUp ? "+" : ""}{ticker.change_pct.toFixed(2)}%
          </span>
        </div>
        <div className="flex items-center gap-4 text-xs text-slate-400">
          <span><span className="text-slate-500">高</span> <span className="font-mono text-slate-200">${fmt(ticker.high_24h)}</span></span>
          <span><span className="text-slate-500">低</span> <span className="font-mono text-slate-200">${fmt(ticker.low_24h)}</span></span>
          <span><span className="text-slate-500">量</span> <span className="font-mono text-slate-200">{fmtVol(ticker.volume_24h)}</span></span>
        </div>
      </div>

      {/* 桌面端：单行展开布局 */}
      <div className="hidden md:flex items-center gap-6 flex-wrap">
        <div className="flex items-baseline gap-2">
          <span className={`text-2xl font-bold font-mono ${changeColor}`}>
            ${fmt(ticker.price)}
          </span>
          <span className={`flex items-center gap-1 text-sm font-medium ${changeColor}`}>
            <TrendIcon className="w-3.5 h-3.5" />
            {isUp ? "+" : ""}{ticker.change_pct.toFixed(2)}%
          </span>
        </div>

        <div className="h-8 w-px bg-slate-700" />

        <div className="flex items-center gap-4 text-sm">
          <div>
            <span className="text-slate-500 mr-1.5">24h 高</span>
            <span className="text-slate-200 font-mono">${fmt(ticker.high_24h)}</span>
          </div>
          <div>
            <span className="text-slate-500 mr-1.5">24h 低</span>
            <span className="text-slate-200 font-mono">${fmt(ticker.low_24h)}</span>
          </div>
        </div>

        <div className="h-8 w-px bg-slate-700" />

        <div className="text-sm">
          <span className="text-slate-500 mr-1.5">24h 量</span>
          <span className="text-slate-200 font-mono">{fmtVol(ticker.volume_24h)}</span>
        </div>
      </div>
    </div>
  );
}
