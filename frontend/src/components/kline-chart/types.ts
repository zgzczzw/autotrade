/**
 * K线图模块类型定义
 */

// K线数据格式
export interface KlineData {
  timestamp: number;      // Unix毫秒时间戳
  open: number;           // 开盘价
  high: number;           // 最高价
  low: number;            // 最低价
  close: number;          // 收盘价
  volume: number;         // 成交量
}

// 交易标记
export interface TradeMarker {
  timestamp: number;      // 时间戳
  price: number;          // 价格
  side: 'buy' | 'sell';   // 买入/卖出
  quantity?: number;      // 数量
  pnl?: number;           // 盈亏
}

// 指标配置
export interface IndicatorsConfig {
  ma?: boolean | number[];    // MA周期，默认[5,10,20,60]
  macd?: boolean;             // MACD开关
  kdj?: boolean;              // KDJ开关
  rsi?: boolean;              // RSI开关
  boll?: boolean;             // BOLL开关
  volume?: boolean;           // 成交量开关，默认true
}

// 组件Props
export interface KlineChartModuleProps {
  // 基础数据
  data: KlineData[];
  
  // 标记数据（买卖点）
  markers?: TradeMarker[];
  
  // 指标配置
  indicators?: IndicatorsConfig;
  
  // 样式配置
  theme?: 'dark' | 'light';
  height?: number;
  
  // 标题
  title?: string;
  
  // 副标题（交易对/时间周期）
  subtitle?: string;

  // 聚焦到指定时间戳（毫秒），变化时图表自动滚动到该位置
  focusTimestamp?: number;

  // 受控时间周期（由父组件管理）
  activePeriod?: string;
  // 时间周期变化回调（提供时切换器为受控模式，父组件负责拉取新数据）
  onPeriodChange?: (period: string) => void;
  // 隐藏内置时间周期切换器（回测等数据预加载场景）
  hidePeriodSelector?: boolean;
}

// 时间周期（全局统一）
export type TimePeriod = '1m' | '15m' | '1h' | '4h' | '1d';
