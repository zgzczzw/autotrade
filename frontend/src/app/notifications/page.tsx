"use client";

import { useEffect, useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import {
  fetchNotificationSettings,
  updateNotificationSettings,
  testNotification,
} from "@/lib/api";

export default function NotificationsPage() {
  const [barkKey, setBarkKey] = useState("");
  const [barkEnabled, setBarkEnabled] = useState(false);
  const [showKey, setShowKey] = useState(false);
  const [saveStatus, setSaveStatus] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [testStatus, setTestStatus] = useState<"idle" | "sending" | "success" | "error">("idle");
  const [testError, setTestError] = useState("");

  useEffect(() => {
    fetchNotificationSettings().then((res: any) => {
      setBarkKey(res.bark_key ?? "");
      setBarkEnabled(res.bark_enabled ?? false);
    }).catch(() => {});
  }, []);

  async function handleSave() {
    setSaveStatus("saving");
    try {
      await updateNotificationSettings({ bark_key: barkKey, bark_enabled: barkEnabled });
      setSaveStatus("saved");
      setTimeout(() => setSaveStatus("idle"), 2000);
    } catch {
      setSaveStatus("error");
      setTimeout(() => setSaveStatus("idle"), 3000);
    }
  }

  async function handleTest() {
    setTestStatus("sending");
    setTestError("");
    try {
      await testNotification();
      setTestStatus("success");
      setTimeout(() => setTestStatus("idle"), 3000);
    } catch (err: any) {
      setTestStatus("error");
      setTestError(err.response?.data?.detail ?? "推送失败，请检查 Bark Key");
      setTimeout(() => { setTestStatus("idle"); setTestError(""); }, 5000);
    }
  }

  return (
    <div className="max-w-xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">通知设置</h1>
        <p className="text-slate-400 text-sm mt-1">配置策略触发时的推送通知</p>
      </div>

      <Card className="bg-slate-900 border-slate-800">
        <CardHeader>
          <CardTitle className="text-white text-lg">Bark 推送</CardTitle>
          <CardDescription className="text-slate-400">
            使用 Bark App 接收 iOS 推送通知。在 Bark App 中复制你的 Key 填入下方。
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="bark-key" className="text-slate-300">Bark Key</Label>
            <div className="relative">
              <Input
                id="bark-key"
                type={showKey ? "text" : "password"}
                value={barkKey}
                onChange={(e) => setBarkKey(e.target.value)}
                placeholder="粘贴你的 Bark Key"
                className="bg-slate-800 border-slate-700 text-white pr-10"
              />
              <button
                type="button"
                onClick={() => setShowKey(!showKey)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-200"
              >
                {showKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>

          <div className="flex items-center justify-between py-1">
            <Label htmlFor="bark-enabled" className="text-slate-300 cursor-pointer">
              启用通知
            </Label>
            <Switch
              id="bark-enabled"
              checked={barkEnabled}
              onCheckedChange={setBarkEnabled}
            />
          </div>

          <div className="flex gap-3 pt-2">
            <Button
              onClick={handleSave}
              disabled={saveStatus === "saving"}
              className="flex-1"
            >
              {saveStatus === "saving" ? "保存中..." : saveStatus === "saved" ? "已保存 ✓" : saveStatus === "error" ? "保存失败" : "保存"}
            </Button>
            <Button
              variant="outline"
              onClick={handleTest}
              disabled={testStatus === "sending" || !barkKey}
              className="flex-1 border-slate-700 text-slate-300 hover:text-white hover:bg-slate-800"
            >
              {testStatus === "sending" ? "发送中..." : testStatus === "success" ? "发送成功 ✓" : testStatus === "error" ? "发送失败" : "测试推送"}
            </Button>
          </div>

          {testError && (
            <p className="text-red-400 text-sm">{testError}</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
