"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { BacktestPanel } from "@/components/backtest-panel";
import { formatSymbol } from "@/lib/utils";
import { ArrowLeft, Play, Pencil, Square } from "lucide-react";
import axios from "axios";
import {
  StrategyPreview,
  deserializeConfig,
} from "@/components/visual-strategy-editor";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

interface Strategy {
  id: number;
  name: string;
  type: string;
  symbol: string;
  timeframe: string;
  status: string;
  position_size: number;
  position_size_type: string;
  stop_loss?: number;
  take_profit?: number;
  sell_size_pct: number;
  notify_enabled: boolean;
  config_json?: string;
  created_at: string;
  updated_at: string;
  trigger_count?: number;
  position_count?: number;
}

export default function StrategyDetailPage() {
  const params = useParams();
  const id = params.id as string;
  const [strategy, setStrategy] = useState<Strategy | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadStrategy();
    const interval = setInterval(loadStrategy, 10000);
    return () => clearInterval(interval);
  }, [id]);

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
            <p className="text-slate-400">
              {formatSymbol(strategy.symbol)} · {strategy.timeframe}
            </p>
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

      <Tabs defaultValue="overview" className="space-y-6">
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
                <div className="flex justify-between">
                  <span className="text-slate-400">交易对</span>
                  <span>{formatSymbol(strategy.symbol)}</span>
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

            <Card className="bg-slate-900 border-slate-800">
              <CardHeader>
                <CardTitle>统计数据</CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div className="flex justify-between">
                  <span className="text-slate-400">触发次数</span>
                  <span className="text-xl font-bold">{strategy.trigger_count || 0}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">当前持仓</span>
                  <span className="text-xl font-bold">{strategy.position_count || 0}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">创建时间</span>
                  <span>{new Date(strategy.created_at).toLocaleString()}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-slate-400">更新时间</span>
                  <span>{new Date(strategy.updated_at).toLocaleString()}</span>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="triggers">
          <Card className="bg-slate-900 border-slate-800">
            <CardContent className="py-12 text-center">
              <p className="text-slate-400">触发历史功能将在后续版本中支持</p>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="positions">
          <Card className="bg-slate-900 border-slate-800">
            <CardContent className="py-12 text-center">
              <p className="text-slate-400">持仓信息功能将在后续版本中支持</p>
            </CardContent>
          </Card>
        </TabsContent>

        <TabsContent value="backtest">
          <BacktestPanel strategyId={id} />
        </TabsContent>
      </Tabs>
    </div>
  );
}
