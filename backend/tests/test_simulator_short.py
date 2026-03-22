"""测试 Simulator.execute_short / execute_cover"""
import pytest
from unittest.mock import AsyncMock, MagicMock
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
    db.add.assert_called()
    assert trigger is not None
    assert trigger.action == "short"
    assert trigger.signal_type == "short"


@pytest.mark.asyncio
async def test_execute_short_insufficient_balance():
    from app.services.simulator import simulator
    account = make_account(balance=100.0)
    db = make_db(account=account)
    trigger = await simulator.execute_short(
        strategy_id=1, symbol="BTCUSDT", quantity=1.0, price=40000.0, db=db
    )
    assert trigger.action == "hold"
    assert "余额不足" in trigger.signal_detail
    assert account.balance == pytest.approx(100.0)


@pytest.mark.asyncio
async def test_execute_cover_success():
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

    trigger = await simulator.execute_cover(
        strategy_id=1, symbol="BTCUSDT", price=38000.0, db=db, user_id=1
    )

    expected_pnl = (40000.0 - 38000.0) * 0.1  # = 200
    assert account.balance == pytest.approx(96000.0 + 4000.0 + expected_pnl)
    assert account.total_pnl == pytest.approx(expected_pnl)
    assert position.closed_at is not None
    assert trigger.action == "cover"
    assert trigger.simulated_pnl == pytest.approx(expected_pnl)


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
            # First call: check_sl_tp queries long position → None
            result.scalar_one_or_none = MagicMock(return_value=None)
        elif n == 1:
            # Second call: check_sl_tp queries short position → position
            result.scalar_one_or_none = MagicMock(return_value=position)
        elif n == 2:
            # Third call: execute_cover re-queries short position → position
            result.scalar_one_or_none = MagicMock(return_value=position)
        else:
            # Fourth call: execute_cover queries account
            result.scalar_one = MagicMock(return_value=account)
        return result

    db.execute = mock_execute

    # Short at 40000, current price 42000 (up 5%), stop loss at 5%
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
            # First call: check_sl_tp queries long position → None
            result.scalar_one_or_none = MagicMock(return_value=None)
        elif n == 1:
            # Second call: check_sl_tp queries short position → position
            result.scalar_one_or_none = MagicMock(return_value=position)
        elif n == 2:
            # Third call: execute_cover re-queries short position → position
            result.scalar_one_or_none = MagicMock(return_value=position)
        else:
            # Fourth call: execute_cover queries account
            result.scalar_one = MagicMock(return_value=account)
        return result

    db.execute = mock_execute

    # Short at 40000, current price 36000 (down 10%), take profit at 10%
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
