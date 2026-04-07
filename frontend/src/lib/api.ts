/**
 * API 客户端（带缓存和请求去重）
 */

import axios, { AxiosResponse } from "axios";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "";

const api = axios.create({
  baseURL: `${API_BASE_URL}/api`,
  headers: {
    "Content-Type": "application/json",
  },
  withCredentials: true,
  timeout: 15000,
});

// 响应拦截器
api.interceptors.response.use(
  (response: AxiosResponse) => response.data,
  (error) => {
    const url: string = error.config?.url ?? "";
    if (error.response?.status === 401 && !url.startsWith("/auth/")) {
      if (typeof window !== "undefined") {
        window.location.href = "/login";
      }
    }
    console.error("API Error:", error.response?.data || error.message);
    return Promise.reject(error);
  }
);

// ---------- 简易请求缓存 & 去重 ----------

interface CacheEntry {
  data: any;
  ts: number;
}

const cache = new Map<string, CacheEntry>();
const inflight = new Map<string, Promise<any>>();

/**
 * 带缓存的 GET 请求
 * @param url   API 路径
 * @param ttl   缓存有效期（毫秒），默认 5 秒
 * @param params  查询参数
 */
async function cachedGet<T>(url: string, ttl: number = 5000, params?: any): Promise<T> {
  const key = url + (params ? JSON.stringify(params) : "");

  // 1. 命中缓存
  const hit = cache.get(key);
  if (hit && Date.now() - hit.ts < ttl) {
    return hit.data as T;
  }

  // 2. 去重：同一请求正在进行中则复用
  const pending = inflight.get(key);
  if (pending) return pending as Promise<T>;

  // 3. 发起请求
  const promise = api.get(url, { params }).then((data) => {
    cache.set(key, { data, ts: Date.now() });
    inflight.delete(key);
    return data as T;
  }).catch((err) => {
    inflight.delete(key);
    throw err;
  });

  inflight.set(key, promise);
  return promise;
}

/** 清除指定前缀的缓存 */
export function invalidateCache(prefix: string) {
  for (const key of cache.keys()) {
    if (key.startsWith(prefix)) cache.delete(key);
  }
}

// Helper function to handle API calls
async function apiCall<T>(promise: Promise<any>): Promise<T> {
  const result = await promise;
  return result as T;
}

// ==================== 仪表盘 ====================

export const fetchDashboard = () => cachedGet("/dashboard", 8000);

// ==================== 大盘行情 ====================

export const fetchSymbols = (q: string = "") =>
  cachedGet<string[]>("/market/symbols", 60000, { q });

export const fetchMarketKlines = (symbol: string, timeframe: string, limit = 1000) =>
  cachedGet("/market/klines", 30000, { symbol, timeframe, limit });

export const fetchTicker = (symbol: string) =>
  cachedGet("/market/ticker", 10000, { symbol });

// ==================== 系统设置 ====================

export const fetchSettings = () => cachedGet("/settings", 30000);

export const updateSettings = (data: {
  data_source: string;
  cryptocompare_api_key?: string;
  timezone?: string;
  site_url?: string;
}) => { invalidateCache("/settings"); return apiCall(api.put("/settings", data)); };

export const testConnection = (data: {
  data_source: string;
  api_key?: string;
}) => apiCall(api.post("/settings/test", data));

// ==================== 策略 ====================

export const fetchStrategies = (params?: { status?: string; page?: number; page_size?: number }) =>
  cachedGet("/strategies", 5000, params);

export const fetchStrategy = (id: string | number) =>
  cachedGet(`/strategies/${id}`, 5000);

export const createStrategy = (data: any) => {
  invalidateCache("/strategies");
  return apiCall(api.post("/strategies", data));
};

export const updateStrategy = (id: string | number, data: any) => {
  invalidateCache("/strategies");
  return apiCall(api.put(`/strategies/${id}`, data));
};

export const deleteStrategy = (id: string | number) => {
  invalidateCache("/strategies");
  return apiCall(api.delete(`/strategies/${id}`));
};

export const startStrategy = (id: string | number) => {
  invalidateCache("/strategies");
  return apiCall(api.post(`/strategies/${id}/start`));
};

export const stopStrategy = (id: string | number) => {
  invalidateCache("/strategies");
  return apiCall(api.post(`/strategies/${id}/stop`));
};

export const exportStrategies = async (): Promise<Blob> => {
  const res = await axios.get(`${API_BASE_URL}/api/strategies/export`, {
    responseType: "blob",
    withCredentials: true,
  });
  return res.data;
};

export const importStrategies = async (file: File): Promise<{ message: string }> => {
  invalidateCache("/strategies");
  const form = new FormData();
  form.append("file", file);
  return apiCall(api.post("/strategies/import", form, { headers: { "Content-Type": "multipart/form-data" } }));
};

// ==================== 触发日志 ====================

export const fetchTriggers = (params?: { strategy_id?: number; symbol?: string; page?: number; page_size?: number }) =>
  cachedGet("/triggers", 5000, params);

// ==================== 账户和持仓 ====================

export const fetchAccount = () => cachedGet("/account", 5000);

export const resetAccount = () => {
  invalidateCache("/account");
  invalidateCache("/dashboard");
  invalidateCache("/positions");
  invalidateCache("/strategies");
  return apiCall(api.post("/account/reset"));
};

export const fetchPositions = (params?: { strategy_id?: number }) =>
  cachedGet("/positions", 5000, params);

// ==================== 认证 ====================

export const authMe = () => cachedGet<{ user: any | null }>("/auth/me", 30000);

export const authLogin = (data: { username: string; password: string }) =>
  apiCall<{ user: any }>(api.post("/auth/login", data));

export const authRegister = (data: { username: string; password: string }) =>
  apiCall<{ user: any }>(api.post("/auth/register", data));

export const authLogout = () => {
  cache.clear();
  return apiCall(api.post("/auth/logout"));
};

// ==================== 通知设置 ====================

export const fetchNotificationSettings = () =>
  cachedGet("/notifications/settings", 30000);

export const updateNotificationSettings = (data: {
  bark_configs?: { id: string; name: string; key: string; enabled: boolean }[];
  bark_enabled?: boolean;
}) => { invalidateCache("/notifications"); return apiCall(api.put("/notifications/settings", data)); };

export const testBarkNotification = (barkKey: string) =>
  apiCall(api.post("/notifications/test", { bark_key: barkKey }));

// ==================== 回测 ====================

export const deleteBatchBacktest = (batchId: string) => {
  invalidateCache("/backtests");
  invalidateCache("/strategies");
  return apiCall(api.delete(`/backtests/batch/${batchId}`));
};

export const fetchBacktestStatus = (strategyId: string | number) =>
  cachedGet<{ running: boolean; current_symbol: string | null; completed: number; total: number }>(
    `/strategies/${strategyId}/backtest/status`, 2000
  );
