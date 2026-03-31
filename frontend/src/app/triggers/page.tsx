"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { formatPrice, formatDateTime, formatSymbol } from "@/lib/utils";
import { History, Trash2, ArrowUpRight, ArrowDownRight, ArrowDown, ArrowUp } from "lucide-react";
import { useRouter } from "next/navigation";
import axios from "axios";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "";

interface Trigger {
  id: number;
  strategy_id: number;
  strategy_name?: string;
  symbol?: string;
  triggered_at: string;
  signal_type: string;
  signal_detail?: string;
  action?: string;
  price?: number;
  quantity?: number;
  simulated_pnl?: number;
}

function getActionStyle(action?: string) {
  switch (action) {
    case "buy":
    case "买入":
      return { label: "买入", class: "bg-green-500/15 text-green-400", icon: ArrowUpRight };
    case "sell":
    case "卖出":
      return { label: "卖出", class: "bg-red-500/15 text-red-400", icon: ArrowDownRight };
    case "short":
    case "开空":
      return { label: "开空", class: "bg-orange-500/15 text-orange-400", icon: ArrowDown };
    case "cover":
    case "平空":
      return { label: "平空", class: "bg-purple-500/15 text-purple-400", icon: ArrowUp };
    default:
      return { label: "观望", class: "bg-slate-800 text-slate-400", icon: History };
  }
}

export default function TriggersPage() {
  const [triggers, setTriggers] = useState<Trigger[]>([]);
  const [loading, setLoading] = useState(true);
  const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());
  const router = useRouter();

  const toggleSelect = (id: number) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const toggleSelectAll = () => {
    if (selectedIds.size === triggers.length) {
      setSelectedIds(new Set());
    } else {
      setSelectedIds(new Set(triggers.map((t) => t.id)));
    }
  };

  const deleteTrigger = async (id: number) => {
    try {
      await axios.delete(`${API_BASE_URL}/api/triggers/${id}`);
      setSelectedIds((prev) => {
        const next = new Set(prev);
        next.delete(id);
        return next;
      });
      loadTriggers();
    } catch (error) {
      console.error("Failed to delete trigger:", error);
    }
  };

  const batchDelete = async () => {
    if (selectedIds.size === 0) return;
    try {
      await axios.post(`${API_BASE_URL}/api/triggers/batch-delete`, {
        ids: Array.from(selectedIds),
      });
      setSelectedIds(new Set());
      loadTriggers();
    } catch (error) {
      console.error("Failed to batch delete triggers:", error);
    }
  };

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

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="h-8 w-32 bg-slate-800 rounded-lg animate-pulse" />
        <div className="bg-slate-900 rounded-xl border border-slate-800 animate-pulse h-96" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-white">触发日志</h1>
          <p className="text-sm text-slate-500 mt-1">共 {triggers.length} 条记录</p>
        </div>
        {selectedIds.size > 0 && (
          <Button
            variant="destructive"
            size="sm"
            onClick={batchDelete}
            className="gap-1.5"
          >
            <Trash2 className="w-3.5 h-3.5" />
            删除 ({selectedIds.size})
          </Button>
        )}
      </div>

      {triggers.length === 0 ? (
        <div className="bg-slate-900 rounded-xl border border-slate-800 py-16 text-center">
          <History className="w-12 h-12 text-slate-700 mx-auto mb-4" />
          <p className="text-slate-400 mb-1">暂无触发记录</p>
          <p className="text-sm text-slate-500">启动策略后将在此显示触发记录</p>
        </div>
      ) : (
        <>
          {/* ── 移动端：卡片列表 ── */}
          <div className="md:hidden space-y-2">
            {triggers.map((trigger) => {
              const actionStyle = getActionStyle(trigger.action);
              const ActionIcon = actionStyle.icon;
              return (
                <div
                  key={trigger.id}
                  className="bg-slate-900 rounded-xl border border-slate-800 p-3.5 active:bg-slate-800/50 transition-colors"
                  onClick={() => router.push(`/strategies/${trigger.strategy_id}?tab=triggers`)}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="flex items-center gap-2 min-w-0 flex-1">
                      <div className={`w-7 h-7 rounded-lg flex items-center justify-center shrink-0 ${actionStyle.class.split(" ")[0]}`}>
                        <ActionIcon className="w-3.5 h-3.5" />
                      </div>
                      <div className="min-w-0">
                        <div className="flex items-center gap-1.5">
                          <span className={`text-xs font-medium px-1.5 py-0.5 rounded ${actionStyle.class}`}>
                            {actionStyle.label}
                          </span>
                          <span className="text-sm font-medium text-slate-200 truncate">
                            {trigger.strategy_name || `策略 #${trigger.strategy_id}`}
                          </span>
                        </div>
                        <div className="flex items-center gap-2 mt-1">
                          <span className="text-[11px] text-slate-500">
                            {formatDateTime(trigger.triggered_at)}
                          </span>
                          {trigger.symbol && (
                            <span className="text-[11px] font-mono text-slate-500">
                              {formatSymbol(trigger.symbol)}
                            </span>
                          )}
                        </div>
                      </div>
                    </div>
                    <div className="text-right shrink-0">
                      {trigger.price && (
                        <p className="text-sm font-mono text-slate-300">{formatPrice(trigger.price)}</p>
                      )}
                      {trigger.simulated_pnl != null ? (
                        <p className={`text-xs font-mono font-medium mt-0.5 ${
                          trigger.simulated_pnl >= 0 ? "text-green-400" : "text-red-400"
                        }`}>
                          {trigger.simulated_pnl >= 0 ? "+" : ""}{formatPrice(trigger.simulated_pnl)}
                        </p>
                      ) : null}
                    </div>
                  </div>
                  {/* 选择 + 删除 */}
                  <div className="flex items-center justify-between mt-2 pt-2 border-t border-slate-800/50">
                    <label
                      className="flex items-center gap-2 text-xs text-slate-500"
                      onClick={(e) => e.stopPropagation()}
                    >
                      <input
                        type="checkbox"
                        checked={selectedIds.has(trigger.id)}
                        onChange={() => toggleSelect(trigger.id)}
                        className="rounded border-slate-600 accent-blue-500"
                      />
                      选择
                    </label>
                    <button
                      onClick={(e) => { e.stopPropagation(); deleteTrigger(trigger.id); }}
                      className="p-1 rounded text-slate-600 hover:text-red-400 hover:bg-red-500/10 transition-colors"
                    >
                      <Trash2 className="w-3.5 h-3.5" />
                    </button>
                  </div>
                </div>
              );
            })}
          </div>

          {/* ── 桌面端：表格 ── */}
          <div className="hidden md:block bg-slate-900 rounded-xl border border-slate-800 overflow-hidden">
            <table className="w-full">
              <thead>
                <tr className="border-b border-slate-800">
                  <th className="p-4 w-10">
                    <input
                      type="checkbox"
                      checked={triggers.length > 0 && selectedIds.size === triggers.length}
                      onChange={toggleSelectAll}
                      className="rounded border-slate-600 accent-blue-500"
                    />
                  </th>
                  <th className="text-left p-4 text-[11px] text-slate-500 font-medium uppercase tracking-wider">时间</th>
                  <th className="text-left p-4 text-[11px] text-slate-500 font-medium uppercase tracking-wider">策略</th>
                  <th className="text-left p-4 text-[11px] text-slate-500 font-medium uppercase tracking-wider">交易对</th>
                  <th className="text-left p-4 text-[11px] text-slate-500 font-medium uppercase tracking-wider">操作</th>
                  <th className="text-left p-4 text-[11px] text-slate-500 font-medium uppercase tracking-wider">价格</th>
                  <th className="text-right p-4 text-[11px] text-slate-500 font-medium uppercase tracking-wider">盈亏</th>
                  <th className="p-4 w-10"></th>
                </tr>
              </thead>
              <tbody>
                {triggers.map((trigger) => {
                  const actionStyle = getActionStyle(trigger.action);
                  const ActionIcon = actionStyle.icon;
                  return (
                    <tr
                      key={trigger.id}
                      className="border-b border-slate-800/50 last:border-0 hover:bg-slate-800/30 transition-colors cursor-pointer"
                      onClick={() => router.push(`/strategies/${trigger.strategy_id}?tab=triggers`)}
                    >
                      <td className="p-4" onClick={(e) => e.stopPropagation()}>
                        <input
                          type="checkbox"
                          checked={selectedIds.has(trigger.id)}
                          onChange={() => toggleSelect(trigger.id)}
                          className="rounded border-slate-600 accent-blue-500"
                        />
                      </td>
                      <td className="p-4 text-sm text-slate-300 whitespace-nowrap">
                        {formatDateTime(trigger.triggered_at)}
                      </td>
                      <td className="p-4 text-sm text-slate-200 font-medium">
                        {trigger.strategy_name || `策略 #${trigger.strategy_id}`}
                      </td>
                      <td className="p-4 text-xs font-mono text-slate-400">
                        {trigger.symbol ? formatSymbol(trigger.symbol) : "-"}
                      </td>
                      <td className="p-4">
                        <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium ${actionStyle.class}`}>
                          <ActionIcon className="w-3 h-3" />
                          {actionStyle.label}
                        </span>
                      </td>
                      <td className="p-4 text-sm font-mono text-slate-300">
                        {trigger.price ? formatPrice(trigger.price) : "-"}
                      </td>
                      <td className="p-4 text-right">
                        {trigger.simulated_pnl !== undefined && trigger.simulated_pnl !== null ? (
                          <span
                            className={`text-sm font-mono font-medium ${
                              trigger.simulated_pnl >= 0 ? "text-green-400" : "text-red-400"
                            }`}
                          >
                            {trigger.simulated_pnl >= 0 ? "+" : ""}
                            {formatPrice(trigger.simulated_pnl)}
                          </span>
                        ) : (
                          <span className="text-slate-600">-</span>
                        )}
                      </td>
                      <td className="p-4" onClick={(e) => e.stopPropagation()}>
                        <button
                          onClick={() => deleteTrigger(trigger.id)}
                          className="p-1 rounded text-slate-600 hover:text-red-400 hover:bg-red-500/10 transition-colors"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
