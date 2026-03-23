"""
策略执行器
- 可视化策略解析执行
- 代码策略沙箱执行（持久化实例，跨 tick 保留状态）
- 策略上下文
"""

import json
from typing import Any, Dict, List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.engine.base_strategy import BaseStrategy
from app.engine.indicators import IndicatorCalculator
from app.engine.market_data import market_data_service
from app.engine.sandbox import sandbox_executor
from app.logger import get_logger
from app.models import Position, Strategy, TriggerLog
from app.services.feishu import notification_service
from app.services.simulator import simulator


logger = get_logger(__name__)


class StrategyContext:
    """
    策略上下文

    提供给策略代码使用的 API
    """

    def __init__(self, strategy: Strategy, db: AsyncSession, current_kline: Optional[dict] = None):
        self.strategy = strategy
        self.db = db
        self.current_kline = current_kline

    async def get_klines(self, limit: int = 100) -> List[dict]:
        """获取 K 线数据（使用策略主时间周期）"""
        primary_tf = self.strategy.timeframe.split(",")[0].strip()
        return await market_data_service.get_klines(
            symbol=self.strategy.symbol,
            timeframe=primary_tf,
            limit=limit,
            db=self.db,
        )

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

    async def get_position(self) -> Optional[Position]:
        """获取当前持仓（任意方向），如有多条取最新一条"""
        result = await self.db.execute(
            select(Position).where(
                Position.strategy_id == self.strategy.id,
                Position.symbol == self.strategy.symbol,
                Position.closed_at.is_(None),
            ).order_by(Position.id.desc())
        )
        return result.scalars().first()

    async def get_balance(self) -> float:
        """获取账户余额（当前用户的 SimAccount）"""
        from app.models import SimAccount

        user_id = getattr(self.strategy, "user_id", None)
        if user_id is not None:
            result = await self.db.execute(
                select(SimAccount).where(SimAccount.user_id == user_id)
            )
        else:
            result = await self.db.execute(select(SimAccount).limit(1))
        account = result.scalar_one()
        return account.balance



class StrategyExecutor:
    """策略执行器"""

    def __init__(self):
        # 持久化代码策略实例，key = strategy_id
        # 跨 tick 保留状态（如缓存的多周期 K 线数据）
        self._strategy_instances: Dict[int, Any] = {}

    def release_instance(self, strategy_id: int) -> None:
        """
        释放策略持久化实例（策略停止时调用）。
        调用 on_stop() 做清理，失败只 warning 不抛出。
        """
        instance = self._strategy_instances.pop(strategy_id, None)
        if instance is None:
            return
        try:
            instance.on_stop()
        except Exception as e:
            logger.warning(f"Strategy {strategy_id} on_stop() error (ignored): {e}")
        logger.info(f"Strategy {strategy_id} instance released")

    async def execute(self, strategy: Strategy, timeframe: Optional[str] = None):
        """
        执行策略。

        Args:
            strategy: 策略实例
            timeframe: 当前触发的时间周期（多时间周期策略由调度器按周期传入）。
                       None 时取 strategy.timeframe 的第一个周期。
        """
        # 确定本次执行的时间周期
        active_tf = timeframe if timeframe else strategy.timeframe.split(",")[0].strip()

        logger.info(
            f"Executing strategy: {strategy.name} (ID: {strategy.id}, tf={active_tf})"
        )

        async with async_session() as db:
            # 拉取当前时间周期的 K 线（ASC 顺序，[-1] 为最新）
            klines = await market_data_service.get_klines(
                symbol=strategy.symbol,
                timeframe=active_tf,
                limit=100,
                db=db,
            )
            current_kline = klines[-1] if klines else None

            ctx = StrategyContext(strategy, db, current_kline)

            try:
                sl_tp_trigger = None
                # 1. 检查止盈止损
                if current_kline:
                    current_price = current_kline["close"]
                    sl_tp_trigger = await simulator.check_stop_loss_take_profit(
                        strategy_id=strategy.id,
                        symbol=strategy.symbol,
                        current_price=current_price,
                        stop_loss_pct=strategy.stop_loss,
                        take_profit_pct=strategy.take_profit,
                        db=db,
                        user_id=getattr(strategy, "user_id", None),
                    )
                    if sl_tp_trigger and strategy.notify_enabled:
                        await self._send_notification(sl_tp_trigger, strategy, db)

                # 2. 执行策略逻辑（止盈止损已触发则跳过）
                trigger = None
                if not sl_tp_trigger:
                    if strategy.type == "visual":
                        signal = await self._execute_visual_strategy(strategy, ctx)
                    else:
                        signal = await self._execute_code_strategy(
                            strategy, ctx, klines, current_kline, active_tf
                        )

                    # 3. 执行交易信号
                    if signal in ("buy", "cover"):
                        trigger = await ctx.buy()
                    elif signal in ("sell", "short"):
                        trigger = await ctx.sell()

                # 4. 发送通知
                if trigger and strategy.notify_enabled:
                    await self._send_notification(trigger, strategy, db)

            except Exception as e:
                logger.error(f"Error executing strategy {strategy.id}: {e}")
                strategy.status = "error"
                await db.commit()
                raise

    async def _send_notification(
        self,
        trigger: TriggerLog,
        strategy: Strategy,
        db: AsyncSession,
    ):
        """发送通知（Feishu + Bark，各自独立判断）"""
        try:
            await notification_service.send_strategy_notification(
                trigger_log=trigger,
                strategy_name=strategy.name,
                symbol=strategy.symbol,
                db=db,
                user_id=getattr(strategy, "user_id", None),
            )
        except Exception as e:
            logger.error(f"Failed to send notification: {e}")

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

    async def _execute_code_strategy(
        self,
        strategy: Strategy,
        ctx: StrategyContext,
        klines: List[dict],
        current_kline: Optional[dict],
        active_tf: str,
    ) -> Optional[str]:
        """
        执行代码策略（使用持久化实例，跨 tick 保留状态）。

        首次执行时创建实例并调用 on_start()；后续复用实例，每次更新 ctx。
        """
        if not strategy.code:
            return None

        try:
            # 获取或创建持久化实例
            instance = self._strategy_instances.get(strategy.id)
            if instance is None:
                instance = sandbox_executor.create_instance(
                    code=strategy.code,
                    context=ctx,
                    strategy_id=strategy.id,
                )
                self._strategy_instances[strategy.id] = instance
            else:
                # 更新 ctx（db session 每次都是新的，必须注入最新的）
                instance.ctx = ctx

            # 调用 on_tick，传入当前触发周期的数据
            data = {
                "symbol": strategy.symbol,
                "timeframe": active_tf,
                "price": current_kline["close"] if current_kline else 0,
                "klines": klines,
            }
            signal = sandbox_executor.call_on_tick(instance, data)
            return signal

        except Exception as e:
            logger.error(f"Code strategy {strategy.id} execution failed: {e}")
            # 实例出错，清除后下次重新创建
            self._strategy_instances.pop(strategy.id, None)
            # 记录错误
            error_trigger = TriggerLog(
                strategy_id=strategy.id,
                signal_type="error",
                signal_detail=f"代码执行错误: {str(e)}",
                action="hold",
            )
            ctx.db.add(error_trigger)
            await ctx.db.commit()
            return None

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

        if indicator == "RSI":
            actual_value = calculator.rsi(params.get("period", 14))
        elif indicator in ("MA_CROSS", "BOLL"):
            if indicator == "MA_CROSS":
                actual_value = calculator.ma_cross(params.get("fast", 5), params.get("slow", 20))
            else:
                actual_value = calculator.bollinger_touch(params.get("period", 20), params.get("std_dev", 2.0))
            return actual_value == value
        elif indicator == "MACD":
            actual_value = calculator.macd_signal(params.get("fast", 12), params.get("slow", 26), params.get("signal", 9))
            return actual_value == value
        elif indicator == "KDJ":
            actual_value = calculator.kdj_signal(params.get("period", 9))
            return actual_value == value
        elif indicator == "VOLUME":
            return calculator.volume_spike(params.get("ma_period", 20), float(value) if value is not None else 1.5)
        elif indicator == "PRICE_CHANGE":
            actual_value = calculator.price_change_pct()
        elif indicator == "PRICE":
            actual_value = calculator.current_price()
        else:
            return False

        if actual_value is None:
            return False

        try:
            v = float(value)
            if operator == "<":
                return actual_value < v
            elif operator == ">":
                return actual_value > v
            elif operator == "==":
                return actual_value == v
            elif operator == "<=":
                return actual_value <= v
            elif operator == ">=":
                return actual_value >= v
        except Exception as e:
            logger.error(f"Error comparing values: {e}")
            return False

        return False


# 全局实例
executor = StrategyExecutor()
