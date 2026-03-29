"""
回测引擎
基于历史数据回测策略表现
支持单时间周期和多时间周期代码策略
"""

import asyncio
import json
import uuid
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from sqlalchemy.ext.asyncio import AsyncSession

from app.engine.indicators import IndicatorCalculator
from app.engine.market_data import market_data_service
from app.logger import get_logger
from app.models import BacktestResult, Position, Strategy

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# 持仓视图：同时支持属性访问和 .get() 方法（兼容代码策略中的 dict-style 调用）
# ---------------------------------------------------------------------------

class PositionView:
    """
    持仓数据视图

    BacktestContext.get_position() 返回此对象而非 ORM 实例，
    使代码策略中的 position.get("side") 调用能正常工作。
    """
    __slots__ = ("side", "entry_price", "quantity", "symbol", "strategy_id")

    def __init__(self, pos: Position):
        self.side = pos.side
        self.entry_price = pos.entry_price
        self.quantity = pos.quantity
        self.symbol = pos.symbol
        self.strategy_id = pos.strategy_id

    def get(self, key: str, default=None):
        return getattr(self, key, default)

    def __bool__(self):
        return True


# ---------------------------------------------------------------------------
# 虚拟账户
# ---------------------------------------------------------------------------

class VirtualAccount:
    """回测使用的虚拟账户"""

    def __init__(self, initial_balance: float = 100000.0):
        self.initial_balance = initial_balance
        self.balance = initial_balance
        self.total_pnl = 0.0
        self.positions: List[Position] = []
        self.trades: List[dict] = []

    def reset(self):
        self.balance = self.initial_balance
        self.total_pnl = 0.0
        self.positions = []
        self.trades = []


# ---------------------------------------------------------------------------
# 回测上下文
# ---------------------------------------------------------------------------

class BacktestContext:
    """回测上下文（传给策略代码，提供同步 API）"""

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

    def get_klines(self, limit: int = 100) -> List[dict]:
        """获取当前 bar 及之前的 K 线（ASC 顺序）"""
        total = len(self.all_klines)
        start = max(0, total - limit)
        return self.all_klines[start:]

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
            symbol=self.symbol,
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
            symbol=self.symbol,
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

    def get_position(self) -> Optional[PositionView]:
        """
        获取当前持仓视图。

        返回 PositionView（而非 ORM 对象），支持代码策略中的
        position.get("side") 调用方式。
        """
        if not self.account.positions:
            return None
        return PositionView(self.account.positions[0])

    def get_balance(self) -> float:
        return self.account.balance


# ---------------------------------------------------------------------------
# 回测引擎
# ---------------------------------------------------------------------------

class BacktestEngine:
    """回测引擎"""

    def __init__(self):
        self._running_tasks: Dict[int, asyncio.Event] = {}
        self._progress: Dict[int, dict] = {}

    def get_progress(self, strategy_id: int) -> Optional[dict]:
        return self._progress.get(strategy_id)

    def is_running(self, strategy_id: int) -> bool:
        return strategy_id in self._running_tasks

    def cancel_backtest(self, strategy_id: int) -> bool:
        if strategy_id not in self._running_tasks:
            return False
        self._running_tasks[strategy_id].set()
        logger.info(f"Backtest cancellation requested for strategy {strategy_id}")
        return True

    async def run_backtest(
        self,
        strategy: Strategy,
        symbol: str,
        start_date: datetime,
        end_date: datetime,
        initial_balance: float = 100000.0,
    ) -> BacktestResult:
        """运行回测"""
        if strategy.id in self._running_tasks:
            raise ValueError("该策略已有回测正在运行")

        cancel_event = asyncio.Event()
        self._running_tasks[strategy.id] = cancel_event
        try:
            return await self._run_single_symbol_backtest(
                strategy, symbol, start_date, end_date, initial_balance, cancel_event
            )
        finally:
            self._running_tasks.pop(strategy.id, None)

    async def run_multi_backtest(
        self,
        strategy: Strategy,
        symbols: List[str],
        start_date: datetime,
        end_date: datetime,
        initial_balance: float = 100000.0,
    ) -> List[BacktestResult]:
        """运行多品种回测"""
        if strategy.id in self._running_tasks:
            raise ValueError("该策略已有回测正在运行")

        cancel_event = asyncio.Event()
        self._running_tasks[strategy.id] = cancel_event
        batch_id = str(uuid.uuid4())
        results = []

        try:
            self._progress[strategy.id] = {"current_symbol": None, "completed": 0, "total": len(symbols)}
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
        """运行单品种回测（内部方法，不管理 _running_tasks）"""
        # 解析时间周期
        timeframes = [tf.strip() for tf in strategy.timeframe.split(",") if tf.strip()]
        primary_tf = timeframes[0]

        logger.info(
            f"Starting backtest: {strategy.name} | tf={strategy.timeframe} "
            f"| {start_date} → {end_date}"
        )

        # 获取主时间周期历史数据
        primary_klines = await market_data_service.fetch_historical_klines(
            symbol=symbol,
            timeframe=primary_tf,
            start_date=start_date,
            end_date=end_date,
        )

        if not primary_klines:
            raise ValueError("No historical data available for backtest")

        logger.info(f"Loaded {len(primary_klines)} klines for primary tf={primary_tf}")

        account = VirtualAccount(initial_balance)
        equity_curve: List[dict] = []

        try:
            is_multitf_code = (
                strategy.type == "code"
                and bool(strategy.code)
                and len(timeframes) > 1
            )

            if is_multitf_code:
                # 获取其余时间周期数据
                other_klines: Dict[str, List[dict]] = {}
                for tf in timeframes[1:]:
                    tf_data = await market_data_service.fetch_historical_klines(
                        symbol=symbol,
                        timeframe=tf,
                        start_date=start_date,
                        end_date=end_date,
                    )
                    other_klines[tf] = tf_data
                    logger.info(f"Loaded {len(tf_data)} klines for tf={tf}")

                equity_curve = await self._run_multitf_code_loop(
                    strategy, symbol, primary_tf, primary_klines, other_klines,
                    account, cancel_event,
                )
            else:
                equity_curve = await self._run_single_tf_loop(
                    strategy, symbol, primary_tf, primary_klines, account, cancel_event,
                )

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

        except asyncio.CancelledError:
            logger.info(f"Backtest for strategy {strategy.id} was cancelled")
            raise

        # 计算统计指标
        stats = self._calculate_stats(account, equity_curve, initial_balance)

        # K 线数据供前端图表展示
        klines_data = [
            {
                "time": k["open_time"].isoformat(),
                "open": k["open"], "high": k["high"],
                "low": k["low"], "close": k["close"], "volume": k["volume"],
            }
            for k in primary_klines
        ]

        result = BacktestResult(
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

        logger.info(
            f"Backtest completed: PnL={stats['total_pnl']:.2f} "
            f"({stats['pnl_percent']:.2f}%), "
            f"Trades={stats['total_trades']}, WinRate={stats['win_rate']:.1f}%"
        )
        return result

    # ------------------------------------------------------------------
    # 单时间周期回测主循环（可视化策略 + 单周期代码策略）
    # ------------------------------------------------------------------

    async def _run_single_tf_loop(
        self,
        strategy: Strategy,
        symbol: str,
        primary_tf: str,
        klines: List[dict],
        account: VirtualAccount,
        cancel_event: asyncio.Event,
    ) -> List[dict]:
        """单时间周期回测主循环"""
        from app.engine.sandbox import sandbox_executor

        equity_curve: List[dict] = []
        code_instance = None  # 代码策略持久化实例

        for i, kline in enumerate(klines):
            if cancel_event.is_set():
                raise asyncio.CancelledError("回测已被用户取消")

            ctx = BacktestContext(strategy, symbol, account, kline, klines[: i + 1])

            # 止盈止损
            sl_tp_triggered = await self._check_stop_loss_take_profit(ctx, strategy)

            if not sl_tp_triggered:
                if strategy.type == "visual":
                    signal, trigger = await self._execute_visual_strategy(strategy, ctx)
                    if signal == "buy":
                        ctx.buy(trigger_reason=trigger)
                    elif signal == "sell":
                        ctx.sell(trigger_reason=trigger)

                elif strategy.type == "code" and strategy.code:
                    # 创建或复用持久化实例
                    if code_instance is None:
                        try:
                            code_instance = sandbox_executor.create_instance(
                                strategy.code, ctx, strategy.id
                            )
                        except Exception as e:
                            logger.warning(f"Code instance creation failed: {e}")
                    else:
                        code_instance.ctx = ctx

                    if code_instance is not None:
                        try:
                            data = {
                                "symbol": symbol,
                                "timeframe": primary_tf,
                                "price": kline["close"],
                                "klines": klines[max(0, i - 99): i + 1],
                            }
                            signal = sandbox_executor.call_on_tick(code_instance, data)
                            if signal == "buy":
                                ctx.buy(trigger_reason="代码策略买入")
                            elif signal == "sell":
                                ctx.sell(trigger_reason="代码策略卖出")
                        except Exception as e:
                            logger.warning(f"Code on_tick error at bar {i}: {e}")
                            code_instance = None  # 出错后下次重新创建

            total_value = account.balance + sum(
                p.quantity * kline["close"] if p.side == "long"
                else p.entry_price * p.quantity + (p.entry_price - kline["close"]) * p.quantity
                for p in account.positions
            )
            equity_curve.append({
                "time": kline["open_time"].isoformat(),
                "balance": round(total_value, 2),
            })

            if i % 100 == 0:
                await asyncio.sleep(0)

        return equity_curve

    # ------------------------------------------------------------------
    # 多时间周期代码策略回测主循环
    # ------------------------------------------------------------------

    async def _run_multitf_code_loop(
        self,
        strategy: Strategy,
        symbol: str,
        primary_tf: str,
        primary_klines: List[dict],
        other_klines: Dict[str, List[dict]],
        account: VirtualAccount,
        cancel_event: asyncio.Event,
    ) -> List[dict]:
        """
        多时间周期代码策略回测主循环。

        以最小周期（primary_tf）的 K 线为主循环，
        每当其他周期出现新 K 线时，额外触发一次 on_tick 以更新策略内部缓存，
        从而模拟真实的多周期信号叠加。
        """
        from app.engine.sandbox import sandbox_executor

        equity_curve: List[dict] = []
        code_instance = None

        # 跟踪各非主周期已处理到的 kline 索引
        tf_cursor: Dict[str, int] = {tf: 0 for tf in other_klines}

        for i, kline in enumerate(primary_klines):
            if cancel_event.is_set():
                raise asyncio.CancelledError("回测已被用户取消")

            current_time = kline["open_time"]
            ctx = BacktestContext(strategy, symbol, account, kline, primary_klines[: i + 1])

            # 创建或复用持久化实例
            if code_instance is None:
                try:
                    code_instance = sandbox_executor.create_instance(
                        strategy.code, ctx, strategy.id
                    )
                except Exception as e:
                    logger.warning(f"Code instance creation failed: {e}")
            else:
                code_instance.ctx = ctx

            if code_instance is None:
                # 实例创建失败，只记录资金曲线
                total_value = account.balance + sum(
                    p.quantity * kline["close"] for p in account.positions
                )
                equity_curve.append({
                    "time": current_time.isoformat(),
                    "balance": round(total_value, 2),
                })
                continue

            # 止盈止损
            sl_tp_triggered = await self._check_stop_loss_take_profit(ctx, strategy)

            if not sl_tp_triggered:
                # ① 先更新各非主周期的 kline 缓存（按时间顺序向前推进）
                for tf, tf_klines in other_klines.items():
                    new_cursor = tf_cursor[tf]
                    while (
                        new_cursor < len(tf_klines)
                        and tf_klines[new_cursor]["open_time"] <= current_time
                    ):
                        new_cursor += 1

                    if new_cursor > tf_cursor[tf]:
                        tf_cursor[tf] = new_cursor
                        tf_slice = tf_klines[:new_cursor]
                        tf_price = tf_slice[-1]["close"]
                        try:
                            sig = sandbox_executor.call_on_tick(code_instance, {
                                "symbol": symbol,
                                "timeframe": tf,
                                "price": tf_price,
                                "klines": tf_slice[-100:],
                            })
                            if sig == "buy":
                                ctx.buy(trigger_reason=f"代码策略买入(tf={tf})")
                            elif sig == "sell":
                                ctx.sell(trigger_reason=f"代码策略卖出(tf={tf})")
                        except Exception as e:
                            logger.warning(f"Code on_tick tf={tf} error at bar {i}: {e}")
                            code_instance = None
                            break

                # ② 主时间周期 on_tick（策略在此更新 klines_3m 并评估信号）
                if code_instance is not None:
                    try:
                        sig = sandbox_executor.call_on_tick(code_instance, {
                            "symbol": symbol,
                            "timeframe": primary_tf,
                            "price": kline["close"],
                            "klines": primary_klines[max(0, i - 99): i + 1],
                        })
                        if sig == "buy":
                            ctx.buy(trigger_reason=f"代码策略买入(tf={primary_tf})")
                        elif sig == "sell":
                            ctx.sell(trigger_reason=f"代码策略卖出(tf={primary_tf})")
                    except Exception as e:
                        logger.warning(
                            f"Code on_tick tf={primary_tf} error at bar {i}: {e}"
                        )
                        code_instance = None

            total_value = account.balance + sum(
                p.quantity * kline["close"] if p.side == "long"
                else p.entry_price * p.quantity + (p.entry_price - kline["close"]) * p.quantity
                for p in account.positions
            )
            equity_curve.append({
                "time": current_time.isoformat(),
                "balance": round(total_value, 2),
            })

            if i % 100 == 0:
                await asyncio.sleep(0)

        return equity_curve

    # ------------------------------------------------------------------
    # 止盈止损
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # 可视化策略执行
    # ------------------------------------------------------------------

    async def _execute_visual_strategy(
        self,
        strategy: Strategy,
        ctx: BacktestContext,
    ) -> Tuple[Optional[str], str]:
        """执行可视化策略，返回 (信号, 触发描述)"""
        import json as _json

        if not strategy.config_json:
            return None, ""

        try:
            config = _json.loads(strategy.config_json)
        except _json.JSONDecodeError:
            return None, ""

        klines = ctx.get_klines(limit=100)
        if not klines:
            return None, ""

        calculator = IndicatorCalculator(klines)
        position = ctx.get_position()

        if position:
            sell_conditions = config.get("sell_conditions", {})
            if self._check_conditions(sell_conditions, calculator):
                trigger = self._collect_trigger_description(sell_conditions, calculator)
                return "sell", trigger
        else:
            buy_conditions = config.get("buy_conditions", {})
            if self._check_conditions(buy_conditions, calculator):
                trigger = self._collect_trigger_description(buy_conditions, calculator)
                return "buy", trigger

        return None, ""

    def _check_conditions(self, conditions: dict, calculator: IndicatorCalculator) -> bool:
        logic = conditions.get("logic", "AND")
        rules = conditions.get("rules", [])
        if not rules:
            return False
        results = [
            self._check_conditions(r, calculator)
            if r.get("type") == "group" or ("logic" in r and "indicator" not in r)
            else self._check_single_condition(r, calculator)
            for r in rules
        ]
        return all(results) if logic == "AND" else any(results)

    def _check_single_condition(self, rule: dict, calculator: IndicatorCalculator) -> bool:
        indicator = rule.get("indicator")
        params = rule.get("params", {})
        operator = rule.get("operator")
        value = rule.get("value")

        if indicator == "RSI":
            actual = calculator.rsi(params.get("period", 14))
        elif indicator == "MA_CROSS":
            return calculator.ma_cross(params.get("fast", 5), params.get("slow", 20)) == value
        elif indicator == "BOLL":
            return calculator.bollinger_touch(params.get("period", 20), params.get("std_dev", 2.0)) == value
        elif indicator == "MACD":
            return calculator.macd_signal(params.get("fast", 12), params.get("slow", 26), params.get("signal", 9)) == value
        elif indicator == "KDJ":
            return calculator.kdj_signal(params.get("period", 9)) == value
        elif indicator == "VOLUME":
            return calculator.volume_spike(params.get("ma_period", 20), float(value) if value is not None else 1.5)
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
            if operator == "<":   return actual < v
            if operator == ">":   return actual > v
            if operator == "==":  return actual == v
            if operator == "<=":  return actual <= v
            if operator == ">=":  return actual >= v
        except Exception:
            return False
        return False

    def _describe_single_condition(self, rule: dict) -> str:
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

    # ------------------------------------------------------------------
    # 统计指标计算
    # ------------------------------------------------------------------

    def _calculate_stats(
        self,
        account: VirtualAccount,
        equity_curve: List[dict],
        initial_balance: float,
    ) -> dict:
        realized_pnl = account.total_pnl
        total_pnl = realized_pnl
        pnl_percent = (total_pnl / initial_balance) * 100

        open_trades = [t for t in account.trades if t["side"] in ("buy", "short")]
        close_trades = [t for t in account.trades if t["side"] in ("sell", "cover")]
        total_trades = len(open_trades) + len(close_trades)
        completed_trades = len(close_trades)

        winning_trades = [t for t in close_trades if t.get("pnl", 0) > 0]
        win_rate = (len(winning_trades) / completed_trades * 100) if completed_trades > 0 else 0

        max_drawdown = self._calculate_max_drawdown(equity_curve)
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


# 全局实例
backtest_engine = BacktestEngine()


def get_backtest_engine() -> BacktestEngine:
    return backtest_engine
