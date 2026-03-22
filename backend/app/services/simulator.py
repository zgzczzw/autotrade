"""
模拟交易引擎
处理模拟买入/卖出逻辑
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.logger import get_logger
from app.models import Position, SimAccount, TriggerLog

logger = get_logger(__name__)


class Simulator:
    """模拟交易引擎"""

    async def execute_buy(
        self,
        strategy_id: int,
        symbol: str,
        quantity: float,
        price: float,
        db: AsyncSession,
        user_id: Optional[int] = None,
    ) -> Optional[TriggerLog]:
        """
        执行模拟买入

        Args:
            strategy_id: 策略 ID
            symbol: 交易对
            quantity: 买入数量
            price: 买入价格
            db: 数据库会话

        Returns:
            TriggerLog 记录
        """
        # 计算所需资金
        required_funds = quantity * price

        # 检查账户余额
        if user_id is not None:
            account_result = await db.execute(
                select(SimAccount).where(SimAccount.user_id == user_id)
            )
        else:
            account_result = await db.execute(select(SimAccount).limit(1))
        account = account_result.scalar_one()

        if account.balance < required_funds:
            logger.warning(
                f"Insufficient balance for buy: required={required_funds}, "
                f"balance={account.balance}"
            )
            # 记录 hold 操作
            trigger = TriggerLog(
                strategy_id=strategy_id,
                signal_type="buy",
                signal_detail="余额不足，跳过买入",
                action="hold",
                price=price,
                quantity=0,
            )
            db.add(trigger)
            await db.commit()
            return trigger

        # 扣除资金
        account.balance -= required_funds

        # 创建持仓
        position = Position(
            strategy_id=strategy_id,
            symbol=symbol,
            side="long",
            entry_price=price,
            quantity=quantity,
        )
        db.add(position)

        # 记录触发
        trigger = TriggerLog(
            strategy_id=strategy_id,
            signal_type="buy",
            signal_detail=f"买入 {quantity} {symbol} @ {price}",
            action="buy",
            price=price,
            quantity=quantity,
        )
        db.add(trigger)

        await db.commit()
        await db.refresh(trigger)

        logger.info(f"模拟买入: {symbol} {quantity} @ {price}")
        return trigger

    async def execute_sell(
        self,
        strategy_id: int,
        symbol: str,
        price: float,
        db: AsyncSession,
        sell_size_pct: float = 100.0,
        user_id: Optional[int] = None,
    ) -> Optional[TriggerLog]:
        """
        执行模拟卖出（平多仓）

        Args:
            strategy_id: 策略 ID
            symbol: 交易对
            price: 卖出价格
            db: 数据库会话

        Returns:
            TriggerLog 记录
        """
        # 查找未平仓的多头持仓
        result = await db.execute(
            select(Position).where(
                Position.strategy_id == strategy_id,
                Position.symbol == symbol,
                Position.side == "long",
                Position.closed_at.is_(None),
            )
        )
        position = result.scalar_one_or_none()

        if not position:
            logger.warning(f"No open position to sell for strategy {strategy_id}")
            trigger = TriggerLog(
                strategy_id=strategy_id,
                signal_type="sell",
                signal_detail="无持仓，跳过卖出",
                action="hold",
                price=price,
                quantity=0,
            )
            db.add(trigger)
            await db.commit()
            return trigger

        # 计算本次卖出数量（支持部分卖出）
        sell_qty = position.quantity * min(sell_size_pct, 100.0) / 100.0
        pnl = (price - position.entry_price) * sell_qty
        sell_value = price * sell_qty

        # 返还资金
        if user_id is not None:
            account_result = await db.execute(
                select(SimAccount).where(SimAccount.user_id == user_id)
            )
        else:
            account_result = await db.execute(select(SimAccount).limit(1))
        account = account_result.scalar_one()
        account.balance += sell_value
        account.total_pnl += pnl

        if sell_size_pct >= 100.0:
            # 全部平仓
            position.pnl = pnl
            position.current_price = price
            position.closed_at = datetime.utcnow()
        else:
            # 部分平仓：减少持仓数量
            position.quantity -= sell_qty

        # 记录触发
        trigger = TriggerLog(
            strategy_id=strategy_id,
            signal_type="sell",
            signal_detail=f"卖出 {sell_qty:.4f} {symbol} @ {price} ({sell_size_pct:.0f}%), 盈亏: {pnl:.2f}",
            action="sell",
            price=price,
            quantity=sell_qty,
            simulated_pnl=pnl,
        )
        db.add(trigger)

        await db.commit()
        await db.refresh(trigger)

        logger.info(f"模拟卖出: {symbol} {sell_qty:.4f} @ {price} ({sell_size_pct}%), PnL: {pnl:.2f}")
        return trigger

    async def execute_short(
        self,
        strategy_id: int,
        symbol: str,
        quantity: float,
        price: float,
        db: AsyncSession,
        user_id: Optional[int] = None,
    ) -> Optional[TriggerLog]:
        """执行模拟开空（锁定保证金）"""
        required_margin = quantity * price

        if user_id is not None:
            account_result = await db.execute(
                select(SimAccount).where(SimAccount.user_id == user_id)
            )
        else:
            account_result = await db.execute(select(SimAccount).limit(1))
        account = account_result.scalar_one()

        if account.balance < required_margin:
            logger.warning(
                f"Insufficient balance for short: required={required_margin}, "
                f"balance={account.balance}"
            )
            trigger = TriggerLog(
                strategy_id=strategy_id,
                signal_type="short",
                signal_detail="余额不足，跳过开空",
                action="hold",
                price=price,
                quantity=0,
            )
            db.add(trigger)
            await db.commit()
            return trigger

        account.balance -= required_margin

        position = Position(
            strategy_id=strategy_id,
            symbol=symbol,
            side="short",
            entry_price=price,
            quantity=quantity,
        )
        db.add(position)

        trigger = TriggerLog(
            strategy_id=strategy_id,
            signal_type="short",
            signal_detail=f"开空 {quantity} {symbol} @ {price}",
            action="short",
            price=price,
            quantity=quantity,
        )
        db.add(trigger)
        await db.commit()
        await db.refresh(trigger)

        logger.info(f"模拟开空: {symbol} {quantity} @ {price}")
        return trigger

    async def execute_cover(
        self,
        strategy_id: int,
        symbol: str,
        price: float,
        db: AsyncSession,
        user_id: Optional[int] = None,
    ) -> Optional[TriggerLog]:
        """执行模拟平空（始终全额平仓）"""
        result = await db.execute(
            select(Position).where(
                Position.strategy_id == strategy_id,
                Position.symbol == symbol,
                Position.side == "short",
                Position.closed_at.is_(None),
            )
        )
        position = result.scalar_one_or_none()

        if not position:
            logger.warning(f"No open short position to cover for strategy {strategy_id}")
            trigger = TriggerLog(
                strategy_id=strategy_id,
                signal_type="cover",
                signal_detail="无空仓，跳过平空",
                action="hold",
                price=price,
                quantity=0,
            )
            db.add(trigger)
            await db.commit()
            return trigger

        quantity = position.quantity
        pnl = (position.entry_price - price) * quantity  # 价跌盈利
        margin_returned = position.entry_price * quantity

        if user_id is not None:
            account_result = await db.execute(
                select(SimAccount).where(SimAccount.user_id == user_id)
            )
        else:
            account_result = await db.execute(select(SimAccount).limit(1))
        account = account_result.scalar_one()
        account.balance += margin_returned + pnl
        account.total_pnl += pnl

        position.pnl = pnl
        position.current_price = price
        position.closed_at = datetime.utcnow()

        trigger = TriggerLog(
            strategy_id=strategy_id,
            signal_type="cover",
            signal_detail=f"平空 {quantity:.4f} {symbol} @ {price}, 盈亏: {pnl:.2f}",
            action="cover",
            price=price,
            quantity=quantity,
            simulated_pnl=pnl,
        )
        db.add(trigger)
        await db.commit()
        await db.refresh(trigger)

        logger.info(f"模拟平空: {symbol} {quantity:.4f} @ {price}, PnL: {pnl:.2f}")
        return trigger

    async def check_stop_loss_take_profit(
        self,
        strategy_id: int,
        symbol: str,
        current_price: float,
        stop_loss_pct: Optional[float],
        take_profit_pct: Optional[float],
        db: AsyncSession,
        user_id: Optional[int] = None,
    ) -> Optional[TriggerLog]:
        """
        检查止盈止损

        Args:
            strategy_id: 策略 ID
            symbol: 交易对
            current_price: 当前价格
            stop_loss_pct: 止损百分比
            take_profit_pct: 止盈百分比
            db: 数据库会话

        Returns:
            如果触发止盈止损，返回 TriggerLog
        """
        result = await db.execute(
            select(Position).where(
                Position.strategy_id == strategy_id,
                Position.symbol == symbol,
                Position.side == "long",
                Position.closed_at.is_(None),
            )
        )
        position = result.scalar_one_or_none()

        if not position:
            return None

        entry_price = position.entry_price
        price_change_pct = (current_price - entry_price) / entry_price * 100

        # 检查止损
        if stop_loss_pct and price_change_pct <= -stop_loss_pct:
            logger.info(f"Stop loss triggered: {price_change_pct:.2f}%")
            trigger = await self.execute_sell(strategy_id, symbol, current_price, db, user_id=user_id)
            trigger.signal_detail = f"[止损] {trigger.signal_detail}"
            await db.commit()
            return trigger

        # 检查止盈
        if take_profit_pct and price_change_pct >= take_profit_pct:
            logger.info(f"Take profit triggered: {price_change_pct:.2f}%")
            trigger = await self.execute_sell(strategy_id, symbol, current_price, db, user_id=user_id)
            trigger.signal_detail = f"[止盈] {trigger.signal_detail}"
            await db.commit()
            return trigger

        return None


# 全局实例
simulator = Simulator()
