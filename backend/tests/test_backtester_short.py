"""测试 BacktestContext 空头交易支持"""
import pytest
from datetime import datetime
from unittest.mock import MagicMock

from app.engine.backtester import BacktestContext, BacktestEngine, VirtualAccount
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

        short_pos = Position(
            strategy_id=1, symbol="BTCUSDT", side="short",
            entry_price=40000.0, quantity=0.025,
        )
        account.positions.append(short_pos)
        account.balance = 99000.0

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

        kline = make_kline(42400.0)  # +6%
        ctx = BacktestContext(strategy, account, kline, [kline])

        engine = BacktestEngine()
        result = await engine._check_stop_loss_take_profit(ctx, strategy)

        assert result is True
        assert len(account.positions) == 0

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

        kline = make_kline(35600.0)  # -11%
        ctx = BacktestContext(strategy, account, kline, [kline])

        engine = BacktestEngine()
        result = await engine._check_stop_loss_take_profit(ctx, strategy)

        assert result is True
        assert len(account.positions) == 0
