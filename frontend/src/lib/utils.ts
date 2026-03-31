import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

/**
 * 格式化交易对显示
 * BTCUSDT -> BTC/USDT
 */
export function formatSymbol(symbol: string): string {
  return symbol.replace(/USDT$/, "/USDT");
}

/**
 * 提取基础币种
 * BTCUSDT -> BTC, ETHUSDT -> ETH
 */
export function baseAsset(symbol: string): string {
  return symbol.replace(/USDT$/, "");
}

/**
 * 格式化价格
 */
export function formatPrice(price: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(price);
}

/**
 * 格式化百分比
 */
export function formatPercent(value: number): string {
  return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
}

const TZ_KEY = "app_timezone";
const TZ_DEFAULT = "Asia/Shanghai";

export function getTimezone(): string {
  if (typeof window === "undefined") return TZ_DEFAULT;
  return localStorage.getItem(TZ_KEY) || TZ_DEFAULT;
}

export function setTimezone(tz: string): void {
  if (typeof window !== "undefined") localStorage.setItem(TZ_KEY, tz);
}

/** 将后端返回的 naive UTC 时间字符串解析为 UTC 毫秒时间戳 */
export function parseUTCTimestamp(dateStr: string): number {
  const utcStr = /[Z+\-]\d{0,2}:?\d{0,2}$/.test(dateStr) ? dateStr : dateStr + "Z";
  return new Date(utcStr).getTime();
}

export function formatDateTime(dateStr: string): string {
  // Backend returns naive UTC strings without timezone indicator.
  // Append 'Z' so JavaScript parses them as UTC instead of local time.
  const utcStr = /[Z+\-]\d{2}:?\d{2}$/.test(dateStr) ? dateStr : dateStr + "Z";
  return new Date(utcStr).toLocaleString("zh-CN", {
    timeZone: getTimezone(),
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}
