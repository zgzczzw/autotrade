// 指标类型
export type IndicatorKey =
  | "RSI"
  | "MA_CROSS"
  | "BOLL"
  | "MACD"
  | "KDJ"
  | "VOLUME"
  | "PRICE_CHANGE"
  | "PRICE";

// 运算符
export type Operator = "<" | ">" | "<=" | ">=" | "==";

// 单条件规则
export interface ConditionRule {
  type: "rule";
  indicator: IndicatorKey;
  params: Record<string, number>;
  operator?: Operator;    // 数值类指标用
  value: string | number; // 枚举类指标用字符串，数值类用 number
}

// 条件组（支持递归嵌套）
export interface ConditionGroup {
  type: "group";
  logic: "AND" | "OR";
  rules: Array<ConditionRule | ConditionGroup>;
}

// 策略完整配置
export interface StrategyConfig {
  buy_conditions: ConditionGroup;
  sell_conditions: ConditionGroup;
  short_conditions?: ConditionGroup;  // 可选，不配置则不做空
  cover_conditions?: ConditionGroup;  // 可选，不配置则依赖止盈止损
}

// 每种指标的元信息
export interface IndicatorDef {
  key: IndicatorKey;
  label: string;
  kind: "numeric" | "enum";   // numeric = 数值比较，enum = 固定枚举值
  defaultParams: Record<string, number>;
  paramDefs: Array<{ key: string; label: string; min?: number; max?: number }>;
  operators?: Operator[];     // kind=numeric 时有效
  enumValues?: Array<{ value: string; label: string }>; // kind=enum 时有效
  defaultValue: string | number;
}

export const INDICATOR_DEFS: IndicatorDef[] = [
  {
    key: "RSI",
    label: "RSI",
    kind: "numeric",
    defaultParams: { period: 14 },
    paramDefs: [{ key: "period", label: "周期", min: 2, max: 100 }],
    operators: ["<", ">", "<=", ">=", "=="],
    defaultValue: 30,
  },
  {
    key: "MA_CROSS",
    label: "MA 均线交叉",
    kind: "enum",
    defaultParams: { fast: 5, slow: 20 },
    paramDefs: [
      { key: "fast", label: "快线", min: 1, max: 200 },
      { key: "slow", label: "慢线", min: 2, max: 500 },
    ],
    enumValues: [
      { value: "golden", label: "金叉（快线上穿慢线）" },
      { value: "death", label: "死叉（快线下穿慢线）" },
    ],
    defaultValue: "golden",
  },
  {
    key: "BOLL",
    label: "布林带",
    kind: "enum",
    defaultParams: { period: 20, std_dev: 2 },
    paramDefs: [
      { key: "period", label: "周期", min: 2, max: 200 },
      { key: "std_dev", label: "标准差", min: 1, max: 5 },
    ],
    enumValues: [
      { value: "above_upper", label: "突破上轨" },
      { value: "below_lower", label: "跌破下轨" },
    ],
    defaultValue: "below_lower",
  },
  {
    key: "MACD",
    label: "MACD",
    kind: "enum",
    defaultParams: { fast: 12, slow: 26, signal: 9 },
    paramDefs: [
      { key: "fast", label: "快线", min: 1, max: 100 },
      { key: "slow", label: "慢线", min: 2, max: 200 },
      { key: "signal", label: "信号线", min: 1, max: 50 },
    ],
    enumValues: [
      { value: "golden", label: "金叉（MACD上穿信号线）" },
      { value: "death", label: "死叉（MACD下穿信号线）" },
      { value: "above_zero", label: "柱状图 > 0" },
      { value: "below_zero", label: "柱状图 < 0" },
    ],
    defaultValue: "golden",
  },
  {
    key: "KDJ",
    label: "KDJ",
    kind: "enum",
    defaultParams: { period: 9 },
    paramDefs: [{ key: "period", label: "周期", min: 2, max: 100 }],
    enumValues: [
      { value: "k_cross_up", label: "K 上穿 D（金叉）" },
      { value: "k_cross_down", label: "K 下穿 D（死叉）" },
      { value: "overbought", label: "超买（K > 80）" },
      { value: "oversold", label: "超卖（K < 20）" },
    ],
    defaultValue: "k_cross_up",
  },
  {
    key: "VOLUME",
    label: "成交量",
    kind: "numeric",
    defaultParams: { ma_period: 20 },
    paramDefs: [{ key: "ma_period", label: "均量周期", min: 2, max: 200 }],
    operators: [">", "<"],
    defaultValue: 1.5,
  },
  {
    key: "PRICE_CHANGE",
    label: "价格涨跌幅 (%)",
    kind: "numeric",
    defaultParams: {},
    paramDefs: [],
    operators: [">", "<", ">=", "<="],
    defaultValue: 3,
  },
  {
    key: "PRICE",
    label: "价格绝对值",
    kind: "numeric",
    defaultParams: {},
    paramDefs: [],
    operators: [">", "<", ">=", "<=", "=="],
    defaultValue: 0,
  },
];

export function getIndicatorDef(key: IndicatorKey): IndicatorDef {
  return INDICATOR_DEFS.find((d) => d.key === key)!;
}

export function makeEmptyRule(): ConditionRule {
  const def = INDICATOR_DEFS[0];
  return {
    type: "rule",
    indicator: def.key,
    params: { ...def.defaultParams },
    operator: def.operators?.[0],
    value: def.defaultValue,
  };
}

export function makeEmptyGroup(): ConditionGroup {
  return {
    type: "group",
    logic: "AND",
    rules: [makeEmptyRule()],
  };
}

export function makeEmptyConfig(): StrategyConfig {
  return {
    buy_conditions: makeEmptyGroup(),
    sell_conditions: makeEmptyGroup(),
  };
}
