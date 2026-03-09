"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { formatSymbol } from "@/lib/utils";
import { Plus, Settings, Trash2 } from "lucide-react";
import axios from "axios";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "";

interface Strategy {
  id: number;
  name: string;
  type: string;
  symbol: string;
  timeframe: string;
  status: string;
  trigger_count?: number;
}

export default function StrategiesPage() {
  const [strategies, setStrategies] = useState<Strategy[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    loadStrategies();
    const interval = setInterval(loadStrategies, 30000);
    return () => clearInterval(interval);
  }, []);

  const loadStrategies = async () => {
    try {
      const response = await axios.get(`${API_BASE_URL}/api/strategies`);
      setStrategies(response.data.items || []);
    } catch (error) {
      console.error("Failed to load strategies:", error);
    } finally {
      setLoading(false);
    }
  };

  const handleToggle = async (strategy: Strategy) => {
    try {
      if (strategy.status === "running") {
        await axios.post(`${API_BASE_URL}/api/strategies/${strategy.id}/stop`);
      } else {
        await axios.post(`${API_BASE_URL}/api/strategies/${strategy.id}/start`);
      }
      loadStrategies();
    } catch (error) {
      console.error("Failed to toggle strategy:", error);
      alert("操作失败，请重试");
    }
  };

  const handleDelete = async (id: number) => {
    if (!confirm("确定要删除此策略吗？关联数据也将被删除。")) return;
    try {
      await axios.delete(`${API_BASE_URL}/api/strategies/${id}`);
      loadStrategies();
    } catch (error) {
      console.error("Failed to delete strategy:", error);
      alert("删除失败，请重试");
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

  return (
    <div>
      <div className="flex items-center justify-between mb-8">
        <h1 className="text-3xl font-bold">策略管理</h1>
        <Link href="/strategies/new">
          <Button>
            <Plus className="w-4 h-4 mr-2" />
            创建策略
          </Button>
        </Link>
      </div>

      {strategies.length === 0 ? (
        <Card className="bg-slate-900 border-slate-800">
          <CardContent className="py-12 text-center">
            <p className="text-slate-400 mb-4">暂无策略</p>
            <Link href="/strategies/new">
              <Button>
                <Plus className="w-4 h-4 mr-2" />
                创建第一个策略
              </Button>
            </Link>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
          {strategies.map((strategy) => (
            <Card key={strategy.id} className="bg-slate-900 border-slate-800">
              <CardHeader className="pb-3">
                <div className="flex items-start justify-between">
                  <div>
                    <CardTitle className="text-lg">{strategy.name}</CardTitle>
                    <p className="text-sm text-slate-400 mt-1">
                      {formatSymbol(strategy.symbol)} · {strategy.timeframe}
                    </p>
                  </div>
                  <div className="flex items-center gap-2">
                    <Link href={`/strategies/${strategy.id}`}>
                      <Button variant="ghost" size="icon" className="h-8 w-8">
                        <Settings className="w-4 h-4" />
                      </Button>
                    </Link>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8 text-red-400 hover:text-red-300"
                      onClick={() => handleDelete(strategy.id)}
                    >
                      <Trash2 className="w-4 h-4" />
                    </Button>
                  </div>
                </div>
              </CardHeader>
              <CardContent>
                <div className="flex items-center justify-between">
                  <div className="space-y-1">
                    {getStatusBadge(strategy.status)}
                    <p className="text-xs text-slate-400">
                      {strategy.type === "visual" ? "可视化策略" : "代码策略"} · 
                      触发 {strategy.trigger_count || 0} 次
                    </p>
                  </div>
                  <Switch
                    checked={strategy.status === "running"}
                    onCheckedChange={() => handleToggle(strategy)}
                    disabled={strategy.status === "error"}
                  />
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
}
