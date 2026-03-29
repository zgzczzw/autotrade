"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { fetchSettings, updateSettings, testConnection, authLogout, resetAccount } from "@/lib/api";
import { setTimezone } from "@/lib/utils";
import { CheckCircle, XCircle, Loader2, FlaskConical, Bell, LogOut, RotateCcw } from "lucide-react";

type DataSource = "binance" | "cryptocompare" | "mock";

const DATA_SOURCE_LABELS: Record<DataSource, { label: string; desc: string }> = {
  binance: {
    label: "Binance",
    desc: "官方 Binance API，真实市场数据。需要代理或海外服务器。",
  },
  cryptocompare: {
    label: "CryptoCompare",
    desc: "CryptoCompare 公共 API，真实历史 OHLCV 数据，免费额度每月 10 万次。",
  },
  mock: {
    label: "Mock（模拟数据）",
    desc: "随机生成价格数据，用于开发和测试，无需网络连接。",
  },
};

export default function SettingsPage() {
  const router = useRouter();
  const [dataSource, setDataSource] = useState<DataSource>("binance");
  const [apiKey, setApiKey] = useState("");
  const [timezone, setTimezoneState] = useState("Asia/Shanghai");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [saveMsg, setSaveMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [testMsg, setTestMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const [resetting, setResetting] = useState(false);
  const [showResetConfirm, setShowResetConfirm] = useState(false);
  const [resetMsg, setResetMsg] = useState<{ ok: boolean; text: string } | null>(null);

  useEffect(() => {
    fetchSettings()
      .then((data: any) => {
        setDataSource(data.data_source as DataSource);
        setApiKey(data.cryptocompare_api_key || "");
        const tz = data.timezone || "Asia/Shanghai";
        setTimezoneState(tz);
        setTimezone(tz);
      })
      .finally(() => setLoading(false));
  }, []);

  const handleSave = async () => {
    setSaving(true);
    setSaveMsg(null);
    try {
      await updateSettings({
        data_source: dataSource,
        cryptocompare_api_key: apiKey,
        timezone,
      });
      setTimezone(timezone);
      setSaveMsg({ ok: true, text: "保存成功" });
    } catch {
      setSaveMsg({ ok: false, text: "保存失败，请重试" });
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    setTesting(true);
    setTestMsg(null);
    try {
      const result: any = await testConnection({
        data_source: dataSource,
        api_key: apiKey,
      });
      setTestMsg({ ok: result.success, text: result.message });
    } catch {
      setTestMsg({ ok: false, text: "测试请求失败" });
    } finally {
      setTesting(false);
    }
  };

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-6 h-6 animate-spin text-slate-400" />
      </div>
    );
  }

  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">系统设置</h1>
        <p className="text-sm text-slate-500 mt-1">配置市场数据来源，切换后立即生效</p>
      </div>

      {/* 数据源选择 */}
      <section className="bg-slate-900 rounded-xl p-6 border border-slate-800">
        <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-4">
          数据源
        </h2>
        <div className="space-y-3">
          {(Object.keys(DATA_SOURCE_LABELS) as DataSource[]).map((src) => {
            const { label, desc } = DATA_SOURCE_LABELS[src];
            const isSelected = dataSource === src;
            return (
              <label
                key={src}
                className={`flex items-start gap-4 p-4 rounded-lg border cursor-pointer transition-colors ${
                  isSelected
                    ? "border-blue-500 bg-blue-500/10"
                    : "border-slate-700 hover:border-slate-600"
                }`}
              >
                <input
                  type="radio"
                  name="data_source"
                  value={src}
                  checked={isSelected}
                  onChange={() => {
                    setDataSource(src);
                    setTestMsg(null);
                    setSaveMsg(null);
                  }}
                  className="mt-1 accent-blue-500"
                />
                <div>
                  <p className="font-medium text-white">{label}</p>
                  <p className="text-sm text-slate-400 mt-0.5">{desc}</p>
                </div>
              </label>
            );
          })}
        </div>
      </section>

      {/* CryptoCompare API Key */}
      {dataSource === "cryptocompare" && (
        <section className="bg-slate-900 rounded-xl p-6 border border-slate-800">
          <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-4">
            CryptoCompare API Key
          </h2>
          <p className="text-sm text-slate-400 mb-3">
            免费账号每月 10 万次调用，在
            <a
              href="https://www.cryptocompare.com/cryptopian/api-keys"
              target="_blank"
              rel="noopener noreferrer"
              className="text-blue-400 hover:underline mx-1"
            >
              CryptoCompare 控制台
            </a>
            申请。不填也可使用（速率限制更严格）。
          </p>
          <input
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            placeholder="留空则使用匿名访问"
            className="w-full px-4 py-2.5 bg-slate-800 border border-slate-700 rounded-lg text-white placeholder-slate-500 focus:outline-none focus:border-blue-500 font-mono text-sm"
          />
        </section>
      )}

      {/* 时区设置 */}
      <section className="bg-slate-900 rounded-xl p-6 border border-slate-800">
        <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wider mb-4">
          时区
        </h2>
        <select
          value={timezone}
          onChange={(e) => setTimezoneState(e.target.value)}
          className="w-full px-4 py-2.5 bg-slate-800 border border-slate-700 rounded-lg text-white focus:outline-none focus:border-blue-500 text-sm"
        >
          <option value="Asia/Shanghai">UTC+8 中国标准时间（北京/上海）</option>
          <option value="Asia/Tokyo">UTC+9 日本标准时间（东京）</option>
          <option value="Asia/Seoul">UTC+9 韩国标准时间（首尔）</option>
          <option value="Asia/Singapore">UTC+8 新加坡标准时间</option>
          <option value="Asia/Hong_Kong">UTC+8 香港时间</option>
          <option value="Europe/London">UTC+0/+1 英国时间（伦敦）</option>
          <option value="Europe/Berlin">UTC+1/+2 中欧时间（柏林）</option>
          <option value="America/New_York">UTC-5/-4 美东时间（纽约）</option>
          <option value="America/Chicago">UTC-6/-5 美中时间（芝加哥）</option>
          <option value="America/Los_Angeles">UTC-8/-7 美西时间（洛杉矶）</option>
          <option value="UTC">UTC+0 协调世界时</option>
        </select>
      </section>

      {/* 测试连接 */}
      <div className="flex items-center gap-4">
        <button
          onClick={handleTest}
          disabled={testing}
          className="flex items-center gap-2 px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white rounded-lg transition-colors disabled:opacity-50 text-sm"
        >
          {testing ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <FlaskConical className="w-4 h-4" />
          )}
          测试连接
        </button>

        {testMsg && (
          <span
            className={`flex items-center gap-1.5 text-sm ${
              testMsg.ok ? "text-green-400" : "text-red-400"
            }`}
          >
            {testMsg.ok ? (
              <CheckCircle className="w-4 h-4" />
            ) : (
              <XCircle className="w-4 h-4" />
            )}
            {testMsg.text}
          </span>
        )}
      </div>

      {/* 保存按钮 */}
      <div className="flex items-center gap-4">
        <button
          onClick={handleSave}
          disabled={saving}
          className="flex items-center gap-2 px-6 py-2.5 bg-blue-600 hover:bg-blue-500 text-white rounded-lg transition-colors disabled:opacity-50 font-medium"
        >
          {saving && <Loader2 className="w-4 h-4 animate-spin" />}
          保存设置
        </button>

        {saveMsg && (
          <span
            className={`flex items-center gap-1.5 text-sm ${
              saveMsg.ok ? "text-green-400" : "text-red-400"
            }`}
          >
            {saveMsg.ok ? (
              <CheckCircle className="w-4 h-4" />
            ) : (
              <XCircle className="w-4 h-4" />
            )}
            {saveMsg.text}
          </span>
        )}
      </div>

      {/* 账号 */}
      <section className="bg-slate-900 rounded-xl border border-slate-800 overflow-hidden">
        <h2 className="text-sm font-semibold text-slate-300 uppercase tracking-wider px-6 py-4 border-b border-slate-800">
          账号
        </h2>
        <Link
          href="/notifications"
          className="flex items-center gap-3 px-6 py-4 text-slate-200 hover:bg-slate-800 transition-colors border-b border-slate-800"
        >
          <Bell className="w-4 h-4 text-slate-400" />
          <span>消息通知</span>
        </Link>
        <div className="border-b border-slate-800">
          {!showResetConfirm ? (
            <button
              onClick={() => { setShowResetConfirm(true); setResetMsg(null); }}
              className="flex items-center gap-3 px-6 py-4 w-full text-left text-orange-400 hover:bg-slate-800 transition-colors"
            >
              <RotateCcw className="w-4 h-4" />
              <div>
                <span>重置账户</span>
                <p className="text-xs text-slate-500 mt-0.5">停止所有策略，清空持仓和交易记录，余额恢复初始值</p>
              </div>
            </button>
          ) : (
            <div className="px-6 py-4 space-y-3">
              <p className="text-sm text-orange-300">确认重置账户？此操作不可撤销，将会：</p>
              <ul className="text-xs text-slate-400 list-disc list-inside space-y-1">
                <li>停止所有运行中的策略</li>
                <li>删除所有持仓和交易记录</li>
                <li>删除所有触发日志</li>
                <li>余额恢复为初始值，盈亏归零</li>
              </ul>
              <div className="flex items-center gap-3">
                <button
                  onClick={async () => {
                    setResetting(true);
                    setResetMsg(null);
                    try {
                      await resetAccount();
                      setResetMsg({ ok: true, text: "账户已重置" });
                      setShowResetConfirm(false);
                    } catch {
                      setResetMsg({ ok: false, text: "重置失败，请重试" });
                    } finally {
                      setResetting(false);
                    }
                  }}
                  disabled={resetting}
                  className="flex items-center gap-2 px-4 py-2 bg-orange-600 hover:bg-orange-500 text-white rounded-lg transition-colors disabled:opacity-50 text-sm font-medium"
                >
                  {resetting && <Loader2 className="w-4 h-4 animate-spin" />}
                  确认重置
                </button>
                <button
                  onClick={() => setShowResetConfirm(false)}
                  className="px-4 py-2 text-slate-400 hover:text-white text-sm transition-colors"
                >
                  取消
                </button>
                {resetMsg && (
                  <span className={`flex items-center gap-1.5 text-sm ${resetMsg.ok ? "text-green-400" : "text-red-400"}`}>
                    {resetMsg.ok ? <CheckCircle className="w-4 h-4" /> : <XCircle className="w-4 h-4" />}
                    {resetMsg.text}
                  </span>
                )}
              </div>
            </div>
          )}
        </div>
        <button
          onClick={async () => {
            try { await authLogout(); } finally { router.push("/login"); }
          }}
          className="flex items-center gap-3 px-6 py-4 w-full text-left text-red-400 hover:bg-slate-800 transition-colors"
        >
          <LogOut className="w-4 h-4" />
          <span>退出登录</span>
        </button>
      </section>
    </div>
  );
}
