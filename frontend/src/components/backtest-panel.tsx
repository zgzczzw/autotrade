"use client";

import { useEffect, useMemo, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { formatPrice } from "@/lib/utils";
import { Loader2, Play, Square, Trash2 } from "lucide-react";
import axios from "axios";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import { KlineChartModule } from "./kline-chart";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface BacktestResult {
  id: number;
  strategy_id: number;
  symbol: string;
  timeframe: string;
  start_date: string;
  end_date: string;
  initial_balance: number;
  final_balance: number;
  total_pnl: number;
  pnl_percent: number;
  win_rate: number;
  max_drawdown: number;
  total_trades: number;
  avg_hold_time?: number;
  equity_curve: string;
  trades: string;
  klines?: string;
  created_at: string;
}

interface BacktestPanelProps {
  strategyId: string;
}

export function BacktestPanel({ strategyId }: BacktestPanelProps) {
  const [backtests, setBacktests] = useState<BacktestResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [running, setRunning] = useState(false);
  const [cancelling, setCancelling] = useState(false);
  const [selectedBacktest, setSelectedBacktest] = useState<BacktestResult | null>(null);
  const [focusTimestamp, setFocusTimestamp] = useState<number | undefined>(undefined);

  // 缓存解析后的 klines / trades，避免父组件重渲染时产生新数组引用
  // 导致子图表 setDataLoader 重触发、滚动位置被重置
  const parsedKlines = useMemo(() => {
    try { return JSON.parse(selectedBacktest?.klines || "[]"); } catch { return []; }
  }, [selectedBacktest?.klines]);

  const parsedTrades = useMemo(() => {
    try { return JSON.parse(selectedBacktest?.trades || "[]"); } catch { return []; }
  }, [selectedBacktest?.trades]);

  const chartMarkers = useMemo(() =>
    parsedTrades.map((t: any) => ({
      timestamp: new Date(t.time).getTime(),
      price: t.price,
      side: t.side,
      quantity: t.quantity,
      pnl: t.pnl,
    })),
  [parsedTrades]);
  const [formData, setFormData] = useState({
    start_date: "",
    end_date: "",
    initial_balance: 100000,
  });

  useEffect(() => {
    loadBacktests();
  }, [strategyId]);

  // 设置默认日期范围（最近30天）
  useEffect(() => {
    const end = new Date();
    const start = new Date();
    start.setDate(start.getDate() - 30);
    
    setFormData(prev => ({
      ...prev,
      start_date: start.toISOString().split("T")[0],
      end_date: end.toISOString().split("T")[0],
    }));
  }, []);

  // 轮询回测状态
  useEffect(() => {
    if (!running) return;

    const interval = setInterval(async () => {
      try {
        const response = await axios.get(
          `${API_BASE_URL}/api/strategies/${strategyId}/backtest/status`
        );
        if (!response.data.running) {
          setRunning(false);
          loadBacktests();
        }
      } catch (error) {
        console.error("Failed to check backtest status:", error);
      }
    }, 2000);

    return () => clearInterval(interval);
  }, [running, strategyId]);

  const loadBacktests = async () => {
    try {
      const response = await axios.get(
        `${API_BASE_URL}/api/strategies/${strategyId}/backtests`
      );
      setBacktests(response.data.items || []);
    } catch (error) {
      console.error("Failed to load backtests:", error);
    }
  };

  const runBacktest = async () => {
    setRunning(true);
    try {
      await axios.post(
        `${API_BASE_URL}/api/strategies/${strategyId}/backtest`,
        {
          start_date: new Date(formData.start_date).toISOString(),
          end_date: new Date(formData.end_date).toISOString(),
          initial_balance: formData.initial_balance,
        }
      );
      loadBacktests();
    } catch (error: any) {
      console.error("Failed to run backtest:", error);
      if (error.response?.data?.detail === "该策略已有回测正在运行") {
        alert("该策略已有回测正在运行，请等待完成或取消");
      } else {
        alert("回测失败，请检查日期范围");
      }
    } finally {
      setRunning(false);
    }
  };

  const cancelBacktest = async () => {
    setCancelling(true);
    try {
      await axios.post(
        `${API_BASE_URL}/api/strategies/${strategyId}/backtest/cancel`
      );
      // 状态将通过轮询更新
    } catch (error: any) {
      console.error("Failed to cancel backtest:", error);
      alert(error.response?.data?.detail || "取消回测失败");
    } finally {
      setCancelling(false);
    }
  };

  const deleteBacktest = async (id: number) => {
    if (!confirm("确定要删除此回测结果吗？")) return;
    try {
      await axios.delete(`${API_BASE_URL}/api/backtests/${id}`);
      loadBacktests();
      if (selectedBacktest?.id === id) {
        setSelectedBacktest(null);
      }
    } catch (error) {
      console.error("Failed to delete backtest:", error);
    }
  };

  const parsedEquityCurve = useMemo(() => {
    try { return JSON.parse(selectedBacktest?.equity_curve || "[]"); } catch { return []; }
  }, [selectedBacktest?.equity_curve]);

  return (
    <div className="space-y-6">
      {/* 回测配置 */}
      <Card className="bg-slate-900 border-slate-800">
        <CardHeader>
          <CardTitle>发起回测</CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-4">
            <div className="space-y-2">
              <Label>开始日期</Label>
              <Input
                type="date"
                value={formData.start_date}
                onChange={(e) =>
                  setFormData({ ...formData, start_date: e.target.value })
                }
                className="bg-slate-800 border-slate-700"
              />
            </div>
            <div className="space-y-2">
              <Label>结束日期</Label>
              <Input
                type="date"
                value={formData.end_date}
                onChange={(e) =>
                  setFormData({ ...formData, end_date: e.target.value })
                }
                className="bg-slate-800 border-slate-700"
              />
            </div>
            <div className="space-y-2">
              <Label>初始资金 (USDT)</Label>
              <Input
                type="number"
                value={formData.initial_balance}
                onChange={(e) =>
                  setFormData({
                    ...formData,
                    initial_balance: parseFloat(e.target.value),
                  })
                }
                className="bg-slate-800 border-slate-700"
              />
            </div>
          </div>
          <div className="flex gap-2">
            <Button onClick={runBacktest} disabled={running}>
              {running ? (
                <>
                  <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                  回测中...
                </>
              ) : (
                <>
                  <Play className="w-4 h-4 mr-2" />
                  开始回测
                </>
              )}
            </Button>
            {running && (
              <Button
                variant="destructive"
                onClick={cancelBacktest}
                disabled={cancelling}
              >
                {cancelling ? (
                  <>
                    <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                    取消中...
                  </>
                ) : (
                  <>
                    <Square className="w-4 h-4 mr-2" />
                    停止回测
                  </>
                )}
              </Button>
            )}
          </div>
        </CardContent>
      </Card>

      {/* 历史回测列表 */}
      {backtests.length > 0 && (
        <Card className="bg-slate-900 border-slate-800">
          <CardHeader>
            <CardTitle>历史回测</CardTitle>
          </CardHeader>
          <CardContent>
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-slate-800">
                    <th className="text-left p-3 text-slate-400">时间</th>
                    <th className="text-left p-3 text-slate-400">总盈亏</th>
                    <th className="text-left p-3 text-slate-400">胜率</th>
                    <th className="text-left p-3 text-slate-400">最大回撤</th>
                    <th className="text-left p-3 text-slate-400">交易笔数</th>
                    <th className="text-right p-3 text-slate-400">操作</th>
                  </tr>
                </thead>
                <tbody>
                  {backtests.map((bt) => (
                    <tr
                      key={bt.id}
                      className={`border-b border-slate-800 last:border-0 cursor-pointer hover:bg-slate-800 ${
                        selectedBacktest?.id === bt.id ? "bg-slate-800" : ""
                      }`}
                      onClick={() => { setSelectedBacktest(bt); setFocusTimestamp(undefined); }}
                    >
                      <td className="p-3">
                        {new Date(bt.created_at).toLocaleDateString()}
                      </td>
                      <td
                        className={`p-3 font-medium ${
                          bt.total_pnl >= 0 ? "text-green-400" : "text-red-400"
                        }`}
                      >
                        {bt.total_pnl >= 0 ? "+" : ""}
                        {formatPrice(bt.total_pnl)} ({bt.pnl_percent.toFixed(2)}%)
                      </td>
                      <td className="p-3">{bt.win_rate.toFixed(1)}%</td>
                      <td className="p-3 text-red-400">
                        {bt.max_drawdown.toFixed(2)}%
                      </td>
                      <td className="p-3">{bt.total_trades}</td>
                      <td className="p-3 text-right">
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-8 w-8 text-red-400"
                          onClick={(e) => {
                            e.stopPropagation();
                            deleteBacktest(bt.id);
                          }}
                        >
                          <Trash2 className="w-4 h-4" />
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}

      {/* 回测详情 */}
      {selectedBacktest && (
        <Card className="bg-slate-900 border-slate-800">
          <CardHeader>
            <CardTitle>回测详情</CardTitle>
          </CardHeader>
          <CardContent className="space-y-6">
            {/* 统计指标 */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
              <StatCard
                label="初始资金"
                value={formatPrice(selectedBacktest.initial_balance)}
              />
              <StatCard
                label="最终资金"
                value={formatPrice(selectedBacktest.final_balance)}
                valueClass={
                  selectedBacktest.final_balance >= selectedBacktest.initial_balance
                    ? "text-green-400"
                    : "text-red-400"
                }
              />
              <StatCard
                label="总盈亏"
                value={`${selectedBacktest.total_pnl >= 0 ? "+" : ""}${formatPrice(
                  selectedBacktest.total_pnl
                )}`}
                valueClass={
                  selectedBacktest.total_pnl >= 0 ? "text-green-400" : "text-red-400"
                }
              />
              <StatCard
                label="盈亏百分比"
                value={`${selectedBacktest.pnl_percent >= 0 ? "+" : ""}${selectedBacktest.pnl_percent.toFixed(
                  2
                )}%`}
                valueClass={
                  selectedBacktest.pnl_percent >= 0 ? "text-green-400" : "text-red-400"
                }
              />
              <StatCard label="胜率" value={`${selectedBacktest.win_rate.toFixed(1)}%`} />
              <StatCard
                label="最大回撤"
                value={`${selectedBacktest.max_drawdown.toFixed(2)}%`}
                valueClass="text-red-400"
              />
              <StatCard label="交易笔数" value={selectedBacktest.total_trades.toString()} />
              <StatCard
                label="平均持仓"
                value={
                  selectedBacktest.avg_hold_time
                    ? `${Math.round(selectedBacktest.avg_hold_time / 3600)}小时`
                    : "-"
                }
              />
            </div>

            {/* 资金曲线图 */}
            <div>
              <h4 className="text-sm font-medium text-slate-400 mb-4">资金曲线</h4>
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={parsedEquityCurve}>
                    <CartesianGrid strokeDasharray="3 3" stroke="#334155" />
                    <XAxis
                      dataKey="time"
                      tickFormatter={(value) =>
                        new Date(value).toLocaleDateString()
                      }
                      stroke="#64748b"
                      fontSize={12}
                    />
                    <YAxis
                      stroke="#64748b"
                      fontSize={12}
                      domain={(() => {
                        // 动态计算Y轴范围，让曲线变化更明显
                        const data = parsedEquityCurve;
                        if (data.length === 0) return [0, 100000];
                        const balances = data.map((d: any) => d.balance);
                        const min = Math.min(...balances);
                        const max = Math.max(...balances);
                        const range = max - min;
                        // 添加10%的边距，确保曲线不会贴边
                        const padding = Math.max(range * 0.1, min * 0.01);
                        return [Math.max(0, min - padding), max + padding];
                      })()}
                      tickFormatter={(value) => {
                        // 根据数值大小动态选择显示格式
                        if (value >= 1000000) return `$${(value / 1000000).toFixed(1)}M`;
                        if (value >= 1000) return `$${(value / 1000).toFixed(1)}k`;
                        return `$${value.toFixed(0)}`;
                      }}
                    />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: "#1e293b",
                        border: "1px solid #334155",
                        borderRadius: "6px",
                      }}
                      labelFormatter={(value) => new Date(value).toLocaleString()}
                      formatter={(value) => [formatPrice(Number(value)), "余额"]}
                    />
                    <Line
                      type="monotone"
                      dataKey="balance"
                      stroke="#3b82f6"
                      strokeWidth={2}
                      dot={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* K线图和买卖点 */}
            {selectedBacktest.klines && (
              <div>
                <h4 className="text-sm font-medium text-slate-400 mb-4">
                  K线图表 (标记买卖点)
                </h4>
                <KlineChartModule
                  data={parsedKlines}
                  markers={chartMarkers}
                  indicators={{ ma: true, macd: true, volume: true }}
                  height={500}
                  title={`回测 K线图表`}
                  subtitle={`${selectedBacktest.symbol} / ${selectedBacktest.timeframe}`}
                  focusTimestamp={focusTimestamp}
                />
              </div>
            )}

            {/* 交易列表 */}
            <div>
              <h4 className="text-sm font-medium text-slate-400 mb-2">交易明细</h4>
              <p className="text-xs text-slate-500 mb-3">点击任意行，K 线图自动聚焦到该时间点</p>
              <div className="bg-slate-800 rounded-lg overflow-hidden">
                <div className="overflow-x-auto max-h-72 overflow-y-auto">
                  <table className="w-full text-sm">
                    <thead className="bg-slate-700 sticky top-0">
                      <tr>
                        <th className="text-left p-2 text-slate-300">时间</th>
                        <th className="text-left p-2 text-slate-300">类型</th>
                        <th className="text-left p-2 text-slate-300">触发条件</th>
                        <th className="text-right p-2 text-slate-300">价格</th>
                        <th className="text-right p-2 text-slate-300">数量</th>
                        <th className="text-right p-2 text-slate-300">盈亏</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(() => {
                        try {
                          const trades = parsedTrades;
                          return trades.length > 0 ? (
                            trades.map((trade: any, index: number) => {
                              const ts = new Date(trade.time).getTime();
                              const isActive = focusTimestamp === ts;
                              return (
                                <tr
                                  key={index}
                                  onClick={() => setFocusTimestamp(ts)}
                                  className={`border-b border-slate-700 last:border-0 cursor-pointer transition-colors ${
                                    isActive
                                      ? "bg-blue-900/40 border-l-2 border-l-blue-500"
                                      : "hover:bg-slate-700/50"
                                  }`}
                                >
                                  <td className="p-2 text-slate-400 whitespace-nowrap">
                                    {new Date(trade.time).toLocaleString()}
                                  </td>
                                  <td className="p-2">
                                    <span
                                      className={`px-2 py-0.5 rounded text-xs font-medium ${
                                        trade.side === "buy"
                                          ? "bg-green-600 text-white"
                                          : "bg-red-600 text-white"
                                      }`}
                                    >
                                      {trade.side === "buy" ? "买入" : "卖出"}
                                    </span>
                                  </td>
                                  <td className="p-2 text-slate-300 text-xs max-w-[200px]">
                                    {trade.trigger || (trade.side === "buy" ? "条件信号" : "条件信号")}
                                  </td>
                                  <td className="p-2 text-right whitespace-nowrap">${trade.price.toFixed(2)}</td>
                                  <td className="p-2 text-right text-slate-400">{trade.quantity.toFixed(4)}</td>
                                  <td
                                    className={`p-2 text-right whitespace-nowrap ${
                                      trade.pnl > 0
                                        ? "text-green-400"
                                        : trade.pnl < 0
                                        ? "text-red-400"
                                        : "text-slate-400"
                                    }`}
                                  >
                                    {trade.pnl !== 0
                                      ? `${trade.pnl > 0 ? "+" : ""}${trade.pnl.toFixed(2)}`
                                      : "-"}
                                  </td>
                                </tr>
                              );
                            })
                          ) : (
                            <tr>
                              <td colSpan={6} className="p-4 text-center text-slate-500">
                                暂无交易记录
                              </td>
                            </tr>
                          );
                        } catch {
                          return (
                            <tr>
                              <td colSpan={6} className="p-4 text-center text-slate-500">
                                交易数据解析失败
                              </td>
                            </tr>
                          );
                        }
                      })()}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}

interface StatCardProps {
  label: string;
  value: string;
  valueClass?: string;
}

function StatCard({ label, value, valueClass }: StatCardProps) {
  return (
    <div className="bg-slate-800 p-4 rounded-lg">
      <p className="text-sm text-slate-400 mb-1">{label}</p>
      <p className={`text-lg font-bold ${valueClass || "text-white"}`}>{value}</p>
    </div>
  );
}
