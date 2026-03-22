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
    s.timeframe = "1h"
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

    with patch("app.engine.executor.simulator") as mock_sim, \
         patch("app.engine.executor.market_data_service") as mock_mds:
        mock_mds.get_klines = AsyncMock(return_value=[make_kline(40000.0)])
        mock_sim.execute_short = AsyncMock(return_value=trigger_mock)
        result = await ctx.short()

    mock_sim.execute_short.assert_called_once()
    call_kwargs = mock_sim.execute_short.call_args
    assert call_kwargs.kwargs["symbol"] == "BTCUSDT"
    assert call_kwargs.kwargs["price"] == pytest.approx(40000.0)
    assert result == trigger_mock


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

    with patch("app.engine.executor.simulator") as mock_sim, \
         patch("app.engine.executor.market_data_service") as mock_mds:
        mock_mds.get_klines = AsyncMock(return_value=[make_kline(40000.0)])
        sell_trigger = MagicMock()
        short_trigger = MagicMock()
        short_trigger.action = "short"
        mock_sim.execute_sell = AsyncMock(return_value=sell_trigger)
        mock_sim.execute_short = AsyncMock(return_value=short_trigger)

        result = await ctx.short()

    # execute_sell must be called first (auto-flip)
    mock_sim.execute_sell.assert_called_once()
    sell_kwargs = mock_sim.execute_sell.call_args.kwargs
    assert sell_kwargs["sell_size_pct"] == 100.0

    # execute_short called after
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

    with patch("app.engine.executor.simulator") as mock_sim, \
         patch("app.engine.executor.market_data_service") as mock_mds:
        mock_mds.get_klines = AsyncMock(return_value=[make_kline(40000.0)])
        cover_trigger = MagicMock()
        buy_trigger = MagicMock()
        buy_trigger.action = "buy"
        mock_sim.execute_cover = AsyncMock(return_value=cover_trigger)
        mock_sim.execute_buy = AsyncMock(return_value=buy_trigger)
        mock_sim.execute_sell = AsyncMock()

        result = await ctx.buy()

    mock_sim.execute_cover.assert_called_once()
    mock_sim.execute_buy.assert_called_once()
    assert result == buy_trigger


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


@pytest.mark.asyncio
async def test_execute_routes_cover_signal():
    """execute() 接收 cover 信号时调用 ctx.cover()"""
    from app.engine.executor import StrategyExecutor

    executor = StrategyExecutor()

    strategy = make_strategy()
    strategy.type = "code"
    strategy.code = "def on_tick(data): return 'cover'"
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

        mock_mds.get_klines = AsyncMock(return_value=[make_kline()])

        with patch("app.engine.executor.simulator") as mock_sim:
            mock_sim.check_stop_loss_take_profit = AsyncMock(return_value=None)

            cover_trigger = MagicMock()
            cover_trigger.action = "cover"

            with patch("app.engine.executor.StrategyContext") as MockCtx:
                ctx_instance = AsyncMock()
                ctx_instance.cover = AsyncMock(return_value=cover_trigger)
                ctx_instance.buy = AsyncMock()
                ctx_instance.sell = AsyncMock()
                ctx_instance.short = AsyncMock()
                MockCtx.return_value = ctx_instance

                mock_sandbox.create_instance = MagicMock(return_value=MagicMock())
                mock_sandbox.call_on_tick = MagicMock(return_value="cover")

                await executor.execute(strategy)

            ctx_instance.cover.assert_called_once()


@pytest.mark.asyncio
async def test_visual_strategy_no_position_buy():
    """可视化策略：无持仓，买入条件满足 → buy"""
    from app.engine.executor import StrategyExecutor, StrategyContext

    executor = StrategyExecutor()
    strategy = make_strategy()
    strategy.config_json = '{"buy_conditions": {"logic": "AND", "rules": [{"indicator": "PRICE", "operator": ">", "value": "100"}]}, "sell_conditions": {"logic": "AND", "rules": []}}'

    db = AsyncMock()
    kline = make_kline(40000.0)
    ctx = StrategyContext(strategy, db, current_kline=kline)

    # get_position → None
    result_mock = MagicMock()
    result_mock.scalar_one_or_none = MagicMock(return_value=None)
    db.execute = AsyncMock(return_value=result_mock)

    with patch("app.engine.executor.market_data_service") as mock_mds:
        # 100 klines all close=40000
        klines = [make_kline(40000.0)] * 100
        mock_mds.get_klines = AsyncMock(return_value=klines)
        signal = await executor._execute_visual_strategy(strategy, ctx)

    assert signal == "buy"


@pytest.mark.asyncio
async def test_visual_strategy_short_position_cover():
    """可视化策略：持空仓，cover条件满足 → cover"""
    from app.engine.executor import StrategyExecutor, StrategyContext
    from app.models import Position

    executor = StrategyExecutor()
    strategy = make_strategy()
    strategy.config_json = '{"buy_conditions": {"logic": "AND", "rules": []}, "sell_conditions": {"logic": "AND", "rules": []}, "cover_conditions": {"logic": "AND", "rules": [{"indicator": "PRICE", "operator": ">", "value": "100"}]}}'

    db = AsyncMock()
    kline = make_kline(40000.0)
    ctx = StrategyContext(strategy, db, current_kline=kline)

    short_pos = MagicMock(spec=Position)
    short_pos.side = "short"
    result_mock = MagicMock()
    result_mock.scalar_one_or_none = MagicMock(return_value=short_pos)
    db.execute = AsyncMock(return_value=result_mock)

    with patch("app.engine.executor.market_data_service") as mock_mds:
        klines = [make_kline(40000.0)] * 100
        mock_mds.get_klines = AsyncMock(return_value=klines)
        signal = await executor._execute_visual_strategy(strategy, ctx)

    assert signal == "cover"


@pytest.mark.asyncio
async def test_visual_strategy_short_position_no_cover_conditions():
    """可视化策略：持空仓，未配置cover条件 → None（依赖止盈止损）"""
    from app.engine.executor import StrategyExecutor, StrategyContext
    from app.models import Position

    executor = StrategyExecutor()
    strategy = make_strategy()
    strategy.config_json = '{"buy_conditions": {"logic": "AND", "rules": []}, "sell_conditions": {"logic": "AND", "rules": []}}'

    db = AsyncMock()
    ctx = StrategyContext(strategy, db, current_kline=make_kline())

    short_pos = MagicMock(spec=Position)
    short_pos.side = "short"
    result_mock = MagicMock()
    result_mock.scalar_one_or_none = MagicMock(return_value=short_pos)
    db.execute = AsyncMock(return_value=result_mock)

    with patch("app.engine.executor.market_data_service") as mock_mds:
        mock_mds.get_klines = AsyncMock(return_value=[make_kline()] * 100)
        signal = await executor._execute_visual_strategy(strategy, ctx)

    assert signal is None
