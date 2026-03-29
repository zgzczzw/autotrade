# Multi-Symbol Strategy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Enable each strategy to support multiple trading pairs (symbols), running the same logic independently on each pair.

**Architecture:** Add a `strategy_symbols` association table. Scheduler registers jobs per (strategy, symbol, timeframe) tuple. Executor and backtester receive an explicit `symbol` parameter instead of reading `strategy.symbol`. Frontend converts single-symbol inputs to multi-select tag inputs.

**Tech Stack:** Python/FastAPI/SQLAlchemy (backend), Next.js/React/TypeScript (frontend), SQLite

**Spec:** `docs/superpowers/specs/2026-03-29-multi-symbol-strategy-design.md`

---

## File Structure

### Backend — New Files
| File | Responsibility |
|------|---------------|
| (none) | All changes fit into existing files |

### Backend — Modified Files
| File | Changes |
|------|---------|
| `backend/app/models.py` | Add `StrategySymbol` model, add `symbols` relationship to `Strategy`, add `symbol` column to `TriggerLog`, add `batch_id` column to `BacktestResult` |
| `backend/app/schemas.py` | Modify `StrategyBase` (remove `symbol`), `StrategyCreate` (add `symbols: List[str]`), `StrategyUpdate` (add `symbols`), `StrategyResponse` (add `symbols`), `TriggerLogResponse` (add `symbol`), `BacktestResponse` (add `batch_id`) |
| `backend/app/database.py` | Add migration for `strategy_symbols` table, `trigger_logs.symbol`, `backtest_results.batch_id`, backfill data |
| `backend/app/routers/strategies.py` | Update create/update/list/detail/export/import to handle `symbols` via association table; add `symbol` query filter; use `selectinload` |
| `backend/app/routers/triggers.py` | Add `symbol` query filter; include `symbol` in response |
| `backend/app/routers/backtests.py` | Change to multi-symbol backtest loop; add batch delete endpoint; enhance status endpoint with progress |
| `backend/app/routers/dashboard.py` | Include `symbol` in trigger responses |
| `backend/app/engine/scheduler.py` | Job ID includes symbol; register jobs per (strategy, symbol, timeframe); `_execute_strategy` receives symbol; use `selectinload` |
| `backend/app/engine/executor.py` | `StrategyContext` receives `symbol`; all `strategy.symbol` → `self.symbol`; instance key = `(strategy_id, symbol)`; `release_instance` clears all instances for strategy |
| `backend/app/engine/backtester.py` | `run_backtest` receives `symbol` param; `BacktestContext` receives `symbol`; all `strategy.symbol` → `symbol`; add `run_multi_backtest` to `BacktestEngine` with progress tracking |
| `backend/app/engine/sandbox.py` | `data["symbol"]` uses `context.symbol` instead of `context.strategy.symbol` (1-line change in `SandboxExecutor.execute` if applicable) |
| `backend/app/services/simulator.py` | Add `symbol=symbol` to every `TriggerLog(...)` constructor |

### Frontend — Modified Files
| File | Changes |
|------|---------|
| `frontend/src/lib/api.ts` | Add `deleteBatchBacktest`, update `fetchTriggers` to accept `symbol` param, add `fetchBacktestStatus` |
| `frontend/src/components/symbol-selector.tsx` | New `MultiSymbolSelector` component (tag-based multi-select) |
| `frontend/src/app/strategies/new/page.tsx` | Replace single `SymbolSelector` with `MultiSymbolSelector`; send `symbols` array in API |
| `frontend/src/app/strategies/[id]/edit/page.tsx` | Replace single symbol display with `MultiSymbolSelector`; send `symbols` in update |
| `frontend/src/app/strategies/page.tsx` | Display symbol tags; add symbol filter dropdown |
| `frontend/src/app/strategies/[id]/page.tsx` | Overview: show symbol tags. Triggers: add symbol switcher. Positions: table for multiple open positions |
| `frontend/src/app/triggers/page.tsx` | Add `交易对` column; add symbol filter |
| `frontend/src/app/page.tsx` | Show symbol in recent triggers |
| `frontend/src/components/backtest-panel.tsx` | Handle `List[BacktestResponse]`; batch grouping by `batch_id`; symbol tabs; progress display |

---

## Task 1: Data Model — `StrategySymbol` and Column Additions

**Files:**
- Modify: `backend/app/models.py:1-206`

- [ ] **Step 1: Add `StrategySymbol` model and update relationships**

In `models.py`, add imports for `Index`, `PrimaryKeyConstraint` at line 8. Add the `StrategySymbol` class after the `Strategy` class. Add `symbols` relationship to `Strategy`.

```python
# In imports (line 7-10), add Index and PrimaryKeyConstraint:
from sqlalchemy import (
    JSON, Boolean, Column, DateTime, Float, ForeignKey, Index, Integer,
    PrimaryKeyConstraint, String, Text, UniqueConstraint, func
)

# After Strategy class (after line 77), add:
class StrategySymbol(Base):
    """策略-交易对关联表"""
    __tablename__ = "strategy_symbols"

    strategy_id = Column(Integer, ForeignKey("strategies.id"), nullable=False)
    symbol = Column(String, nullable=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        PrimaryKeyConstraint("strategy_id", "symbol"),
        Index("ix_strategy_symbols_symbol", "symbol"),
    )

    strategy = relationship("Strategy", back_populates="symbols")

# In Strategy class, add relationship after line 77:
    symbols = relationship("StrategySymbol", back_populates="strategy", cascade="all, delete-orphan")
```

- [ ] **Step 2: Add `symbol` column to `TriggerLog`**

After line 93 (`simulated_pnl`), add:
```python
    symbol = Column(String, nullable=True)
```

- [ ] **Step 3: Add `batch_id` column to `BacktestResult`**

After line 200 (`klines`), add:
```python
    batch_id = Column(String, nullable=True, index=True)
```

- [ ] **Step 4: Verify model changes load correctly**

Run: `cd /home/autotrade/autotrade/backend && source venv/bin/activate && python -c "from app.models import StrategySymbol, Strategy, TriggerLog, BacktestResult; print('Models OK')"`
Expected: `Models OK`

- [ ] **Step 5: Commit**

```bash
git add backend/app/models.py
git commit -m "feat: add StrategySymbol model, symbol to TriggerLog, batch_id to BacktestResult"
```

---

## Task 2: Database Migration

**Files:**
- Modify: `backend/app/database.py:20-98`

- [ ] **Step 1: Add migration SQL statements**

In `database.py`, add these migrations to the `migrations` list (after line 34):

```python
            # Multi-symbol strategy support
            "ALTER TABLE trigger_logs ADD COLUMN symbol VARCHAR",
            "ALTER TABLE backtest_results ADD COLUMN batch_id VARCHAR",
```

- [ ] **Step 2: Add backfill logic for `strategy_symbols`**

After the admin user backfill section (after line 98, before `await session.commit()`), add:

```python
        # Backfill strategy_symbols from existing strategies
        from app.models import StrategySymbol
        existing_symbols = await session.execute(
            select(StrategySymbol).limit(1)
        )
        if existing_symbols.scalar_one_or_none() is None:
            # First run after migration: copy strategy.symbol → strategy_symbols
            all_strategies = await session.execute(select(Strategy))
            for s in all_strategies.scalars().all():
                session.add(StrategySymbol(
                    strategy_id=s.id,
                    symbol=s.symbol or "BTCUSDT",
                ))

        # Backfill trigger_logs.symbol from strategy.symbol
        await session.execute(
            text("""
                UPDATE trigger_logs SET symbol = (
                    SELECT strategies.symbol FROM strategies
                    WHERE strategies.id = trigger_logs.strategy_id
                ) WHERE trigger_logs.symbol IS NULL
            """)
        )
```

- [ ] **Step 3: Test migration runs without errors**

Run: `cd /home/autotrade/autotrade/backend && source venv/bin/activate && python -c "import asyncio; from app.database import init_db; asyncio.run(init_db()); print('Migration OK')"`
Expected: `Migration OK`

- [ ] **Step 4: Commit**

```bash
git add backend/app/database.py
git commit -m "feat: add migration for strategy_symbols table and trigger_logs.symbol backfill"
```

---

## Task 3: Schema Changes

**Files:**
- Modify: `backend/app/schemas.py:1-298`

- [ ] **Step 1: Update imports**

At line 8, add `field_validator`:
```python
from pydantic import BaseModel, ConfigDict, Field, field_validator
```

- [ ] **Step 2: Remove `symbol` from `StrategyBase`**

Remove line 17 (`symbol: str = Field(..., min_length=1)`).

- [ ] **Step 3: Update `StrategyCreate` to accept `symbols` list**

Replace `StrategyCreate` (lines 27-30):
```python
class StrategyCreate(StrategyBase):
    """创建策略请求"""
    symbols: List[str] = Field(..., min_length=1)
    config_json: Optional[str] = None
    code: Optional[str] = None

    @field_validator("symbols")
    @classmethod
    def deduplicate_symbols(cls, v):
        deduped = list(dict.fromkeys(v))
        if not deduped:
            raise ValueError("至少需要一个交易对")
        return deduped
```

- [ ] **Step 4: Add `symbols` to `StrategyUpdate`**

After line 43 (`notify_enabled`), add:
```python
    symbols: Optional[List[str]] = None
```

- [ ] **Step 5: Update `StrategyResponse` to include `symbols`**

Add field after line 50 (inside `StrategyResponse`):
```python
    symbols: List[str] = []
```

- [ ] **Step 6: Add `symbol` to `TriggerLogResponse`**

After line 91 (`strategy_name`), add:
```python
    symbol: Optional[str] = None
```

- [ ] **Step 7: Add `batch_id` to `BacktestResponse`**

After line 201 (`created_at`), add:
```python
    batch_id: Optional[str] = None
```

- [ ] **Step 8: Verify schemas parse correctly**

Run: `cd /home/autotrade/autotrade/backend && source venv/bin/activate && python -c "from app.schemas import StrategyCreate, StrategyResponse, TriggerLogResponse, BacktestResponse; print('Schemas OK')"`
Expected: `Schemas OK`

- [ ] **Step 9: Commit**

```bash
git add backend/app/schemas.py
git commit -m "feat: update schemas for multi-symbol support (symbols list, trigger symbol, batch_id)"
```

---

## Task 4: Strategy Routes — Create, Update, List, Detail

**Files:**
- Modify: `backend/app/routers/strategies.py:1-408`

- [ ] **Step 1: Add imports**

Add to imports at top:
```python
from sqlalchemy.orm import selectinload
from app.models import Strategy, StrategySymbol, User
```

- [ ] **Step 2: Helper function for StrategyResponse conversion**

Add after `router` definition (line 31):
```python
def _strategy_to_response(strategy: Strategy, **extra) -> StrategyResponse:
    """Convert Strategy ORM + symbols relationship to StrategyResponse."""
    resp = StrategyResponse.model_validate(strategy)
    resp.symbols = [s.symbol for s in strategy.symbols]
    for k, v in extra.items():
        setattr(resp, k, v)
    return resp
```

- [ ] **Step 3: Update `list_strategies` — add `selectinload` and `symbol` filter**

In `list_strategies`, add optional `symbol` query param and update the query:

```python
@router.get("/strategies", response_model=StrategyList)
async def list_strategies(
    status: Optional[str] = Query(None, description="筛选状态: running/stopped/error"),
    symbol: Optional[str] = Query(None, description="筛选交易对"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取策略列表"""
    query = select(Strategy).where(Strategy.user_id == current_user.id)

    if status:
        query = query.where(Strategy.status == status)
    if symbol:
        query = query.join(StrategySymbol).where(StrategySymbol.symbol == symbol)

    # 总数
    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar()

    # 分页
    query = query.options(selectinload(Strategy.symbols))
    query = query.offset((page - 1) * page_size).limit(page_size)
    query = query.order_by(Strategy.created_at.desc())

    result = await db.execute(query)
    items = result.scalars().unique().all()

    # 批量查询每个策略的触发次数
    from app.models import TriggerLog
    strategy_ids = [s.id for s in items]
    if strategy_ids:
        tc_result = await db.execute(
            select(TriggerLog.strategy_id, func.count())
            .where(TriggerLog.strategy_id.in_(strategy_ids))
            .group_by(TriggerLog.strategy_id)
        )
        trigger_counts = dict(tc_result.all())
    else:
        trigger_counts = {}

    response_items = []
    for item in items:
        resp = _strategy_to_response(item, trigger_count=trigger_counts.get(item.id, 0))
        response_items.append(resp)

    return StrategyList(
        items=response_items,
        total=total,
        page=page,
        page_size=page_size,
    )
```

- [ ] **Step 4: Update `create_strategy` — handle `symbols` list**

Replace the create endpoint to pop `symbols`, create `StrategySymbol` rows:

```python
@router.post("/strategies", response_model=StrategyResponse, status_code=status.HTTP_201_CREATED)
async def create_strategy(
    data: StrategyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建新策略"""
    if data.type == "visual" and not data.config_json:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="可视化策略必须提供 config_json",
        )
    if data.type == "code" and not data.code:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="代码策略必须提供 code",
        )

    if data.type == "code" and data.code:
        is_valid, errors = validate_code(data.code)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"代码验证失败: {'; '.join(errors)}",
            )

    # Pop symbols before creating ORM object
    create_data = data.model_dump()
    symbols = create_data.pop("symbols")
    create_data["symbol"] = symbols[0] if symbols else "BTCUSDT"  # legacy field

    strategy = Strategy(**create_data)
    strategy.user_id = current_user.id
    db.add(strategy)
    await db.flush()  # get strategy.id

    # Create StrategySymbol rows
    for sym in symbols:
        db.add(StrategySymbol(strategy_id=strategy.id, symbol=sym))

    await db.commit()

    # Reload with symbols relationship
    result = await db.execute(
        select(Strategy).where(Strategy.id == strategy.id)
        .options(selectinload(Strategy.symbols))
    )
    strategy = result.scalar_one()

    logger.info(f"创建策略: {strategy.name} (ID: {strategy.id})")
    return _strategy_to_response(strategy)
```

- [ ] **Step 5: Update `get_strategy` — add `selectinload`**

```python
@router.get("/strategies/{strategy_id}", response_model=StrategyResponse)
async def get_strategy(
    strategy_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取策略详情"""
    result = await db.execute(
        select(Strategy).where(Strategy.id == strategy_id)
        .options(selectinload(Strategy.symbols))
    )
    strategy = result.scalar_one_or_none()

    if not strategy or strategy.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="策略不存在",
        )

    from app.models import TriggerLog, Position
    trigger_count_result = await db.execute(
        select(func.count()).where(TriggerLog.strategy_id == strategy_id)
    )
    position_count_result = await db.execute(
        select(func.count()).where(
            Position.strategy_id == strategy_id,
            Position.closed_at.is_(None)
        )
    )

    return _strategy_to_response(
        strategy,
        trigger_count=trigger_count_result.scalar(),
        position_count=position_count_result.scalar(),
    )
```

- [ ] **Step 6: Update `update_strategy` — handle `symbols` replacement**

In the update endpoint, add symbols handling after `update_data = data.model_dump(exclude_unset=True)`:

```python
    # Handle symbols update (full replacement)
    new_symbols = update_data.pop("symbols", None)

    for key, value in update_data.items():
        setattr(strategy, key, value)

    if new_symbols is not None:
        # Delete existing symbols
        from sqlalchemy import delete
        await db.execute(
            delete(StrategySymbol).where(StrategySymbol.strategy_id == strategy.id)
        )
        # Insert new symbols
        for sym in new_symbols:
            db.add(StrategySymbol(strategy_id=strategy.id, symbol=sym))
        # Update legacy field
        strategy.symbol = new_symbols[0] if new_symbols else "BTCUSDT"

    await db.commit()

    # Reload with symbols
    result = await db.execute(
        select(Strategy).where(Strategy.id == strategy.id)
        .options(selectinload(Strategy.symbols))
    )
    strategy = result.scalar_one()

    logger.info(f"更新策略: {strategy.name} (ID: {strategy.id})")
    return _strategy_to_response(strategy)
```

- [ ] **Step 7: Update export — exclude `symbol` from EXPORT_FIELDS**

Change `EXPORT_FIELDS` to remove `"symbol"`:
```python
EXPORT_FIELDS = [
    "name", "type", "config_json", "code", "timeframe",
    "position_size", "position_size_type", "stop_loss", "take_profit",
    "sell_size_pct", "notify_enabled",
]
```

- [ ] **Step 8: Update import — create default `StrategySymbol`**

In `import_strategies`, after `db.add(strategy)` (around line 201), add:
```python
        await db.flush()
        db.add(StrategySymbol(strategy_id=strategy.id, symbol=item.get("symbol", "BTCUSDT")))
```

And ensure `strategy = Strategy(...)` includes `symbol=item.get("symbol", "BTCUSDT")`.

- [ ] **Step 9: Test backend starts and strategy CRUD works**

Run: `cd /home/autotrade/autotrade/backend && source venv/bin/activate && python -c "from app.routers.strategies import router; print('Routes OK')"`
Expected: `Routes OK`

- [ ] **Step 10: Commit**

```bash
git add backend/app/routers/strategies.py
git commit -m "feat: update strategy routes for multi-symbol CRUD with selectinload"
```

---

## Task 5: Simulator — Add `symbol` to TriggerLog Records

**Files:**
- Modify: `backend/app/services/simulator.py:1-410`

- [ ] **Step 1: Add `symbol=symbol` to all TriggerLog constructors**

There are 4 places where `TriggerLog(...)` is created. Add `symbol=symbol` to each:

1. `execute_buy` (around line 77): Add `symbol=symbol,` to `TriggerLog(...)`
2. `execute_sell` (around line 161): Add `symbol=symbol,` to `TriggerLog(...)`
3. `execute_short` (around line 230): Add `symbol=symbol,` to `TriggerLog(...)`
4. `execute_cover` (around line 306): Add `symbol=symbol,` to `TriggerLog(...)`

Example for `execute_buy`:
```python
        trigger = TriggerLog(
            strategy_id=strategy_id,
            signal_type="买入",
            signal_detail=f"买入 {quantity} {symbol} @ {price}",
            action="买入",
            price=price,
            quantity=quantity,
            position_effect="开仓",
            symbol=symbol,  # NEW
        )
```

- [ ] **Step 2: Commit**

```bash
git add backend/app/services/simulator.py
git commit -m "feat: add symbol field to all TriggerLog records in simulator"
```

---

## Task 6: Executor — Multi-Symbol Support

**Files:**
- Modify: `backend/app/engine/executor.py:1-447`

- [ ] **Step 1: Update `StrategyContext.__init__` to accept `symbol`**

Change line 35:
```python
    def __init__(self, strategy: Strategy, db: AsyncSession, symbol: str, current_kline: Optional[dict] = None):
        self.strategy = strategy
        self.db = db
        self.symbol = symbol
        self.current_kline = current_kline
```

- [ ] **Step 2: Replace all `self.strategy.symbol` with `self.symbol` in StrategyContext**

In `get_klines` (line 43-48):
```python
        return await market_data_service.get_klines(
            symbol=self.symbol,
            ...
        )
```

In `buy` — change `symbol=self.strategy.symbol` to `symbol=self.symbol` in all 3 places (lines 68, 83-86):
- `simulator.execute_cover(..., symbol=self.symbol, ...)`
- `simulator.execute_buy(..., symbol=self.symbol, ...)`

In `sell` — change `symbol=self.strategy.symbol` to `symbol=self.symbol` in all 3 places (lines 109-112, 127-130):
- `simulator.execute_sell(..., symbol=self.symbol, ...)`
- `simulator.execute_short(..., symbol=self.symbol, ...)`

In `get_position` (line 141):
```python
                Position.symbol == self.symbol,
```

- [ ] **Step 3: Update `StrategyExecutor._strategy_instances` to use tuple key**

Change line 169:
```python
        self._strategy_instances: Dict[tuple, Any] = {}
```

- [ ] **Step 4: Update `release_instance` for multi-key cleanup**

Replace the method (lines 171-183):
```python
    def release_instance(self, strategy_id: int) -> None:
        """释放策略的所有持久化实例（所有 symbol 的实例）"""
        keys_to_remove = [k for k in self._strategy_instances if k[0] == strategy_id]
        for key in keys_to_remove:
            instance = self._strategy_instances.pop(key)
            try:
                instance.on_stop()
            except Exception as e:
                logger.warning(f"Strategy {key} on_stop() error (ignored): {e}")
        if keys_to_remove:
            logger.info(f"Strategy {strategy_id}: released {len(keys_to_remove)} instance(s)")
```

- [ ] **Step 5: Update `execute()` to accept `symbol` parameter**

Change signature (line 185):
```python
    async def execute(self, strategy: Strategy, symbol: str, timeframe: Optional[str] = None):
```

Replace `strategy.symbol` with `symbol` in the method body:
- Line 203-207: `market_data_service.get_klines(symbol=symbol, ...)`
- Line 211: `ctx = StrategyContext(strategy, db, symbol, current_kline)`
- Line 218-220: `simulator.check_stop_loss_take_profit(strategy_id=strategy.id, symbol=symbol, ...)`
- Line 267: `symbol=symbol` in `_send_notification`

- [ ] **Step 6: Update `_send_notification` to accept explicit `symbol`**

Change signature and body (lines 256-272):
```python
    async def _send_notification(self, trigger: TriggerLog, strategy: Strategy, db: AsyncSession, symbol: str):
        try:
            await notification_service.send_strategy_notification(
                trigger_log=trigger,
                strategy_name=strategy.name,
                symbol=symbol,
                db=db,
                user_id=getattr(strategy, "user_id", None),
            )
        except Exception as e:
            logger.error(f"Failed to send notification: {e}")
```

Update the two call sites to pass `symbol`:
- Line 228: `await self._send_notification(sl_tp_trigger, strategy, db, symbol)`
- Line 248: `await self._send_notification(trigger, strategy, db, symbol)`

- [ ] **Step 7: Update `_execute_code_strategy` for tuple-keyed instances**

Change lines 339-346:
```python
            instance_key = (strategy.id, symbol)
            instance = self._strategy_instances.get(instance_key)
            if instance is None:
                instance = sandbox_executor.create_instance(
                    code=strategy.code,
                    context=ctx,
                    strategy_id=strategy.id,
                )
                self._strategy_instances[instance_key] = instance
            else:
                instance.ctx = ctx
```

And change `data["symbol"]` (line 353):
```python
                "symbol": symbol,
```

And the cleanup (line 364):
```python
                self._strategy_instances.pop(instance_key, None)
```

- [ ] **Step 8: Commit**

```bash
git add backend/app/engine/executor.py
git commit -m "feat: executor receives explicit symbol, instances keyed by (strategy_id, symbol)"
```

---

## Task 6.5: Sandbox — Use `context.symbol`

**Files:**
- Modify: `backend/app/engine/sandbox.py:282-284`

- [ ] **Step 1: Update `SandboxExecutor.execute` to use `context.symbol`**

At line 283, change:
```python
            "symbol": context.strategy.symbol,
```
to:
```python
            "symbol": context.symbol,
```

This ensures the sandbox passes the per-execution symbol (from `StrategyContext.symbol`) rather than the legacy `strategy.symbol` field.

- [ ] **Step 2: Commit**

```bash
git add backend/app/engine/sandbox.py
git commit -m "feat: sandbox uses context.symbol instead of context.strategy.symbol"
```

---

## Task 7: Scheduler — Per-Symbol Job Registration

**Files:**
- Modify: `backend/app/engine/scheduler.py:1-196`

- [ ] **Step 1: Add `selectinload` import and `StrategySymbol` import**

```python
from sqlalchemy.orm import selectinload
from app.models import Strategy, StrategySymbol
```

- [ ] **Step 2: Update `start_strategy` to register jobs per (symbol, timeframe)**

Replace lines 61-115:
```python
    async def start_strategy(self, strategy_id: int) -> bool:
        async with async_session() as db:
            result = await db.execute(
                select(Strategy).where(Strategy.id == strategy_id)
                .options(selectinload(Strategy.symbols))
            )
            strategy = result.scalar_one_or_none()

            if not strategy:
                logger.error(f"Strategy {strategy_id} not found")
                return False

            if strategy.status != "running":
                logger.warning(f"Strategy {strategy_id} is not in running status")
                return False

            # Reject if no symbols
            symbols = [s.symbol for s in strategy.symbols]
            if not symbols:
                logger.error(f"Strategy {strategy_id} has no symbols configured")
                return False

            # 先清理旧 job
            if strategy_id in self.running_jobs:
                self.stop_strategy(strategy_id)

            timeframes = [tf.strip() for tf in strategy.timeframe.split(",") if tf.strip()]

            job_ids: List[str] = []
            for sym in symbols:
                for tf in timeframes:
                    interval = self._timeframe_to_seconds(tf)
                    job_id = f"strategy_{strategy_id}_{sym}_{tf}"

                    self.scheduler.add_job(
                        func=self._execute_strategy,
                        trigger=IntervalTrigger(seconds=interval),
                        id=job_id,
                        args=[strategy_id, sym, tf],
                        replace_existing=True,
                    )
                    job_ids.append(job_id)

            self.running_jobs[strategy_id] = job_ids
            logger.info(
                f"Strategy '{strategy.name}' (ID:{strategy_id}) "
                f"started with {len(symbols)} symbol(s) × {len(timeframes)} tf(s) = {len(job_ids)} job(s)"
            )
            return True
```

- [ ] **Step 3: Update `_execute_strategy` to accept and pass `symbol`**

Replace lines 157-174:
```python
    async def _execute_strategy(self, strategy_id: int, symbol: str, timeframe: str):
        """执行策略任务（由调度器按 symbol × timeframe 触发）"""
        async with async_session() as db:
            result = await db.execute(
                select(Strategy).where(Strategy.id == strategy_id)
            )
            strategy = result.scalar_one_or_none()

            if not strategy or strategy.status != "running":
                self.stop_strategy(strategy_id)
                return

            try:
                await executor.execute(strategy, symbol=symbol, timeframe=timeframe)
            except Exception as e:
                logger.error(
                    f"Error executing strategy {strategy_id} "
                    f"(symbol={symbol}, tf={timeframe}): {e}"
                )
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/engine/scheduler.py
git commit -m "feat: scheduler registers jobs per (strategy, symbol, timeframe) tuple"
```

---

## Task 8: Backtester — Multi-Symbol Backtest

**Files:**
- Modify: `backend/app/engine/backtester.py`

- [ ] **Step 1: Add `uuid` import**

At top of file, add:
```python
import uuid
```

- [ ] **Step 2: Update `BacktestContext.__init__` to accept `symbol`**

Change `BacktestContext.__init__` (around line 77):
```python
    def __init__(
        self,
        strategy: Strategy,
        symbol: str,
        account: VirtualAccount,
        current_kline: Optional[dict],
        all_klines: List[dict],
    ):
        self.strategy = strategy
        self.symbol = symbol
        self.account = account
        self.current_kline = current_kline
        self.all_klines = all_klines
```

- [ ] **Step 3: Update `BacktestContext.buy/sell` to use `self.symbol`**

In `buy()` (around line 137-139), change `symbol=self.strategy.symbol` → `symbol=self.symbol`
In `sell()` (around line 205-207), change `symbol=self.strategy.symbol` → `symbol=self.symbol`

- [ ] **Step 4: Update `run_backtest` to accept `symbol` parameter**

Change signature to:
```python
    async def run_backtest(
        self,
        strategy: Strategy,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        initial_balance: float = 100000.0,
    ) -> BacktestResult:
```

Replace all `strategy.symbol` with `symbol` inside the method:
- `market_data_service.fetch_historical_klines(symbol=symbol, ...)`
- `BacktestResult(... symbol=symbol ...)`

- [ ] **Step 5: Update `_run_single_tf_loop` to pass `symbol` to `BacktestContext`**

Where `BacktestContext` is created (around line 417):
```python
            ctx = BacktestContext(strategy, symbol, account, kline, klines[: i + 1])
```

And in code strategy `data` dict (around line 444-445):
```python
                            data = {
                                "symbol": symbol,
                                ...
                            }
```

Add `symbol` parameter to method signature:
```python
    async def _run_single_tf_loop(self, strategy, symbol, primary_tf, klines, account, cancel_event):
```

- [ ] **Step 6: Update `_run_multitf_code_loop` similarly**

Add `symbol` parameter, pass to `BacktestContext` and `data`.

- [ ] **Step 7: Add `_progress` dict and `run_multi_backtest` method**

In `BacktestEngine.__init__`, add:
```python
        self._progress: Dict[int, dict] = {}
```

Add new method:
```python
    async def run_multi_backtest(
        self,
        strategy: Strategy,
        symbols: List[str],
        start_date: datetime,
        end_date: datetime,
        initial_balance: float = 100000.0,
    ) -> List[BacktestResult]:
        """Run backtests for multiple symbols sequentially."""
        if strategy.id in self._running_tasks:
            raise ValueError("该策略已有回测正在运行")

        cancel_event = asyncio.Event()
        self._running_tasks[strategy.id] = cancel_event
        batch_id = str(uuid.uuid4())
        results = []

        try:
            self._progress[strategy.id] = {
                "current_symbol": None, "completed": 0, "total": len(symbols)
            }
            for i, symbol in enumerate(symbols):
                if cancel_event.is_set():
                    break
                self._progress[strategy.id]["current_symbol"] = symbol
                result = await self._run_single_symbol_backtest(
                    strategy, symbol, start_date, end_date, initial_balance, cancel_event
                )
                result.batch_id = batch_id
                results.append(result)
                self._progress[strategy.id]["completed"] = i + 1
        finally:
            self._running_tasks.pop(strategy.id, None)
            self._progress.pop(strategy.id, None)

        return results

    async def _run_single_symbol_backtest(
        self,
        strategy: Strategy,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        initial_balance: float,
        cancel_event: asyncio.Event,
    ) -> BacktestResult:
        """Run backtest for a single symbol (extracted from run_backtest, no _running_tasks management)."""
        # This is essentially the old run_backtest body, but without _running_tasks management
        # and accepting symbol as parameter. The cancel_event is passed in from run_multi_backtest.
        timeframes = [tf.strip() for tf in strategy.timeframe.split(",") if tf.strip()]
        primary_tf = timeframes[0]

        primary_klines = await market_data_service.fetch_historical_klines(
            symbol=symbol,
            timeframe=primary_tf,
            start_date=start_date,
            end_date=end_date,
        )

        if not primary_klines:
            raise ValueError(f"No historical data for {symbol}")

        account = VirtualAccount(initial_balance)
        equity_curve = []

        is_multitf_code = (
            strategy.type == "code" and bool(strategy.code) and len(timeframes) > 1
        )

        if is_multitf_code:
            other_klines = {}
            for tf in timeframes[1:]:
                other_klines[tf] = await market_data_service.fetch_historical_klines(
                    symbol=symbol, timeframe=tf, start_date=start_date, end_date=end_date,
                )
            equity_curve = await self._run_multitf_code_loop(
                strategy, symbol, primary_tf, primary_klines, other_klines, account, cancel_event,
            )
        else:
            equity_curve = await self._run_single_tf_loop(
                strategy, symbol, primary_tf, primary_klines, account, cancel_event,
            )

        # Force close all positions
        if account.positions:
            last_kline = primary_klines[-1]
            for pos in list(account.positions):
                price = last_kline["close"]
                if pos.side == "long":
                    pnl = (price - pos.entry_price) * pos.quantity
                    account.balance += price * pos.quantity
                else:
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

        stats = self._calculate_stats(account, equity_curve, initial_balance)

        klines_data = [
            {
                "time": k["open_time"].isoformat(),
                "open": k["open"], "high": k["high"],
                "low": k["low"], "close": k["close"], "volume": k["volume"],
            }
            for k in primary_klines
        ]

        return BacktestResult(
            strategy_id=strategy.id,
            symbol=symbol,
            timeframe=primary_tf,
            start_date=start_date,
            end_date=end_date,
            initial_balance=initial_balance,
            final_balance=account.balance,
            total_pnl=stats["total_pnl"],
            pnl_percent=stats["pnl_percent"],
            win_rate=stats["win_rate"],
            max_drawdown=stats["max_drawdown"],
            total_trades=stats["total_trades"],
            avg_hold_time=stats["avg_hold_time"],
            equity_curve=json.dumps(equity_curve),
            trades=json.dumps(account.trades),
            klines=json.dumps(klines_data),
        )

    def get_progress(self, strategy_id: int) -> Optional[dict]:
        return self._progress.get(strategy_id)
```

- [ ] **Step 8: Update old `run_backtest` to delegate to `_run_single_symbol_backtest`**

The old `run_backtest` should now delegate for backward compatibility:
```python
    async def run_backtest(self, strategy, symbol, start_date, end_date, initial_balance=100000.0):
        """Run single-symbol backtest (backward compatible)."""
        if strategy.id in self._running_tasks:
            raise ValueError("该策略已有回测正在运行")
        cancel_event = asyncio.Event()
        self._running_tasks[strategy.id] = cancel_event
        try:
            return await self._run_single_symbol_backtest(
                strategy, symbol, start_date, end_date, initial_balance, cancel_event,
            )
        finally:
            self._running_tasks.pop(strategy.id, None)
```

- [ ] **Step 9: Commit**

```bash
git add backend/app/engine/backtester.py
git commit -m "feat: backtester supports multi-symbol with batch_id and progress tracking"
```

---

## Task 9: Backtest Routes — Multi-Symbol Response and Batch Delete

**Files:**
- Modify: `backend/app/routers/backtests.py:1-264`

- [ ] **Step 1: Update `create_backtest` to use `run_multi_backtest`**

```python
from sqlalchemy.orm import selectinload
from app.models import BacktestResult, Strategy, StrategySymbol, User

@router.post("/strategies/{strategy_id}/backtest", response_model=List[BacktestResponse])
async def create_backtest(
    strategy_id: int,
    data: BacktestCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(
        select(Strategy).where(Strategy.id == strategy_id)
        .options(selectinload(Strategy.symbols))
    )
    strategy = result.scalar_one_or_none()

    if not strategy or strategy.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="策略不存在")

    start_date = convert_to_naive(data.start_date)
    end_date = convert_to_naive(data.end_date)

    if start_date >= end_date:
        raise HTTPException(status_code=400, detail="结束时间必须晚于开始时间")
    if end_date > datetime.utcnow():
        raise HTTPException(status_code=400, detail="结束时间不能是将来")

    symbols = [s.symbol for s in strategy.symbols]
    if not symbols:
        raise HTTPException(status_code=400, detail="策略未配置交易对")

    try:
        results = await backtest_engine.run_multi_backtest(
            strategy=strategy,
            symbols=symbols,
            start_date=start_date,
            end_date=end_date,
            initial_balance=data.initial_balance,
        )

        responses = []
        for r in results:
            r.user_id = current_user.id
            db.add(r)
            await db.flush()
            responses.append(BacktestResponse.model_validate(r))

        await db.commit()
        return responses

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Backtest failed: {e}")
        raise HTTPException(status_code=500, detail=f"回测执行失败: {str(e)}")
```

Add `List` import: `from typing import List, Optional`

- [ ] **Step 2: Add batch delete endpoint**

```python
@router.delete("/backtests/batch/{batch_id}", response_model=MessageResponse)
async def delete_batch_backtest(
    batch_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除一批回测结果"""
    result = await db.execute(
        select(BacktestResult).where(
            BacktestResult.batch_id == batch_id,
            BacktestResult.user_id == current_user.id,
        )
    )
    items = result.scalars().all()

    if not items:
        raise HTTPException(status_code=404, detail="回测结果不存在")

    for item in items:
        await db.delete(item)
    await db.commit()

    logger.info(f"Batch {batch_id} deleted ({len(items)} results)")
    return MessageResponse(message=f"已删除 {len(items)} 条回测结果")
```

**Important:** This endpoint must be defined BEFORE the `/backtests/{backtest_id}` route to avoid path parameter conflicts.

- [ ] **Step 3: Update status endpoint to include progress**

Replace the status endpoint:
```python
@router.get("/strategies/{strategy_id}/backtest/status")
async def get_backtest_status(
    strategy_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Strategy).where(Strategy.id == strategy_id))
    strategy = result.scalar_one_or_none()

    if not strategy or strategy.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="策略不存在")

    engine = get_backtest_engine()
    progress = engine.get_progress(strategy_id)
    return {
        "running": engine.is_running(strategy_id),
        "current_symbol": progress["current_symbol"] if progress else None,
        "completed": progress["completed"] if progress else 0,
        "total": progress["total"] if progress else 0,
    }
```

- [ ] **Step 4: Commit**

```bash
git add backend/app/routers/backtests.py
git commit -m "feat: backtest routes return list, add batch delete, add progress status"
```

---

## Task 10: Trigger Routes and Dashboard — Symbol Field

**Files:**
- Modify: `backend/app/routers/triggers.py:1-121`
- Modify: `backend/app/routers/dashboard.py:1-97`

- [ ] **Step 1: Add `symbol` filter to `list_triggers`**

Add `symbol` query param:
```python
    symbol: Optional[str] = Query(None, description="筛选交易对"),
```

Add filter:
```python
    if symbol:
        base_query = base_query.where(TriggerLog.symbol == symbol)
```

- [ ] **Step 2: Dashboard — `symbol` field is already in `TriggerLogResponse`**

The `TriggerLogResponse` already uses `model_validate` which will pick up the `symbol` field from the ORM object automatically via `from_attributes=True`. No code change needed in dashboard.py.

- [ ] **Step 3: Commit**

```bash
git add backend/app/routers/triggers.py backend/app/routers/dashboard.py
git commit -m "feat: add symbol filter to trigger list endpoint"
```

---

## Task 11: Frontend API Client Updates

**Files:**
- Modify: `frontend/src/lib/api.ts:1-214`

- [ ] **Step 1: Update `fetchTriggers` to accept `symbol` param**

```typescript
export const fetchTriggers = (params?: { strategy_id?: number; symbol?: string; page?: number; page_size?: number }) =>
  cachedGet("/triggers", 5000, params);
```

- [ ] **Step 2: Add `deleteBatchBacktest` function**

```typescript
export const deleteBatchBacktest = (batchId: string) => {
  invalidateCache("/backtests");
  return apiCall(api.delete(`/backtests/batch/${batchId}`));
};
```

- [ ] **Step 3: Add `fetchBacktestStatus` with progress fields**

```typescript
export const fetchBacktestStatus = (strategyId: string | number) =>
  cachedGet<{ running: boolean; current_symbol: string | null; completed: number; total: number }>(
    `/strategies/${strategyId}/backtest/status`, 2000
  );
```

- [ ] **Step 4: Commit**

```bash
git add frontend/src/lib/api.ts
git commit -m "feat: frontend API client updates for multi-symbol (triggers filter, batch delete, backtest status)"
```

---

## Task 12: Frontend — Multi-Symbol Selector Component

**Files:**
- Modify: `frontend/src/components/symbol-selector.tsx`

- [ ] **Step 1: Add `MultiSymbolSelector` component**

Add a new exported component to the file (keep the existing `SymbolSelector` for backward compat):

```typescript
interface MultiSymbolSelectorProps {
  value: string[];
  onChange: (symbols: string[]) => void;
}

export function MultiSymbolSelector({ value, onChange }: MultiSymbolSelectorProps) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [symbols, setSymbols] = useState<string[]>([]);
  const [loading, setLoading] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  useEffect(() => {
    if (!open) return;
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(async () => {
      setLoading(true);
      try {
        const result = await fetchSymbols(query);
        setSymbols((result as string[]).filter((s) => !value.includes(s)));
      } catch {
        setSymbols([]);
      } finally {
        setLoading(false);
      }
    }, 300);
    return () => { if (debounceRef.current) clearTimeout(debounceRef.current); };
  }, [query, open, value]);

  const handleOpen = async () => {
    setOpen(true);
    setQuery("");
    setLoading(true);
    try {
      const result = await fetchSymbols("");
      setSymbols((result as string[]).filter((s) => !value.includes(s)));
    } catch {
      setSymbols([]);
    } finally {
      setLoading(false);
    }
  };

  const handleSelect = (symbol: string) => {
    onChange([...value, symbol]);
    setQuery("");
  };

  const handleRemove = (symbol: string) => {
    onChange(value.filter((s) => s !== symbol));
  };

  return (
    <div ref={containerRef} className="relative">
      {/* Selected tags */}
      <div
        className="flex flex-wrap gap-1.5 min-h-[42px] px-3 py-2 bg-slate-800 border border-slate-700 rounded-lg cursor-text"
        onClick={!open ? handleOpen : undefined}
      >
        {value.map((s) => (
          <span
            key={s}
            className="inline-flex items-center gap-1 px-2 py-0.5 bg-blue-500/20 text-blue-400 text-xs font-mono rounded"
          >
            {s}
            <button
              onClick={(e) => { e.stopPropagation(); handleRemove(s); }}
              className="hover:text-blue-200"
            >
              <X className="w-3 h-3" />
            </button>
          </span>
        ))}
        {value.length === 0 && (
          <span className="text-slate-500 text-sm">点击添加交易对...</span>
        )}
      </div>

      {/* Dropdown */}
      {open && (
        <div className="absolute top-full left-0 mt-1 w-72 bg-slate-800 border border-slate-700 rounded-xl shadow-2xl z-50 overflow-hidden">
          <div className="flex items-center gap-2 px-3 py-2 border-b border-slate-700">
            <Search className="w-4 h-4 text-slate-400 shrink-0" />
            <input
              autoFocus
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="搜索交易对..."
              className="flex-1 bg-transparent text-sm text-white placeholder-slate-500 outline-none"
            />
          </div>
          <div className="max-h-48 overflow-y-auto">
            {loading ? (
              <p className="text-center text-xs text-slate-500 py-4">加载中...</p>
            ) : symbols.length === 0 ? (
              <p className="text-center text-xs text-slate-500 py-4">未找到结果</p>
            ) : (
              symbols.map((s) => (
                <button
                  key={s}
                  onClick={() => handleSelect(s)}
                  className="w-full text-left px-4 py-2 text-sm font-mono text-slate-200 hover:bg-slate-700 transition-colors"
                >
                  {s}
                </button>
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/components/symbol-selector.tsx
git commit -m "feat: add MultiSymbolSelector component for tag-based multi-select"
```

---

**IMPORTANT NOTE for all frontend tasks:** The backend `StrategyResponse` will no longer include a `symbol` (singular) field — it's replaced by `symbols: string[]`. All frontend code that reads `strategy.symbol` must be changed to `strategy.symbols[0]` or `strategy.symbols` as appropriate. Use the pattern `(strategy.symbols || [strategy.symbol])` for backward compatibility during development if needed.

---

## Task 13: Frontend — Strategy Create Page

**Files:**
- Modify: `frontend/src/app/strategies/new/page.tsx`

- [ ] **Step 1: Replace single symbol with multi-symbol**

1. Import `MultiSymbolSelector`:
```typescript
import { MultiSymbolSelector } from "@/components/symbol-selector";
```

2. Change state from `symbol: "BTCUSDT"` to `symbols: ["BTCUSDT"]`

3. Replace `<SymbolSelector value={form.symbol} onChange={...} />` with:
```tsx
<MultiSymbolSelector
  value={form.symbols}
  onChange={(symbols) => setForm({ ...form, symbols })}
/>
```

4. In the submit handler, send `symbols` instead of `symbol`:
```typescript
const payload = {
  ...form,
  symbols: form.symbols,
};
// Remove the old `symbol` key if present
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/app/strategies/new/page.tsx
git commit -m "feat: strategy create page uses multi-symbol selector"
```

---

## Task 14: Frontend — Strategy Edit Page

**Files:**
- Modify: `frontend/src/app/strategies/[id]/edit/page.tsx`

- [ ] **Step 1: Load and display symbols from strategy response**

1. Import `MultiSymbolSelector`
2. Initialize form with `symbols: strategy.symbols || [strategy.symbol]`
3. Replace any symbol display with `MultiSymbolSelector`
4. Include `symbols` in update payload

- [ ] **Step 2: Commit**

```bash
git add "frontend/src/app/strategies/[id]/edit/page.tsx"
git commit -m "feat: strategy edit page supports multi-symbol editing"
```

---

## Task 15: Frontend — Strategy List Page

**Files:**
- Modify: `frontend/src/app/strategies/page.tsx`

- [ ] **Step 1: Display symbol tags on strategy cards**

Replace single symbol text with tag group. When >3 symbols, show collapsed: `BTCUSDT +2`.

```tsx
{/* Symbol tags */}
<div className="flex flex-wrap gap-1 mt-2">
  {(strategy.symbols || [strategy.symbol]).slice(0, 3).map((s: string) => (
    <span key={s} className="px-1.5 py-0.5 text-xs font-mono bg-slate-700 text-slate-300 rounded">
      {s}
    </span>
  ))}
  {(strategy.symbols || [strategy.symbol]).length > 3 && (
    <span className="px-1.5 py-0.5 text-xs bg-slate-700 text-slate-400 rounded">
      +{(strategy.symbols || [strategy.symbol]).length - 3}
    </span>
  )}
</div>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/app/strategies/page.tsx
git commit -m "feat: strategy list shows symbol tags with collapse for >3"
```

---

## Task 16: Frontend — Strategy Detail Page

**Files:**
- Modify: `frontend/src/app/strategies/[id]/page.tsx`

- [ ] **Step 1: Overview tab — show symbol tags instead of single symbol**

Replace the single symbol display with a tag group (same pattern as list page).

- [ ] **Step 2: Triggers tab — add symbol switcher dropdown**

Add a `<select>` dropdown populated with the strategy's symbols. Default to the first symbol. When changed:
- Reload K-line chart for the selected symbol
- Filter trigger table by selected symbol via `fetchTriggers({ strategy_id, symbol })`
- Add "全部" option that hides K-line chart and shows all triggers

- [ ] **Step 3: Positions tab — show multiple open positions as table**

Replace single position card with a table showing all open positions (each with its symbol, side, entry_price, quantity, unrealized_pnl).

- [ ] **Step 4: Commit**

```bash
git add "frontend/src/app/strategies/[id]/page.tsx"
git commit -m "feat: strategy detail shows symbol tags, symbol switcher, multi-position table"
```

---

## Task 17: Frontend — Trigger Log Page

**Files:**
- Modify: `frontend/src/app/triggers/page.tsx`

- [ ] **Step 1: Add `交易对` column to table**

Add column after strategy name:
```tsx
<th className="...">交易对</th>
```

And in the row:
```tsx
<td className="...">{trigger.symbol ? trigger.symbol.replace("USDT", "/USDT") : "—"}</td>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/app/triggers/page.tsx
git commit -m "feat: trigger log page shows symbol column"
```

---

## Task 18: Frontend — Dashboard

**Files:**
- Modify: `frontend/src/app/page.tsx`

- [ ] **Step 1: Show symbol in recent triggers**

In the recent triggers section, add symbol display:
```tsx
<span className="text-xs text-slate-500 font-mono">
  {trigger.symbol ? trigger.symbol.replace("USDT", "/USDT") : ""}
</span>
```

- [ ] **Step 2: Commit**

```bash
git add frontend/src/app/page.tsx
git commit -m "feat: dashboard shows symbol in recent triggers"
```

---

## Task 19: Frontend — Backtest Panel

**Files:**
- Modify: `frontend/src/components/backtest-panel.tsx`

- [ ] **Step 1: Handle `List[BacktestResponse]` from API**

The backtest create endpoint now returns `BacktestResponse[]`. Update the response handling:
- Store the array of results
- Group historical results by `batch_id` for display
- Each null `batch_id` result is its own entry

- [ ] **Step 2: Add symbol tabs for multi-symbol results**

When a batch has multiple results, show tabs (`BTCUSDT | ETHUSDT`) above the result view. Each tab renders the existing stats/chart/trade-table for that symbol's result.

- [ ] **Step 3: Show progress during backtest**

Poll the status endpoint. Display: "正在回测 ETHUSDT (2/5)" using `current_symbol`, `completed`, `total`.

- [ ] **Step 4: Add batch delete button**

When viewing a batch, the delete button calls `deleteBatchBacktest(batch_id)` instead of the single delete endpoint. For legacy results without `batch_id`, use the existing single delete.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/components/backtest-panel.tsx
git commit -m "feat: backtest panel handles multi-symbol results with batch grouping and progress"
```

---

## Task 20: End-to-End Verification

- [ ] **Step 1: Start backend and verify no errors**

```bash
cd /home/autotrade/autotrade/backend
source venv/bin/activate
python -c "
import asyncio
from app.database import init_db
asyncio.run(init_db())
print('DB migration OK')
"
```

- [ ] **Step 2: Start frontend and verify no build errors**

```bash
cd /home/autotrade/autotrade/frontend
npm run build 2>&1 | tail -5
```

- [ ] **Step 3: Test create strategy with multiple symbols**

Use curl or the frontend to create a strategy with `symbols: ["BTCUSDT", "ETHUSDT"]`. Verify the response includes the `symbols` array.

- [ ] **Step 4: Test backtest returns list**

Trigger a backtest. Verify the response is an array with `batch_id` set on each result.

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "feat: multi-symbol strategy support - complete implementation"
```
