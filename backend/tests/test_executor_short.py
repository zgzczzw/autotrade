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
        buy_trigger = MagicMock(action="买入", position_effect="开仓")
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
        cover_trigger = MagicMock(action="买入", position_effect="平仓")
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
        short_trigger = MagicMock(action="卖出", position_effect="开仓")
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
        sell_trigger = MagicMock(action="卖出", position_effect="平仓")
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
    """可视化策略：无持仓，买入条件满足 → buy（buy优先于sell）"""
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
