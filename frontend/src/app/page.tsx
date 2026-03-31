"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { formatPrice, formatDateTime } from "@/lib/utils";
import {
  Wallet,
  TrendingUp,
  TrendingDown,
  Activity,
  Zap,
  ArrowUpRight,
  ArrowDownRight,
  Clock,
} from "lucide-react";
import axios from "axios";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "";

interface DashboardData {
  balance: number;
  total_pnl: number;
  running_strategies: number;
  long_strategies: number;
  short_strategies: number;
  today_triggers: number;
  recent_triggers: any[];
}

export default function DashboardPage() {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadDashboard();
    const interval = setInterval(loadDashboard, 30000);
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
    return (
      <div className="space-y-6">
        <div className="h-8 w-32 bg-slate-800 rounded-lg animate-pulse" />
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          {[...Array(4)].map((_, i) => (
            <div key={i} className="h-28 bg-slate-900 rounded-xl border border-slate-800 animate-pulse" />
          ))}
        </div>
        <div className="h-64 bg-slate-900 rounded-xl border border-slate-800 animate-pulse" />
      </div>
    );
  }

  if (!data) {
    return <div className="text-center py-12 text-red-400">加载失败</div>;
  }

  const pnlPercent = data.balance > 0 ? ((data.total_pnl / (data.balance - data.total_pnl)) * 100) : 0;

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold text-white">仪表盘</h1>

      {/* 统计卡片 */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCard
          title="账户余额"
          value={formatPrice(data.balance)}
          icon={Wallet}
          accent="blue"
        />
        <StatCard
          title="总盈亏"
          value={`${data.total_pnl >= 0 ? "+" : ""}${formatPrice(data.total_pnl)}`}
          subtitle={`${pnlPercent >= 0 ? "+" : ""}${pnlPercent.toFixed(2)}%`}
          icon={data.total_pnl >= 0 ? TrendingUp : TrendingDown}
          accent={data.total_pnl >= 0 ? "green" : "red"}
        />
        <StatCard
          title="运行中策略"
          value={data.running_strategies.toString()}
          subtitle={
            data.long_strategies > 0 || data.short_strategies > 0
              ? `${data.long_strategies} 多 / ${data.short_strategies} 空`
              : undefined
          }
          icon={Zap}
          accent="amber"
        />
        <StatCard
          title="今日触发"
          value={data.today_triggers.toString()}
          icon={Activity}
          accent="purple"
        />
      </div>

      {/* 最近触发记录 */}
      <div className="bg-slate-900 rounded-xl border border-slate-800">
        <div className="flex items-center justify-between px-5 py-4 border-b border-slate-800">
          <h2 className="font-semibold text-white flex items-center gap-2">
            <Clock className="w-4 h-4 text-slate-400" />
            最近触发
          </h2>
          <span className="text-xs text-slate-500">{data.recent_triggers.length} 条记录</span>
        </div>
        {data.recent_triggers.length === 0 ? (
          <div className="py-12 text-center">
            <Activity className="w-10 h-10 text-slate-700 mx-auto mb-3" />
            <p className="text-slate-500 text-sm">暂无触发记录</p>
          </div>
        ) : (
          <div className="divide-y divide-slate-800/50">
            {data.recent_triggers.map((trigger: any) => {
              const isBuy = ["buy", "买入"].includes(trigger.action || "");
              const isSell = ["sell", "卖出"].includes(trigger.action || "");
              return (
                <Link
                  key={trigger.id}
                  href={`/strategies/${trigger.strategy_id}?tab=triggers`}
                  className="flex items-center gap-3 px-5 py-3 hover:bg-slate-800/30 transition-colors cursor-pointer"
                >
                  <div className={`w-8 h-8 rounded-lg flex items-center justify-center shrink-0 ${
                    isBuy ? "bg-green-500/10" : isSell ? "bg-red-500/10" : "bg-slate-800"
                  }`}>
                    {isBuy ? (
                      <ArrowUpRight className="w-4 h-4 text-green-400" />
                    ) : isSell ? (
                      <ArrowDownRight className="w-4 h-4 text-red-400" />
                    ) : (
                      <Activity className="w-4 h-4 text-slate-500" />
                    )}
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-slate-200 truncate">
                      {trigger.strategy_name || `策略 #${trigger.strategy_id}`}
                      {trigger.symbol && (
                        <span className="ml-1.5 text-[11px] font-mono text-slate-500">{trigger.symbol}</span>
                      )}
                    </p>
                    <p className="text-xs text-slate-500">
                      {formatDateTime(trigger.triggered_at)}
                    </p>
                  </div>
                  <div className="text-right shrink-0">
                    <span
                      className={`inline-block px-2 py-0.5 rounded text-xs font-medium ${
                        isBuy
                          ? "bg-green-500/15 text-green-400"
                          : isSell
                          ? "bg-red-500/15 text-red-400"
                          : "bg-slate-800 text-slate-400"
                      }`}
                    >
                      {trigger.action || "观望"}
                    </span>
                    {trigger.price && (
                      <p className="text-xs text-slate-500 mt-0.5 font-mono">
                        {formatPrice(trigger.price)}
                      </p>
                    )}
                  </div>
                </Link>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}

const ACCENT_STYLES = {
  blue:   { bg: "bg-blue-500/10",   icon: "text-blue-400",   value: "text-white" },
  green:  { bg: "bg-green-500/10",  icon: "text-green-400",  value: "text-green-400" },
  red:    { bg: "bg-red-500/10",    icon: "text-red-400",    value: "text-red-400" },
  amber:  { bg: "bg-amber-500/10",  icon: "text-amber-400",  value: "text-white" },
  purple: { bg: "bg-purple-500/10", icon: "text-purple-400", value: "text-white" },
};

interface StatCardProps {
  title: string;
  value: string;
  subtitle?: string;
  icon: React.ElementType;
  accent: keyof typeof ACCENT_STYLES;
}

function StatCard({ title, value, subtitle, icon: Icon, accent }: StatCardProps) {
  const style = ACCENT_STYLES[accent];
  return (
    <div className="bg-slate-900 rounded-xl border border-slate-800 p-4 hover:border-slate-700 transition-colors">
      <div className="flex items-center justify-between mb-3">
        <span className="text-xs font-medium text-slate-400 uppercase tracking-wide">{title}</span>
        <div className={`w-8 h-8 rounded-lg flex items-center justify-center ${style.bg}`}>
          <Icon className={`w-4 h-4 ${style.icon}`} />
        </div>
      </div>
      <p className={`text-xl font-bold font-mono ${style.value}`}>{value}</p>
      {subtitle && (
        <p className={`text-xs mt-0.5 ${style.icon}`}>{subtitle}</p>
      )}
    </div>
  );
}
