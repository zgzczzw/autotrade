"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { fetchMarketKlines, fetchTicker } from "@/lib/api";
import { KlineChartModule } from "@/components/kline-chart";
import { SymbolSelector } from "@/components/symbol-selector";
import { TickerBar } from "@/components/ticker-bar";

const TIMEFRAMES = [
  { label: "15m", value: "15m" },
  { label: "1h",  value: "1h"  },
  { label: "4h",  value: "4h"  },
  { label: "1d",  value: "1d"  },
];

const DEFAULT_SYMBOL = "BTCUSDT";
const DEFAULT_TF = "1h";
const KLINES_LIMIT = 200;

export default function MarketPage() {
  const [symbol, setSymbol] = useState(DEFAULT_SYMBOL);
  const [timeframe, setTimeframe] = useState(DEFAULT_TF);
  const [klines, setKlines] = useState<any[]>([]);
  const [ticker, setTicker] = useState<any>(null);
  const [klinesLoading, setKlinesLoading] = useState(false);
  const [tickerLoading, setTickerLoading] = useState(false);

  // 轮询 interval refs
  const tickerTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const klinesTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadTicker = useCallback(async (sym: string) => {
    try {
      const data = await fetchTicker(sym);
      setTicker(data);
    } catch {
      // 静默失败，保留旧数据
    }
  }, []);

  const loadKlines = useCallback(async (sym: string, tf: string) => {
    setKlinesLoading(true);
    try {
      const data = await fetchMarketKlines(sym, tf, KLINES_LIMIT);
      setKlines(data as any[]);
    } catch {
      setKlines([]);
    } finally {
      setKlinesLoading(false);
    }
  }, []);

  // 初始加载 + symbol/timeframe 变化时重新加载
  useEffect(() => {
    setTickerLoading(true);
    loadTicker(symbol).finally(() => setTickerLoading(false));
    loadKlines(symbol, timeframe);
  }, [symbol, timeframe, loadTicker, loadKlines]);

  // 启动轮询
  useEffect(() => {
    if (tickerTimerRef.current) clearInterval(tickerTimerRef.current);
    if (klinesTimerRef.current) clearInterval(klinesTimerRef.current);

    tickerTimerRef.current = setInterval(() => loadTicker(symbol), 30_000);
    klinesTimerRef.current = setInterval(() => loadKlines(symbol, timeframe), 60_000);

    return () => {
      if (tickerTimerRef.current) clearInterval(tickerTimerRef.current);
      if (klinesTimerRef.current) clearInterval(klinesTimerRef.current);
    };
  }, [symbol, timeframe, loadTicker, loadKlines]);

  return (
    <div className="flex flex-col gap-4 h-full">
      {/* 顶栏：交易对选择 + 时间周期 */}
      <div className="flex items-center justify-between gap-4 flex-wrap">
        <SymbolSelector value={symbol} onChange={setSymbol} />

        <div className="flex items-center gap-1 bg-slate-900 border border-slate-800 rounded-lg p-1">
          {TIMEFRAMES.map((tf) => (
            <button
              key={tf.value}
              onClick={() => setTimeframe(tf.value)}
              className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
                timeframe === tf.value
                  ? "bg-blue-600 text-white"
                  : "text-slate-400 hover:text-slate-200"
              }`}
            >
              {tf.label}
            </button>
          ))}
        </div>
      </div>

      {/* 行情摘要 */}
      <TickerBar ticker={ticker} loading={tickerLoading} />

      {/* K 线图 */}
      <div className="flex-1 min-h-0">
        {klinesLoading && klines.length === 0 ? (
          <div className="flex items-center justify-center h-full text-slate-500 text-sm">
            加载中...
          </div>
        ) : (
          <KlineChartModule
            data={klines}
            indicators={{ ma: true, volume: true }}
            height={560}
            title={symbol}
            subtitle={timeframe}
          />
        )}
      </div>
    </div>
  );
}
