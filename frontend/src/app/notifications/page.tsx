"use client";

import { useEffect, useState } from "react";
import { Eye, EyeOff, Plus, Trash2, Send } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import {
  fetchNotificationSettings,
  updateNotificationSettings,
  testBarkNotification,
} from "@/lib/api";

interface BarkConfig {
  id: string;
  name: string;
  key: string;
  enabled: boolean;
}

function genId() {
  return Math.random().toString(36).slice(2, 10);
}

export default function NotificationsPage() {
  const [configs, setConfigs] = useState<BarkConfig[]>([]);
  const [barkEnabled, setBarkEnabled] = useState(false);
  const [showKeys, setShowKeys] = useState<Record<string, boolean>>({});
  const [saveStatus, setSaveStatus] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [testingId, setTestingId] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<Record<string, { ok: boolean; msg: string }>>({});

  useEffect(() => {
    fetchNotificationSettings().then((res: any) => {
      setConfigs(res.bark_configs ?? []);
      setBarkEnabled(res.bark_enabled ?? false);
    }).catch(() => {});
  }, []);

  function addConfig() {
    setConfigs((prev) => [...prev, { id: genId(), name: "", key: "", enabled: true }]);
  }

  function removeConfig(id: string) {
    setConfigs((prev) => prev.filter((c) => c.id !== id));
  }

  function updateConfig(id: string, field: keyof BarkConfig, value: string | boolean) {
    setConfigs((prev) =>
      prev.map((c) => (c.id === id ? { ...c, [field]: value } : c))
    );
  }

  async function handleSave() {
    setSaveStatus("saving");
    try {
      await updateNotificationSettings({ bark_configs: configs, bark_enabled: barkEnabled });
      setSaveStatus("saved");
      setTimeout(() => setSaveStatus("idle"), 2000);
    } catch {
      setSaveStatus("error");
      setTimeout(() => setSaveStatus("idle"), 3000);
    }
  }

  async function handleTest(cfg: BarkConfig) {
    setTestingId(cfg.id);
    setTestResult((prev) => ({ ...prev, [cfg.id]: { ok: false, msg: "" } }));
    try {
      await testBarkNotification(cfg.key);
      setTestResult((prev) => ({ ...prev, [cfg.id]: { ok: true, msg: "发送成功" } }));
    } catch (err: any) {
      const detail = err.response?.data?.detail ?? "推送失败";
      setTestResult((prev) => ({ ...prev, [cfg.id]: { ok: false, msg: detail } }));
    } finally {
      setTestingId(null);
      setTimeout(() => {
        setTestResult((prev) => {
          const next = { ...prev };
          delete next[cfg.id];
          return next;
        });
      }, 4000);
    }
  }

  return (
    <div className="max-w-xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">通知设置</h1>
        <p className="text-sm text-slate-500 mt-1">配置策略触发时的推送通知</p>
      </div>

      <Card className="bg-slate-900 border-slate-800">
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="text-white text-lg">Bark 推送</CardTitle>
              <CardDescription className="text-slate-400">
                支持多个设备，在 Bark App 中复制 Key 填入下方。
              </CardDescription>
            </div>
            <div className="flex items-center gap-2">
              <Label htmlFor="bark-global" className="text-sm text-slate-400">
                总开关
              </Label>
              <Switch
                id="bark-global"
                checked={barkEnabled}
                onCheckedChange={setBarkEnabled}
              />
            </div>
          </div>
        </CardHeader>
        <CardContent className="space-y-4">
          {configs.length === 0 && (
            <div className="text-center py-6 text-slate-500 text-sm">
              暂无配置，点击下方按钮添加
            </div>
          )}

          {configs.map((cfg) => (
            <div
              key={cfg.id}
              className="rounded-lg border border-slate-800 bg-slate-800/30 p-4 space-y-3"
            >
              <div className="flex items-center gap-3">
                <Input
                  value={cfg.name}
                  onChange={(e) => updateConfig(cfg.id, "name", e.target.value)}
                  placeholder="备注名称（如 iPhone）"
                  className="bg-slate-800 border-slate-700 text-white text-sm h-8 flex-1"
                />
                <Switch
                  checked={cfg.enabled}
                  onCheckedChange={(v) => updateConfig(cfg.id, "enabled", v)}
                />
                <button
                  onClick={() => removeConfig(cfg.id)}
                  className="p-1.5 rounded text-slate-500 hover:text-red-400 hover:bg-red-500/10 transition-colors"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>

              <div className="flex items-center gap-2">
                <div className="relative flex-1">
                  <Input
                    type={showKeys[cfg.id] ? "text" : "password"}
                    value={cfg.key}
                    onChange={(e) => updateConfig(cfg.id, "key", e.target.value)}
                    placeholder="Bark Key"
                    className="bg-slate-800 border-slate-700 text-white text-sm h-8 pr-8"
                  />
                  <button
                    type="button"
                    onClick={() =>
                      setShowKeys((prev) => ({ ...prev, [cfg.id]: !prev[cfg.id] }))
                    }
                    className="absolute right-2 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-200"
                  >
                    {showKeys[cfg.id] ? (
                      <EyeOff className="w-3.5 h-3.5" />
                    ) : (
                      <Eye className="w-3.5 h-3.5" />
                    )}
                  </button>
                </div>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => handleTest(cfg)}
                  disabled={!cfg.key || testingId === cfg.id}
                  className="border-slate-700 text-slate-300 hover:text-white hover:bg-slate-800 h-8 px-3"
                >
                  <Send className="w-3.5 h-3.5" />
                </Button>
              </div>

              {testResult[cfg.id] && (
                <p
                  className={`text-xs ${
                    testResult[cfg.id].ok ? "text-green-400" : "text-red-400"
                  }`}
                >
                  {testResult[cfg.id].msg}
                </p>
              )}
            </div>
          ))}

          <Button
            variant="outline"
            size="sm"
            onClick={addConfig}
            className="w-full border-dashed border-slate-700 text-slate-400 hover:text-white hover:bg-slate-800"
          >
            <Plus className="w-4 h-4 mr-1.5" />
            添加设备
          </Button>

          <div className="pt-2">
            <Button
              onClick={handleSave}
              disabled={saveStatus === "saving"}
              className="w-full"
            >
              {saveStatus === "saving"
                ? "保存中..."
                : saveStatus === "saved"
                ? "已保存 ✓"
                : saveStatus === "error"
                ? "保存失败"
                : "保存"}
            </Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
