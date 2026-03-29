# Multi-Symbol Strategy Design

## Overview

Each strategy supports multiple trading pairs (symbols), running the same logic independently on each pair. Users can also query all strategies associated with a given trading pair. Trigger history and notifications distinguish which trading pair triggered the event.

## Requirements Summary

| Requirement | Decision |
|---|---|
| Strategy-to-symbol relationship | One strategy → many symbols (via association table) |
| Execution model | Same logic runs independently per symbol |
| Capital management | Shared user-level `sim_account` (unchanged) |
| Parameter configuration | Unified per strategy (all symbols share same position_size, stop_loss, etc.) |
| Backtesting | Independent per symbol, each produces its own `backtest_results` record |
| Import/Export | Export excludes symbols; import defaults to `BTCUSDT` |
| Symbol limit per strategy | No limit |

## Data Model Changes

### 1. New Table: `strategy_symbols`

Association table linking strategies to their trading pairs.

```python
class StrategySymbol(Base):
    __tablename__ = "strategy_symbols"

    strategy_id = Column(Integer, ForeignKey("strategies.id"), nullable=False)
    symbol = Column(String, nullable=False)  # e.g. "BTCUSDT"
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    __table_args__ = (
        PrimaryKeyConstraint("strategy_id", "symbol"),
    )

    strategy = relationship("Strategy", back_populates="symbols")
```

### 2. `strategies` Table Changes

- **Keep** `symbol` field with default value `"BTCUSDT"` for backward compatibility with user code strategies that reference `strategy.symbol`
- **Add** relationship: `symbols = relationship("StrategySymbol", back_populates="strategy", cascade="all, delete-orphan")`

The `strategy.symbol` field is retained solely for code strategy compatibility. The authoritative list of trading pairs is always `strategy_symbols`.

### 3. `trigger_logs` Table Changes

- **Add** `symbol` column: `Column(String, nullable=True)` — nullable to accommodate existing records without symbol data

### 4. `notification_logs` — No Changes

Symbol is accessible via `trigger_log → symbol`. No redundant field needed.

### 5. `positions` — No Changes

Already has a `symbol` field. Works as-is.

### 6. `backtest_results` — No Changes

Each backtest run targets one symbol and produces one record. When user triggers "backtest all", the backend runs independent backtests for each symbol in the strategy, each creating its own `backtest_results` row with that symbol.

### Data Migration (Alembic)

Create an Alembic migration script that:

1. Creates `strategy_symbols` table
2. Adds `symbol` column (nullable) to `trigger_logs`
3. For each existing strategy, inserts one row into `strategy_symbols` with the strategy's current `symbol` value
4. For existing `trigger_logs`, backfills `symbol` from the associated strategy's `symbol` field (best-effort, leave null if strategy deleted)
5. Keep `strategies.symbol` field with its current value (do NOT delete), update default to `"BTCUSDT"`

**Note:** The project uses inline migration at startup (`models.Base.metadata.create_all`). If Alembic is not set up, the migration logic should be added to the startup sequence.

## Scheduler Changes

### Job Registration

**Current:** `strategy_{id}_{tf}` — one job per (strategy, timeframe)

**New:** `strategy_{id}_{symbol}_{tf}` — one job per (strategy, symbol, timeframe)

Example: Strategy ID=1, symbols=["BTCUSDT", "ETHUSDT"], timeframe="15m,4h"
→ 4 jobs:
- `strategy_1_BTCUSDT_15m`
- `strategy_1_BTCUSDT_4h`
- `strategy_1_ETHUSDT_15m`
- `strategy_1_ETHUSDT_4h`

### `_execute_strategy` Signature

```python
async def _execute_strategy(self, strategy_id: int, symbol: str, timeframe: str):
```

### `start_strategy` Logic

```python
async def start_strategy(self, strategy_id: int) -> bool:
    # Load strategy with symbols
    # Reject if strategy has no symbols
    # For each symbol × timeframe: register job
```

### `stop_strategy` Logic

```python
def stop_strategy(self, strategy_id: int):
    # Remove all jobs for this strategy (all symbols × timeframes)
    # Release all code strategy instances for this strategy
```

## Executor Changes (`executor.py`)

### `execute(strategy, symbol, timeframe)`

New `symbol` parameter:
- Fetch K-lines using the passed `symbol` (not `strategy.symbol`)
- Check stop-loss/take-profit using the passed `symbol`
- Send notifications using the passed `symbol`

### `StrategyContext`

Constructor receives `symbol` parameter:

```python
class StrategyContext:
    def __init__(self, strategy, db, symbol, current_kline=None):
        self.strategy = strategy
        self.db = db
        self.symbol = symbol  # current trading pair
        self.current_kline = current_kline
```

All internal references change from `self.strategy.symbol` to `self.symbol`:
- `get_klines()` → uses `self.symbol`
- `get_position()` → filters by `self.symbol`
- `buy()` → passes `self.symbol` to `simulator.execute_buy()` / `simulator.execute_cover()`
- `sell()` → passes `self.symbol` to `simulator.execute_sell()` / `simulator.execute_short()`

### Code Strategy Instances

Instance key changes from `strategy_id` to `(strategy_id, symbol)`:

```python
self._strategy_instances: Dict[tuple[int, str], Any] = {}
```

Each (strategy, symbol) pair gets its own independent instance with its own state.

### `release_instance` Adaptation

Must release ALL instances for a given `strategy_id` (iterate over all `(strategy_id, *)` keys):

```python
def release_instance(self, strategy_id: int) -> None:
    keys_to_remove = [k for k in self._strategy_instances if k[0] == strategy_id]
    for key in keys_to_remove:
        instance = self._strategy_instances.pop(key)
        try:
            instance.on_stop()
        except Exception as e:
            logger.warning(f"Strategy {key} on_stop() error (ignored): {e}")
    logger.info(f"Strategy {strategy_id}: released {len(keys_to_remove)} instance(s)")
```

### `on_tick` Data

```python
data = {
    "symbol": symbol,        # current trading pair
    "timeframe": active_tf,
    "price": current_kline["close"],
    "klines": klines,
}
```

No change in structure — code strategies already receive `symbol` in data dict.

## Simulator Changes (`simulator.py`) — No Code Changes

The Simulator already accepts `symbol` as an explicit parameter in all methods (`execute_buy`, `execute_sell`, `execute_short`, `execute_cover`, `check_stop_loss_take_profit`). It does NOT read `strategy.symbol` internally. The only change is that callers (StrategyContext) now pass `self.symbol` instead of `self.strategy.symbol`.

**TriggerLog symbol population:** The Simulator creates `TriggerLog` records. A new `symbol` parameter must be added to each `TriggerLog(...)` constructor call so that new trigger logs are tagged with the correct symbol. This is the ONLY change needed in `simulator.py`.

## Sandbox Changes (`sandbox.py`)

The `SandboxExecutor.execute()` method builds `data = {"symbol": context.strategy.symbol, ...}`. This must change to `data = {"symbol": context.symbol, ...}` to use the per-execution symbol from StrategyContext.

## Backtester Changes (`backtester.py`)

### `run_backtest` Signature

Add `symbol` parameter:

```python
async def run_backtest(strategy, symbol, start_date, end_date, initial_balance) -> BacktestResult:
```

All internal `strategy.symbol` references replaced with the passed `symbol` parameter:
- `market_data_service.fetch_historical_klines(symbol=symbol, ...)`
- `BacktestContext(strategy, symbol, ...)` — BacktestContext also receives explicit `symbol`
- `Position(symbol=symbol, ...)`
- `BacktestResult(symbol=symbol, ...)`

### Route Changes (`routers/backtests.py`)

The backtest route loops over strategy symbols and runs independent backtests:

```python
@router.post("/strategies/{strategy_id}/backtest")
async def create_backtest(strategy_id: int, req: BacktestCreate):
    strategy = ...  # load with symbols
    results = []
    for sym in strategy.symbols:
        result = await run_backtest(strategy, sym.symbol, req.start_date, req.end_date, req.initial_balance)
        results.append(result)
    return results
```

**Response type changes** from `BacktestResponse` to `List[BacktestResponse]`. This is a breaking change for frontend — frontend must be updated to handle the list.

## API & Schema Changes

### Strategy Schemas

**`StrategyBase`:**
- Remove `symbol: str` field (no longer needed in base schema)

**`StrategyCreate`:**
```python
class StrategyCreate(StrategyBase):
    symbols: List[str] = Field(..., min_length=1)  # at least one symbol required
    config_json: Optional[str] = None
    code: Optional[str] = None
```

**`StrategyUpdate`:**
```python
class StrategyUpdate(BaseModel):
    symbols: Optional[List[str]] = None  # full replacement on update
    # ... other fields unchanged
```

**`StrategyResponse`:**
```python
class StrategyResponse(StrategyBase):
    symbols: List[str]  # extracted from strategy_symbols relationship
    # ... other fields unchanged
```

**ORM-to-Pydantic mapping note:** The SQLAlchemy `Strategy.symbols` relationship returns `StrategySymbol` objects, not strings. The route handler must convert before returning:

```python
strategy_dict = {**strategy.__dict__}
strategy_dict["symbols"] = [s.symbol for s in strategy.symbols]
return StrategyResponse(**strategy_dict)
```

Or add a `@computed_field` / `@property` on the ORM model. The implementation plan should decide the approach.

### Strategy Route Changes (`routers/strategies.py`)

**Create:** `model_dump()` will include `symbols` key which is not an ORM column. The route must:
1. Pop `symbols` from the dict
2. Create the `Strategy` ORM object (with `symbol` defaulting to `"BTCUSDT"`)
3. Create `StrategySymbol` rows for each symbol
4. Commit

**Export:** The `EXPORT_FIELDS` list should exclude `symbol` (legacy field). Exported JSON has no symbol data.

**Import:** Create strategy with `symbol="BTCUSDT"` (default), then create one `StrategySymbol` row with `"BTCUSDT"`.

### Trigger Log Schema

**`TriggerLogResponse`:**
```python
class TriggerLogResponse(BaseModel):
    symbol: Optional[str] = None  # new field
    # ... other fields unchanged
```

### API Endpoints

**Strategy list with symbol filter:**
```
GET /api/strategies?symbol=BTCUSDT
```
Filters via JOIN on `strategy_symbols`. No new route needed.

**Trigger list with symbol filter:**
```
GET /api/triggers?symbol=BTCUSDT
```
Filters on `trigger_logs.symbol`. No new route needed.

**Backtest:**
```
POST /api/strategies/{id}/backtest
```
Unchanged request body. Backend iterates all symbols, runs independent backtests, returns list of results. Each result is a separate `backtest_results` row.

### Import/Export

**Export:** Excludes `symbols` from exported JSON.

**Import:** Strategy is saved with default symbol `["BTCUSDT"]` in `strategy_symbols`. User can modify before starting.

## Notification Changes

`send_strategy_notification` receives `symbol` from executor (not from `strategy.symbol`):

```python
await notification_service.send_strategy_notification(
    trigger_log=trigger,
    strategy_name=strategy.name,
    symbol=symbol,  # passed from executor, not strategy.symbol
    db=db,
    user_id=getattr(strategy, "user_id", None),
)
```

Notification message template includes symbol:
```
策略「双均线交叉」触发 买入信号
交易对：BTCUSDT
价格：67,500.00
数量：0.015
```

## Frontend Changes

### Strategy Create/Edit Form

- Single symbol input → **Multi-select tag input**
- Search via `/api/market/symbols?q=BTC`, display candidates in dropdown
- Selected symbols shown as removable tags
- Minimum 1 symbol required to save

### Strategy List Page

- Symbol column displays tag group: `BTCUSDT` `ETHUSDT` `SOLUSDT`
- Collapse when >3: `BTCUSDT +2`
- New symbol filter dropdown

### Strategy Detail Page

- Header shows full symbol tag list
- Trigger history table adds `交易对` column
- Positions table already has `symbol` column (no change)

### Trigger Log Page (Global)

- Table adds `交易对` column
- New symbol filter dropdown

### Backtest Results Page

- Results displayed per symbol (tab or list)
- Each symbol shows its own metrics and equity curve

### Strategy Import Dialog

- After import, strategy gets default `BTCUSDT`
- User can modify symbols before saving

## Error Handling

| Scenario | Handling |
|---|---|
| Start strategy with no symbols | Reject, return error |
| Edit symbols while strategy running | Must stop strategy first |
| K-line fetch fails for one symbol | Skip that symbol for this tick, log error, other symbols unaffected |
| Delete strategy | Cascade deletes strategy_symbols, trigger_logs, positions |
| Old trigger_logs without symbol | Frontend displays `—` for null values |
| User code accesses `strategy.symbol` | Returns default `"BTCUSDT"`, not the per-execution symbol. Users should use `ctx.symbol` or `data["symbol"]` instead. Document this in migration notes |
