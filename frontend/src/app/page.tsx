"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatPrice, formatDateTime } from "@/lib/utils";
import { TrendingUp, TrendingDown, Activity, Zap } from "lucide-react";
import axios from "axios";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "";

interface DashboardData {
  balance: number;
  total_pnl: number;
  running_strategies: number;
  today_triggers: number;
  recent_triggers: any[];
}

export default function DashboardPage() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadDashboard();
    const interval = setInterval(loadDashboard, 10000);
    return () => clearInterval(interval);
  }, []);

  const loadDashboard = async () => {
    try {
      const response = await axios.get(`${API_BASE_URL}/api/dashboard`);
      setData(response.data);
    } catch (error) {
      console.error("Failed to load dashboard:", error);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return <div className="text-center py-12">加载中...</div>;
  }

  if (!data) {
    return <div className="text-center py-12 text-red-400">加载失败</div>;
  }

  return (
    <div>
      <h1 className="text-2xl md:text-3xl font-bold mb-6 md:mb-8">仪表盘</h1>

      {/* 统计卡片 */}
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-6 mb-8">
        <StatCard
          title="账户余额"
          value={formatPrice(data.balance)}
          icon={Activity}
          trend={data.balance >= 100000 ? "up" : "down"}
        />
        <StatCard
          title="总盈亏"
          value={formatPrice(data.total_pnl)}
          icon={data.total_pnl >= 0 ? TrendingUp : TrendingDown}
          valueClass={data.total_pnl >= 0 ? "text-green-400" : "text-red-400"}
        />
        <StatCard
          title="运行中策略"
          value={data.running_strategies.toString()}
          icon={Zap}
        />
        <StatCard
          title="今日触发"
          value={data.today_triggers.toString()}
          icon={Activity}
        />
      </div>

      {/* 最近触发记录 */}
      <Card className="bg-slate-900 border-slate-800">
        <CardHeader>
          <CardTitle>最近触发记录</CardTitle>
        </CardHeader>
        <CardContent>
          {data.recent_triggers.length === 0 ? (
            <p className="text-slate-400 text-center py-8">暂无触发记录</p>
          ) : (
            <div className="space-y-3">
              {data.recent_triggers.map((trigger: any) => (
                <div
                  key={trigger.id}
                  className="flex items-center justify-between p-3 bg-slate-800 rounded-lg"
                >
                  <div>
                    <p className="font-medium">{trigger.strategy_name || `策略 #${trigger.strategy_id}`}</p>
                    <p className="text-sm text-slate-400">
                      {formatDateTime(trigger.triggered_at)}
                    </p>
                  </div>
                  <div className="text-right">
                    <span
                      className={`px-2 py-1 rounded text-xs font-medium ${
                        trigger.action === "buy"
                          ? "bg-green-900 text-green-300"
                          : trigger.action === "sell"
                          ? "bg-red-900 text-red-300"
                          : "bg-slate-700 text-slate-300"
                      }`}
                    >
                      {trigger.action?.toUpperCase() || "HOLD"}
                    </span>
                    {trigger.price && (
                      <p className="text-sm text-slate-400 mt-1">
                        @ {formatPrice(trigger.price)}
                      </p>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

interface StatCardProps {
  title: string;
  value: string;
  icon: React.ElementType;
  trend?: "up" | "down";
  valueClass?: string;
}

function StatCard({ title, value, icon: Icon, trend, valueClass }: StatCardProps) {
  return (
    <Card className="bg-slate-900 border-slate-800">
      <CardContent className="p-6">
        <div className="flex items-center justify-between">
          <div>
            <p className="text-sm text-slate-400 mb-1">{title}</p>
            <p className={`text-2xl font-bold ${valueClass || "text-white"}`}>
              {value}
            </p>
          </div>
          <div
            className={`p-3 rounded-lg ${
              trend === "up"
                ? "bg-green-900/50"
                : trend === "down"
                ? "bg-red-900/50"
                : "bg-slate-800"
            }`}
          >
            <Icon
              className={`w-6 h-6 ${
                trend === "up"
                  ? "text-green-400"
                  : trend === "down"
                  ? "text-red-400"
                  : "text-slate-400"
              }`}
            />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
