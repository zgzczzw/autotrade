# Simplify Trading Signals Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Simplify the trading signal system from 4 signals (buy/sell/short/cover) to 2 signals (buy/sell), with the system auto-determining the actual operation based on current position state.

**Architecture:** StrategyContext becomes the position-aware dispatch layer. `buy()` and `sell()` check current position and route to the appropriate simulator atomic operation. Simulator's 4 atomic operations remain unchanged. BacktestContext gets matching logic for short support.

**Tech Stack:** Python, SQLAlchemy async, pytest

**Spec:** `docs/superpowers/specs/2026-03-23-simplify-signals-design.md`

---

### Task 1: Rewrite StrategyContext.buy() and sell() with position-aware dispatch

**Files:**
- Modify: `backend/app/engine/executor.py:50-162`
- Test: `backend/tests/test_executor_short.py`

- [ ] **Step 1: Rewrite test file for new signal semantics**

Replace the entire test file `backend/tests/test_executor_short.py` with tests for the new behavior:

```python
"""测试 StrategyContext 持仓感知信号路由"""
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
    s.timeframe = "1h"
    return s


def make_kline(close=40000.0):
    return {"close": close, "open": 39000.0, "high": 41000.0, "low": 38000.0, "volume": 100.0}


@pytest.mark.asyncio
async def test_buy_no_position_opens_long():
    """空仓 + buy → execute_buy（开多）"""
    from app.engine.executor import StrategyContext

    strategy = make_strategy()
    db = AsyncMock()
    ctx = StrategyContext(strategy, db, current_kline=make_kline())

    with patch.object(ctx, "get_position", new_callable=AsyncMock, return_value=None), \
         patch("app.engine.executor.simulator") as mock_sim, \
         patch("app.engine.executor.market_data_service") as mock_mds:
        mock_mds.get_klines = AsyncMock(return_value=[make_kline()])
        buy_trigger = MagicMock(action="buy")
        mock_sim.execute_buy = AsyncMock(return_value=buy_trigger)

        result = await ctx.buy()

    mock_sim.execute_buy.assert_called_once()
    assert result == buy_trigger


@pytest.mark.asyncio
async def test_buy_holding_short_covers():
    """持空 + buy → execute_cover（平空），不开多"""
    from app.engine.executor import StrategyContext
    from app.models import Position

    strategy = make_strategy()
    db = AsyncMock()
    ctx = StrategyContext(strategy, db, current_kline=make_kline())

    short_pos = MagicMock(spec=Position, side="short")

    with patch.object(ctx, "get_position", new_callable=AsyncMock, return_value=short_pos), \
         patch("app.engine.executor.simulator") as mock_sim, \
         patch("app.engine.executor.market_data_service") as mock_mds:
        mock_mds.get_klines = AsyncMock(return_value=[make_kline()])
        cover_trigger = MagicMock(action="cover")
        mock_sim.execute_cover = AsyncMock(return_value=cover_trigger)
        mock_sim.execute_buy = AsyncMock()

        result = await ctx.buy()

    mock_sim.execute_cover.assert_called_once()
    mock_sim.execute_buy.assert_not_called()
    assert result == cover_trigger


@pytest.mark.asyncio
async def test_buy_holding_long_holds():
    """持多 + buy → hold（已持多，跳过）"""
    from app.engine.executor import StrategyContext
    from app.models import Position

    strategy = make_strategy()
    db = AsyncMock()
    ctx = StrategyContext(strategy, db, current_kline=make_kline())

    long_pos = MagicMock(spec=Position, side="long")

    with patch.object(ctx, "get_position", new_callable=AsyncMock, return_value=long_pos), \
         patch("app.engine.executor.simulator") as mock_sim, \
         patch("app.engine.executor.market_data_service") as mock_mds:
        mock_mds.get_klines = AsyncMock(return_value=[make_kline()])
        mock_sim.execute_buy = AsyncMock()
        mock_sim.execute_cover = AsyncMock()

        result = await ctx.buy()

    mock_sim.execute_buy.assert_not_called()
    mock_sim.execute_cover.assert_not_called()
    assert result is None


@pytest.mark.asyncio
async def test_sell_no_position_opens_short():
    """空仓 + sell → execute_short（开空）"""
    from app.engine.executor import StrategyContext

    strategy = make_strategy()
    db = AsyncMock()
    ctx = StrategyContext(strategy, db, current_kline=make_kline())

    with patch.object(ctx, "get_position", new_callable=AsyncMock, return_value=None), \
         patch("app.engine.executor.simulator") as mock_sim, \
         patch("app.engine.executor.market_data_service") as mock_mds:
        mock_mds.get_klines = AsyncMock(return_value=[make_kline()])
        short_trigger = MagicMock(action="short")
        mock_sim.execute_short = AsyncMock(return_value=short_trigger)

        result = await ctx.sell()

    mock_sim.execute_short.assert_called_once()
    assert result == short_trigger


@pytest.mark.asyncio
async def test_sell_holding_long_closes():
    """持多 + sell → execute_sell（平多）"""
    from app.engine.executor import StrategyContext
    from app.models import Position

    strategy = make_strategy()
    db = AsyncMock()
    ctx = StrategyContext(strategy, db, current_kline=make_kline())

    long_pos = MagicMock(spec=Position, side="long")

    with patch.object(ctx, "get_position", new_callable=AsyncMock, return_value=long_pos), \
         patch("app.engine.executor.simulator") as mock_sim, \
         patch("app.engine.executor.market_data_service") as mock_mds:
        mock_mds.get_klines = AsyncMock(return_value=[make_kline()])
        sell_trigger = MagicMock(action="sell")
        mock_sim.execute_sell = AsyncMock(return_value=sell_trigger)

        result = await ctx.sell()

    mock_sim.execute_sell.assert_called_once()
    assert result == sell_trigger


@pytest.mark.asyncio
async def test_sell_holding_short_holds():
    """持空 + sell → hold（已持空，跳过）"""
    from app.engine.executor import StrategyContext
    from app.models import Position

    strategy = make_strategy()
    db = AsyncMock()
    ctx = StrategyContext(strategy, db, current_kline=make_kline())

    short_pos = MagicMock(spec=Position, side="short")

    with patch.object(ctx, "get_position", new_callable=AsyncMock, return_value=short_pos), \
         patch("app.engine.executor.simulator") as mock_sim, \
         patch("app.engine.executor.market_data_service") as mock_mds:
        mock_mds.get_klines = AsyncMock(return_value=[make_kline()])
        mock_sim.execute_sell = AsyncMock()
        mock_sim.execute_short = AsyncMock()

        result = await ctx.sell()

    mock_sim.execute_sell.assert_not_called()
    mock_sim.execute_short.assert_not_called()
    assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_executor_short.py -v`
Expected: FAIL — current `buy()` when holding short does cover + buy (not cover only), `sell()` when empty returns hold (not short), etc.

- [ ] **Step 3: Rewrite StrategyContext.buy() and sell(), remove short() and cover()**

Replace lines 50-162 of `backend/app/engine/executor.py` (the `buy`, `sell`, `short`, `cover` methods) with:

```python
    async def buy(self, quantity: Optional[float] = None) -> Optional[TriggerLog]:
        """买入：空仓→开多，持空→平空，持多→跳过"""
        klines = await self.get_klines(limit=1)
        if not klines:
            logger.error("No kline data available for buy")
            return None

        price = self.current_kline["close"] if self.current_kline else klines[-1]["close"]
        position = await self.get_position()

        if position and position.side == "long":
            # 已持多，跳过
            return None

        if position and position.side == "short":
            # 持空 → 平空
            return await simulator.execute_cover(
                strategy_id=self.strategy.id,
                symbol=self.strategy.symbol,
                price=price,
                db=self.db,
                user_id=getattr(self.strategy, "user_id", None),
            )

        # 空仓 → 开多
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

    async def sell(self, quantity: Optional[float] = None) -> Optional[TriggerLog]:
        """卖出：空仓→开空，持多→平多，持空→跳过"""
        klines = await self.get_klines(limit=1)
        if not klines:
            logger.error("No kline data available for sell")
            return None

        price = self.current_kline["close"] if self.current_kline else klines[-1]["close"]
        position = await self.get_position()

        if position and position.side == "short":
            # 已持空，跳过
            return None

        if position and position.side == "long":
            # 持多 → 平多
            sell_size_pct = getattr(self.strategy, "sell_size_pct", 100.0) or 100.0
            return await simulator.execute_sell(
                strategy_id=self.strategy.id,
                symbol=self.strategy.symbol,
                price=price,
                db=self.db,
                sell_size_pct=sell_size_pct,
                user_id=getattr(self.strategy, "user_id", None),
            )

        # 空仓 → 开空
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
```

Also delete `_calculate_buy_quantity` method (lines 189-193) — it's unused.

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_executor_short.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/engine/executor.py backend/tests/test_executor_short.py
git commit -m "feat: rewrite StrategyContext buy/sell with position-aware dispatch

Remove short() and cover() methods. buy() now auto-covers when
holding short, sell() auto-opens short when empty."
```

---

### Task 2: Simplify executor signal routing and sandbox validation

**Files:**
- Modify: `backend/app/engine/executor.py:274-281`
- Modify: `backend/app/engine/sandbox.py:224-231`

- [ ] **Step 1: Simplify signal routing in executor**

In `backend/app/engine/executor.py`, replace lines 274-281:

```python
                    # 3. 执行交易信号
                    if signal == "buy":
                        trigger = await ctx.buy()
                    elif signal == "sell":
                        trigger = await ctx.sell()
```

Remove the `elif signal == "short"` and `elif signal == "cover"` branches.

- [ ] **Step 2: Update sandbox signal whitelist**

In `backend/app/engine/sandbox.py`, replace the signal validation (lines 228-231) in `call_on_tick`:

```python
                signal = instance.on_tick(data)
                if signal in ("buy", "sell", "hold"):
                    return signal
                if signal in ("short", "cover"):
                    logger.warning(
                        f"Strategy returned deprecated signal '{signal}', ignoring. "
                        f"Use 'buy'/'sell' instead."
                    )
                return None
```

Also update the docstring (line 224) from `"buy", "sell", "short", "cover", "hold", 或 None` to `"buy", "sell", "hold", 或 None`.

- [ ] **Step 3: Run existing tests to verify nothing breaks**

Run: `cd backend && python -m pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 4: Commit**

```bash
git add backend/app/engine/executor.py backend/app/engine/sandbox.py
git commit -m "refactor: simplify signal routing to buy/sell only

Remove short/cover branches from executor. Add deprecation warning
in sandbox for strategies still returning short/cover signals."
```

---

### Task 3: Simplify visual strategy signal logic

**Note:** Task 1 rewrites `test_executor_short.py` completely. The new tests in this task are appended to the file from Task 1. Tasks 1→2→3 must execute in order.

**Files:**
- Modify: `backend/app/engine/executor.py:311-358` (StrategyExecutor._execute_visual_strategy)
- Test: `backend/tests/test_executor_short.py` (append visual strategy tests)

- [ ] **Step 1: Write visual strategy tests (append to test file from Task 1)**

Append to `backend/tests/test_executor_short.py`:

```python
@pytest.mark.asyncio
async def test_visual_strategy_no_position_sell_opens_short():
    """可视化策略：无持仓，sell条件满足 → sell（开空）"""
    from app.engine.executor import StrategyExecutor, StrategyContext
    import json

    executor = StrategyExecutor()
    strategy = make_strategy()
    # buy_conditions won't match (PRICE > 999999), sell_conditions will match (PRICE > 100)
    strategy.config_json = json.dumps({
        "buy_conditions": {"logic": "AND", "rules": [{"indicator": "PRICE", "operator": ">", "value": "999999"}]},
        "sell_conditions": {"logic": "AND", "rules": [{"indicator": "PRICE", "operator": ">", "value": "100"}]},
    })

    db = AsyncMock()
    ctx = StrategyContext(strategy, db, current_kline=make_kline())

    with patch.object(ctx, "get_position", new_callable=AsyncMock, return_value=None), \
         patch("app.engine.executor.market_data_service") as mock_mds:
        mock_mds.get_klines = AsyncMock(return_value=[make_kline()] * 100)
        signal = await executor._execute_visual_strategy(strategy, ctx)

    assert signal == "sell"


@pytest.mark.asyncio
async def test_visual_strategy_short_position_buy_covers():
    """可视化策略：持空仓，buy条件满足 → buy（平空）"""
    from app.engine.executor import StrategyExecutor, StrategyContext
    from app.models import Position
    import json

    executor = StrategyExecutor()
    strategy = make_strategy()
    strategy.config_json = json.dumps({
        "buy_conditions": {"logic": "AND", "rules": [{"indicator": "PRICE", "operator": ">", "value": "100"}]},
        "sell_conditions": {"logic": "AND", "rules": []},
    })

    db = AsyncMock()
    ctx = StrategyContext(strategy, db, current_kline=make_kline())

    short_pos = MagicMock(spec=Position, side="short")

    with patch.object(ctx, "get_position", new_callable=AsyncMock, return_value=short_pos), \
         patch("app.engine.executor.market_data_service") as mock_mds:
        mock_mds.get_klines = AsyncMock(return_value=[make_kline()] * 100)
        signal = await executor._execute_visual_strategy(strategy, ctx)

    assert signal == "buy"


@pytest.mark.asyncio
async def test_visual_strategy_no_position_buy():
    """可视化策略：无持仓，买入条件满足 → buy"""
    from app.engine.executor import StrategyExecutor, StrategyContext
    import json

    executor = StrategyExecutor()
    strategy = make_strategy()
    strategy.config_json = json.dumps({
        "buy_conditions": {"logic": "AND", "rules": [{"indicator": "PRICE", "operator": ">", "value": "100"}]},
        "sell_conditions": {"logic": "AND", "rules": [{"indicator": "PRICE", "operator": ">", "value": "100"}]},
    })

    db = AsyncMock()
    ctx = StrategyContext(strategy, db, current_kline=make_kline())

    with patch.object(ctx, "get_position", new_callable=AsyncMock, return_value=None), \
         patch("app.engine.executor.market_data_service") as mock_mds:
        mock_mds.get_klines = AsyncMock(return_value=[make_kline()] * 100)
        signal = await executor._execute_visual_strategy(strategy, ctx)

    # buy has priority over sell when both conditions match
    assert signal == "buy"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_executor_short.py::test_visual_strategy_no_position_sell_opens_short tests/test_executor_short.py::test_visual_strategy_short_position_buy_covers -v`
Expected: FAIL (current code returns "short"/"cover" instead of "sell"/"buy")

- [ ] **Step 3: Update `_execute_visual_strategy` method**

Replace the method body (lines 311-358 of `backend/app/engine/executor.py`):

```python
    async def _execute_visual_strategy(
        self,
        strategy: Strategy,
        ctx: StrategyContext,
    ) -> Optional[str]:
        """执行可视化策略（buy/sell 两路信号，根据持仓自动判断操作）"""
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

        if position is None:
            # 无持仓：buy_conditions → buy（开多），sell_conditions → sell（开空）
            if self._check_conditions(buy_conditions, calculator):
                return "buy"
            if self._check_conditions(sell_conditions, calculator):
                return "sell"
            return None

        if position.side == "long":
            # 持多：sell_conditions → sell（平多）
            if self._check_conditions(sell_conditions, calculator):
                return "sell"
            return None

        if position.side == "short":
            # 持空：buy_conditions → buy（平空）
            if self._check_conditions(buy_conditions, calculator):
                return "buy"
            return None

        return None
```

- [ ] **Step 4: Run tests**

Run: `cd backend && python -m pytest tests/test_executor_short.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/engine/executor.py backend/tests/test_executor_short.py
git commit -m "refactor: simplify visual strategy to buy/sell signals only

Remove short_conditions/cover_conditions. Sell conditions now open
short when empty, buy conditions now cover when holding short."
```

---

### Task 4: Add short support to BacktestContext

**Files:**
- Modify: `backend/app/engine/backtester.py:95-176` (BacktestContext.buy/sell/get_position)
- Test: `backend/tests/test_backtester_short.py` (new)

- [ ] **Step 1: Write failing tests for BacktestContext short support**

Create `backend/tests/test_backtester_short.py`:

```python
"""测试 BacktestContext 空头交易支持"""
import pytest
from datetime import datetime
from unittest.mock import MagicMock

from app.engine.backtester import BacktestContext, VirtualAccount
from app.models import Position


def make_strategy():
    s = MagicMock()
    s.id = 1
    s.symbol = "BTCUSDT"
    s.position_size = 1000.0
    s.position_size_type = "fixed"
    s.sell_size_pct = 100.0
    s.stop_loss = 5.0
    s.take_profit = 10.0
    return s


def make_kline(close=40000.0, time=None):
    return {
        "close": close, "open": 39000.0, "high": 41000.0,
        "low": 38000.0, "volume": 100.0,
        "open_time": time or datetime(2026, 1, 1),
    }


class TestSellOpensShort:
    def test_sell_no_position_opens_short(self):
        """空仓 + sell → 开空"""
        account = VirtualAccount(100000.0)
        strategy = make_strategy()
        kline = make_kline(40000.0)
        ctx = BacktestContext(strategy, account, kline, [kline])

        result = ctx.sell()

        assert result is True
        assert len(account.positions) == 1
        assert account.positions[0].side == "short"
        assert account.positions[0].entry_price == 40000.0
        # 保证金被锁定
        assert account.balance < 100000.0

    def test_sell_holding_short_holds(self):
        """持空 + sell → 返回 False"""
        account = VirtualAccount(100000.0)
        strategy = make_strategy()
        kline = make_kline(40000.0)

        short_pos = Position(
            strategy_id=1, symbol="BTCUSDT", side="short",
            entry_price=40000.0, quantity=0.025,
        )
        account.positions.append(short_pos)
        account.balance = 99000.0

        ctx = BacktestContext(strategy, account, kline, [kline])
        result = ctx.sell()

        assert result is False


class TestBuyCoversShort:
    def test_buy_holding_short_covers(self):
        """持空 + buy → 平空"""
        account = VirtualAccount(100000.0)
        strategy = make_strategy()

        # 开空 @ 40000，当前价 38000（盈利）
        short_pos = Position(
            strategy_id=1, symbol="BTCUSDT", side="short",
            entry_price=40000.0, quantity=0.025,
        )
        account.positions.append(short_pos)
        account.balance = 99000.0  # 1000 margin locked

        kline = make_kline(38000.0)
        ctx = BacktestContext(strategy, account, kline, [kline])

        result = ctx.buy()

        assert result is True
        assert len(account.positions) == 0
        # PnL = (40000 - 38000) * 0.025 = 50
        assert account.total_pnl == pytest.approx(50.0)

    def test_buy_holding_long_holds(self):
        """持多 + buy → 返回 False"""
        account = VirtualAccount(100000.0)
        strategy = make_strategy()
        kline = make_kline(40000.0)

        long_pos = Position(
            strategy_id=1, symbol="BTCUSDT", side="long",
            entry_price=39000.0, quantity=0.025,
        )
        account.positions.append(long_pos)

        ctx = BacktestContext(strategy, account, kline, [kline])
        result = ctx.buy()

        assert result is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_backtester_short.py -v`
Expected: FAIL

- [ ] **Step 3: Implement position-aware buy/sell in BacktestContext**

Replace `buy()` and `sell()` in `backend/app/engine/backtester.py` (lines 95-162):

```python
    def buy(self, quantity: Optional[float] = None, trigger_reason: str = "") -> bool:
        """买入：空仓→开多，持空→平空，持多→跳过"""
        price = self.current_kline["close"]
        position = self.get_position()

        if position and position.side == "long":
            return False

        if position and position.side == "short":
            # 平空
            raw_pos = self.account.positions[0]
            pnl = (raw_pos.entry_price - price) * raw_pos.quantity
            margin_returned = raw_pos.entry_price * raw_pos.quantity
            self.account.balance += margin_returned + pnl
            self.account.total_pnl += pnl
            raw_pos.pnl = pnl
            raw_pos.current_price = price
            raw_pos.closed_at = self.current_kline["open_time"]
            self.account.positions.remove(raw_pos)
            self.account.trades.append({
                "time": self.current_kline["open_time"].isoformat(),
                "side": "cover",
                "price": price,
                "quantity": raw_pos.quantity,
                "pnl": pnl,
                "trigger": trigger_reason,
            })
            return True

        # 空仓 → 开多
        if quantity is not None:
            qty = quantity
        elif self.strategy.position_size_type == "percent":
            qty = self.account.balance * self.strategy.position_size / 100.0 / price
        else:
            qty = self.strategy.position_size / price

        cost = qty * price
        if self.account.balance < cost:
            return False

        self.account.balance -= cost
        position = Position(
            strategy_id=self.strategy.id,
            symbol=self.strategy.symbol,
            side="long",
            entry_price=price,
            quantity=qty,
            opened_at=self.current_kline["open_time"],
        )
        self.account.positions.append(position)
        self.account.trades.append({
            "time": self.current_kline["open_time"].isoformat(),
            "side": "buy",
            "price": price,
            "quantity": qty,
            "pnl": 0,
            "trigger": trigger_reason,
        })
        return True

    def sell(self, quantity: Optional[float] = None, trigger_reason: str = "") -> bool:
        """卖出：空仓→开空，持多→平多，持空→跳过"""
        price = self.current_kline["close"]
        position = self.get_position()

        if position and position.side == "short":
            return False

        if position and position.side == "long":
            # 平多
            raw_pos = self.account.positions[0]
            sell_size_pct = getattr(self.strategy, "sell_size_pct", 100.0) or 100.0
            sell_qty = quantity if quantity is not None else raw_pos.quantity * min(sell_size_pct, 100.0) / 100.0

            pnl = (price - raw_pos.entry_price) * sell_qty
            self.account.balance += price * sell_qty
            self.account.total_pnl += pnl

            self.account.trades.append({
                "time": self.current_kline["open_time"].isoformat(),
                "side": "sell",
                "price": price,
                "quantity": sell_qty,
                "pnl": pnl,
                "trigger": trigger_reason,
            })

            if sell_size_pct >= 100.0 or (quantity is None and sell_qty >= raw_pos.quantity):
                raw_pos.current_price = price
                raw_pos.pnl = pnl
                raw_pos.closed_at = self.current_kline["open_time"]
                self.account.positions.remove(raw_pos)
            else:
                raw_pos.quantity -= sell_qty
            return True

        # 空仓 → 开空
        if quantity is not None:
            qty = quantity
        elif self.strategy.position_size_type == "percent":
            qty = self.account.balance * self.strategy.position_size / 100.0 / price
        else:
            qty = self.strategy.position_size / price

        margin = qty * price
        if self.account.balance < margin:
            return False

        self.account.balance -= margin
        position = Position(
            strategy_id=self.strategy.id,
            symbol=self.strategy.symbol,
            side="short",
            entry_price=price,
            quantity=qty,
            opened_at=self.current_kline["open_time"],
        )
        self.account.positions.append(position)
        self.account.trades.append({
            "time": self.current_kline["open_time"].isoformat(),
            "side": "short",
            "price": price,
            "quantity": qty,
            "pnl": 0,
            "trigger": trigger_reason,
        })
        return True
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && python -m pytest tests/test_backtester_short.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/engine/backtester.py backend/tests/test_backtester_short.py
git commit -m "feat: add short support to BacktestContext buy/sell

buy() covers short positions, sell() opens short when empty.
No auto-flip — each signal only does one operation."
```

---

### Task 5: Fix backtest stop-loss/take-profit, force-close, and equity curve for shorts

**Files:**
- Modify: `backend/app/engine/backtester.py:534-556` (_check_stop_loss_take_profit)
- Modify: `backend/app/engine/backtester.py:267-283` (force-close)
- Modify: `backend/app/engine/backtester.py:395-401, 517-523` (equity curve)
- Modify: `backend/app/engine/backtester.py:741-751` (_calculate_avg_hold_time)
- Test: `backend/tests/test_backtester_short.py` (append)

- [ ] **Step 1: Add tests for short stop-loss, force-close, equity curve**

Append to `backend/tests/test_backtester_short.py`:

```python
from app.engine.backtester import BacktestEngine, VirtualAccount


class TestShortStopLossTakeProfit:
    @pytest.mark.asyncio
    async def test_short_stop_loss(self):
        """空头止损：价格上涨超过阈值 → ctx.buy()"""
        account = VirtualAccount(100000.0)
        strategy = make_strategy()
        strategy.stop_loss = 5.0
        strategy.take_profit = 10.0

        short_pos = Position(
            strategy_id=1, symbol="BTCUSDT", side="short",
            entry_price=40000.0, quantity=0.025,
        )
        account.positions.append(short_pos)
        account.balance = 99000.0

        # Price rose 6% → should trigger stop loss
        kline = make_kline(42400.0)  # +6%
        ctx = BacktestContext(strategy, account, kline, [kline])

        engine = BacktestEngine()
        result = await engine._check_stop_loss_take_profit(ctx, strategy)

        assert result is True
        assert len(account.positions) == 0  # position closed

    @pytest.mark.asyncio
    async def test_short_take_profit(self):
        """空头止盈：价格下跌超过阈值 → ctx.buy()"""
        account = VirtualAccount(100000.0)
        strategy = make_strategy()
        strategy.stop_loss = 5.0
        strategy.take_profit = 10.0

        short_pos = Position(
            strategy_id=1, symbol="BTCUSDT", side="short",
            entry_price=40000.0, quantity=0.025,
        )
        account.positions.append(short_pos)
        account.balance = 99000.0

        # Price dropped 11% → should trigger take profit
        kline = make_kline(35600.0)  # -11%
        ctx = BacktestContext(strategy, account, kline, [kline])

        engine = BacktestEngine()
        result = await engine._check_stop_loss_take_profit(ctx, strategy)

        assert result is True
        assert len(account.positions) == 0


class TestEquityCurve:
    def test_short_position_equity_value(self):
        """空头持仓市值 = 保证金 + 浮动盈亏"""
        account = VirtualAccount(100000.0)

        short_pos = Position(
            strategy_id=1, symbol="BTCUSDT", side="short",
            entry_price=40000.0, quantity=0.025,
        )
        account.positions.append(short_pos)
        account.balance = 99000.0  # 1000 margin locked

        current_price = 38000.0
        # short value = entry_price * qty + (entry_price - current_price) * qty
        #             = 40000 * 0.025 + (40000 - 38000) * 0.025
        #             = 1000 + 50 = 1050
        expected_value = short_pos.entry_price * short_pos.quantity + \
                        (short_pos.entry_price - current_price) * short_pos.quantity
        assert expected_value == pytest.approx(1050.0)

        total = account.balance + expected_value
        assert total == pytest.approx(100050.0)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd backend && python -m pytest tests/test_backtester_short.py -v`
Expected: Stop-loss/take-profit tests FAIL (current code only handles long positions)

- [ ] **Step 3: Update `_check_stop_loss_take_profit` for shorts**

Replace `_check_stop_loss_take_profit` in `backend/app/engine/backtester.py` (lines 534-556):

```python
    async def _check_stop_loss_take_profit(
        self,
        ctx: BacktestContext,
        strategy: Strategy,
    ) -> bool:
        """检查止盈止损，返回 True 表示已触发（本 K 线跳过策略信号）"""
        position = ctx.get_position()
        if not position:
            return False

        current_price = ctx.current_kline["close"]
        entry_price = position.entry_price
        price_change_pct = (current_price - entry_price) / entry_price * 100

        if position.side == "long":
            if strategy.stop_loss and price_change_pct <= -strategy.stop_loss:
                ctx.sell(trigger_reason=f"止损 ({price_change_pct:+.2f}%)")
                return True
            if strategy.take_profit and price_change_pct >= strategy.take_profit:
                ctx.sell(trigger_reason=f"止盈 ({price_change_pct:+.2f}%)")
                return True
        elif position.side == "short":
            if strategy.stop_loss and price_change_pct >= strategy.stop_loss:
                ctx.buy(trigger_reason=f"止损 ({price_change_pct:+.2f}%)")
                return True
            if strategy.take_profit and price_change_pct <= -strategy.take_profit:
                ctx.buy(trigger_reason=f"止盈 ({price_change_pct:+.2f}%)")
                return True

        return False
```

- [ ] **Step 4: Update force-close at backtest end**

Replace lines 267-283 of `backend/app/engine/backtester.py`:

```python
            # 回测结束：强制平仓所有持仓
            if account.positions:
                last_kline = primary_klines[-1]
                for pos in list(account.positions):
                    price = last_kline["close"]
                    if pos.side == "long":
                        pnl = (price - pos.entry_price) * pos.quantity
                        account.balance += price * pos.quantity
                    else:  # short
                        pnl = (pos.entry_price - price) * pos.quantity
                        account.balance += pos.entry_price * pos.quantity + pnl
                    account.total_pnl += pnl
                    account.trades.append({
                        "time": last_kline["open_time"].isoformat(),
                        "side": "sell" if pos.side == "long" else "cover",
                        "price": price,
                        "quantity": pos.quantity,
                        "pnl": pnl,
                        "trigger": "回测结束平仓",
                    })
                    account.positions.remove(pos)
                logger.info(f"回测结束：已平仓所有持仓，累计盈亏: {account.total_pnl:.2f}")
```

- [ ] **Step 5: Update equity curve calculation**

In both `_run_single_tf_loop` and `_run_multitf_code_loop`, update the equity curve calculation. The current code:
```python
total_value = account.balance + sum(
    p.quantity * kline["close"] for p in account.positions
)
```

Replace with:
```python
total_value = account.balance + sum(
    p.quantity * kline["close"] if p.side == "long"
    else p.entry_price * p.quantity + (p.entry_price - kline["close"]) * p.quantity
    for p in account.positions
)
```

This appears in two places:
1. `_run_single_tf_loop` (around line 395)
2. `_run_multitf_code_loop` (around lines 456 and 517)

- [ ] **Step 6: Update `_calculate_avg_hold_time` for short trades**

Replace `_calculate_avg_hold_time` (lines 741-751):

```python
    def _calculate_avg_hold_time(self, trades: List[dict]) -> Optional[int]:
        hold_times = []
        open_time = None
        for trade in trades:
            if trade["side"] in ("buy", "short"):
                open_time = datetime.fromisoformat(trade["time"])
            elif trade["side"] in ("sell", "cover") and open_time:
                close_time = datetime.fromisoformat(trade["time"])
                hold_times.append(int((close_time - open_time).total_seconds()))
                open_time = None
        return int(sum(hold_times) / len(hold_times)) if hold_times else None
```

- [ ] **Step 7: Run all tests**

Run: `cd backend && python -m pytest tests/test_backtester_short.py tests/test_executor_short.py -v`
Expected: All tests PASS

- [ ] **Step 8: Commit**

```bash
git add backend/app/engine/backtester.py backend/tests/test_backtester_short.py
git commit -m "feat: add short support to backtest engine

Support short stop-loss/take-profit, correct equity curve for short
positions, fix force-close PnL, and extend hold time stats."
```

---

### Task 6: Update strategy documentation

**Files:**
- Modify: `docs/strategies.md`

- [ ] **Step 1: Add signal semantics section to docs/strategies.md**

After the "## 使用说明" section (before "### 注意事项"), add:

```markdown
### 信号说明

策略只需要返回两种信号：

- `"buy"` — 买入信号
- `"sell"` — 卖出信号
- `None` — 不操作

系统会根据当前持仓状态自动判断实际操作：

| 当前持仓 | buy | sell |
|---------|-----|------|
| 空仓 | 开多 | 开空 |
| 持多 | 跳过 | 平多 |
| 持空 | 平空 | 跳过 |

不需要手动判断持仓状态来决定返回什么信号。策略逻辑只需关注"此时应该买入还是卖出"。
```

- [ ] **Step 2: Commit**

```bash
git add docs/strategies.md
git commit -m "docs: add signal semantics to strategy guide"
```

---

### Task 7: Run full test suite and verify

- [ ] **Step 1: Run all backend tests**

Run: `cd backend && python -m pytest tests/ -v`
Expected: All tests PASS

- [ ] **Step 2: Verify no remaining references to ctx.short() or ctx.cover()**

Run: `grep -rn "ctx\.short\(\)\|ctx\.cover\(\)" backend/app/` — should return no results.

Run: `grep -rn "\.short()\|\.cover()" backend/app/engine/` — should only match simulator calls, not StrategyContext/BacktestContext.

- [ ] **Step 3: Final commit if any fixes needed**

Only if tests revealed issues that needed fixing.
