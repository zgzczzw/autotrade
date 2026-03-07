# 策略可视化配置功能设计文档

**日期**：2026-03-07
**状态**：已审批

---

## 背景

创建策略页面的「可视化配置」Tab 当前为占位符，后端已有基础的 visual strategy 执行逻辑（支持 RSI、MA交叉、布林带）。本次设计将完整实现可视化条件编辑器，使非技术用户无需写代码即可配置交易策略。

---

## 设计目标

- 支持树形嵌套条件逻辑（最多 3 层），每层可选 AND / OR
- 支持 8 种指标/价格条件
- 保存后展示自然语言预览，帮助用户确认配置意图
- 与现有回测引擎、实盘执行器完全打通

---

## Config JSON 数据结构

节点分两种类型，支持递归嵌套：

```json
{
  "buy_conditions": {
    "type": "group",
    "logic": "AND",
    "rules": [
      {
        "type": "rule",
        "indicator": "RSI",
        "params": { "period": 14 },
        "operator": "<",
        "value": 30
      },
      {
        "type": "group",
        "logic": "OR",
        "rules": [
          {
            "type": "rule",
            "indicator": "MA_CROSS",
            "params": { "fast": 5, "slow": 20 },
            "value": "golden"
          },
          {
            "type": "rule",
            "indicator": "BOLL",
            "params": { "period": 20, "std_dev": 2 },
            "value": "below_lower"
          }
        ]
      }
    ]
  },
  "sell_conditions": {
    "type": "group",
    "logic": "OR",
    "rules": [
      {
        "type": "rule",
        "indicator": "RSI",
        "params": { "period": 14 },
        "operator": ">",
        "value": 70
      }
    ]
  }
}
```

**向下兼容**：旧格式（无 `type` 字段）由解析器自动识别为 group 节点处理。

---

## 支持的指标列表

| 指标 key | 显示名 | 参数 | 运算符/可选值 |
|----------|--------|------|---------------|
| `RSI` | RSI | period | `<` `>` `<=` `>=` `==` + 数值 |
| `MA_CROSS` | MA均线交叉 | fast, slow | `golden`（金叉）/ `death`（死叉）|
| `BOLL` | 布林带 | period, std_dev | `above_upper`（突破上轨）/ `below_lower`（突破下轨）|
| `MACD` | MACD | fast, slow, signal | `golden`（金叉）/ `death`（死叉）/ `above_zero`（柱>0）/ `below_zero`（柱<0）|
| `KDJ` | KDJ | period | `k_cross_up`（K上穿D）/ `k_cross_down`（K下穿D）/ `overbought`（>80）/ `oversold`（<20）|
| `VOLUME` | 成交量 | ma_period | `>` + N 倍均量（数值）|
| `PRICE_CHANGE` | 价格涨跌幅 | — | `>` `<` + 百分比数值 |
| `PRICE` | 价格绝对值 | — | `>` `<` `==` + 数值 |

---

## 前端组件结构

```
frontend/src/components/visual-strategy-editor/
├── index.ts                 # 统一导出
├── types.ts                 # ConditionGroup / ConditionRule / IndicatorDef 类型
├── condition-group.tsx      # 递归条件组（AND/OR 切换、添加条件、添加子组、删除）
├── condition-rule.tsx       # 单条件行（指标选择 → 参数配置 → 运算符 → 值）
├── strategy-preview.tsx     # 底部自然语言预览块
└── utils.ts                 # config 序列化/反序列化、generatePreviewText()
```

**集成点**：
- `frontend/src/app/strategies/new/page.tsx`：替换可视化 Tab 占位符
- `frontend/src/app/strategies/[id]/page.tsx`：编辑策略时回显配置

### UI 交互示意

```
买入条件  [全部满足 AND ▾]
├─ RSI(14)  [<]  [30]                              [×]
├─ 条件组  [任一满足 OR ▾]                          [×]
│  ├─ MA均线  快[5] 慢[20]  [金叉]                 [×]
│  └─ 布林带  [突破下轨]                            [×]
│  └─ [+ 添加条件]
└─ [+ 添加条件]  [+ 添加条件组]

卖出条件  [任一满足 OR ▾]
└─ RSI(14)  [>]  [70]                              [×]
└─ [+ 添加条件]  [+ 添加条件组]

─────────────────────────────────────────────────
预览：当 RSI(14) 小于 30，且满足以下任一条件：
  · MA(5) 上穿 MA(20)（金叉）
  · 价格跌破布林带下轨
时买入。

当 RSI(14) 大于 70 时卖出。
```

**约束**：
- 最多 3 层嵌套，超过后「添加条件组」按钮禁用
- 每组最多 10 条规则

---

## 后端改动

### `backend/app/engine/indicators.py`

新增函数：
- `calculate_macd(data, fast, slow, signal)` → `{"macd": float, "signal": float, "histogram": float}`
- `calculate_kdj(highs, lows, closes, period)` → `{"k": float, "d": float, "j": float}`
- `check_macd_cross(data, fast, slow, signal)` → `"golden" | "death" | "above_zero" | "below_zero" | None`
- `check_kdj_signal(highs, lows, closes, period)` → `"k_cross_up" | "k_cross_down" | "overbought" | "oversold" | None`
- `check_volume(volumes, ma_period, multiplier)` → `bool`

`IndicatorCalculator` 新增对应方法，并接收 `highs`、`lows`、`volumes` 数据。

### `backend/app/engine/backtester.py`

`_check_single_condition` 扩展：
- 支持 `type: "group"` 节点的递归解析（调用 `_check_conditions`）
- 新增 MACD、KDJ、VOLUME、PRICE_CHANGE、PRICE 指标处理分支

`BacktestContext.__init__` 中 `IndicatorCalculator` 传入完整 OHLCV 数据。

### `backend/app/engine/executor.py`

同步更新 `_execute_visual_strategy`，与 backtester 保持一致的条件解析逻辑（提取为共用函数避免重复）。

---

## 实施阶段

| 阶段 | 内容 |
|------|------|
| 1 | 前端类型定义 + utils（序列化/预览文本生成） |
| 2 | `condition-rule.tsx`（单条件行） |
| 3 | `condition-group.tsx`（递归条件组） |
| 4 | `strategy-preview.tsx` |
| 5 | 集成到 new/page.tsx 和 [id]/page.tsx |
| 6 | 后端 indicators.py 扩展 |
| 7 | 后端 backtester.py + executor.py 扩展 |
| 8 | 联调测试（创建策略 → 回测验证条件生效） |
