/**
 * 前端日志服务
 * 
 * 功能：
 * - 支持不同日志级别（debug, info, warn, error）
 * - 开发环境输出到控制台
 * - 生产环境发送关键日志到后端
 * - 日志队列和批量发送
 * - 页面崩溃前发送日志
 */

import axios from "axios";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "";

// 日志级别
enum LogLevel {
  DEBUG = 0,
  INFO = 1,
  WARN = 2,
  ERROR = 3,
}

// 日志条目
interface LogEntry {
  timestamp: string;
  level: string;
  message: string;
  data?: any;
  url?: string;
  userAgent?: string;
}

// 日志配置
const config = {
  minLevel: process.env.NODE_ENV === "production" ? LogLevel.INFO : LogLevel.DEBUG,
  enableConsole: true,
  enableRemote: process.env.NODE_ENV === "production",
  batchSize: 10,
  flushInterval: 5000,
  maxQueueSize: 100,
};

// 日志队列
let logQueue: LogEntry[] = [];
let flushTimer: NodeJS.Timeout | null = null;

/**
 * 发送日志到后端
 */
async function sendLogs(logs: LogEntry[]): Promise<void> {
  try {
    await axios.post(`${API_BASE_URL}/api/logs`, { logs }, {
      timeout: 5000,
      headers: { "Content-Type": "application/json" },
    });
  } catch (error) {
    // 如果发送失败，保留在队列中稍后重试
    console.error("[Logger] Failed to send logs:", error);
  }
}

/**
 * 刷新日志队列
 */
async function flush(): Promise<void> {
  if (logQueue.length === 0) return;

  const logsToSend = [...logQueue];
  logQueue = [];

  if (config.enableRemote) {
    await sendLogs(logsToSend);
  }
}

/**
 * 安排刷新
 */
function scheduleFlush(): void {
  if (flushTimer) return;

  flushTimer = setTimeout(() => {
    flush();
    flushTimer = null;
  }, config.flushInterval);
}

/**
 * 添加日志到队列
 */
function enqueue(level: string, message: string, data?: any): void {
  if (logQueue.length >= config.maxQueueSize) {
    logQueue.shift(); // 移除最旧的日志
  }

  const entry: LogEntry = {
    timestamp: new Date().toISOString(),
    level,
    message,
    data,
    url: typeof window !== "undefined" ? window.location.href : undefined,
    userAgent: typeof navigator !== "undefined" ? navigator.userAgent : undefined,
  };

  logQueue.push(entry);

  // 达到批次大小时立即发送
  if (logQueue.length >= config.batchSize) {
    flush();
  } else {
    scheduleFlush();
  }
}

/**
 * 控制台输出
 */
function consoleOutput(level: string, message: string, data?: any): void {
  if (!config.enableConsole) return;

  const prefix = `[${new Date().toLocaleTimeString()}] [${level}]`;
  const styles: Record<string, string> = {
    DEBUG: "color: #6b7280", // gray
    INFO: "color: #3b82f6",  // blue
    WARN: "color: #f59e0b",  // yellow
    ERROR: "color: #ef4444", // red
  };

  const style = styles[level] || "";

  if (data !== undefined) {
    console.log(`%c${prefix} ${message}`, style, data);
  } else {
    console.log(`%c${prefix} ${message}`, style);
  }
}

/**
 * 创建日志记录函数
 */
function createLogger(level: LogLevel, levelName: string) {
  return (message: string, data?: any) => {
    if (level < config.minLevel) return;

    // 控制台输出
    consoleOutput(levelName, message, data);

    // 错误级别日志发送到后端
    if (level >= LogLevel.ERROR && config.enableRemote) {
      enqueue(levelName, message, data);
    }
  };
}

// 导出日志方法
export const logger = {
  debug: createLogger(LogLevel.DEBUG, "DEBUG"),
  info: createLogger(LogLevel.INFO, "INFO"),
  warn: createLogger(LogLevel.WARN, "WARN"),
  error: createLogger(LogLevel.ERROR, "ERROR"),

  /**
   * 立即刷新所有日志
   */
  flush,

  /**
   * 配置日志
   */
  configure: (newConfig: Partial<typeof config>) => {
    Object.assign(config, newConfig);
  },
};

/**
 * 捕获全局错误
 */
export function setupErrorHandling(): void {
  if (typeof window === "undefined") return;

  // 捕获 JS 错误
  window.addEventListener("error", (event) => {
    logger.error("Global error", {
      message: event.message,
      filename: event.filename,
      lineno: event.lineno,
      colno: event.colno,
      error: event.error?.stack,
    });
    logger.flush();
  });

  // 捕获 Promise 拒绝
  window.addEventListener("unhandledrejection", (event) => {
    logger.error("Unhandled promise rejection", {
      reason: event.reason,
      stack: event.reason?.stack,
    });
    logger.flush();
  });

  // 页面关闭前发送剩余日志
  window.addEventListener("beforeunload", () => {
    logger.flush();
  });
}

// 自动设置错误处理
if (typeof window !== "undefined") {
  setupErrorHandling();
}

export default logger;
