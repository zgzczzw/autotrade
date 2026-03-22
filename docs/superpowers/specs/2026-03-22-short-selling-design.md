# 做空功能设计文档

**日期：** 2026-03-22
**状态：** 已批准

---

## 背景与目标

AutoTrade 目前只支持做多模拟交易（`buy` 开多、`sell` 平多）。目标是扩展为支持双向交易，同一策略可以做多也可以做空，并支持自动翻仓。

---

## 信号系统

新增 4 信号语义（与现有 `buy`/`sell` 并存，均为字符串返回值）：

| 信号 | 含义 | 自动翻仓 |
|------|------|---------|
| `buy` | 开多头仓 | 若当前持空仓 → 先自动平空（`cover`），再开多 |
| `sell` | 平多头仓 | 若无多仓 → 跳过（`hold`） |
| `short` | 开空头仓 | 若当前持多仓 → 先自动平多（`sell`），再开空 |
| `cover` | 平空头仓 | 若无空仓 → 跳过（`hold`） |

自动翻仓逻辑封装在 `StrategyContext.buy()` / `StrategyContext.short()` 内部，对策略代码和视觉策略透明。

---

## 数据模型

**无需新增或修改表结构。** `Position.side` 字段已存在（`VARCHAR`），当前值为 `"long"`，扩展为支持 `"short"`。

---

## 保证金机制

做空与做多完全对称：

- **开空**：从账户余额扣除保证金 = `quantity × entry_price`
- **平空**：返还保证金 + PnL，其中 `PnL = (entry_price - close_price) × quantity`（价跌盈利）
- 若余额不足以支付保证金，跳过开空，记录 `action="hold"`，`signal_detail="余额不足，跳过开空"`

---

## 止盈止损扩展

`check_stop_loss_take_profit` 同时检查多头和空头持仓，触发条件方向取反：

| 方向 | 止损触发 | 止盈触发 |
|------|---------|---------|
| 多头 | 价格下跌 ≥ `stop_loss_pct` | 价格上涨 ≥ `take_profit_pct` |
| 空头 | 价格上涨 ≥ `stop_loss_pct` | 价格下跌 ≥ `take_profit_pct` |

止损触发调用 `execute_cover`，`signal_detail` 前缀 `[止损]`；止盈同理前缀 `[止盈]`。

---

## 后端改动

### `backend/app/services/simulator.py`

**新增 `execute_short`：**

```python
async def execute_short(
    self,
    strategy_id: int,
    symbol: str,
    quantity: float,
    price: float,
    db: AsyncSession,
    user_id: Optional[int] = None,
) -> Optional[TriggerLog]:
    """
    执行模拟开空
    - 扣除保证金 = quantity × price
    - 创建 side="short" Position
    - 记录 TriggerLog(signal_type="short", action="short")
    """
```

**新增 `execute_cover`：**

```python
async def execute_cover(
    self,
    strategy_id: int,
    symbol: str,
    price: float,
    db: AsyncSession,
    cover_size_pct: float = 100.0,
    user_id: Optional[int] = None,
) -> Optional[TriggerLog]:
    """
    执行模拟平空
    - 查找 side="short" 未平仓持仓
    - PnL = (entry_price - close_price) × quantity
    - 返还保证金 + PnL
    - 记录 TriggerLog(signal_type="cover", action="cover")
    """
```

**修改 `check_stop_loss_take_profit`：**
- 查询多头仓（现有逻辑不变）
- 新增查询空头仓，触发条件取反，调用 `execute_cover`

---

### `backend/app/engine/executor.py`

**`StrategyContext` 新增两个方法：**

```python
async def short(self, quantity: Optional[float] = None) -> Optional[TriggerLog]:
    """
    开空：
    1. 若当前有多头仓 → 先调用 execute_sell 平多（自动翻仓）
    2. 计算数量（与 buy 逻辑对称）
    3. 调用 execute_short
    """

async def cover(self, quantity: Optional[float] = None) -> Optional[TriggerLog]:
    """
    平空：直接调用 execute_cover
    """
```

`buy()` 方法新增翻仓前置：若有空头仓 → 先调用 `execute_cover` 平空，再开多。

**`execute()` 信号路由扩展：**

```python
if signal == "buy":
    trigger = await ctx.buy()
elif signal == "sell":
    trigger = await ctx.sell()
elif signal == "short":
    trigger = await ctx.short()
elif signal == "cover":
    trigger = await ctx.cover()
```

---

### `backend/app/engine/executor.py` — 视觉策略逻辑

`_execute_visual_strategy` 扩展：

```
当前无持仓：
  检查 buy_conditions  → 返回 "buy"
  检查 short_conditions（若配置） → 返回 "short"

当前持多仓：
  检查 sell_conditions → 返回 "sell"

当前持空仓：
  检查 cover_conditions（若配置） → 返回 "cover"
```

优先级：止盈止损（在 executor 外层） > 平仓信号 > 开仓信号。

---

### `backend/app/schemas.py`

`TriggerLog` 相关 schema 的 `signal_type` / `action` 枚举扩展为包含 `"short"` / `"cover"`（当前为字符串类型，无需修改）。

---

## 前端改动

### 视觉策略编辑器

在现有「买入条件」/「卖出条件」区块下方，新增两个**可选折叠区块**：

- **「开空条件」**：与买入条件使用相同的条件构建器组件，折叠时显示「未配置（策略不做空）」
- **「平空条件」**：与卖出条件使用相同的条件构建器组件，折叠时显示「未配置（依赖止盈止损平空）」

`config_json` 扩展结构（两字段均为可选）：

```json
{
  "buy_conditions":   { "logic": "AND", "rules": [...] },
  "sell_conditions":  { "logic": "AND", "rules": [...] },
  "short_conditions": { "logic": "AND", "rules": [...] },
  "cover_conditions": { "logic": "AND", "rules": [...] }
}
```

### 持仓/日志页面

- 持仓列表新增「方向」列，显示「多」/ 「空」徽章（区分颜色：多头绿色，空头红色）
- 触发日志中 `signal_type="short"` 显示「开空」，`"cover"` 显示「平空」

---

## 不在范围内

- 杠杆（保证金倍数）
- 强制平仓（爆仓机制）
- 同一策略同时持有多头和空头仓（自动翻仓保证互斥）
- 回测引擎支持做空（回测是独立模块，本次不改）
