# 简化交易信号：从四路信号到买入/卖出

## 背景

当前系统有四种交易信号：`buy`（开多）、`sell`（平多）、`short`（开空）、`cover`（平空）。策略作者需要理解四种操作的语义，增加了认知负担。

实际上，只需要 **买入（buy）** 和 **卖出（sell）** 两种信号，系统根据当前持仓状态自动推断实际操作。例如，空仓时卖出就是开空——直观、好理解。

## 信号语义

| 当前持仓 | buy 信号 | sell 信号 |
|---------|----------|-----------|
| 空仓    | 开多（execute_buy）  | 开空（execute_short） |
| 持多    | hold（已持多，跳过）  | 平多（execute_sell）  |
| 持空    | 平空（execute_cover） | hold（已持空，跳过）  |

关键决策：**不自动翻仓**。持多时 sell 只平多，不会同时开空；持空时 buy 只平空，不会同时开多。

注意：当前代码中 `buy()` 和 `short()` 有自动翻仓逻辑（买入时若持空会先平空再开多）。本次改动**移除自动翻仓**，改为只执行对应方向的平仓操作。

## 改动范围

### 1. StrategyContext（executor.py）— 核心改动

改造 `buy()` 和 `sell()` 方法，加入持仓状态判断：

**buy()：**
- 查询当前持仓
- 空仓 → 调用 `simulator.execute_buy()`（开多）
- 持空 → 调用 `simulator.execute_cover()`（平空）
- 持多 → 记录 hold，返回 TriggerLog（signal_type="buy", action="hold"）

**sell()：**
- 查询当前持仓
- 空仓 → 调用 `simulator.execute_short()`（开空）
- 持多 → 调用 `simulator.execute_sell()`（平多）
- 持空 → 记录 hold，返回 TriggerLog（signal_type="sell", action="hold"）

删除 `short()` 和 `cover()` 公开方法。

### 2. Sandbox 信号验证（sandbox.py）

`call_on_tick()` 中的信号白名单从 `("buy", "sell", "short", "cover", "hold")` 改为 `("buy", "sell", "hold")`。策略返回 `"short"` 或 `"cover"` 时记录 warning 日志并返回 None。

### 3. Executor 信号路由（executor.py）

简化信号分发，从四路变两路：

```python
# 之前
if signal == "buy":
    trigger = await ctx.buy()
elif signal == "sell":
    trigger = await ctx.sell()
elif signal == "short":
    trigger = await ctx.short()
elif signal == "cover":
    trigger = await ctx.cover()

# 之后
if signal == "buy":
    trigger = await ctx.buy()
elif signal == "sell":
    trigger = await ctx.sell()
```

### 4. Simulator（simulator.py）— 不改

`execute_buy`、`execute_sell`、`execute_short`、`execute_cover` 四个方法保留不动。它们是底层原子操作，由 StrategyContext 根据持仓状态选择调用。

### 5. Visual Strategy（executor.py `_execute_visual_strategy`）

简化信号逻辑，不再需要单独的 `short_conditions` 和 `cover_conditions`：

- 空仓时：buy_conditions 满足 → `"buy"`（开多），sell_conditions 满足 → `"sell"`（开空）
- 持多时：sell_conditions 满足 → `"sell"`（平多）
- 持空时：buy_conditions 满足 → `"buy"`（平空）

已保存的策略配置中若存在 `short_conditions`/`cover_conditions` 字段，忽略即可（不读取）。无需数据迁移。

### 6. BacktestContext（backtester.py）

当前 BacktestContext 只有 buy/sell 且只处理多头。需要加入同样的持仓判断逻辑：

**buy()：**
- 空仓 → 创建 long Position
- 持空 → 平空，盈亏公式：`(entry_price - current_price) * quantity`，归还保证金 `entry_price * quantity`
- 持多 → 返回 False

**sell()：**
- 空仓 → 创建 short Position，锁定保证金 `quantity * price`
- 持多 → 平多（现有逻辑），盈亏公式：`(current_price - entry_price) * quantity`
- 持空 → 返回 False

**止盈止损 `_check_stop_loss_take_profit`：**
- 持多 + 触发 → `ctx.sell()`（平多）
- 持空 + 触发 → `ctx.buy()`（平空）
- 空头止损：价格上涨超过阈值（`price_change_pct >= stop_loss_pct`）
- 空头止盈：价格下跌超过阈值（`price_change_pct <= -take_profit_pct`）

**回测结束强制平仓：**
- 多头：`pnl = (price - entry_price) * quantity`，归还 `price * quantity`
- 空头：`pnl = (entry_price - price) * quantity`，归还 `entry_price * quantity + pnl`

**资金曲线（equity curve）：**
- 多头持仓市值：`quantity * current_price`
- 空头持仓市值：`entry_price * quantity + (entry_price - current_price) * quantity`（即保证金 + 浮动盈亏）

**持仓时长统计 `_calculate_avg_hold_time`：**
- 当前只配对 buy→sell，需扩展支持 short→cover 配对

### 7. Feishu 通知（feishu.py）— 不改

action 标签映射保留（buy=买入, sell=卖出, short=开空, cover=平空）。TriggerLog 的 `action` 字段仍由 simulator 底层写入具体操作类型。

### 8. 前端 / Schema — 不改

`signal_type` 字段：策略发出的信号，只有 `buy` 或 `sell`。
`action` 字段：实际执行的操作，仍保留 buy/sell/short/cover/hold 五种值。

前端展示无需改动，因为它基于 `action` 字段显示。

### 9. BaseStrategy（base_strategy.py）

`on_tick` 文档字符串已经只提到 `"buy"` 和 `"sell"`，无需修改。

### 10. 测试

- 更新 `test_executor_short.py`：去掉直接调用 `ctx.short()` / `ctx.cover()` 的测试，改为通过 `ctx.sell()`（空仓时开空）和 `ctx.buy()`（持空时平空）测试
- 更新 `test_simulator_short.py`：simulator 层不变，测试应保持原样
- 新增 BacktestContext 空头回测测试（开空、平空、空头止盈止损、空头资金曲线）

### 11. 策略文档（docs/strategies.md）

更新策略编写指南，说明只需返回 `"buy"` 或 `"sell"`，系统自动根据持仓判断操作。
