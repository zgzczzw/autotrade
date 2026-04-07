"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useSearchParams } from "next/navigation";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { BacktestPanel } from "@/components/backtest-panel";
import dynamic from "next/dynamic";
import { TradeMarker } from "@/components/kline-chart/types";

const KlineChartModule = dynamic(
  () => import("@/components/kline-chart").then((mod) => mod.KlineChartModule),
  { ssr: false }
);
import { fetchMarketKlines } from "@/lib/api";
import { formatPrice, formatSymbol, formatDateTime, parseUTCTimestamp } from "@/lib/utils";
import { ArrowLeft, ChevronLeft, ChevronRight, History, Pencil, Play, Square, TrendingUp, TrendingDown, Activity, Target, BarChart3 } from "lucide-react";
import axios from "axios";
import {
  StrategyPreview,
  deserializeConfig,
} from "@/components/visual-strategy-editor";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "";

interface Strategy {
  id: number;
  name: string;
  type: string;
  symbol: string;
  symbols?: string[];
  timeframe: string;
  status: string;
  position_size: number;
  position_size_type: string;
  stop_loss?: number;
  take_profit?: number;
  sell_size_pct: number;
  notify_enabled: boolean;
  config_json?: string;
  code?: string;
  created_at: string;
  updated_at: string;
  trigger_count?: number;
  position_count?: number;
}

interface Trigger {
  id: number;
  strategy_id: number;
  symbol?: string;
  triggered_at: string;
  signal_type: string;
  signal_detail?: string;
  action?: string;
  price?: number;
  quantity?: number;
  simulated_pnl?: number;
}

interface Position {
  id: number;
  strategy_id: number;
  symbol: string;
  side: string;
  entry_price: number;
  quantity: number;
  current_price?: number;
  pnl?: number;
  unrealized_pnl?: number;
  opened_at: string;
  closed_at?: string;
}

export default function StrategyDetailPage() {
  const params = useParams();
  const searchParams = useSearchParams();
  const id = params.id as string;
  const initialTab = searchParams.get("tab") || "overview";
  const [activeTab, setActiveTab] = useState(initialTab);
  const [strategy, setStrategy] = useState<Strategy | null>(null);
  const [loading, setLoading] = useState(true);
  const [triggers, setTriggers] = useState<Trigger[]>([]);
  const [triggersTotal, setTriggersTotal] = useState(0);
  const [triggersPage, setTriggersPage] = useState(1);
  const [triggersLoading, setTriggersLoading] = useState(false);
  const [triggersLoaded, setTriggersLoaded] = useState(false);
  const [currentPositions, setCurrentPositions] = useState<Position[]>([]);
  const [posHistory, setPosHistory] = useState<Position[]>([]);
  const [posHistoryTotal, setPosHistoryTotal] = useState(0);
  const [posHistoryPage, setPosHistoryPage] = useState(1);
  const [positionsLoading, setPositionsLoading] = useState(false);
  const [positionsLoaded, setPositionsLoaded] = useState(false);
  const [klines, setKlines] = useState<any[]>([]);
  const [klinesLoading, setKlinesLoading] = useState(false);
  const [chartPeriod, setChartPeriod] = useState("1h");
  const [focusTimestamp, setFocusTimestamp] = useState<number | undefined>();
  const [allTriggers, setAllTriggers] = useState<Trigger[]>([]);
  const [stats, setStats] = useState<any>(null);
  const [statsLoading, setStatsLoading] = useState(true);

  const loadStats = async () => {
    setStatsLoading(true);
    try {
      const response = await axios.get(`${API_BASE_URL}/api/strategies/${id}/stats`);
      setStats(response.data);
    } catch (error) {
      console.error("Failed to load stats:", error);
    } finally {
      setStatsLoading(false);
    }
  };

  useEffect(() => {
    loadStrategy();
    loadStats();
    const interval = setInterval(() => { loadStrategy(); loadStats(); }, 30000);
    return () => clearInterval(interval);
  }, [id]);

  const strategySymbols = strategy?.symbols || (strategy?.symbol ? [strategy.symbol] : []);

  // 如果 URL 带 tab 参数，等 strategy 加载完后加载对应数据
  useEffect(() => {
    if (!strategy) return;
    if (activeTab === "triggers" && !triggersLoaded) {
      loadTriggers(1);
      const firstSymbol = strategySymbols[0];
      if (firstSymbol) loadKlines(firstSymbol, chartPeriod);
      loadAllTriggers();
    }
    if (activeTab === "positions" && !positionsLoaded) {
      loadPositions(1);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [strategy, activeTab]);

  const loadStrategy = async () => {
    try {
      const response = await axios.get(`${API_BASE_URL}/api/strategies/${id}`);
      setStrategy(response.data);
    } catch (error) {
      console.error("Failed to load strategy:", error);
    } finally {
      setLoading(false);
    }
  };

  const loadTriggers = async (page = 1) => {
    setTriggersLoading(true);
    try {
      const response = await axios.get(
        `${API_BASE_URL}/api/triggers?strategy_id=${id}&page=${page}&page_size=20`
      );
      setTriggers(response.data.items || []);
      setTriggersTotal(response.data.total || 0);
      setTriggersPage(page);
    } catch (error) {
      console.error("Failed to load triggers:", error);
    } finally {
      setTriggersLoading(false);
      setTriggersLoaded(true);
    }
  };

  const loadKlines = async (sym: string, tf: string) => {
    setKlinesLoading(true);
    try {
      const data = await fetchMarketKlines(sym, tf, 500);
      setKlines(data as any[]);
    } catch (error) {
      console.error("Failed to load klines:", error);
    } finally {
      setKlinesLoading(false);
    }
  };

  const loadAllTriggers = async () => {
    try {
      const response = await axios.get(
        `${API_BASE_URL}/api/triggers?strategy_id=${id}&page=1&page_size=500`
      );
      setAllTriggers(response.data.items || []);
    } catch (error) {
      console.error("Failed to load all triggers:", error);
    }
  };

  const handleChartPeriodChange = (period: string) => {
    setChartPeriod(period);
    const firstSymbol = strategySymbols[0];
    if (firstSymbol) {
      loadKlines(firstSymbol, period);
    }
  };

  const tradeMarkers: TradeMarker[] = useMemo(() => {
    return allTriggers
      .filter((t) => t.action && t.action !== "观望" && t.price)
      .map((t) => ({
        timestamp: parseUTCTimestamp(t.triggered_at),
        price: t.price!,
        side: (t.action === "买入" ? "buy" : "sell") as "buy" | "sell",
        quantity: t.quantity,
        pnl: t.simulated_pnl,
      }));
  }, [allTriggers]);

  const loadPositions = async (page = 1) => {
    setPositionsLoading(true);
    try {
      if (page === 1) {
        const [openRes, historyRes] = await Promise.all([
          axios.get(`${API_BASE_URL}/api/positions?strategy_id=${id}`),
          axios.get(`${API_BASE_URL}/api/positions/history?strategy_id=${id}&page=1&page_size=20`),
        ]);
        setCurrentPositions(openRes.data.items || []);
        setPosHistory(historyRes.data.items || []);
        setPosHistoryTotal(historyRes.data.total || 0);
        setPosHistoryPage(1);
        setPositionsLoaded(true);
      } else {
        const historyRes = await axios.get(
          `${API_BASE_URL}/api/positions/history?strategy_id=${id}&page=${page}&page_size=20`
        );
        setPosHistory(historyRes.data.items || []);
        setPosHistoryTotal(historyRes.data.total || 0);
        setPosHistoryPage(page);
        setPositionsLoaded(true);
      }
    } catch (error) {
      console.error("Failed to load positions:", error);
    } finally {
      setPositionsLoading(false);
    }
  };

  const handleToggle = async () => {
    if (!strategy) return;
    try {
      if (strategy.status === "running") {
        await axios.post(`${API_BASE_URL}/api/strategies/${strategy.id}/stop`);
      } else {
        await axios.post(`${API_BASE_URL}/api/strategies/${strategy.id}/start`);
      }
      loadStrategy();
    } catch (error) {
      console.error("Failed to toggle strategy:", error);
      alert("操作失败");
    }
  };

  const getStatusBadge = (status: string) => {
    switch (status) {
      case "running":
        return <Badge className="bg-green-600">运行中</Badge>;
      case "stopped":
        return <Badge variant="secondary">已停止</Badge>;
      case "error":
        return <Badge variant="destructive">错误</Badge>;
      default:
        return <Badge variant="outline">{status}</Badge>;
    }
  };

  const getActionBadge = (action?: string) => {
    switch (action) {
      case "buy":
      case "买入":
        return <Badge className="bg-green-600">买入</Badge>;
      case "sell":
      case "卖出":
        return <Badge className="bg-red-600">卖出</Badge>;
      case "short":
      case "开空":
        return <Badge className="bg-orange-600">开空</Badge>;
      case "cover":
      case "平空":
        return <Badge className="bg-purple-600">平空</Badge>;
      default:
        return <Badge variant="secondary">观望</Badge>;
    }
  };

  if (loading) {
    return <div className="text-center py-12">加载中...</div>;
  }

  if (!strategy) {
    return <div className="text-center py-12 text-red-400">策略不存在</div>;
  }

  return (
    <div>
      <div className="flex items-center justify-between mb-8">
        <div className="flex items-center gap-4">
          <Link href="/strategies">
            <Button variant="ghost" size="icon">
              <ArrowLeft className="w-5 h-5" />
            </Button>
          </Link>
          <div>
            <h1 className="text-3xl font-bold">{strategy.name}</h1>
            <div className="flex items-center gap-1.5 mt-1 flex-wrap">
              {(strategy.symbols || (strategy.symbol ? [strategy.symbol] : [])).map((s) => (
                <span key={s} className="text-xs text-slate-400 font-mono bg-slate-800 px-1.5 py-0.5 rounded">
                  {formatSymbol(s)}
                </span>
              ))}
              <span className="text-slate-600">·</span>
              <span className="text-xs text-slate-400">{strategy.timeframe}</span>
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {strategy.status === "stopped" && (
            <Link href={`/strategies/${strategy.id}/edit`}>
              <Button variant="outline">
                <Pencil className="w-4 h-4 mr-2" />
                编辑
              </Button>
            </Link>
          )}
          <Button
            variant={strategy.status === "running" ? "destructive" : "default"}
            onClick={handleToggle}
          >
            {strategy.status === "running" ? (
              <>
                <Square className="w-4 h-4 mr-2" />
                停止
              </>
            ) : (
              <>
                <Play className="w-4 h-4 mr-2" />
                启动
              </>
            )}
          </Button>
        </div>
      </div>

      <Tabs
        value={activeTab}
        className="space-y-6"
        onValueChange={(value) => {
          setActiveTab(value);
          if (value === "triggers" && !triggersLoaded) {
            loadTriggers(1);
            const firstSym = strategySymbols[0];
            if (firstSym) {
              loadKlines(firstSym, chartPeriod);
            }
            loadAllTriggers();
          }
          if (value === "positions" && !positionsLoaded) {
            loadPositions(1);
          }
        }}
      >
        <TabsList className="bg-slate-900">
          <TabsTrigger value="overview">概览</TabsTrigger>
          <TabsTrigger value="triggers">触发历史</TabsTrigger>
          <TabsTrigger value="positions">持仓</TabsTrigger>
          <TabsTrigger value="backtest">回测</TabsTrigger>
        </TabsList>

        <TabsContent value="overview">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            <Card className="bg-slate-900 border-slate-800">
              <CardHeader>
                <CardTitle>策略信息</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex justify-between">
                  <span className="text-slate-400">状态</span>
                  {getStatusBadge(strategy.status)}
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">类型</span>
                  <span>{strategy.type === "visual" ? "可视化" : "代码"}</span>
                </div>
                <div className="flex justify-between items-start">
                  <span className="text-slate-400">交易对</span>
                  <div className="flex flex-wrap gap-1 justify-end">
                    {(strategy.symbols || (strategy.symbol ? [strategy.symbol] : [])).map((s) => (
                      <span key={s} className="text-xs font-mono bg-slate-800 px-1.5 py-0.5 rounded">
                        {formatSymbol(s)}
                      </span>
                    ))}
                  </div>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">时间周期</span>
                  <span>{strategy.timeframe}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">每次买入</span>
                  <span>
                    {strategy.position_size}
                    {strategy.position_size_type === "fixed" ? " USDT" : "% 余额"}
                  </span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">每次卖出</span>
                  <span>{strategy.sell_size_pct ?? 100}%</span>
                </div>
                {strategy.stop_loss && (
                  <div className="flex justify-between">
                    <span className="text-slate-400">止损</span>
                    <span>{strategy.stop_loss}%</span>
                  </div>
                )}
                {strategy.take_profit && (
                  <div className="flex justify-between">
                    <span className="text-slate-400">止盈</span>
                    <span>{strategy.take_profit}%</span>
                  </div>
                )}
                <div className="flex justify-between">
                  <span className="text-slate-400">飞书通知</span>
                  <span>{strategy.notify_enabled ? "已开启" : "已关闭"}</span>
                </div>
              </CardContent>
            </Card>

            {strategy.type === "visual" && strategy.config_json && strategy.config_json !== "{}" && (
              <Card className="bg-slate-900 border-slate-800 md:col-span-2">
                <CardHeader>
                  <CardTitle>策略条件</CardTitle>
                </CardHeader>
                <CardContent>
                  <StrategyPreview
                    config={deserializeConfig(strategy.config_json)}
                    stopLoss={strategy.stop_loss}
                    takeProfit={strategy.take_profit}
                  />
                </CardContent>
              </Card>
            )}

            {strategy.type === "code" && strategy.code && (
              <Card className="bg-slate-900 border-slate-800 md:col-span-2">
                <CardHeader>
                  <CardTitle>策略代码</CardTitle>
                </CardHeader>
                <CardContent className="p-0">
                  <pre className="p-4 text-sm font-mono text-slate-200 overflow-x-auto whitespace-pre leading-relaxed">
                    {strategy.code}
                  </pre>
                </CardContent>
              </Card>
            )}

            {/* 绩效统计 */}
            <Card className="bg-slate-900 border-slate-800 md:col-span-2">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <BarChart3 className="w-5 h-5" />
                  绩效统计
                </CardTitle>
              </CardHeader>
              <CardContent>
                {statsLoading && !stats ? (
                  <div className="text-center py-6 text-slate-400">加载中...</div>
                ) : stats ? (
                  <div className="space-y-6">
                    {/* 当前持仓 */}
                    <div>
                      <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">当前持仓</h3>
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                        <div className="bg-slate-800/50 rounded-lg p-3">
                          <p className="text-xs text-slate-400 mb-1">持仓数</p>
                          <p className="text-xl font-bold">{stats.open_position_count}</p>
                        </div>
                        <div className="bg-slate-800/50 rounded-lg p-3">
                          <p className="text-xs text-slate-400 mb-1">持仓价值</p>
                          <p className="text-xl font-bold">{formatPrice(stats.open_value)}</p>
                        </div>
                        <div className="bg-slate-800/50 rounded-lg p-3">
                          <p className="text-xs text-slate-400 mb-1">浮动盈亏</p>
                          <p className={`text-xl font-bold ${stats.unrealized_pnl >= 0 ? "text-green-400" : "text-red-400"}`}>
                            {stats.unrealized_pnl >= 0 ? "+" : ""}{formatPrice(stats.unrealized_pnl)}
                          </p>
                        </div>
                        <div className="bg-slate-800/50 rounded-lg p-3">
                          <p className="text-xs text-slate-400 mb-1">浮动盈亏率</p>
                          <p className={`text-xl font-bold ${stats.unrealized_pnl_pct >= 0 ? "text-green-400" : "text-red-400"}`}>
                            {stats.unrealized_pnl_pct >= 0 ? "+" : ""}{stats.unrealized_pnl_pct}%
                          </p>
                        </div>
                      </div>
                    </div>

                    {/* 历史业绩 */}
                    <div>
                      <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">历史业绩</h3>
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
                        <div className="bg-slate-800/50 rounded-lg p-3">
                          <p className="text-xs text-slate-400 mb-1">累计盈亏</p>
                          <p className={`text-xl font-bold ${stats.total_realized_pnl >= 0 ? "text-green-400" : "text-red-400"}`}>
                            {stats.total_realized_pnl >= 0 ? "+" : ""}{formatPrice(stats.total_realized_pnl)}
                          </p>
                        </div>
                        <div className="bg-slate-800/50 rounded-lg p-3">
                          <p className="text-xs text-slate-400 mb-1">累计收益率</p>
                          <p className={`text-xl font-bold ${stats.realized_pnl_pct >= 0 ? "text-green-400" : "text-red-400"}`}>
                            {stats.realized_pnl_pct >= 0 ? "+" : ""}{stats.realized_pnl_pct}%
                          </p>
                        </div>
                        <div className="bg-slate-800/50 rounded-lg p-3">
                          <p className="text-xs text-slate-400 mb-1">最大回撤</p>
                          <p className="text-xl font-bold text-orange-400">
                            {stats.max_drawdown > 0 ? `-${formatPrice(stats.max_drawdown)}` : "0"}
                          </p>
                        </div>
                        <div className="bg-slate-800/50 rounded-lg p-3">
                          <p className="text-xs text-slate-400 mb-1">最大回撤率</p>
                          <p className="text-xl font-bold text-orange-400">
                            {stats.max_drawdown_pct > 0 ? `-${stats.max_drawdown_pct}%` : "0%"}
                          </p>
                        </div>
                      </div>
                    </div>

                    {/* 交易统计 */}
                    <div>
                      <h3 className="text-xs font-semibold text-slate-500 uppercase tracking-wider mb-3">交易统计</h3>
                      <div className="grid grid-cols-2 md:grid-cols-5 gap-4">
                        <div className="bg-slate-800/50 rounded-lg p-3">
                          <p className="text-xs text-slate-400 mb-1">总交易数</p>
                          <p className="text-xl font-bold">{stats.total_trades}</p>
                        </div>
                        <div className="bg-slate-800/50 rounded-lg p-3">
                          <p className="text-xs text-slate-400 mb-1">盈利 / 亏损</p>
                          <p className="text-xl font-bold">
                            <span className="text-green-400">{stats.win_count}</span>
                            <span className="text-slate-500"> / </span>
                            <span className="text-red-400">{stats.loss_count}</span>
                          </p>
                        </div>
                        <div className="bg-slate-800/50 rounded-lg p-3">
                          <p className="text-xs text-slate-400 mb-1">胜率</p>
                          <p className="text-xl font-bold">{stats.win_rate}%</p>
                        </div>
                        <div className="bg-slate-800/50 rounded-lg p-3">
                          <p className="text-xs text-slate-400 mb-1">平均盈亏</p>
                          <p className={`text-xl font-bold ${stats.avg_pnl >= 0 ? "text-green-400" : "text-red-400"}`}>
                            {stats.avg_pnl >= 0 ? "+" : ""}{formatPrice(stats.avg_pnl)}
                          </p>
                        </div>
                        <div className="bg-slate-800/50 rounded-lg p-3">
                          <p className="text-xs text-slate-400 mb-1">触发次数</p>
                          <p className="text-xl font-bold">{stats.trigger_count}</p>
                        </div>
                      </div>
                    </div>

                    {/* 时间信息 */}
                    <div className="flex gap-6 text-sm text-slate-500 pt-2 border-t border-slate-800">
                      <span>创建: {formatDateTime(strategy.created_at)}</span>
                      <span>更新: {formatDateTime(strategy.updated_at)}</span>
                    </div>
                  </div>
                ) : (
                  <div className="text-center py-6 text-slate-500">暂无统计数据</div>
                )}
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="triggers">
          {strategy && triggersLoaded && (
            <div className="mb-4">
              <KlineChartModule
                data={klines}
                markers={tradeMarkers}
                indicators={{ ma: true, volume: true }}
                height={400}
                title={strategy.name}
                subtitle={`${strategySymbols[0] || ""} · ${chartPeriod}`}
                activePeriod={chartPeriod}
                onPeriodChange={handleChartPeriodChange}
                focusTimestamp={focusTimestamp}
              />
            </div>
          )}
          {!triggersLoaded ? (
            triggersLoading ? (
              <div className="text-center py-12 text-slate-400">加载中...</div>
            ) : null
          ) : triggers.length === 0 ? (
            <Card className="bg-slate-900 border-slate-800">
              <CardContent className="py-12 text-center">
                <History className="w-12 h-12 text-slate-600 mx-auto mb-4" />
                <p className="text-slate-400">暂无触发记录</p>
                <p className="text-sm text-slate-500 mt-2">
                  启动策略后将在此显示触发记录
                </p>
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-4">
              <Card className={`bg-slate-900 border-slate-800 transition-opacity ${triggersLoading ? "opacity-60" : ""}`}>
                <CardContent className="p-0">
                  <div className="overflow-x-auto">
                    <table className="w-full">
                      <thead>
                        <tr className="border-b border-slate-800">
                          <th className="text-left p-4 text-slate-400 font-medium">时间</th>
                          {strategySymbols.length > 1 && (
                            <th className="text-left p-4 text-slate-400 font-medium">交易对</th>
                          )}
                          <th className="text-left p-4 text-slate-400 font-medium">操作</th>
                          <th className="text-left p-4 text-slate-400 font-medium">价格</th>
                          <th className="text-left p-4 text-slate-400 font-medium">数量</th>
                          <th className="text-right p-4 text-slate-400 font-medium">盈亏</th>
                          <th className="text-left p-4 text-slate-400 font-medium">备注</th>
                        </tr>
                      </thead>
                      <tbody>
                        {triggers.map((trigger) => (
                          <tr
                            key={trigger.id}
                            className="border-b border-slate-800 last:border-0 cursor-pointer hover:bg-slate-800/50 transition-colors"
                            onClick={() => {
                              if (trigger.triggered_at) {
                                setFocusTimestamp(new Date(trigger.triggered_at).getTime());
                              }
                            }}
                          >
                            <td className="p-4 whitespace-nowrap">
                              {formatDateTime(trigger.triggered_at)}
                            </td>
                            {strategySymbols.length > 1 && (
                              <td className="p-4 text-xs font-mono text-slate-400">
                                {trigger.symbol ? formatSymbol(trigger.symbol) : "-"}
                              </td>
                            )}
                            <td className="p-4">{getActionBadge(trigger.action)}</td>
                            <td className="p-4">
                              {trigger.price ? formatPrice(trigger.price) : "-"}
                            </td>
                            <td className="p-4">
                              {trigger.quantity != null
                                ? trigger.quantity.toFixed(4)
                                : "-"}
                            </td>
                            <td className="p-4 text-right">
                              {trigger.simulated_pnl != null ? (
                                <span
                                  className={
                                    trigger.simulated_pnl >= 0
                                      ? "text-green-400"
                                      : "text-red-400"
                                  }
                                >
                                  {trigger.simulated_pnl >= 0 ? "+" : ""}
                                  {formatPrice(trigger.simulated_pnl)}
                                </span>
                              ) : (
                                "-"
                              )}
                            </td>
                            <td className="p-4 text-sm text-slate-400 max-w-xs truncate">
                              {trigger.signal_detail || "-"}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </CardContent>
              </Card>

              {/* 分页控件 */}
              <div className="flex items-center justify-center gap-4 text-sm text-slate-400">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => loadTriggers(triggersPage - 1)}
                  disabled={triggersPage <= 1}
                >
                  <ChevronLeft className="w-4 h-4 mr-1" />
                  上一页
                </Button>
                <span>
                  第 {triggersPage} / {Math.ceil(triggersTotal / 20)} 页，共 {triggersTotal} 条
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => loadTriggers(triggersPage + 1)}
                  disabled={triggersPage >= Math.ceil(triggersTotal / 20)}
                >
                  下一页
                  <ChevronRight className="w-4 h-4 ml-1" />
                </Button>
              </div>
            </div>
          )}
        </TabsContent>

        <TabsContent value="positions">
          {!positionsLoaded ? (
            positionsLoading ? (
              <div className="text-center py-12 text-slate-400">加载中...</div>
            ) : null
          ) : (
            <div className="space-y-6">
              {/* 当前持仓 */}
              <div>
                <h3 className="text-sm font-medium text-slate-400 mb-3">当前持仓</h3>
                {currentPositions.length > 0 ? (
                  <div className="space-y-2">
                    {currentPositions.map((pos) => (
                      <Card key={pos.id} className="bg-slate-900 border-slate-800">
                        <CardContent className="p-4">
                          <div className="flex flex-wrap gap-4 items-center">
                            <span className="text-xs font-mono text-slate-300 bg-slate-800 px-2 py-0.5 rounded">
                              {formatSymbol(pos.symbol)}
                            </span>
                            <Badge className={pos.side === "long" ? "bg-green-600" : "bg-orange-600"}>
                              {pos.side === "long" ? "多仓" : "空仓"}
                            </Badge>
                            <div className="flex gap-6 text-sm">
                              <div>
                                <span className="text-slate-400 mr-2">开仓价</span>
                                <span>{formatPrice(pos.entry_price)}</span>
                              </div>
                              <div>
                                <span className="text-slate-400 mr-2">价值</span>
                                <span>{formatPrice(pos.quantity * pos.entry_price)}</span>
                              </div>
                              {pos.unrealized_pnl != null && (
                                <div>
                                  <span className="text-slate-400 mr-2">浮动盈亏</span>
                                  <span className={pos.unrealized_pnl >= 0 ? "text-green-400" : "text-red-400"}>
                                    {pos.unrealized_pnl >= 0 ? "+" : ""}
                                    {formatPrice(pos.unrealized_pnl)}
                                  </span>
                                </div>
                              )}
                            </div>
                          </div>
                        </CardContent>
                      </Card>
                    ))}
                  </div>
                ) : (
                  <p className="text-sm text-slate-500">当前无持仓</p>
                )}
              </div>

              {/* 历史平仓记录 */}
              <div>
                <h3 className="text-sm font-medium text-slate-400 mb-3">历史平仓记录</h3>
                {posHistory.length === 0 ? (
                  <Card className="bg-slate-900 border-slate-800">
                    <CardContent className="py-12 text-center">
                      <TrendingUp className="w-12 h-12 text-slate-600 mx-auto mb-4" />
                      <p className="text-slate-400">暂无平仓记录</p>
                    </CardContent>
                  </Card>
                ) : (
                  <div className="space-y-4">
                    <Card className={`bg-slate-900 border-slate-800 transition-opacity ${positionsLoading ? "opacity-60" : ""}`}>
                      <CardContent className="p-0">
                        <div className="overflow-x-auto">
                          <table className="w-full">
                            <thead>
                              <tr className="border-b border-slate-800">
                                <th className="text-left p-4 text-slate-400 font-medium">开仓时间</th>
                                <th className="text-left p-4 text-slate-400 font-medium">平仓时间</th>
                                <th className="text-left p-4 text-slate-400 font-medium">交易对</th>
                                <th className="text-left p-4 text-slate-400 font-medium">方向</th>
                                <th className="text-left p-4 text-slate-400 font-medium">开仓价</th>
                                <th className="text-left p-4 text-slate-400 font-medium">平仓价</th>
                                <th className="text-left p-4 text-slate-400 font-medium">数量</th>
                                <th className="text-right p-4 text-slate-400 font-medium">盈亏</th>
                              </tr>
                            </thead>
                            <tbody>
                              {posHistory.map((pos) => (
                                <tr key={pos.id} className="border-b border-slate-800 last:border-0">
                                  <td className="p-4 whitespace-nowrap">{formatDateTime(pos.opened_at)}</td>
                                  <td className="p-4 whitespace-nowrap">{pos.closed_at ? formatDateTime(pos.closed_at) : "-"}</td>
                                  <td className="p-4 text-xs font-mono text-slate-400">{formatSymbol(pos.symbol)}</td>
                                  <td className="p-4">
                                    <Badge className={pos.side === "long" ? "bg-green-600" : "bg-orange-600"}>
                                      {pos.side === "long" ? "多仓" : "空仓"}
                                    </Badge>
                                  </td>
                                  <td className="p-4">{formatPrice(pos.entry_price)}</td>
                                  <td className="p-4">{pos.current_price ? formatPrice(pos.current_price) : "-"}</td>
                                  <td className="p-4">{formatPrice(pos.quantity * pos.entry_price)}</td>
                                  <td className="p-4 text-right">
                                    {pos.pnl != null ? (
                                      <span className={pos.pnl >= 0 ? "text-green-400" : "text-red-400"}>
                                        {pos.pnl >= 0 ? "+" : ""}{formatPrice(pos.pnl)}
                                      </span>
                                    ) : "-"}
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </CardContent>
                    </Card>

                    {/* 分页控件 */}
                    <div className="flex items-center justify-center gap-4 text-sm text-slate-400">
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => loadPositions(posHistoryPage - 1)}
                        disabled={posHistoryPage <= 1}
                      >
                        <ChevronLeft className="w-4 h-4 mr-1" />
                        上一页
                      </Button>
                      <span>
                        第 {posHistoryPage} / {Math.ceil(posHistoryTotal / 20)} 页，共 {posHistoryTotal} 条
                      </span>
                      <Button
                        variant="outline"
                        size="sm"
                        onClick={() => loadPositions(posHistoryPage + 1)}
                        disabled={posHistoryPage >= Math.ceil(posHistoryTotal / 20)}
                      >
                        下一页
                        <ChevronRight className="w-4 h-4 ml-1" />
                      </Button>
                    </div>
                  </div>
                )}
              </div>
            </div>
          )}
        </TabsContent>

        <TabsContent value="backtest">
          <BacktestPanel strategyId={id} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
