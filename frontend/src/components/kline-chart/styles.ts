/**
 * K线图模块样式配置
 */

// 深色主题配置
export const darkTheme = {
  // 背景色
  backgroundColor: '#0f172a',
  
  // 网格线
  grid: {
    horizontal: {
      color: '#1e293b',
      style: 'dashed',
    },
    vertical: {
      color: '#1e293b',
      style: 'dashed',
    },
  },
  
  // 蜡烛图
  candle: {
    upColor: '#22c55e',      // 涨 - 绿色
    downColor: '#ef4444',    // 跌 - 红色
    upBorderColor: '#22c55e',
    downBorderColor: '#ef4444',
    upWickColor: '#22c55e',
    downWickColor: '#ef4444',
  },
  
  // 指标颜色
  indicator: {
    // MA
    ma5: '#f59e0b',    // amber
    ma10: '#3b82f6',   // blue
    ma20: '#8b5cf6',   // violet
    ma60: '#ec4899',   // pink
    
    // MACD
    macdFast: '#3b82f6',
    macdSlow: '#f59e0b',
    macdDiff: '#22c55e',
    macdDea: '#ef4444',
    
    // KDJ
    k: '#3b82f6',
    d: '#f59e0b',
    j: '#ef4444',
    
    // RSI
    rsi: '#8b5cf6',
    
    // BOLL
    bollUpper: '#f59e0b',
    bollMiddle: '#3b82f6',
    bollLower: '#f59e0b',
  },
  
  // 文字颜色
  textColor: '#94a3b8',
  
  // 十字光标
  crosshair: {
    horizontal: {
      color: '#64748b',
      style: 'dashed',
    },
    vertical: {
      color: '#64748b',
      style: 'dashed',
    },
    text: {
      backgroundColor: '#1e293b',
      color: '#e2e8f0',
    },
  },
  
  // 标记
  marker: {
    buy: '#3b82f6',
    sell: '#f59e0b',
  },
};

// 浅色主题配置
export const lightTheme = {
  backgroundColor: '#ffffff',
  grid: {
    horizontal: {
      color: '#e2e8f0',
      style: 'dashed',
    },
    vertical: {
      color: '#e2e8f0',
      style: 'dashed',
    },
  },
  candle: {
    upColor: '#ef4444',      // 涨 - 红色
    downColor: '#22c55e',    // 跌 - 绿色
    upBorderColor: '#ef4444',
    downBorderColor: '#22c55e',
    upWickColor: '#ef4444',
    downWickColor: '#22c55e',
  },
  indicator: {
    ma5: '#f59e0b',
    ma10: '#3b82f6',
    ma20: '#8b5cf6',
    ma60: '#ec4899',
    macdFast: '#3b82f6',
    macdSlow: '#f59e0b',
    macdDiff: '#22c55e',
    macdDea: '#ef4444',
    k: '#3b82f6',
    d: '#f59e0b',
    j: '#ef4444',
    rsi: '#8b5cf6',
    bollUpper: '#f59e0b',
    bollMiddle: '#3b82f6',
    bollLower: '#f59e0b',
  },
  textColor: '#475569',
  crosshair: {
    horizontal: {
      color: '#94a3b8',
      style: 'dashed',
    },
    vertical: {
      color: '#94a3b8',
      style: 'dashed',
    },
    text: {
      backgroundColor: '#f1f5f9',
      color: '#1e293b',
    },
  },
  marker: {
    buy: '#3b82f6',
    sell: '#f59e0b',
  },
};

// 获取主题配置
export function getThemeConfig(theme: 'dark' | 'light' = 'dark') {
  return theme === 'dark' ? darkTheme : lightTheme;
}
