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
| `buy` | 开多头仓 | 若当前持空仓 → 先自动平空（100% 平仓），再开多 |
| `sell` | 平多头仓 | 若无多仓 → 跳过（`hold`） |
| `short` | 开空头仓 | 若当前持多仓 → 先自动平多（100% 平仓），再开空 |
| `cover` | 平空头仓 | 若无空仓 → 跳过（`hold`，signal_detail="无空仓，跳过平空"） |

**自动翻仓规则：**
- `buy()` 内部检测到空仓时，直接调用 `simulator.execute_cover(..., cover_size_pct=100.0)` 全额平空，不经过 `ctx.cover()`（避免 `sell_size_pct` 部分平仓语义干扰）
- `short()` 内部检测到多仓时，直接调用 `simulator.execute_sell(..., sell_size_pct=100.0)` 全额平多，不经过 `ctx.sell()`
- 自动翻仓产生的 TriggerLog 会被单独记录（`action="sell"` 或 `action="cover"`），随后开仓也产生一条 TriggerLog，`execute()` 返回的是**开仓那条** TriggerLog 用于通知

---

## 数据模型

**无需新增或修改表结构。** `Position.side` 字段已存在（`VARCHAR`），当前值为 `"long"`，扩展为支持 `"short"`。现有多头持仓继续显示 `side="long"`，无需迁移。

---

## `get_position()` 行为

`StrategyContext.get_position()` 的查询**不加 `side` 过滤**，返回当前策略任何方向的未平仓持仓（`closed_at IS NULL`）。调用方通过 `position.side` 判断方向：

- `_execute_visual_strategy` 通过 `position.side == "long"` / `"short"` 分支
- `buy()` / `short()` 中的自动翻仓检测也通过此方法获取当前持仓再判断 `side`
- 代码策略调用 `ctx.get_position()` 时，返回值的 `side` 属性现在可能为 `"short"`，策略代码可自行判断

---

## 保证金机制

做空与做多完全对称（`position_size` / `position_size_type` 参数语义相同）：

- **开空**：从账户余额扣除保证金 = `quantity × entry_price`
  - `position_size_type == "percent"`：`quantity = balance × position_size / 100.0 / price`
  - `position_size_type == "fixed"`：`quantity = position_size / price`
- **平空**：返还保证金 + PnL，其中 `PnL = (entry_price - close_price) × quantity`（价跌盈利）
- 若余额不足以支付保证金，跳过开空，记录 `action="hold"`，`signal_detail="余额不足，跳过开空"`

`execute_cover` **不接受** `cover_size_pct` 参数（始终全额平仓），与 `execute_sell` 的 `sell_size_pct` 不对称——做空暂不支持部分平仓，保持简单。

---

## 止盈止损扩展

`check_stop_loss_take_profit` 同时检查多头和空头持仓，触发条件方向取反：

| 方向 | 止损触发 | 止盈触发 |
|------|---------|---------|
| 多头 | 价格下跌 ≥ `stop_loss_pct` | 价格上涨 ≥ `take_profit_pct` |
| 空头 | 价格上涨 ≥ `stop_loss_pct` | 价格下跌 ≥ `take_profit_pct` |

空头止盈止损触发时调用 `execute_cover`，随后**复用现有 double-commit 模式**（与多头一致）：

```python
trigger = await self.execute_cover(strategy_id, symbol, current_price, db, user_id=user_id)
trigger.signal_detail = f"[止损] {trigger.signal_detail}"
await db.commit()   # execute_cover 内部已 commit 一次，此处再 commit signal_detail 修改
return trigger
```

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
    - 若余额不足：记录 TriggerLog(action="hold", signal_detail="余额不足，跳过开空")，commit，return
    - 扣除保证金 = quantity × price
    - 创建 side="short" Position
    - 记录 TriggerLog(signal_type="short", action="short",
                      signal_detail="开空 {quantity} {symbol} @ {price}")
    - commit，return trigger
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
    user_id: Optional[int] = None,
) -> Optional[TriggerLog]:
    """
    执行模拟平空（始终全额平仓）
    - 查找 side="short" 且 closed_at IS NULL 的持仓
    - 若无持仓：记录 TriggerLog(action="hold", signal_detail="无空仓，跳过平空")，commit，return
    - PnL = (entry_price - close_price) × quantity
    - 返还保证金（entry_price × quantity）到余额，account.total_pnl += PnL
    - 关闭持仓：position.pnl = PnL, position.current_price = price, position.closed_at = now
    - 记录 TriggerLog(signal_type="cover", action="cover",
                      signal_detail="平空 {qty:.4f} {symbol} @ {price}, 盈亏: {pnl:.2f}")
    - commit，return trigger
    """
```

**修改 `check_stop_loss_take_profit`：**

在现有多头检查之后，新增空头检查：
```python
# 空头止损（价格上涨）
result = await db.execute(select(Position).where(..., side="short", closed_at IS NULL))
short_position = result.scalar_one_or_none()
if short_position:
    price_change_pct = (current_price - short_position.entry_price) / short_position.entry_price * 100
    if stop_loss_pct and price_change_pct >= stop_loss_pct:
        trigger = await self.execute_cover(strategy_id, symbol, current_price, db, user_id=user_id)
        trigger.signal_detail = f"[止损] {trigger.signal_detail}"
        await db.commit()
        return trigger
    if take_profit_pct and price_change_pct <= -take_profit_pct:
        trigger = await self.execute_cover(strategy_id, symbol, current_price, db, user_id=user_id)
        trigger.signal_detail = f"[止盈] {trigger.signal_detail}"
        await db.commit()
        return trigger
```

---

### `backend/app/engine/executor.py`

**`StrategyContext.get_position()` 修改：**

移除 `Position.side == "long"` 过滤，改为查询任意方向的未平仓持仓：

```python
async def get_position(self) -> Optional[Position]:
    result = await self.db.execute(
        select(Position).where(
            Position.strategy_id == self.strategy.id,
            Position.symbol == self.strategy.symbol,
            Position.closed_at.is_(None),
        )
    )
    return result.scalar_one_or_none()
```

**`StrategyContext.buy()` 扩展（自动翻仓）：**

```python
async def buy(self, quantity=None):
    # 自动翻仓：若持有空仓，先全额平空
    # 使用 self.current_kline["close"] 作为翻仓价格（与本次 tick 开多价格一致，避免二次 IO）
    position = await self.get_position()
    if position and position.side == "short":
        flip_price = self.current_kline["close"] if self.current_kline else (await self.get_klines(limit=1))[-1]["close"]
        await simulator.execute_cover(   # 返回值有意丢弃（TriggerLog 已 commit 到 DB）
            strategy_id=self.strategy.id,
            symbol=self.strategy.symbol,
            price=flip_price,
            db=self.db,
            user_id=getattr(self.strategy, "user_id", None),
        )
    # 原有开多逻辑不变 ...
```

**`StrategyContext` 新增 `short()` 和 `cover()`：**

```python
async def short(self, quantity: Optional[float] = None) -> Optional[TriggerLog]:
    """
    开空：
    1. 自动翻仓：若持有多仓，先调用 simulator.execute_sell(..., sell_size_pct=100.0) 全额平多
       - 翻仓价格使用 self.current_kline["close"]（与本次 tick 一致，避免二次 IO）
       - execute_sell 返回值有意丢弃（TriggerLog 已 commit 到 DB）
    2. 计算数量（与 buy 逻辑对称，使用 position_size / position_size_type）
    3. 调用 simulator.execute_short
    """

async def cover(self, quantity: Optional[float] = None) -> Optional[TriggerLog]:
    """平空：直接调用 simulator.execute_cover（全额）"""
```

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

`_execute_visual_strategy` 扩展逻辑（替换现有方法体）：

```
position = await ctx.get_position()

if position is None:
    # 无持仓：先检查 buy，再检查 short（两者均为真时 buy 优先）
    if _check_conditions(buy_conditions, calculator):
        return "buy"
    if short_conditions and _check_conditions(short_conditions, calculator):
        return "short"
    return None

if position.side == "long":
    # 持多仓：检查卖出条件
    if _check_conditions(sell_conditions, calculator):
        return "sell"
    return None

if position.side == "short":
    # 持空仓：检查平空条件（未配置则返回 None，依赖止盈止损）
    if cover_conditions and _check_conditions(cover_conditions, calculator):
        return "cover"
    return None
```

优先级：止盈止损（executor 外层先执行）> 平仓信号 > 开仓信号。

---

### `backend/app/schemas.py`

`TriggerLog` 相关 schema 的 `signal_type` / `action` 字段当前为字符串类型，无需修改。

---

## 前端改动

### 视觉策略编辑器

在现有「买入条件」/「卖出条件」区块下方，新增两个**可选折叠区块**：

- **「开空条件」**：与买入条件使用相同的条件构建器组件，折叠时显示「未配置（策略不做空）」
- **「平空条件」**：与卖出条件使用相同的条件构建器组件，折叠时显示「未配置（依赖止盈止损平空）」

`config_json` 扩展结构（两字段均为可选，不配置时不写入 JSON）：

```json
{
  "buy_conditions":   { "logic": "AND", "rules": [...] },
  "sell_conditions":  { "logic": "AND", "rules": [...] },
  "short_conditions": { "logic": "AND", "rules": [...] },
  "cover_conditions": { "logic": "AND", "rules": [...] }
}
```

### 持仓列表页面

- 新增「方向」列，显示徽章：多头绿色「多」，空头红色「空」
- 现有持仓 `side="long"` 直接显示「多」徽章，无需迁移

### 触发日志页面

- `signal_type="short"` 显示「开空」，`signal_type="cover"` 显示「平空」
- 现有 `signal_type="buy"` / `"sell"` 显示不变

---

## 不在范围内

- 杠杆（保证金倍数）
- 强制平仓（爆仓机制）
- 做空部分平仓（`cover` 始终全额平仓）
- 同一策略同时持有多头和空头仓（自动翻仓保证互斥）
- 回测引擎支持做空（回测是独立模块，本次不改）
