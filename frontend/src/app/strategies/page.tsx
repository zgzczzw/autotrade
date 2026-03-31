"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { formatSymbol } from "@/lib/utils";
import { Plus, Settings, Trash2, Zap, Code, Eye, Bot, Download, Upload } from "lucide-react";
import axios from "axios";
import { exportStrategies, importStrategies } from "@/lib/api";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "";

interface Strategy {
  id: number;
  name: string;
  type: string;
  symbol: string;
  symbols?: string[];
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

  const handleExport = async () => {
    try {
      const blob = await exportStrategies();
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "autotrade-strategies.json";
      a.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      console.error("Failed to export:", error);
      alert("导出失败");
    }
  };

  const handleImport = async () => {
    const input = document.createElement("input");
    input.type = "file";
    input.accept = ".json";
    input.onchange = async (e) => {
      const file = (e.target as HTMLInputElement).files?.[0];
      if (!file) return;
      try {
        const res = await importStrategies(file);
        alert((res as any).message || "导入成功");
        loadStrategies();
      } catch (error: any) {
        const msg = error.response?.data?.detail || "导入失败";
        alert(msg);
      }
    };
    input.click();
  };

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <div className="h-8 w-32 bg-slate-800 rounded-lg animate-pulse" />
          <div className="h-9 w-24 bg-slate-800 rounded-lg animate-pulse" />
        </div>
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {[...Array(3)].map((_, i) => (
            <div key={i} className="h-36 bg-slate-900 rounded-xl border border-slate-800 animate-pulse" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-white">策略管理</h1>
        <div className="flex items-center gap-2">
          <Button size="sm" variant="outline" className="gap-1.5" onClick={handleImport}>
            <Upload className="w-3.5 h-3.5" />
            导入
          </Button>
          <Button size="sm" variant="outline" className="gap-1.5" onClick={handleExport} disabled={strategies.length === 0}>
            <Download className="w-3.5 h-3.5" />
            导出
          </Button>
          <Link href="/strategies/new">
            <Button size="sm" className="gap-1.5">
              <Plus className="w-4 h-4" />
              创建策略
            </Button>
          </Link>
        </div>
      </div>

      {strategies.length === 0 ? (
        <div className="bg-slate-900 rounded-xl border border-slate-800 py-16 text-center">
          <Bot className="w-12 h-12 text-slate-700 mx-auto mb-4" />
          <p className="text-slate-400 mb-1">暂无策略</p>
          <p className="text-sm text-slate-500 mb-5">创建你的第一个交易策略开始自动化交易</p>
          <Link href="/strategies/new">
            <Button size="sm" className="gap-1.5">
              <Plus className="w-4 h-4" />
              创建策略
            </Button>
          </Link>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {strategies.map((strategy) => {
            const isRunning = strategy.status === "running";
            const isError = strategy.status === "error";
            return (
              <div
                key={strategy.id}
                className={`bg-slate-900 rounded-xl border transition-all hover:border-slate-700 ${
                  isRunning ? "border-slate-700/80" : isError ? "border-red-900/50" : "border-slate-800"
                }`}
              >
                <div className="p-4">
                  {/* 头部 */}
                  <div className="flex items-start justify-between mb-3">
                    <div className="flex-1 min-w-0">
                      <Link href={`/strategies/${strategy.id}`} className="group">
                        <h3 className="font-semibold text-white truncate group-hover:text-blue-400 transition-colors">
                          {strategy.name}
                        </h3>
                      </Link>
                      <div className="flex items-center gap-1.5 mt-1 flex-wrap">
                        {(strategy.symbols || (strategy.symbol ? [strategy.symbol] : [])).slice(0, 3).map((s) => (
                          <span key={s} className="text-[11px] text-slate-400 font-mono bg-slate-800 px-1.5 py-0.5 rounded">
                            {formatSymbol(s)}
                          </span>
                        ))}
                        {(strategy.symbols || []).length > 3 && (
                          <span className="text-[11px] text-slate-500">
                            +{(strategy.symbols || []).length - 3}
                          </span>
                        )}
                        <span className="text-slate-700">·</span>
                        <span className="text-xs text-slate-500">{strategy.timeframe}</span>
                      </div>
                    </div>
                    <Switch
                      checked={isRunning}
                      onCheckedChange={() => handleToggle(strategy)}
                      disabled={isError}
                    />
                  </div>

                  {/* 底部信息 */}
                  <div className="flex items-center justify-between pt-3 border-t border-slate-800/50">
                    <div className="flex items-center gap-2">
                      {/* 状态指示 */}
                      <div className="flex items-center gap-1.5">
                        <div className={`w-1.5 h-1.5 rounded-full ${
                          isRunning ? "bg-green-400 animate-pulse" : isError ? "bg-red-400" : "bg-slate-600"
                        }`} />
                        <span className={`text-xs ${
                          isRunning ? "text-green-400" : isError ? "text-red-400" : "text-slate-500"
                        }`}>
                          {isRunning ? "运行中" : isError ? "错误" : "已停止"}
                        </span>
                      </div>
                      <span className="text-slate-700">·</span>
                      <span className="text-xs text-slate-500 flex items-center gap-1">
                        {strategy.type === "visual" ? <Eye className="w-3 h-3" /> : <Code className="w-3 h-3" />}
                        {strategy.type === "visual" ? "可视化" : "代码"}
                      </span>
                      <span className="text-slate-700">·</span>
                      <span className="text-xs text-slate-500 flex items-center gap-1">
                        <Zap className="w-3 h-3" />
                        {strategy.trigger_count || 0}
                      </span>
                    </div>
                    <div className="flex items-center gap-1">
                      <Link href={`/strategies/${strategy.id}`}>
                        <button className="p-1.5 rounded-md text-slate-500 hover:text-slate-300 hover:bg-slate-800 transition-colors">
                          <Settings className="w-3.5 h-3.5" />
                        </button>
                      </Link>
                      <button
                        className="p-1.5 rounded-md text-slate-500 hover:text-red-400 hover:bg-red-500/10 transition-colors"
                        onClick={() => handleDelete(strategy.id)}
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
