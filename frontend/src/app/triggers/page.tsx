"use client";

import { useEffect, useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { formatPrice } from "@/lib/utils";
import { History } from "lucide-react";
import axios from "axios";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "";

interface Trigger {
  id: number;
  strategy_id: number;
  strategy_name?: string;
  triggered_at: string;
  signal_type: string;
  signal_detail?: string;
  action?: string;
  price?: number;
  quantity?: number;
  simulated_pnl?: number;
}

export default function TriggersPage() {
  const [triggers, setTriggers] = useState<Trigger[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadTriggers();
  }, []);

  const loadTriggers = async () => {
    try {
      const response = await axios.get(`${API_BASE_URL}/api/triggers`);
      setTriggers(response.data.items || []);
    } catch (error) {
      console.error("Failed to load triggers:", error);
    } finally {
      setLoading(false);
    }
  };

  const getActionBadge = (action?: string) => {
    switch (action) {
      case "buy":
        return <Badge className="bg-green-600">买入</Badge>;
      case "sell":
        return <Badge className="bg-red-600">卖出</Badge>;
      case "short":
        return <Badge className="bg-orange-600">开空</Badge>;
      case "cover":
        return <Badge className="bg-purple-600">平空</Badge>;
      default:
        return <Badge variant="secondary">观望</Badge>;
    }
  };

  if (loading) {
    return <div className="text-center py-12">加载中...</div>;
  }

  return (
    <div>
      <h1 className="text-2xl md:text-3xl font-bold mb-6 md:mb-8">触发日志</h1>

      {triggers.length === 0 ? (
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
        <Card className="bg-slate-900 border-slate-800">
          <CardContent className="p-0">
            <div className="overflow-x-auto">
              <table className="w-full">
                <thead>
                  <tr className="border-b border-slate-800">
                    <th className="text-left p-4 text-slate-400 font-medium">时间</th>
                    <th className="text-left p-4 text-slate-400 font-medium">策略</th>
                    <th className="text-left p-4 text-slate-400 font-medium">操作</th>
                    <th className="text-left p-4 text-slate-400 font-medium">价格</th>
                    <th className="text-right p-4 text-slate-400 font-medium">盈亏</th>
                  </tr>
                </thead>
                <tbody>
                  {triggers.map((trigger) => (
                    <tr key={trigger.id} className="border-b border-slate-800 last:border-0">
                      <td className="p-4">
                        {new Date(trigger.triggered_at).toLocaleString()}
                      </td>
                      <td className="p-4">
                        {trigger.strategy_name || `策略 #${trigger.strategy_id}`}
                      </td>
                      <td className="p-4">{getActionBadge(trigger.action)}</td>
                      <td className="p-4">
                        {trigger.price ? formatPrice(trigger.price) : "-"}
                      </td>
                      <td className="p-4 text-right">
                        {trigger.simulated_pnl !== undefined ? (
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
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
