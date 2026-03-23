# TriggerLog 操作中文化 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Change TriggerLog action/signal_type from English (buy/sell/short/cover/hold) to Chinese (买入/卖出/观望), add `position_effect` field (开仓/平仓).

**Architecture:** Modify TriggerLog model to add `position_effect` column. Update all 4 simulator execute methods to use Chinese values. Update frontend badges and notifications to match. The `position_effect` column must be added via ALTER TABLE since `Base.metadata.create_all` does not add columns to existing tables.

**Tech Stack:** Python/SQLAlchemy (backend), React/TypeScript (frontend), pytest (tests)

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `backend/app/models.py` | Modify | Add `position_effect` column to TriggerLog |
| `backend/app/schemas.py` | Modify | Add `position_effect` to TriggerLogResponse |
| `backend/app/database.py` | Modify | Add ALTER TABLE to add `position_effect` column to existing tables |
| `backend/app/services/simulator.py` | Modify | Change all action/signal_type values to Chinese, add position_effect |
| `backend/app/engine/executor.py` | Modify | Change error TriggerLog to Chinese values |
| `backend/app/services/feishu.py` | Modify | Simplify notification mappings, add position_effect to notifications |
| `frontend/src/app/triggers/page.tsx` | Modify | Update getActionBadge for Chinese values |
| `frontend/src/app/strategies/[id]/page.tsx` | Modify | Update getActionBadge for Chinese values |
| `frontend/src/app/page.tsx` | Modify | Update dashboard action display |
| `backend/tests/test_simulator_short.py` | Modify | Update assertions to Chinese values, add position_effect assertions |
| `backend/tests/test_executor_short.py` | Modify | Update mock values to Chinese |

---

### Task 1: Model + Schema + DB Migration

**Files:**
- Modify: `backend/app/models.py:89` (add column after `action`)
- Modify: `backend/app/schemas.py:95` (add field after `action`)
- Modify: `backend/app/database.py:25` (add ALTER TABLE after create_all)

- [ ] **Step 1: Add `position_effect` to TriggerLog model**

In `backend/app/models.py`, add after line 89 (`action = Column(String, nullable=True)`):

```python
position_effect = Column(String, nullable=True)  # 开仓 / 平仓
```

- [ ] **Step 2: Add `position_effect` to TriggerLogResponse schema**

In `backend/app/schemas.py`, add after line 95 (`action: Optional[str] = None`):

```python
position_effect: Optional[str] = None
```

- [ ] **Step 3: Add ALTER TABLE to database.py**

`Base.metadata.create_all` does not add new columns to existing tables. Add column migration logic after `create_all` in `backend/app/database.py`. Find the `create_all` call (line 25) and add after it:

```python
# Add new columns to existing tables (create_all won't add columns to existing tables)
from sqlalchemy import text, inspect
inspector = inspect(conn)
trigger_columns = [c["name"] for c in inspector.get_columns("trigger_logs")]
if "position_effect" not in trigger_columns:
    conn.execute(text("ALTER TABLE trigger_logs ADD COLUMN position_effect VARCHAR"))
```

This code runs inside the existing `async with engine.begin() as conn:` block, within the `run_sync` callback. Read the file to understand the exact structure before editing.

- [ ] **Step 4: Verify import works**

Run: `cd /home/autotrade/autotrade/backend && python3 -c "from app.models import TriggerLog; print(TriggerLog.__table__.columns.keys())"`
Expected: output includes `position_effect`

- [ ] **Step 5: Commit**

```bash
git add backend/app/models.py backend/app/schemas.py backend/app/database.py
git commit -m "feat: add position_effect column to TriggerLog model, schema, and DB"
```

---

### Task 2: Simulator — Chinese values + position_effect

**Files:**
- Modify: `backend/app/services/simulator.py`
- Modify: `backend/tests/test_simulator_short.py`

- [ ] **Step 1: Update test assertions to expect Chinese values**

In `backend/tests/test_simulator_short.py`, update all assertions:

**test_execute_short_success** (line 64-65):
```python
# Before:
assert trigger.action == "short"
assert trigger.signal_type == "short"
# After:
assert trigger.action == "卖出"
assert trigger.signal_type == "卖出"
assert trigger.position_effect == "开仓"
```

**test_execute_short_insufficient_balance** (line 76):
```python
# Before:
assert trigger.action == "hold"
# After:
assert trigger.action == "观望"
assert trigger.signal_type == "卖出"
assert trigger.position_effect is None
```

**test_execute_cover_success** (line 122):
```python
# Before:
assert trigger.action == "cover"
# After:
assert trigger.action == "买入"
assert trigger.signal_type == "买入"
assert trigger.position_effect == "平仓"
```

Also add two new tests for execute_buy coverage:

```python
@pytest.mark.asyncio
async def test_execute_buy_success_chinese():
    """买入成功：action/signal_type 为中文，position_effect 为开仓"""
    from app.services.simulator import simulator

    account = make_account(balance=50000.0)
    db = make_db(account=account)

    trigger = await simulator.execute_buy(
        strategy_id=1,
        symbol="BTCUSDT",
        quantity=0.1,
        price=40000.0,
        db=db,
        user_id=1,
    )

    assert trigger.action == "买入"
    assert trigger.signal_type == "买入"
    assert trigger.position_effect == "开仓"


@pytest.mark.asyncio
async def test_execute_buy_insufficient_balance_chinese():
    """买入余额不足：action 为观望"""
    from app.services.simulator import simulator

    account = make_account(balance=100.0)
    db = make_db(account=account)

    trigger = await simulator.execute_buy(
        strategy_id=1, symbol="BTCUSDT", quantity=1.0, price=40000.0, db=db
    )
    assert trigger.action == "观望"
    assert trigger.signal_type == "买入"
    assert trigger.position_effect is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd /home/autotrade/autotrade/backend && python3 -m pytest tests/test_simulator_short.py -v`
Expected: 5 failures (action/signal_type values don't match)

- [ ] **Step 3: Update simulator.py — all 4 execute methods**

**execute_buy (lines 61-68 hold case):**
```python
trigger = TriggerLog(
    strategy_id=strategy_id,
    signal_type="买入",
    signal_detail="余额不足，跳过买入",
    action="观望",
    price=price,
    quantity=0,
)
```

**execute_buy (lines 87-94 success case):**
```python
trigger = TriggerLog(
    strategy_id=strategy_id,
    signal_type="买入",
    signal_detail=f"买入 {quantity} {symbol} @ {price}",
    action="买入",
    price=price,
    quantity=quantity,
    position_effect="开仓",
)
```

**execute_sell (lines 137-144 hold case):**
```python
trigger = TriggerLog(
    strategy_id=strategy_id,
    signal_type="卖出",
    signal_detail="无持仓，跳过卖出",
    action="观望",
    price=price,
    quantity=0,
)
```

**execute_sell (lines 180-188 success case):**
```python
trigger = TriggerLog(
    strategy_id=strategy_id,
    signal_type="卖出",
    signal_detail=f"卖出 {total_sell_qty:.4f} {symbol} @ {price} ({sell_size_pct:.0f}%), 盈亏: {total_pnl:.2f}",
    action="卖出",
    price=price,
    quantity=total_sell_qty,
    simulated_pnl=total_pnl,
    position_effect="平仓",
)
```

**execute_short (lines 234-241 hold case):**
```python
trigger = TriggerLog(
    strategy_id=strategy_id,
    signal_type="卖出",
    signal_detail="余额不足，跳过开空",
    action="观望",
    price=price,
    quantity=0,
)
```

**execute_short (lines 257-264 success case):**
```python
trigger = TriggerLog(
    strategy_id=strategy_id,
    signal_type="卖出",
    signal_detail=f"开空 {quantity} {symbol} @ {price}",
    action="卖出",
    price=price,
    quantity=quantity,
    position_effect="开仓",
)
```

**execute_cover (lines 304-311 hold case):**
```python
trigger = TriggerLog(
    strategy_id=strategy_id,
    signal_type="买入",
    signal_detail="无空仓，跳过平空",
    action="观望",
    price=price,
    quantity=0,
)
```

**execute_cover (lines 342-350 success case):**
```python
trigger = TriggerLog(
    strategy_id=strategy_id,
    signal_type="买入",
    signal_detail=f"平空 {total_quantity:.4f} {symbol} @ {price}, 盈亏: {total_pnl:.2f}",
    action="买入",
    price=price,
    quantity=total_quantity,
    simulated_pnl=total_pnl,
    position_effect="平仓",
)
```

Also update the docstrings:
- execute_short: `TriggerLog（action="short" 成功开空` → `TriggerLog（action="卖出" 成功开空`
- execute_cover: `TriggerLog（action="cover" 成功平空` → `TriggerLog（action="买入" 成功平空`

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd /home/autotrade/autotrade/backend && python3 -m pytest tests/test_simulator_short.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/simulator.py backend/tests/test_simulator_short.py
git commit -m "feat: change simulator TriggerLog values to Chinese, add position_effect"
```

---

### Task 3: Executor error handling

**Files:**
- Modify: `backend/app/engine/executor.py:366-371`

- [ ] **Step 1: Update error TriggerLog to Chinese values**

In `backend/app/engine/executor.py`, change the error handling block (around line 366-371):

```python
# Before:
error_trigger = TriggerLog(
    strategy_id=strategy.id,
    signal_type="error",
    signal_detail=f"代码执行错误: {str(e)}",
    action="hold",
)
# After:
error_trigger = TriggerLog(
    strategy_id=strategy.id,
    signal_type="错误",
    signal_detail=f"代码执行错误: {str(e)}",
    action="观望",
)
```

- [ ] **Step 2: Run existing tests to verify nothing breaks**

Run: `cd /home/autotrade/autotrade/backend && python3 -m pytest tests/ -v --timeout=10 2>&1 | tail -20`
Expected: all tests pass

- [ ] **Step 3: Commit**

```bash
git add backend/app/engine/executor.py
git commit -m "feat: change executor error TriggerLog to Chinese values"
```

---

### Task 4: Executor tests — update mock values

**Files:**
- Modify: `backend/tests/test_executor_short.py`

- [ ] **Step 1: Update mock action values in test_executor_short.py**

These tests mock simulator return values. The mock `action` values should reflect what the simulator now returns. Update these lines:

**test_buy_no_position_opens_long** (line 35):
```python
# Before:
buy_trigger = MagicMock(action="buy")
# After:
buy_trigger = MagicMock(action="买入", position_effect="开仓")
```

**test_buy_holding_short_covers** (line 60):
```python
# Before:
cover_trigger = MagicMock(action="cover")
# After:
cover_trigger = MagicMock(action="买入", position_effect="平仓")
```

**test_sell_no_position_opens_short** (line 110):
```python
# Before:
short_trigger = MagicMock(action="short")
# After:
short_trigger = MagicMock(action="卖出", position_effect="开仓")
```

**test_sell_holding_long_closes** (line 135):
```python
# Before:
sell_trigger = MagicMock(action="sell")
# After:
sell_trigger = MagicMock(action="卖出", position_effect="平仓")
```

Note: These tests verify routing (which simulator method is called), not action values. The mock values are updated for consistency with the new Chinese values.

- [ ] **Step 2: Run tests to verify they pass**

Run: `cd /home/autotrade/autotrade/backend && python3 -m pytest tests/test_executor_short.py -v`
Expected: 9 passed

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_executor_short.py
git commit -m "test: update executor test mocks to use Chinese action values"
```

---

### Task 5: Feishu notification service

**Files:**
- Modify: `backend/app/services/feishu.py:93-96,120,180,201-202`

- [ ] **Step 1: Simplify _build_trade_card (lines 93-96)**

```python
# Before:
action_labels = {"buy": "买入", "sell": "卖出", "short": "开空", "cover": "平空"}
action_colors = {"buy": "green", "sell": "red", "short": "orange", "cover": "purple"}
action_text = action_labels.get(action, "观望")
header_color = action_colors.get(action, "grey")

# After:
action_colors = {"买入": "green", "卖出": "red"}
action_text = action  # action is already Chinese
header_color = action_colors.get(action, "grey")
```

- [ ] **Step 2: Add position_effect to _build_trade_card notification content**

The `_build_trade_card` method signature needs a new `position_effect` parameter. Add it after `action`:

```python
def _build_trade_card(
    self,
    strategy_name: str,
    signal_type: str,
    signal_detail: str,
    action: str,
    symbol: str,
    price: Optional[float],
    pnl: Optional[float],
    position_effect: Optional[str] = None,  # NEW
) -> dict:
```

Update the card content text (line 120) to include position_effect:

```python
# Before:
"content": f"**操作:** {action_text}\\n**交易对:** {symbol}\\n**价格:** {price_text} USDT{pnl_text}",
# After (add position_effect if present):
effect_text = f"（{position_effect}）" if position_effect else ""
"content": f"**操作:** {action_text}{effect_text}\\n**交易对:** {symbol}\\n**价格:** {price_text} USDT{pnl_text}",
```

- [ ] **Step 3: Update send_strategy_notification to pass position_effect**

Update the call to `_build_trade_card` (around line 176-183) to pass `position_effect`:

```python
# Before:
action=trigger_log.action or "hold",
# After:
action=trigger_log.action or "观望",
position_effect=getattr(trigger_log, "position_effect", None),
```

- [ ] **Step 4: Simplify Bark notification (lines 201-202) and add position_effect**

```python
# Before:
action_map = {"buy": "买入", "sell": "卖出", "short": "开空", "cover": "平空", "hold": "观望"}
action_text = action_map.get(trigger_log.action or "hold", trigger_log.action or "hold")
price_text = f"{trigger_log.price:.2f}" if trigger_log.price else "-"
title = f"AutoTrade: {strategy_name}"
body = f"{action_text} {symbol} @ {price_text} USDT"

# After:
action_text = trigger_log.action or "观望"
effect_text = f"（{trigger_log.position_effect}）" if getattr(trigger_log, "position_effect", None) else ""
price_text = f"{trigger_log.price:.2f}" if trigger_log.price else "-"
title = f"AutoTrade: {strategy_name}"
body = f"{action_text}{effect_text} {symbol} @ {price_text} USDT"
```

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/feishu.py
git commit -m "feat: simplify feishu notifications for Chinese values, add position_effect"
```

---

### Task 6: Frontend — 3 files

**Files:**
- Modify: `frontend/src/app/triggers/page.tsx:44-57`
- Modify: `frontend/src/app/strategies/[id]/page.tsx:176-189`
- Modify: `frontend/src/app/page.tsx:100-109`

- [ ] **Step 1: Update getActionBadge in triggers/page.tsx (lines 44-57)**

```typescript
const getActionBadge = (action?: string) => {
  switch (action) {
    case "buy":
    case "买入":
      return <Badge className="bg-green-600">买入</Badge>;
    case "sell":
    case "卖出":
      return <Badge className="bg-red-600">卖出</Badge>;
    default:
      return <Badge variant="secondary">观望</Badge>;
  }
};
```

- [ ] **Step 2: Update getActionBadge in strategies/[id]/page.tsx (lines 176-189)**

Same change as Step 1.

- [ ] **Step 3: Update dashboard action display in page.tsx (lines 100-109)**

```typescript
<span
  className={`px-2 py-1 rounded text-xs font-medium ${
    ["buy", "买入"].includes(trigger.action || "")
      ? "bg-green-900 text-green-300"
      : ["sell", "卖出"].includes(trigger.action || "")
      ? "bg-red-900 text-red-300"
      : "bg-slate-700 text-slate-300"
  }`}
>
  {trigger.action || "观望"}
</span>
```

Note: The `.toUpperCase()` call is removed since Chinese values don't need uppercasing.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/app/triggers/page.tsx frontend/src/app/strategies/\[id\]/page.tsx frontend/src/app/page.tsx
git commit -m "feat: update frontend action badges for Chinese values with backward compat"
```

---

### Task 7: Run all tests

- [ ] **Step 1: Run all backend tests**

Run: `cd /home/autotrade/autotrade/backend && python3 -m pytest tests/ -v --timeout=10`
Expected: all tests pass

- [ ] **Step 2: Verify frontend builds**

Run: `cd /home/autotrade/autotrade/frontend && npx next build 2>&1 | tail -10`
Expected: build succeeds
