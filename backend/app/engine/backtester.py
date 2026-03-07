"""
回测引擎
基于历史数据回测策略表现
"""

import asyncio
import json
from copy import deepcopy
from datetime import datetime, timedelta
from typing import Dict, List, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.executor import StrategyContext
from app.engine.indicators import IndicatorCalculator
from app.engine.market_data import market_data_service
from app.logger import get_logger
from app.models import BacktestResult, Position, Strategy, TriggerLog

logger = get_logger(__name__)


class VirtualAccount:
    """回测使用的虚拟账户"""

    def __init__(self, initial_balance: float = 100000.0):
        self.initial_balance = initial_balance
        self.balance = initial_balance
        self.total_pnl = 0.0
        self.positions: List[Position] = []
        self.trades: List[dict] = []

    def reset(self):
        """重置账户"""
        self.balance = self.initial_balance
        self.total_pnl = 0.0
        self.positions = []
        self.trades = []


class BacktestContext:
    """回测上下文"""

    def __init__(
        self,
        strategy: Strategy,
        account: VirtualAccount,
        current_kline: dict,
        all_klines: List[dict],
    ):
        self.strategy = strategy
        self.account = account
        self.current_kline = current_kline
        self.all_klines = all_klines

    def get_klines(self, limit: int = 100) -> List[dict]:
        """获取 K 线数据"""
        idx = self.all_klines.index(self.current_kline)
        start_idx = max(0, idx - limit + 1)
        return self.all_klines[start_idx : idx + 1]

    def buy(self, quantity: Optional[float] = None, trigger_reason: str = "") -> bool:
        """买入（回测模式）"""
        price = self.current_kline["close"]
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
        """卖出（回测模式）"""
        if not self.account.positions:
            return False

        position = self.account.positions[0]
        price = self.current_kline["close"]
        sell_size_pct = getattr(self.strategy, "sell_size_pct", 100.0) or 100.0
        sell_qty = quantity if quantity is not None else position.quantity * min(sell_size_pct, 100.0) / 100.0

        pnl = (price - position.entry_price) * sell_qty
        sell_value = price * sell_qty

        self.account.balance += sell_value
        self.account.total_pnl += pnl

        self.account.trades.append({
            "time": self.current_kline["open_time"].isoformat(),
            "side": "sell",
            "price": price,
            "quantity": sell_qty,
            "pnl": pnl,
            "trigger": trigger_reason,
        })

        if sell_size_pct >= 100.0 or quantity is None and sell_qty >= position.quantity:
            position.current_price = price
            position.pnl = pnl
            position.closed_at = self.current_kline["open_time"]
            self.account.positions.remove(position)
        else:
            position.quantity -= sell_qty

        return True

    def get_position(self) -> Optional[Position]:
        """获取当前持仓"""
        return self.account.positions[0] if self.account.positions else None

    def get_balance(self) -> float:
        """获取账户余额"""
        return self.account.balance

    def _calculate_buy_quantity(self, price: float) -> float:
        """计算买入数量"""
        if self.strategy.position_size_type == "percent":
            return self.account.balance * self.strategy.position_size / 100.0 / price
        return self.strategy.position_size / price


class BacktestEngine:
    """回测引擎"""

    def __init__(self):
        # 存储正在运行的回测任务
        self._running_tasks: Dict[int, asyncio.Event] = {}

    def is_running(self, strategy_id: int) -> bool:
        """检查策略是否正在回测"""
        return strategy_id in self._running_tasks

    def cancel_backtest(self, strategy_id: int) -> bool:
        """
        取消正在运行的回测
        
        Returns:
            bool: 是否成功取消
        """
        if strategy_id not in self._running_tasks:
            return False
        
        cancel_event = self._running_tasks[strategy_id]
        cancel_event.set()
        logger.info(f"Backtest cancellation requested for strategy {strategy_id}")
        return True

    async def run_backtest(
        self,
        strategy: Strategy,
        start_date: datetime,
        end_date: datetime,
        initial_balance: float = 100000.0,
    ) -> BacktestResult:
        """
        运行回测

        Args:
            strategy: 策略实例
            start_date: 回测开始时间
            end_date: 回测结束时间
            initial_balance: 初始资金

        Returns:
            BacktestResult 实例
        """
        # 检查是否已有回测在运行
        if strategy.id in self._running_tasks:
            raise ValueError("该策略已有回测正在运行")

        # 创建取消事件
        cancel_event = asyncio.Event()
        self._running_tasks[strategy.id] = cancel_event

        logger.info(
            f"Starting backtest for strategy {strategy.name} "
            f"from {start_date} to {end_date}"
        )

        # 1. 获取历史 K 线数据
        klines = await market_data_service.fetch_historical_klines(
            symbol=strategy.symbol,
            timeframe=strategy.timeframe,
            start_date=start_date,
            end_date=end_date,
        )

        if not klines:
            raise ValueError("No historical data available for backtest")

        logger.info(f"Loaded {len(klines)} klines for backtest")

        # 2. 创建虚拟账户
        account = VirtualAccount(initial_balance)

        # 3. 运行回测（逐 K 线执行）
        equity_curve = []

        try:
            for i, kline in enumerate(klines):
                # 检查是否被取消
                if cancel_event.is_set():
                    logger.info(f"Backtest cancelled for strategy {strategy.id} at kline {i}")
                    raise asyncio.CancelledError("回测已被用户取消")
                
                # 创建回测上下文
                ctx = BacktestContext(strategy, account, kline, klines[: i + 1])

                # 检查止盈止损；触发后本根 K 线跳过策略信号
                sl_tp_triggered = await self._check_stop_loss_take_profit(ctx, strategy)
                if not sl_tp_triggered:
                    # 执行策略逻辑，返回 (信号, 触发描述)
                    signal, trigger = await self._execute_strategy_logic(strategy, ctx)
                    if signal == "buy":
                        ctx.buy(trigger_reason=trigger)
                    elif signal == "sell":
                        ctx.sell(trigger_reason=trigger)

                # 记录资金曲线
                total_value = account.balance
                for pos in account.positions:
                    total_value += pos.quantity * kline["close"]

                equity_curve.append({
                    "time": kline["open_time"].isoformat(),
                    "balance": round(total_value, 2),
                })

                # 每100根K线检查一次取消，避免过于频繁
                if i % 100 == 0:
                    await asyncio.sleep(0)

            # 回测结束：平仓所有持仓
            if account.positions:
                last_kline = klines[-1]
                for pos in list(account.positions):
                    price = last_kline["close"]
                    pnl = (price - pos.entry_price) * pos.quantity
                    sell_value = price * pos.quantity
                    
                    account.balance += sell_value
                    account.total_pnl += pnl
                    
                    account.trades.append({
                        "time": last_kline["open_time"].isoformat(),
                        "side": "sell",
                        "price": price,
                        "quantity": pos.quantity,
                        "pnl": pnl,
                    })
                    account.positions.remove(pos)
                
                logger.info(f"回测结束：已平掉所有持仓，最终盈亏: {account.total_pnl:.2f}")

        except asyncio.CancelledError:
            logger.info(f"Backtest for strategy {strategy.id} was cancelled")
            raise
        finally:
            # 清理任务记录
            self._running_tasks.pop(strategy.id, None)

        # 4. 计算统计指标
        stats = self._calculate_stats(account, equity_curve, initial_balance)

        # 5. 准备K线数据（用于前端图表显示）
        klines_data = []
        for k in klines:
            klines_data.append({
                "time": k["open_time"].isoformat(),
                "open": k["open"],
                "high": k["high"],
                "low": k["low"],
                "close": k["close"],
                "volume": k["volume"],
            })

        # 6. 创建回测结果
        result = BacktestResult(
            strategy_id=strategy.id,
            symbol=strategy.symbol,
            timeframe=strategy.timeframe,
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

        logger.info(
            f"Backtest completed: PnL={stats['total_pnl']:.2f} "
            f"({stats['pnl_percent']:.2f}%), "
            f"Trades={stats['total_trades']}, "
            f"Win Rate={stats['win_rate']:.2f}%"
        )

        return result

    async def _check_stop_loss_take_profit(
        self,
        ctx: BacktestContext,
        strategy: Strategy,
    ) -> bool:
        """检查止盈止损，返回 True 表示已触发（本 K 线应跳过策略信号）"""
        position = ctx.get_position()
        if not position:
            return False

        current_price = ctx.current_kline["close"]
        entry_price = position.entry_price
        price_change_pct = (current_price - entry_price) / entry_price * 100

        # 检查止损
        if strategy.stop_loss and price_change_pct <= -strategy.stop_loss:
            ctx.sell(trigger_reason=f"止损 ({price_change_pct:+.2f}%)")
            return True

        # 检查止盈
        if strategy.take_profit and price_change_pct >= strategy.take_profit:
            ctx.sell(trigger_reason=f"止盈 ({price_change_pct:+.2f}%)")
            return True

        return False

    async def _execute_strategy_logic(
        self,
        strategy: Strategy,
        ctx: BacktestContext,
    ) -> tuple:
        """执行策略逻辑，返回 (信号, 触发描述)"""
        if strategy.type == "visual":
            return await self._execute_visual_strategy(strategy, ctx)
        else:
            # 代码策略在回测中简化处理
            return None, ""

    async def _execute_visual_strategy(
        self,
        strategy: Strategy,
        ctx: BacktestContext,
    ) -> tuple:
        """执行可视化策略，返回 (信号, 触发描述)"""
        import json

        if not strategy.config_json:
            return None, ""

        try:
            config = json.loads(strategy.config_json)
        except json.JSONDecodeError:
            return None, ""

        # 获取 K 线数据
        klines = ctx.get_klines(limit=100)
        if not klines:
            return None, ""

        calculator = IndicatorCalculator(klines)

        # 检查是否有持仓
        position = ctx.get_position()

        # 如果有持仓，检查卖出条件
        if position:
            sell_conditions = config.get("sell_conditions", {})
            if self._check_conditions(sell_conditions, calculator):
                trigger = self._collect_trigger_description(sell_conditions, calculator)
                return "sell", trigger

        # 如果没有持仓，检查买入条件
        else:
            buy_conditions = config.get("buy_conditions", {})
            if self._check_conditions(buy_conditions, calculator):
                trigger = self._collect_trigger_description(buy_conditions, calculator)
                return "buy", trigger

        return None, ""

    def _check_conditions(
        self,
        conditions: dict,
        calculator: IndicatorCalculator,
    ) -> bool:
        """检查条件组合（支持嵌套 group）"""
        logic = conditions.get("logic", "AND")
        rules = conditions.get("rules", [])

        if not rules:
            return False

        results = []
        for rule in rules:
            if rule.get("type") == "group" or ("logic" in rule and "indicator" not in rule):
                result = self._check_conditions(rule, calculator)
            else:
                result = self._check_single_condition(rule, calculator)
            results.append(result)

        return all(results) if logic == "AND" else any(results)

    def _check_single_condition(
        self,
        rule: dict,
        calculator: IndicatorCalculator,
    ) -> bool:
        """检查单个条件规则"""
        indicator = rule.get("indicator")
        params = rule.get("params", {})
        operator = rule.get("operator")
        value = rule.get("value")

        # ── 枚举类指标 ──────────────────────────────────────
        if indicator == "RSI":
            actual = calculator.rsi(params.get("period", 14))
        elif indicator in ("MA_CROSS", "BOLL"):
            # 兼容旧格式 key
            if indicator == "MA_CROSS":
                actual = calculator.ma_cross(
                    params.get("fast", 5), params.get("slow", 20)
                )
            else:
                actual = calculator.bollinger_touch(
                    params.get("period", 20), params.get("std_dev", 2.0)
                )
            return actual == value
        elif indicator == "MACD":
            actual = calculator.macd_signal(
                params.get("fast", 12),
                params.get("slow", 26),
                params.get("signal", 9),
            )
            return actual == value
        elif indicator == "KDJ":
            actual = calculator.kdj_signal(params.get("period", 9))
            return actual == value
        # ── 数值类指标 ──────────────────────────────────────
        elif indicator == "VOLUME":
            multiplier = float(value) if value is not None else 1.5
            return calculator.volume_spike(params.get("ma_period", 20), multiplier)
        elif indicator == "PRICE_CHANGE":
            actual = calculator.price_change_pct()
        elif indicator == "PRICE":
            actual = calculator.current_price()
        else:
            return False

        if actual is None:
            return False

        try:
            v = float(value)
            if operator == "<":
                return actual < v
            elif operator == ">":
                return actual > v
            elif operator == "==":
                return actual == v
            elif operator == "<=":
                return actual <= v
            elif operator == ">=":
                return actual >= v
        except Exception:
            return False

        return False

    def _describe_single_condition(self, rule: dict) -> str:
        """生成单条条件的人类可读描述"""
        indicator = rule.get("indicator", "")
        params = rule.get("params", {})
        operator = rule.get("operator", "")
        value = rule.get("value", "")

        ENUM_LABELS = {
            "golden": "金叉", "death": "死叉",
            "above_upper": "突破上轨", "below_lower": "跌破下轨",
            "k_cross_up": "K上穿D(金叉)", "k_cross_down": "K下穿D(死叉)",
            "overbought": "超买(K>80)", "oversold": "超卖(K<20)",
            "above_zero": "柱状图>0", "below_zero": "柱状图<0",
        }

        if indicator == "RSI":
            return f"RSI({params.get('period', 14)}) {operator} {value}"
        elif indicator == "MA_CROSS":
            return f"MA({params.get('fast', 5)}/{params.get('slow', 20)}) {ENUM_LABELS.get(str(value), str(value))}"
        elif indicator == "BOLL":
            return f"BOLL({params.get('period', 20)}) {ENUM_LABELS.get(str(value), str(value))}"
        elif indicator == "MACD":
            return f"MACD {ENUM_LABELS.get(str(value), str(value))}"
        elif indicator == "KDJ":
            return f"KDJ {ENUM_LABELS.get(str(value), str(value))}"
        elif indicator == "VOLUME":
            return f"成交量 > {value}倍均量"
        elif indicator == "PRICE_CHANGE":
            return f"涨跌幅 {operator} {value}%"
        elif indicator == "PRICE":
            return f"价格 {operator} {value}"
        return indicator

    def _collect_trigger_description(self, conditions: dict, calculator: IndicatorCalculator) -> str:
        """收集已命中条件的描述文字"""
        logic = conditions.get("logic", "AND")
        rules = conditions.get("rules", [])
        descs = []
        for rule in rules:
            if rule.get("type") == "group" or ("logic" in rule and "indicator" not in rule):
                if self._check_conditions(rule, calculator):
                    descs.append(self._collect_trigger_description(rule, calculator))
            else:
                if self._check_single_condition(rule, calculator):
                    descs.append(self._describe_single_condition(rule))
        sep = " + " if logic == "AND" else " | "
        return sep.join(d for d in descs if d)

    def _calculate_stats(
        self,
        account: VirtualAccount,
        equity_curve: List[dict],
        initial_balance: float,
    ) -> dict:
        """计算回测统计指标"""
        # 计算已实现盈亏（来自卖出交易）
        realized_pnl = account.total_pnl
        
        # 计算浮动盈亏（来自未平仓持仓）
        unrealized_pnl = 0.0
        if account.positions and equity_curve:
            current_price = equity_curve[-1].get("balance", account.balance)
            # 从资金曲线反推当前价格
            for pos in account.positions:
                # 使用持仓的 entry_price 和 current_price 计算浮动盈亏
                unrealized_pnl += pos.pnl if pos.pnl else 0
        
        total_pnl = realized_pnl + unrealized_pnl
        pnl_percent = (total_pnl / initial_balance) * 100

        # 统计交易次数（买入和卖出都统计）
        buy_trades = [t for t in account.trades if t["side"] == "buy"]
        sell_trades = [t for t in account.trades if t["side"] == "sell"]
        total_trades = len(buy_trades) + len(sell_trades)
        
        # 已完成交易对数（一次完整买卖算一对）
        completed_trades = len(sell_trades)

        # 胜率（基于已完成交易）
        winning_trades = [t for t in sell_trades if t.get("pnl", 0) > 0]
        win_rate = (len(winning_trades) / completed_trades * 100) if completed_trades > 0 else 0

        # 最大回撤
        max_drawdown = self._calculate_max_drawdown(equity_curve)

        # 平均持仓时间
        avg_hold_time = self._calculate_avg_hold_time(account.trades)

        return {
            "total_pnl": total_pnl,
            "pnl_percent": pnl_percent,
            "win_rate": win_rate,
            "max_drawdown": max_drawdown,
            "total_trades": total_trades,
            "avg_hold_time": avg_hold_time,
        }

    def _calculate_max_drawdown(self, equity_curve: List[dict]) -> float:
        """计算最大回撤"""
        if not equity_curve:
            return 0.0

        max_drawdown = 0.0
        peak = equity_curve[0]["balance"]

        for point in equity_curve:
            balance = point["balance"]
            if balance > peak:
                peak = balance
            drawdown = (peak - balance) / peak * 100
            if drawdown > max_drawdown:
                max_drawdown = drawdown

        return max_drawdown

    def _calculate_avg_hold_time(self, trades: List[dict]) -> Optional[int]:
        """计算平均持仓时间（秒）"""
        hold_times = []
        buy_time = None

        for trade in trades:
            if trade["side"] == "buy":
                buy_time = datetime.fromisoformat(trade["time"])
            elif trade["side"] == "sell" and buy_time:
                sell_time = datetime.fromisoformat(trade["time"])
                hold_time = (sell_time - buy_time).total_seconds()
                hold_times.append(int(hold_time))
                buy_time = None

        if not hold_times:
            return None

        return int(sum(hold_times) / len(hold_times))


# 全局实例
backtest_engine = BacktestEngine()


def get_backtest_engine() -> BacktestEngine:
    """获取回测引擎实例"""
    return backtest_engine
