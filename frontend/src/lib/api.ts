/**
 * API 客户端
 */

import axios, { AxiosResponse } from "axios";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "";

const api = axios.create({
  baseURL: `${API_BASE_URL}/api`,
  headers: {
    "Content-Type": "application/json",
  },
});

// 响应拦截器
api.interceptors.response.use(
  (response: AxiosResponse) => response.data,
  (error) => {
    console.error("API Error:", error.response?.data || error.message);
    return Promise.reject(error);
  }
);

// Helper function to handle API calls
async function apiCall<T>(promise: Promise<any>): Promise<T> {
  const result = await promise;
  return result as T;
}

// ==================== 仪表盘 ====================

export const fetchDashboard = () => apiCall(api.get("/dashboard"));

// ==================== 大盘行情 ====================

export const fetchSymbols = (q: string = "") =>
  apiCall<string[]>(api.get("/market/symbols", { params: { q } }));

export const fetchMarketKlines = (symbol: string, timeframe: string, limit = 1000) =>
  apiCall(api.get("/market/klines", { params: { symbol, timeframe, limit } }));

export const fetchTicker = (symbol: string) =>
  apiCall(api.get("/market/ticker", { params: { symbol } }));

// ==================== 系统设置 ====================

export const fetchSettings = () => apiCall(api.get("/settings"));

export const updateSettings = (data: {
  data_source: string;
  cryptocompare_api_key?: string;
}) => apiCall(api.put("/settings", data));

export const testConnection = (data: {
  data_source: string;
  api_key?: string;
}) => apiCall(api.post("/settings/test", data));

// ==================== 策略 ====================

export const fetchStrategies = (params?: { status?: string; page?: number; page_size?: number }) =>
  apiCall(api.get("/strategies", { params }));

export const fetchStrategy = (id: string | number) =>
  apiCall(api.get(`/strategies/${id}`));

export const createStrategy = (data: any) =>
  apiCall(api.post("/strategies", data));

export const updateStrategy = (id: string | number, data: any) =>
  apiCall(api.put(`/strategies/${id}`, data));

export const deleteStrategy = (id: string | number) =>
  apiCall(api.delete(`/strategies/${id}`));

export const startStrategy = (id: string | number) =>
  apiCall(api.post(`/strategies/${id}/start`));

export const stopStrategy = (id: string | number) =>
  apiCall(api.post(`/strategies/${id}/stop`));

// ==================== 触发日志 ====================

export const fetchTriggers = (params?: { strategy_id?: number; page?: number; page_size?: number }) =>
  apiCall(api.get("/triggers", { params }));

// ==================== 账户和持仓 ====================

export const fetchAccount = () => apiCall(api.get("/account"));

export const resetAccount = () => apiCall(api.post("/account/reset"));

export const fetchPositions = (params?: { strategy_id?: number }) =>
  apiCall(api.get("/positions", { params }));
