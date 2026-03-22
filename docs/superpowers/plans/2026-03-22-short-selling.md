# 做空功能 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为模拟交易引擎添加做空支持，策略可发出 `short`（开空）/`cover`（平空）信号，并在信号冲突时自动翻仓。

**Architecture:** 在 `Simulator` 中新增 `execute_short` / `execute_cover` 方法（与现有 `execute_buy`/`execute_sell` 对称）；在 `StrategyContext` 中新增 `short()` / `cover()` 方法并在 `buy()` 中植入翻仓前置逻辑；`_execute_visual_strategy` 扩展为 4 路信号逻辑；前端视觉策略编辑器新增可选的开空/平空条件区块，持仓和日志页面新增方向标识。

**Tech Stack:** Python 3 / FastAPI / SQLAlchemy async / SQLite / pytest-asyncio（后端），Next.js / TypeScript / shadcn/ui（前端）

---

## 文件变更一览

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `backend/app/services/simulator.py` | 修改 | 新增 `execute_short`、`execute_cover`；扩展 `check_stop_loss_take_profit` |
| `backend/app/engine/executor.py` | 修改 | 修改 `get_position()`；扩展 `buy()`；新增 `short()`、`cover()`；更新信号路由和视觉策略逻辑 |
| `backend/tests/test_simulator_short.py` | 新建 | simulator 做空单元测试 |
| `backend/tests/test_executor_short.py` | 新建 | executor 信号路由 + 翻仓逻辑测试 |
| `frontend/src/components/visual-strategy-editor/types.ts` | 修改 | `StrategyConfig` 增加可选 `short_conditions` / `cover_conditions` |
| `frontend/src/components/visual-strategy-editor/utils.ts` | 修改 | `deserializeConfig`、`generatePreviewText` 支持新字段 |
| `frontend/src/components/visual-strategy-editor/strategy-preview.tsx` | 修改 | 展示开空/平空预览文本 |
| `frontend/src/app/strategies/new/page.tsx` | 修改 | 新增可折叠开空/平空条件区块 |
| `frontend/src/app/strategies/[id]/edit/page.tsx` | 修改 | 同上 |
| `frontend/src/app/triggers/page.tsx` | 修改 | 新增 `short`/`cover` badge |
| `frontend/src/app/strategies/[id]/page.tsx` | 不变 | 持仓 Tab 仍为占位符，方向徽章待持仓列表功能实现时添加 |

---

## Task 1: execute_short + execute_cover

**Files:**
- Modify: `backend/app/services/simulator.py`
- Create: `backend/tests/test_simulator_short.py`

背景：`simulator.py` 已有 `execute_buy` / `execute_sell`。本任务镜像这两个方法，实现做空的开仓和平仓。

- [ ] **Step 1: 安装测试依赖、创建 pytest 配置**

```bash
cd /home/autotrade/autotrade/backend
# 系统 Python，需要 --break-system-packages
pip3 install pytest pytest-asyncio --break-system-packages -q
```

新建 `backend/pytest.ini`（这两个配置是必须的，缺一不可）：

```ini
[pytest]
asyncio_mode = auto
pythonpath = .
```

确认可收集：
```bash
python3 -m pytest --collect-only 2>&1 | head -5
```

预期：输出 `no tests ran` 或收集到 0 个测试（没有报 import error 或 asyncio 警告）。

- [ ] **Step 2: 写失败测试 — `execute_short` 正常开空**

新建 `backend/tests/__init__.py`（空文件）和 `backend/tests/test_simulator_short.py`：

```python
"""测试 Simulator.execute_short / execute_cover"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime


def make_account(balance=100000.0, total_pnl=0.0):
    acc = MagicMock()
    acc.balance = balance
    acc.total_pnl = total_pnl
    return acc


def make_db(account=None, position=None):
    """返回一个 mock AsyncSession"""
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    # execute 返回值
    result = MagicMock()
    result.scalar_one = MagicMock(return_value=account or make_account())
    result.scalar_one_or_none = MagicMock(return_value=position)
    db.execute = AsyncMock(return_value=result)
    return db


@pytest.mark.asyncio
async def test_execute_short_success():
    """开空成功：余额足够，创建 side=short 持仓，扣除保证金"""
    from app.services.simulator import simulator

    account = make_account(balance=50000.0)
    db = make_db(account=account)

    trigger = await simulator.execute_short(
        strategy_id=1,
        symbol="BTCUSDT",
        quantity=0.1,
        price=40000.0,
        db=db,
        user_id=1,
    )

    # 扣除保证金 0.1 * 40000 = 4000
    assert account.balance == pytest.approx(46000.0)
    # 创建了 Position
    db.add.assert_called()
    # TriggerLog action = "short"
    assert trigger is not None
    assert trigger.action == "short"
    assert trigger.signal_type == "short"
```

- [ ] **Step 3: 运行测试，确认失败**

```bash
cd /home/autotrade/autotrade/backend
python3 -m pytest tests/test_simulator_short.py::test_execute_short_success -v
```

预期：`FAILED` — `AttributeError: 'Simulator' object has no attribute 'execute_short'`

- [ ] **Step 4: 实现 `execute_short`**

在 `backend/app/services/simulator.py` 的 `execute_sell` 方法之后添加：

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
    """执行模拟开空（锁定保证金）"""
    required_margin = quantity * price

    # 查找账户
    if user_id is not None:
        account_result = await db.execute(
            select(SimAccount).where(SimAccount.user_id == user_id)
        )
    else:
        account_result = await db.execute(select(SimAccount).limit(1))
    account = account_result.scalar_one()

    if account.balance < required_margin:
        logger.warning(
            f"Insufficient balance for short: required={required_margin}, "
            f"balance={account.balance}"
        )
        trigger = TriggerLog(
            strategy_id=strategy_id,
            signal_type="short",
            signal_detail="余额不足，跳过开空",
            action="hold",
            price=price,
            quantity=0,
        )
        db.add(trigger)
        await db.commit()
        return trigger

    # 扣除保证金
    account.balance -= required_margin

    # 创建空头持仓
    position = Position(
        strategy_id=strategy_id,
        symbol=symbol,
        side="short",
        entry_price=price,
        quantity=quantity,
    )
    db.add(position)

    trigger = TriggerLog(
        strategy_id=strategy_id,
        signal_type="short",
        signal_detail=f"开空 {quantity} {symbol} @ {price}",
        action="short",
        price=price,
        quantity=quantity,
    )
    db.add(trigger)
    await db.commit()
    await db.refresh(trigger)

    logger.info(f"模拟开空: {symbol} {quantity} @ {price}")
    return trigger
```

- [ ] **Step 5: 运行测试，确认通过**

```bash
python3 -m pytest tests/test_simulator_short.py::test_execute_short_success -v
```

预期：`PASSED`

- [ ] **Step 6: 写 `execute_short` 余额不足测试**

在 `test_simulator_short.py` 追加：

```python
@pytest.mark.asyncio
async def test_execute_short_insufficient_balance():
    """余额不足时返回 hold"""
    from app.services.simulator import simulator

    account = make_account(balance=100.0)
    db = make_db(account=account)

    trigger = await simulator.execute_short(
        strategy_id=1, symbol="BTCUSDT", quantity=1.0, price=40000.0, db=db
    )

    assert trigger.action == "hold"
    assert "余额不足" in trigger.signal_detail
    assert account.balance == pytest.approx(100.0)  # 未扣款
```

- [ ] **Step 7: 写失败测试 — `execute_cover` 正常平空**

```python
@pytest.mark.asyncio
async def test_execute_cover_success():
    """平空成功：价格下跌，盈利，余额增加，持仓关闭"""
    from app.services.simulator import simulator
    from app.models import Position

    position = MagicMock(spec=Position)
    position.entry_price = 40000.0
    position.quantity = 0.1
    position.side = "short"
    position.pnl = None
    position.current_price = None
    position.closed_at = None

    account = make_account(balance=96000.0, total_pnl=0.0)

    # execute 第一次返回 position，第二次返回 account
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    calls = [0]

    async def mock_execute(stmt):
        result = MagicMock()
        if calls[0] == 0:
            result.scalar_one_or_none = MagicMock(return_value=position)
        else:
            result.scalar_one = MagicMock(return_value=account)
        calls[0] += 1
        return result

    db.execute = mock_execute

    # 平空价格 = 38000（低于开空价 40000，盈利）
    trigger = await simulator.execute_cover(
        strategy_id=1, symbol="BTCUSDT", price=38000.0, db=db, user_id=1
    )

    # PnL = (40000 - 38000) * 0.1 = 200
    expected_pnl = (40000.0 - 38000.0) * 0.1
    # 返还保证金 40000 * 0.1 = 4000，加上盈利 200
    assert account.balance == pytest.approx(96000.0 + 4000.0 + expected_pnl)
    assert account.total_pnl == pytest.approx(expected_pnl)
    assert position.closed_at is not None
    assert trigger.action == "cover"
    assert trigger.simulated_pnl == pytest.approx(expected_pnl)
```

- [ ] **Step 8: 运行失败测试**

```bash
python3 -m pytest tests/test_simulator_short.py::test_execute_cover_success -v
```

预期：`FAILED` — `AttributeError: 'Simulator' object has no attribute 'execute_cover'`

- [ ] **Step 9: 实现 `execute_cover`**

在 `execute_short` 之后添加：

```python
async def execute_cover(
    self,
    strategy_id: int,
    symbol: str,
    price: float,
    db: AsyncSession,
    user_id: Optional[int] = None,
) -> Optional[TriggerLog]:
    """执行模拟平空（始终全额平仓）"""
    # 查找未平仓的空头持仓
    result = await db.execute(
        select(Position).where(
            Position.strategy_id == strategy_id,
            Position.symbol == symbol,
            Position.side == "short",
            Position.closed_at.is_(None),
        )
    )
    position = result.scalar_one_or_none()

    if not position:
        logger.warning(f"No open short position to cover for strategy {strategy_id}")
        trigger = TriggerLog(
            strategy_id=strategy_id,
            signal_type="cover",
            signal_detail="无空仓，跳过平空",
            action="hold",
            price=price,
            quantity=0,
        )
        db.add(trigger)
        await db.commit()
        return trigger

    quantity = position.quantity
    pnl = (position.entry_price - price) * quantity  # 价跌盈利
    margin_returned = position.entry_price * quantity

    # 返还保证金 + PnL 到账户
    if user_id is not None:
        account_result = await db.execute(
            select(SimAccount).where(SimAccount.user_id == user_id)
        )
    else:
        account_result = await db.execute(select(SimAccount).limit(1))
    account = account_result.scalar_one()
    account.balance += margin_returned + pnl
    account.total_pnl += pnl

    # 关闭持仓
    position.pnl = pnl
    position.current_price = price
    position.closed_at = datetime.utcnow()

    trigger = TriggerLog(
        strategy_id=strategy_id,
        signal_type="cover",
        signal_detail=f"平空 {quantity:.4f} {symbol} @ {price}, 盈亏: {pnl:.2f}",
        action="cover",
        price=price,
        quantity=quantity,
        simulated_pnl=pnl,
    )
    db.add(trigger)
    await db.commit()
    await db.refresh(trigger)

    logger.info(f"模拟平空: {symbol} {quantity:.4f} @ {price}, PnL: {pnl:.2f}")
    return trigger
```

- [ ] **Step 10: 运行所有 simulator 测试**

```bash
python3 -m pytest tests/test_simulator_short.py -v
```

预期：所有测试 `PASSED`

- [ ] **Step 11: 提交**

```bash
cd /home/autotrade/autotrade
git add backend/app/services/simulator.py backend/tests/
git commit -m "feat: add execute_short and execute_cover to Simulator"
```

---

## Task 2: check_stop_loss_take_profit 扩展空头

**Files:**
- Modify: `backend/app/services/simulator.py`
- Modify: `backend/tests/test_simulator_short.py`

- [ ] **Step 1: 写失败测试 — 空头止损（价格上涨）**

在 `test_simulator_short.py` 追加：

```python
@pytest.mark.asyncio
async def test_check_sl_tp_short_stop_loss():
    """空头止损：价格上涨超过 stop_loss_pct"""
    from app.services.simulator import simulator
    from app.models import Position

    position = MagicMock(spec=Position)
    position.entry_price = 40000.0
    position.quantity = 0.1
    position.side = "short"
    position.pnl = None
    position.current_price = None
    position.closed_at = None

    account = make_account(balance=96000.0)
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    call_count = [0]
    async def mock_execute(stmt):
        result = MagicMock()
        n = call_count[0]
        call_count[0] += 1
        if n == 0:
            # 第一次：查多头仓 → None
            result.scalar_one_or_none = MagicMock(return_value=None)
        elif n == 1:
            # 第二次：查空头仓 → position
            result.scalar_one_or_none = MagicMock(return_value=position)
        else:
            # 第三次：查账户
            result.scalar_one = MagicMock(return_value=account)
        return result

    db.execute = mock_execute

    # 开空 40000，当前价 42000（上涨 5%），止损阈值 5%
    trigger = await simulator.check_stop_loss_take_profit(
        strategy_id=1,
        symbol="BTCUSDT",
        current_price=42000.0,
        stop_loss_pct=5.0,
        take_profit_pct=None,
        db=db,
    )

    assert trigger is not None
    assert "[止损]" in trigger.signal_detail
```

- [ ] **Step 2: 运行失败测试**

```bash
cd /home/autotrade/autotrade/backend
python3 -m pytest tests/test_simulator_short.py::test_check_sl_tp_short_stop_loss -v
```

预期：`FAILED`（目前 `check_stop_loss_take_profit` 只查多头仓，返回 None）

- [ ] **Step 3: 扩展 `check_stop_loss_take_profit`**

在 `backend/app/services/simulator.py` 的 `check_stop_loss_take_profit` 方法中，现有多头检查完毕后（`return None` 之前）添加空头检查：

```python
    # ── 空头止盈止损 ──────────────────────────────────────
    short_result = await db.execute(
        select(Position).where(
            Position.strategy_id == strategy_id,
            Position.symbol == symbol,
            Position.side == "short",
            Position.closed_at.is_(None),
        )
    )
    short_position = short_result.scalar_one_or_none()

    if short_position:
        entry_price = short_position.entry_price
        price_change_pct = (current_price - entry_price) / entry_price * 100

        # 空头止损：价格上涨 ≥ stop_loss_pct
        if stop_loss_pct and price_change_pct >= stop_loss_pct:
            logger.info(f"Short stop loss triggered: +{price_change_pct:.2f}%")
            trigger = await self.execute_cover(strategy_id, symbol, current_price, db, user_id=user_id)
            trigger.signal_detail = f"[止损] {trigger.signal_detail}"
            await db.commit()
            return trigger

        # 空头止盈：价格下跌 ≥ take_profit_pct
        if take_profit_pct and price_change_pct <= -take_profit_pct:
            logger.info(f"Short take profit triggered: {price_change_pct:.2f}%")
            trigger = await self.execute_cover(strategy_id, symbol, current_price, db, user_id=user_id)
            trigger.signal_detail = f"[止盈] {trigger.signal_detail}"
            await db.commit()
            return trigger

    return None
```

注意：删除原有结尾的 `return None`，用上面代码的末尾 `return None` 代替。

- [ ] **Step 4: 写空头止盈测试**

```python
@pytest.mark.asyncio
async def test_check_sl_tp_short_take_profit():
    """空头止盈：价格下跌超过 take_profit_pct"""
    from app.services.simulator import simulator
    from app.models import Position

    position = MagicMock(spec=Position)
    position.entry_price = 40000.0
    position.quantity = 0.1
    position.side = "short"
    position.pnl = None
    position.current_price = None
    position.closed_at = None

    account = make_account(balance=96000.0)
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()

    call_count = [0]
    async def mock_execute(stmt):
        result = MagicMock()
        n = call_count[0]
        call_count[0] += 1
        if n == 0:
            result.scalar_one_or_none = MagicMock(return_value=None)   # 无多仓
        elif n == 1:
            result.scalar_one_or_none = MagicMock(return_value=position)  # 有空仓
        else:
            result.scalar_one = MagicMock(return_value=account)
        return result

    db.execute = mock_execute

    # 开空 40000，当前价 36000（下跌 10%），止盈阈值 10%
    trigger = await simulator.check_stop_loss_take_profit(
        strategy_id=1,
        symbol="BTCUSDT",
        current_price=36000.0,
        stop_loss_pct=None,
        take_profit_pct=10.0,
        db=db,
    )

    assert trigger is not None
    assert "[止盈]" in trigger.signal_detail
```

- [ ] **Step 5: 运行所有 simulator 测试**

```bash
python3 -m pytest tests/test_simulator_short.py -v
```

预期：所有测试 `PASSED`

- [ ] **Step 6: 提交**

```bash
cd /home/autotrade/autotrade
git add backend/app/services/simulator.py backend/tests/test_simulator_short.py
git commit -m "feat: extend check_stop_loss_take_profit for short positions"
```

---

## Task 3: StrategyContext — get_position + short/cover + buy 翻仓

**Files:**
- Modify: `backend/app/engine/executor.py`
- Create: `backend/tests/test_executor_short.py`

- [ ] **Step 1: 写失败测试 — `ctx.short()` 开空**

新建 `backend/tests/test_executor_short.py`：

```python
"""测试 StrategyContext.short / cover 及翻仓逻辑"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def make_strategy(position_size=1000.0, position_size_type="fixed", user_id=1):
    s = MagicMock()
    s.id = 1
    s.symbol = "BTCUSDT"
    s.position_size = position_size
    s.position_size_type = position_size_type
    s.user_id = user_id
    s.sell_size_pct = 100.0
    return s


def make_kline(close=40000.0):
    return {"close": close, "open": 39000.0, "high": 41000.0, "low": 38000.0, "volume": 100.0}


@pytest.mark.asyncio
async def test_ctx_short_no_position():
    """无持仓时 short() 直接开空"""
    from app.engine.executor import StrategyContext

    strategy = make_strategy()
    db = AsyncMock()
    kline = make_kline(40000.0)
    ctx = StrategyContext(strategy, db, current_kline=kline)

    # get_position → None（无持仓）
    result_mock = MagicMock()
    result_mock.scalar_one_or_none = MagicMock(return_value=None)
    db.execute = AsyncMock(return_value=result_mock)

    trigger_mock = MagicMock()
    trigger_mock.action = "short"

    with patch("app.engine.executor.simulator") as mock_sim:
        mock_sim.execute_short = AsyncMock(return_value=trigger_mock)
        result = await ctx.short()

    mock_sim.execute_short.assert_called_once()
    call_kwargs = mock_sim.execute_short.call_args
    assert call_kwargs.kwargs["symbol"] == "BTCUSDT"
    assert call_kwargs.kwargs["price"] == pytest.approx(40000.0)
    assert result == trigger_mock
```

- [ ] **Step 2: 运行失败**

```bash
cd /home/autotrade/autotrade/backend
python3 -m pytest tests/test_executor_short.py::test_ctx_short_no_position -v
```

预期：`FAILED` — `StrategyContext has no attribute 'short'`

- [ ] **Step 3: 修改 `get_position()` 移除 side 过滤**

在 `backend/app/engine/executor.py` 中，找到 `get_position` 方法（约第 94 行），将其改为：

```python
async def get_position(self) -> Optional[Position]:
    """获取当前持仓（任意方向）"""
    result = await self.db.execute(
        select(Position).where(
            Position.strategy_id == self.strategy.id,
            Position.symbol == self.strategy.symbol,
            Position.closed_at.is_(None),
        )
    )
    return result.scalar_one_or_none()
```

（移除原有的 `Position.side == "long"` 过滤条件）

- [ ] **Step 4: 实现 `short()` 和 `cover()`**

在 `StrategyContext` 的 `sell()` 方法之后添加：

```python
async def short(self, quantity: Optional[float] = None) -> Optional[TriggerLog]:
    """开空（自动翻仓：若持多仓先全额平多）"""
    klines = await self.get_klines(limit=1)
    if not klines:
        logger.error("No kline data available for short")
        return None

    price = self.current_kline["close"] if self.current_kline else klines[-1]["close"]

    # 自动翻仓：若持有多仓，先全额平多
    position = await self.get_position()
    if position and position.side == "long":
        await simulator.execute_sell(
            strategy_id=self.strategy.id,
            symbol=self.strategy.symbol,
            price=price,
            db=self.db,
            sell_size_pct=100.0,
            user_id=getattr(self.strategy, "user_id", None),
        )  # 返回值有意丢弃（TriggerLog 已 commit 到 DB）

    # 计算开空数量
    if quantity is not None:
        qty = quantity
    elif self.strategy.position_size_type == "percent":
        balance = await self.get_balance()
        qty = balance * self.strategy.position_size / 100.0 / price
    else:
        qty = self.strategy.position_size / price

    return await simulator.execute_short(
        strategy_id=self.strategy.id,
        symbol=self.strategy.symbol,
        quantity=qty,
        price=price,
        db=self.db,
        user_id=getattr(self.strategy, "user_id", None),
    )

async def cover(self, quantity: Optional[float] = None) -> Optional[TriggerLog]:
    """平空"""
    klines = await self.get_klines(limit=1)
    if not klines:
        logger.error("No kline data available for cover")
        return None

    price = self.current_kline["close"] if self.current_kline else klines[-1]["close"]

    return await simulator.execute_cover(
        strategy_id=self.strategy.id,
        symbol=self.strategy.symbol,
        price=price,
        db=self.db,
        user_id=getattr(self.strategy, "user_id", None),
    )
```

- [ ] **Step 5: 扩展 `buy()` 加入翻仓前置**

在 `buy()` 方法开头（`klines = await self.get_klines(limit=1)` 之前）插入：

```python
async def buy(self, quantity: Optional[float] = None) -> Optional[TriggerLog]:
    """买入（自动翻仓：若持空仓先全额平空）"""
    klines = await self.get_klines(limit=1)
    if not klines:
        logger.error("No kline data available for buy")
        return None

    price = klines[-1]["close"]

    # 自动翻仓：若持有空仓，先全额平空
    position = await self.get_position()
    if position and position.side == "short":
        flip_price = self.current_kline["close"] if self.current_kline else price
        await simulator.execute_cover(
            strategy_id=self.strategy.id,
            symbol=self.strategy.symbol,
            price=flip_price,
            db=self.db,
            user_id=getattr(self.strategy, "user_id", None),
        )  # 返回值有意丢弃（TriggerLog 已 commit 到 DB）

    # 原有计算数量逻辑
    if quantity is not None:
        qty = quantity
    elif self.strategy.position_size_type == "percent":
        balance = await self.get_balance()
        qty = balance * self.strategy.position_size / 100.0 / price
    else:
        qty = self.strategy.position_size / price

    return await simulator.execute_buy(
        strategy_id=self.strategy.id,
        symbol=self.strategy.symbol,
        quantity=qty,
        price=price,
        db=self.db,
        user_id=getattr(self.strategy, "user_id", None),
    )
```

- [ ] **Step 6: 写翻仓测试**

在 `test_executor_short.py` 追加：

```python
@pytest.mark.asyncio
async def test_ctx_short_flips_from_long():
    """持多仓时 short() 先平多再开空"""
    from app.engine.executor import StrategyContext
    from app.models import Position

    strategy = make_strategy()
    db = AsyncMock()
    kline = make_kline(40000.0)
    ctx = StrategyContext(strategy, db, current_kline=kline)

    long_position = MagicMock(spec=Position)
    long_position.side = "long"

    result_mock = MagicMock()
    result_mock.scalar_one_or_none = MagicMock(return_value=long_position)
    db.execute = AsyncMock(return_value=result_mock)

    with patch("app.engine.executor.simulator") as mock_sim:
        sell_trigger = MagicMock()
        short_trigger = MagicMock()
        short_trigger.action = "short"
        mock_sim.execute_sell = AsyncMock(return_value=sell_trigger)
        mock_sim.execute_short = AsyncMock(return_value=short_trigger)

        result = await ctx.short()

    # execute_sell 必须先被调用（翻仓）
    mock_sim.execute_sell.assert_called_once()
    sell_kwargs = mock_sim.execute_sell.call_args.kwargs
    assert sell_kwargs["sell_size_pct"] == 100.0

    # execute_short 之后被调用
    mock_sim.execute_short.assert_called_once()
    assert result == short_trigger


@pytest.mark.asyncio
async def test_ctx_buy_flips_from_short():
    """持空仓时 buy() 先平空再开多"""
    from app.engine.executor import StrategyContext
    from app.models import Position

    strategy = make_strategy()
    db = AsyncMock()
    kline = make_kline(40000.0)
    ctx = StrategyContext(strategy, db, current_kline=kline)

    short_position = MagicMock(spec=Position)
    short_position.side = "short"

    result_mock = MagicMock()
    result_mock.scalar_one_or_none = MagicMock(return_value=short_position)
    db.execute = AsyncMock(return_value=result_mock)

    with patch("app.engine.executor.simulator") as mock_sim:
        cover_trigger = MagicMock()
        buy_trigger = MagicMock()
        buy_trigger.action = "buy"
        mock_sim.execute_cover = AsyncMock(return_value=cover_trigger)
        mock_sim.execute_buy = AsyncMock(return_value=buy_trigger)
        mock_sim.execute_sell = AsyncMock()

        # 注意：strategy.position_size_type = "fixed"，不会调用 get_balance，无需 mock
        result = await ctx.buy()

    mock_sim.execute_cover.assert_called_once()
    mock_sim.execute_buy.assert_called_once()
    assert result == buy_trigger
```

- [ ] **Step 7: 运行所有 executor 测试**

```bash
python3 -m pytest tests/test_executor_short.py -v
```

预期：所有测试 `PASSED`

- [ ] **Step 8: 提交**

```bash
cd /home/autotrade/autotrade
git add backend/app/engine/executor.py backend/tests/test_executor_short.py
git commit -m "feat: add short/cover to StrategyContext with auto-flip logic"
```

---

## Task 4: execute() 信号路由 + _execute_visual_strategy 扩展

**Files:**
- Modify: `backend/app/engine/executor.py`
- Modify: `backend/tests/test_executor_short.py`

- [ ] **Step 1: 写测试 — execute() 路由 short/cover 信号**

在 `test_executor_short.py` 追加：

```python
@pytest.mark.asyncio
async def test_execute_routes_short_signal():
    """execute() 接收 short 信号时调用 ctx.short()"""
    from app.engine.executor import StrategyExecutor
    from unittest.mock import patch, AsyncMock, MagicMock

    executor = StrategyExecutor()

    strategy = make_strategy()
    strategy.type = "code"
    strategy.code = "def on_tick(data): return 'short'"
    strategy.notify_enabled = False
    strategy.stop_loss = None
    strategy.take_profit = None
    strategy.timeframe = "1h"
    strategy.status = "running"

    with patch("app.engine.executor.async_session") as mock_session_cls, \
         patch("app.engine.executor.market_data_service") as mock_mds, \
         patch("app.engine.executor.sandbox_executor") as mock_sandbox:

        db = AsyncMock()
        db.__aenter__ = AsyncMock(return_value=db)
        db.__aexit__ = AsyncMock(return_value=False)
        mock_session_cls.return_value = db

        klines = [make_kline()]
        mock_mds.get_klines = AsyncMock(return_value=klines)

        # stop-loss check → None
        with patch("app.engine.executor.simulator") as mock_sim:
            mock_sim.check_stop_loss_take_profit = AsyncMock(return_value=None)

            short_trigger = MagicMock()
            short_trigger.action = "short"

            # StrategyContext.short() mock
            with patch("app.engine.executor.StrategyContext") as MockCtx:
                ctx_instance = AsyncMock()
                ctx_instance.short = AsyncMock(return_value=short_trigger)
                ctx_instance.buy = AsyncMock()
                ctx_instance.sell = AsyncMock()
                ctx_instance.cover = AsyncMock()
                MockCtx.return_value = ctx_instance

                # sandbox returns "short"
                mock_sandbox.create_instance = MagicMock(return_value=MagicMock())
                mock_sandbox.call_on_tick = MagicMock(return_value="short")

                await executor.execute(strategy)

            ctx_instance.short.assert_called_once()
```

- [ ] **Step 2: 运行失败**

```bash
cd /home/autotrade/autotrade/backend
python3 -m pytest tests/test_executor_short.py::test_execute_routes_short_signal -v
```

预期：`FAILED`（executor 的信号路由没有 `short`/`cover` 分支）

- [ ] **Step 3: 扩展信号路由**

在 `backend/app/engine/executor.py` 的 `execute()` 方法中，找到信号路由部分（约第 203-207 行）：

```python
                    # 3. 执行交易信号
                    if signal == "buy":
                        trigger = await ctx.buy()
                    elif signal == "sell":
                        trigger = await ctx.sell()
```

替换为：

```python
                    # 3. 执行交易信号
                    if signal == "buy":
                        trigger = await ctx.buy()
                    elif signal == "sell":
                        trigger = await ctx.sell()
                    elif signal == "short":
                        trigger = await ctx.short()
                    elif signal == "cover":
                        trigger = await ctx.cover()
```

- [ ] **Step 4: 扩展 `_execute_visual_strategy`**

将 `_execute_visual_strategy` 方法整体替换为：

```python
async def _execute_visual_strategy(
    self,
    strategy: Strategy,
    ctx: StrategyContext,
) -> Optional[str]:
    """执行可视化策略（支持多空四路信号）"""
    if not strategy.config_json:
        return None

    try:
        config = json.loads(strategy.config_json)
    except json.JSONDecodeError:
        logger.error(f"Invalid config_json for strategy {strategy.id}")
        return None

    klines = await ctx.get_klines(limit=100)
    if not klines:
        return None

    calculator = IndicatorCalculator(klines)
    position = await ctx.get_position()

    buy_conditions = config.get("buy_conditions", {})
    sell_conditions = config.get("sell_conditions", {})
    short_conditions = config.get("short_conditions")   # 可选，None 表示不做空
    cover_conditions = config.get("cover_conditions")   # 可选，None 表示依赖止盈止损

    if position is None:
        # 无持仓：先检查 buy，再检查 short（buy 优先）
        if self._check_conditions(buy_conditions, calculator):
            return "buy"
        if short_conditions and self._check_conditions(short_conditions, calculator):
            return "short"
        return None

    if position.side == "long":
        # 持多仓：检查卖出条件
        if self._check_conditions(sell_conditions, calculator):
            return "sell"
        return None

    if position.side == "short":
        # 持空仓：检查平空条件（未配置则返回 None，依赖止盈止损）
        if cover_conditions and self._check_conditions(cover_conditions, calculator):
            return "cover"
        return None

    return None
```

- [ ] **Step 5: 运行所有后端测试**

```bash
cd /home/autotrade/autotrade/backend
python3 -m pytest tests/ -v
```

预期：所有测试 `PASSED`

- [ ] **Step 6: 提交**

```bash
cd /home/autotrade/autotrade
git add backend/app/engine/executor.py backend/tests/test_executor_short.py
git commit -m "feat: route short/cover signals and extend visual strategy logic"
```

---

## Task 5: 前端 — 视觉策略编辑器类型 + 工具函数

**Files:**
- Modify: `frontend/src/components/visual-strategy-editor/types.ts`
- Modify: `frontend/src/components/visual-strategy-editor/utils.ts`
- Modify: `frontend/src/components/visual-strategy-editor/strategy-preview.tsx`
- Modify: `frontend/src/components/visual-strategy-editor/index.ts`

- [ ] **Step 1: 扩展 `StrategyConfig` 类型**

在 `frontend/src/components/visual-strategy-editor/types.ts` 中，将 `StrategyConfig` 接口改为：

```typescript
// 策略完整配置
export interface StrategyConfig {
  buy_conditions: ConditionGroup;
  sell_conditions: ConditionGroup;
  short_conditions?: ConditionGroup;  // 可选，不配置则不做空
  cover_conditions?: ConditionGroup;  // 可选，不配置则依赖止盈止损
}
```

- [ ] **Step 2: 更新 `deserializeConfig`**

在 `frontend/src/components/visual-strategy-editor/utils.ts` 中，将 `deserializeConfig` 改为：

```typescript
export function deserializeConfig(json: string): StrategyConfig {
  try {
    const parsed = JSON.parse(json);
    const config: StrategyConfig = {
      buy_conditions: normalizeGroup(parsed.buy_conditions ?? { logic: "AND", rules: [] }),
      sell_conditions: normalizeGroup(parsed.sell_conditions ?? { logic: "AND", rules: [] }),
    };
    if (parsed.short_conditions) {
      config.short_conditions = normalizeGroup(parsed.short_conditions);
    }
    if (parsed.cover_conditions) {
      config.cover_conditions = normalizeGroup(parsed.cover_conditions);
    }
    return config;
  } catch {
    return makeEmptyConfig();
  }
}
```

- [ ] **Step 3: 更新 `serializeConfig`（排除空的可选字段）**

将 `serializeConfig` 改为：

```typescript
export function serializeConfig(config: StrategyConfig): string {
  const obj: Record<string, unknown> = {
    buy_conditions: config.buy_conditions,
    sell_conditions: config.sell_conditions,
  };
  if (config.short_conditions && config.short_conditions.rules.length > 0) {
    obj.short_conditions = config.short_conditions;
  }
  if (config.cover_conditions && config.cover_conditions.rules.length > 0) {
    obj.cover_conditions = config.cover_conditions;
  }
  return JSON.stringify(obj);
}
```

- [ ] **Step 4: 更新 `generatePreviewText`**

将 `generatePreviewText` 改为：

```typescript
export function generatePreviewText(config: StrategyConfig): string {
  const buyLogic = config.buy_conditions.logic === "AND" ? "全部" : "任一";
  const sellLogic = config.sell_conditions.logic === "AND" ? "全部" : "任一";

  let text = `买入信号（满足${buyLogic}条件时买入）：\n${describeGroup(config.buy_conditions)}`;
  text += `\n\n卖出信号（满足${sellLogic}条件时卖出）：\n${describeGroup(config.sell_conditions)}`;

  if (config.short_conditions && config.short_conditions.rules.length > 0) {
    const shortLogic = config.short_conditions.logic === "AND" ? "全部" : "任一";
    text += `\n\n开空信号（满足${shortLogic}条件时开空）：\n${describeGroup(config.short_conditions)}`;
  }
  if (config.cover_conditions && config.cover_conditions.rules.length > 0) {
    const coverLogic = config.cover_conditions.logic === "AND" ? "全部" : "任一";
    text += `\n\n平空信号（满足${coverLogic}条件时平空）：\n${describeGroup(config.cover_conditions)}`;
  }

  return text;
}
```

- [ ] **Step 5: 读取 `strategy-preview.tsx` 确认无需修改**

`StrategyPreview` 只调用 `generatePreviewText(config)`，类型签名未变，无需修改。

- [ ] **Step 6: 提交**

```bash
cd /home/autotrade/autotrade
git add frontend/src/components/visual-strategy-editor/
git commit -m "feat: extend StrategyConfig type and utils for short/cover conditions"
```

---

## Task 6: 前端 — 策略新建/编辑页面添加开空/平空条件

**Files:**
- Modify: `frontend/src/app/strategies/new/page.tsx`
- Modify: `frontend/src/app/strategies/[id]/edit/page.tsx`

注意：`new/page.tsx` 和 `edit/page.tsx` 结构相同，参照 `new` 的改法同步到 `edit`。

- [ ] **Step 1: 在 new/page.tsx 添加开空/平空折叠区块**

在 `new/page.tsx` 的视觉策略 `TabsContent value="visual"` 中，在现有 `<StrategyPreview .../>` 之前插入：

```tsx
{/* 开空条件（可选折叠） */}
<details className="group">
  <summary className="cursor-pointer select-none text-sm font-medium text-slate-300 hover:text-white flex items-center gap-2 py-2">
    <span className="transition-transform group-open:rotate-90">▶</span>
    开空条件
    <span className="text-xs text-slate-500 font-normal">
      {visualConfig.short_conditions ? "已配置" : "未配置（策略不做空）"}
    </span>
  </summary>
  <div className="mt-2 space-y-2">
    {!visualConfig.short_conditions ? (
      <button
        type="button"
        onClick={() =>
          setVisualConfig({ ...visualConfig, short_conditions: makeEmptyGroup() })
        }
        className="text-sm text-blue-400 hover:text-blue-300"
      >
        + 添加开空条件
      </button>
    ) : (
      <>
        <ConditionGroupEditor
          group={visualConfig.short_conditions}
          onChange={(g) => setVisualConfig({ ...visualConfig, short_conditions: g })}
          label="开空条件"
        />
        <button
          type="button"
          onClick={() => {
            const { short_conditions, ...rest } = visualConfig;
            setVisualConfig(rest as typeof visualConfig);
          }}
          className="text-xs text-slate-500 hover:text-red-400"
        >
          移除开空条件
        </button>
      </>
    )}
  </div>
</details>

{/* 平空条件（可选折叠） */}
<details className="group">
  <summary className="cursor-pointer select-none text-sm font-medium text-slate-300 hover:text-white flex items-center gap-2 py-2">
    <span className="transition-transform group-open:rotate-90">▶</span>
    平空条件
    <span className="text-xs text-slate-500 font-normal">
      {visualConfig.cover_conditions ? "已配置" : "未配置（依赖止盈止损平空）"}
    </span>
  </summary>
  <div className="mt-2 space-y-2">
    {!visualConfig.cover_conditions ? (
      <button
        type="button"
        onClick={() =>
          setVisualConfig({ ...visualConfig, cover_conditions: makeEmptyGroup() })
        }
        className="text-sm text-blue-400 hover:text-blue-300"
      >
        + 添加平空条件
      </button>
    ) : (
      <>
        <ConditionGroupEditor
          group={visualConfig.cover_conditions}
          onChange={(g) => setVisualConfig({ ...visualConfig, cover_conditions: g })}
          label="平空条件"
        />
        <button
          type="button"
          onClick={() => {
            const { cover_conditions, ...rest } = visualConfig;
            setVisualConfig(rest as typeof visualConfig);
          }}
          className="text-xs text-slate-500 hover:text-red-400"
        >
          移除平空条件
        </button>
      </>
    )}
  </div>
</details>
```

同时，`makeEmptyGroup` 在当前 `new/page.tsx` 的 import 中**尚未引入**，必须添加。将导入行从：

```typescript
import {
  ConditionGroupEditor,
  StrategyPreview,
  serializeConfig,
  makeEmptyConfig,
} from "@/components/visual-strategy-editor";
```

改为：

```typescript
import {
  ConditionGroupEditor,
  StrategyPreview,
  serializeConfig,
  makeEmptyConfig,
  makeEmptyGroup,
} from "@/components/visual-strategy-editor";
```

- [ ] **Step 2: 对 edit/page.tsx 应用相同改动**

读取 `frontend/src/app/strategies/[id]/edit/page.tsx`，在 `deserializeConfig` 初始化 `visualConfig` 的位置确认 `short_conditions` / `cover_conditions` 会被正确读取（`deserializeConfig` 已在 Task 5 扩展，无需额外处理），然后在 visual tab 中插入与 Step 1 完全相同的两个 `<details>` 区块。

同时，将 `edit/page.tsx` 的 `import { ..., makeEmptyConfig }` 行也加入 `makeEmptyGroup`（与 Step 1 对 `new/page.tsx` 的改法完全一致，否则 TypeScript 编译会报错）。

- [ ] **Step 3: 提交**

```bash
cd /home/autotrade/autotrade
git add frontend/src/app/strategies/new/page.tsx frontend/src/app/strategies/[id]/edit/page.tsx
git commit -m "feat: add optional short/cover condition editors in strategy form"
```

---

## Task 7: 前端 — 日志空头标签（持仓页面暂为占位符，跳过）

**Files:**
- Modify: `frontend/src/app/triggers/page.tsx`

> **注意：** `frontend/src/app/strategies/[id]/page.tsx` 的持仓 Tab 目前是占位符（显示「持仓信息功能将在后续版本中支持」），尚无持仓列表渲染。方向徽章将在持仓列表功能实现时一并添加，本次只处理触发日志页。

- [ ] **Step 1: 扩展触发日志的 action badge**

在 `triggers/page.tsx` 的 `getActionBadge` 函数中，添加 `short`/`cover` case：

```typescript
const getActionBadge = (action?: string) => {
  switch (action) {
    case "buy":
      return <Badge className="bg-green-600">买入</Badge>;
    case "sell":
      return <Badge className="bg-red-600">卖出</Badge>;
    case "short":
      return <Badge className="bg-orange-600">开空</Badge>;
    case "cover":
      return <Badge className="bg-purple-600">平空</Badge>;
    default:
      return <Badge variant="secondary">观望</Badge>;
  }
};
```

- [ ] **Step 2: 提交**

```bash
cd /home/autotrade/autotrade
git add frontend/src/app/triggers/page.tsx
git commit -m "feat: add short/cover labels in trigger log"
```

---

## Task 8: 重新编译前端并重启

- [ ] **Step 1: 重新编译前端**

```bash
cd /home/autotrade/autotrade/frontend && npm run build
```

预期：`✓ Compiled successfully`（若有 TypeScript 错误，修复后再运行）

- [ ] **Step 2: 重启前端服务**

```bash
kill $(lsof -ti:13000) 2>/dev/null; sleep 2
nohup npm exec next start -- -H 0.0.0.0 -p 13000 > /home/autotrade/autotrade/logs/frontend.log 2>&1 &
```

- [ ] **Step 3: 冒烟测试**

```bash
# 后端测试
cd /home/autotrade/autotrade/backend
python3 -m pytest tests/ -v

# 前端冒烟
sleep 3
curl -s http://localhost:13000/ | grep -o "<title>.*</title>"
```

预期：后端所有测试通过；前端返回 HTML 页面。

- [ ] **Step 4: 提交**

```bash
cd /home/autotrade/autotrade
git add -A
git commit -m "chore: rebuild frontend for short selling feature"
```
