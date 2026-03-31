"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Switch } from "@/components/ui/switch";
import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import axios from "axios";
import { MultiSymbolSelector } from "@/components/symbol-selector";
import {
  ConditionGroupEditor,
  StrategyPreview,
  serializeConfig,
  makeEmptyConfig,
  makeEmptyGroup,
} from "@/components/visual-strategy-editor";
import type { StrategyConfig } from "@/components/visual-strategy-editor";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "";

export default function NewStrategyPage() {
  const router = useRouter();
  const [loading, setLoading] = useState(false);
  const [formData, setFormData] = useState({
    name: "",
    type: "visual",
    symbols: ["BTCUSDT"],
    timeframe: "1h",
    position_size: 100,
    position_size_type: "fixed",
    sell_size_pct: 100,
    stop_loss: "",
    take_profit: "",
    notify_enabled: true,
    config_json: "{}",
    code: "",
  });
  const [visualConfig, setVisualConfig] = useState<StrategyConfig>(makeEmptyConfig());

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);

    try {
      const data = {
        ...formData,
        stop_loss: formData.stop_loss ? parseFloat(formData.stop_loss) : null,
        take_profit: formData.take_profit ? parseFloat(formData.take_profit) : null,
        config_json: formData.type === "visual" ? serializeConfig(visualConfig) : formData.config_json,
      };
      await axios.post(`${API_BASE_URL}/api/strategies`, data);
      router.push("/strategies");
    } catch (error) {
      console.error("Failed to create strategy:", error);
      alert("创建失败，请检查输入");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <div className="flex items-center gap-4 mb-8">
        <Link href="/strategies">
          <Button variant="ghost" size="icon">
            <ArrowLeft className="w-5 h-5" />
          </Button>
        </Link>
        <h1 className="text-2xl md:text-3xl font-bold">创建策略</h1>
      </div>

      <Card className="bg-slate-900 border-slate-800 w-full max-w-2xl">
        <form onSubmit={handleSubmit}>
          <CardHeader>
            <CardTitle>基础配置</CardTitle>
          </CardHeader>
          <CardContent className="space-y-6">
            {/* 策略名称 */}
            <div className="space-y-2">
              <Label htmlFor="name">策略名称</Label>
              <Input
                id="name"
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                placeholder="输入策略名称"
                required
                className="bg-slate-800 border-slate-700"
              />
            </div>

            {/* 策略类型 */}
            <Tabs
              value={formData.type}
              onValueChange={(v) => setFormData({ ...formData, type: v || "visual" })}
            >
              <TabsList className="grid w-full grid-cols-2">
                <TabsTrigger value="visual">可视化配置</TabsTrigger>
                <TabsTrigger value="code">代码编写</TabsTrigger>
              </TabsList>

              <TabsContent value="visual" className="mt-4 space-y-4">
                <ConditionGroupEditor
                  group={visualConfig.buy_conditions}
                  onChange={(g) => setVisualConfig({ ...visualConfig, buy_conditions: g })}
                  label="买入条件"
                />
                <ConditionGroupEditor
                  group={visualConfig.sell_conditions}
                  onChange={(g) => setVisualConfig({ ...visualConfig, sell_conditions: g })}
                  label="卖出条件"
                />

                {/* 开空条件（可选折叠） */}
                <details className="group">
                  <summary className="cursor-pointer select-none text-sm font-medium text-slate-300 hover:text-white flex items-center gap-2 py-2">
                    <span className="transition-transform group-open:rotate-90">▶</span>
                    开空条件
                    <span className="text-xs text-slate-500 font-normal">
                      {visualConfig.short_conditions ? "已配置" : "未配置（策略不做空）"}
                    </span>
                  </summary>
                  <div className="mt-2 space-y-2">
                    {!visualConfig.short_conditions ? (
                      <button
                        type="button"
                        onClick={() =>
                          setVisualConfig({ ...visualConfig, short_conditions: makeEmptyGroup() })
                        }
                        className="text-sm text-blue-400 hover:text-blue-300"
                      >
                        + 添加开空条件
                      </button>
                    ) : (
                      <>
                        <ConditionGroupEditor
                          group={visualConfig.short_conditions}
                          onChange={(g) => setVisualConfig({ ...visualConfig, short_conditions: g })}
                          label="开空条件"
                        />
                        <button
                          type="button"
                          onClick={() => {
                            const { short_conditions, ...rest } = visualConfig;
                            setVisualConfig(rest as typeof visualConfig);
                          }}
                          className="text-xs text-slate-500 hover:text-red-400"
                        >
                          移除开空条件
                        </button>
                      </>
                    )}
                  </div>
                </details>

                {/* 平空条件（可选折叠） */}
                <details className="group">
                  <summary className="cursor-pointer select-none text-sm font-medium text-slate-300 hover:text-white flex items-center gap-2 py-2">
                    <span className="transition-transform group-open:rotate-90">▶</span>
                    平空条件
                    <span className="text-xs text-slate-500 font-normal">
                      {visualConfig.cover_conditions ? "已配置" : "未配置（依赖止盈止损平空）"}
                    </span>
                  </summary>
                  <div className="mt-2 space-y-2">
                    {!visualConfig.cover_conditions ? (
                      <button
                        type="button"
                        onClick={() =>
                          setVisualConfig({ ...visualConfig, cover_conditions: makeEmptyGroup() })
                        }
                        className="text-sm text-blue-400 hover:text-blue-300"
                      >
                        + 添加平空条件
                      </button>
                    ) : (
                      <>
                        <ConditionGroupEditor
                          group={visualConfig.cover_conditions}
                          onChange={(g) => setVisualConfig({ ...visualConfig, cover_conditions: g })}
                          label="平空条件"
                        />
                        <button
                          type="button"
                          onClick={() => {
                            const { cover_conditions, ...rest } = visualConfig;
                            setVisualConfig(rest as typeof visualConfig);
                          }}
                          className="text-xs text-slate-500 hover:text-red-400"
                        >
                          移除平空条件
                        </button>
                      </>
                    )}
                  </div>
                </details>

                <StrategyPreview
                  config={visualConfig}
                  stopLoss={formData.stop_loss ? parseFloat(formData.stop_loss) : null}
                  takeProfit={formData.take_profit ? parseFloat(formData.take_profit) : null}
                />
              </TabsContent>

              <TabsContent value="code" className="mt-4">
                <div className="space-y-2">
                  <Label htmlFor="code">策略代码 (Python)</Label>
                  <textarea
                    id="code"
                    value={formData.code}
                    onChange={(e) => setFormData({ ...formData, code: e.target.value })}
                    placeholder="# 在此编写策略代码\n# 后续将支持 Monaco Editor"
                    className="w-full h-32 p-3 bg-slate-800 border border-slate-700 rounded-md font-mono text-sm"
                  />
                </div>
              </TabsContent>
            </Tabs>

            {/* 交易对 */}
            <div className="space-y-2">
              <Label>交易对</Label>
              <MultiSymbolSelector
                value={formData.symbols}
                onChange={(symbols) => setFormData({ ...formData, symbols })}
              />
            </div>

            {/* 时间周期 */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="timeframe">时间周期</Label>
                <Select
                  value={formData.timeframe}
                  onValueChange={(v) => setFormData({ ...formData, timeframe: v || "1h" })}
                >
                  <SelectTrigger className="bg-slate-800 border-slate-700">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="1m">1分钟</SelectItem>
                    <SelectItem value="5m">5分钟</SelectItem>
                    <SelectItem value="1h">1小时</SelectItem>
                    <SelectItem value="1d">1天</SelectItem>
                  </SelectContent>
                </Select>
              </div>
            </div>

            {/* 仓位配置 */}
            <div className="space-y-3">
              <Label className="text-sm font-medium">仓位配置</Label>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="position_size" className="text-xs text-slate-400">
                    每次买入
                    {formData.position_size_type === "fixed" ? "（USDT）" : "（账户余额 %）"}
                  </Label>
                  <Input
                    id="position_size"
                    type="number"
                    value={formData.position_size}
                    onChange={(e) => setFormData({ ...formData, position_size: parseFloat(e.target.value) })}
                    required
                    min={0}
                    className="bg-slate-800 border-slate-700"
                  />
                </div>

                <div className="space-y-2">
                  <Label htmlFor="position_size_type" className="text-xs text-slate-400">买入类型</Label>
                  <Select
                    value={formData.position_size_type}
                    onValueChange={(v) => setFormData({ ...formData, position_size_type: v || "fixed" })}
                  >
                    <SelectTrigger className="bg-slate-800 border-slate-700">
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="fixed">固定金额 (USDT)</SelectItem>
                      <SelectItem value="percent">账户余额百分比 (%)</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="sell_size_pct" className="text-xs text-slate-400">
                  每次卖出仓位比例 (%) — 100% 表示全部清仓
                </Label>
                <div className="flex items-center gap-3">
                  <Input
                    id="sell_size_pct"
                    type="number"
                    value={formData.sell_size_pct}
                    onChange={(e) => setFormData({ ...formData, sell_size_pct: Math.min(100, Math.max(1, parseFloat(e.target.value) || 100)) })}
                    min={1}
                    max={100}
                    className="bg-slate-800 border-slate-700 w-28"
                  />
                  <span className="text-sm text-slate-400">%</span>
                  <div className="flex gap-2">
                    {[25, 50, 75, 100].map((v) => (
                      <button
                        key={v}
                        type="button"
                        onClick={() => setFormData({ ...formData, sell_size_pct: v })}
                        className={`px-2 py-1 text-xs rounded border transition-colors ${
                          formData.sell_size_pct === v
                            ? "bg-blue-600 border-blue-500 text-white"
                            : "bg-slate-800 border-slate-700 text-slate-400 hover:border-slate-500"
                        }`}
                      >
                        {v}%
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </div>

            {/* 止盈止损 */}
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="stop_loss">止损 (%)</Label>
                <Input
                  id="stop_loss"
                  type="number"
                  value={formData.stop_loss}
                  onChange={(e) => setFormData({ ...formData, stop_loss: e.target.value })}
                  placeholder="可选"
                  className="bg-slate-800 border-slate-700"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="take_profit">止盈 (%)</Label>
                <Input
                  id="take_profit"
                  type="number"
                  value={formData.take_profit}
                  onChange={(e) => setFormData({ ...formData, take_profit: e.target.value })}
                  placeholder="可选"
                  className="bg-slate-800 border-slate-700"
                />
              </div>
            </div>

            {/* 通知开关 */}
            <div className="flex items-center justify-between">
              <Label htmlFor="notify_enabled">启用通知（飞书 / Bark）</Label>
              <Switch
                id="notify_enabled"
                checked={formData.notify_enabled}
                onCheckedChange={(v) => setFormData({ ...formData, notify_enabled: v })}
              />
            </div>

            {/* 提交按钮 */}
            <div className="flex justify-end gap-4">
              <Link href="/strategies">
                <Button type="button" variant="outline">
                  取消
                </Button>
              </Link>
              <Button type="submit" disabled={loading}>
                {loading ? "创建中..." : "创建策略"}
              </Button>
            </div>
          </CardContent>
        </form>
      </Card>
    </div>
  );
}
