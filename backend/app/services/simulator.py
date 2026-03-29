"""
模拟交易引擎
处理模拟买入/卖出逻辑
"""

from datetime import datetime, timezone
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
            return None

        # 扣除资金
        account.balance -= required_funds

        # 创建持仓
        position = Position(
            strategy_id=strategy_id,
            symbol=symbol,
            side="long",
            entry_price=price,
            quantity=quantity,
            user_id=user_id,
        )
        db.add(position)

        # 记录触发
        trigger = TriggerLog(
            strategy_id=strategy_id,
            symbol=symbol,
            signal_type="买入",
            signal_detail=f"买入 {quantity} {symbol} @ {price}",
            action="买入",
            price=price,
            quantity=quantity,
            position_effect="开仓",
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
        # 查找所有未平仓的多头持仓
        result = await db.execute(
            select(Position).where(
                Position.strategy_id == strategy_id,
                Position.symbol == symbol,
                Position.side == "long",
                Position.closed_at.is_(None),
            ).order_by(Position.id)
        )
        positions = list(result.scalars().all())

        if not positions:
            logger.warning(f"No open position to sell for strategy {strategy_id}")
            return None

        # 返还资金
        if user_id is not None:
            account_result = await db.execute(
                select(SimAccount).where(SimAccount.user_id == user_id)
            )
        else:
            account_result = await db.execute(select(SimAccount).limit(1))
        account = account_result.scalar_one()

        # 平掉所有多头持仓
        total_sell_qty = 0.0
        total_pnl = 0.0
        for position in positions:
            sell_qty = position.quantity * min(sell_size_pct, 100.0) / 100.0
            pnl = (price - position.entry_price) * sell_qty
            sell_value = price * sell_qty

            account.balance += sell_value
            account.total_pnl += pnl

            if sell_size_pct >= 100.0:
                position.pnl = pnl
                position.current_price = price
                position.closed_at = datetime.utcnow()
            else:
                position.quantity -= sell_qty

            total_sell_qty += sell_qty
            total_pnl += pnl

        # 记录触发
        trigger = TriggerLog(
            strategy_id=strategy_id,
            symbol=symbol,
            signal_type="卖出",
            signal_detail=f"卖出 {total_sell_qty:.4f} {symbol} @ {price} ({sell_size_pct:.0f}%), 盈亏: {total_pnl:.2f} USDT",
            action="卖出",
            price=price,
            quantity=total_sell_qty,
            simulated_pnl=total_pnl,
            position_effect="平仓",
        )
        db.add(trigger)

        await db.commit()
        await db.refresh(trigger)

        logger.info(f"模拟卖出: {symbol} {total_sell_qty:.4f} @ {price} ({sell_size_pct}%), PnL: {total_pnl:.2f}")
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
        """执行模拟开空（锁定保证金）

        Args:
            strategy_id: 策略 ID
            symbol: 交易对
            quantity: 开空数量
            price: 开空价格
            db: 数据库会话
            user_id: 用户 ID（用于查找 SimAccount）

        Returns:
            TriggerLog（action="卖出" 成功开空，action="观望" 余额不足跳过）
        """
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
            return None

        account.balance -= required_margin

        position = Position(
            strategy_id=strategy_id,
            symbol=symbol,
            side="short",
            entry_price=price,
            quantity=quantity,
            user_id=user_id,
        )
        db.add(position)

        trigger = TriggerLog(
            strategy_id=strategy_id,
            symbol=symbol,
            signal_type="卖出",
            signal_detail=f"开空 {quantity} {symbol} @ {price}",
            action="卖出",
            price=price,
            quantity=quantity,
            position_effect="开仓",
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
        """执行模拟平空（始终全额平仓）

        Args:
            strategy_id: 策略 ID
            symbol: 交易对
            price: 平空价格
            db: 数据库会话
            user_id: 用户 ID（用于查找 SimAccount）

        Returns:
            TriggerLog（action="买入" 成功平空，action="观望" 无空仓跳过）
        """
        result = await db.execute(
            select(Position).where(
                Position.strategy_id == strategy_id,
                Position.symbol == symbol,
                Position.side == "short",
                Position.closed_at.is_(None),
            ).order_by(Position.id)
        )
        positions = list(result.scalars().all())

        if not positions:
            logger.warning(f"No open short position to cover for strategy {strategy_id}")
            return None

        if user_id is not None:
            account_result = await db.execute(
                select(SimAccount).where(SimAccount.user_id == user_id)
            )
        else:
            account_result = await db.execute(select(SimAccount).limit(1))
        account = account_result.scalar_one()

        # 平掉所有空头持仓
        total_quantity = 0.0
        total_pnl = 0.0
        for position in positions:
            quantity = position.quantity
            pnl = (position.entry_price - price) * quantity
            margin_returned = position.entry_price * quantity

            account.balance += margin_returned + pnl
            account.total_pnl += pnl

            position.pnl = pnl
            position.current_price = price
            position.closed_at = datetime.now(timezone.utc)

            total_quantity += quantity
            total_pnl += pnl

        trigger = TriggerLog(
            strategy_id=strategy_id,
            symbol=symbol,
            signal_type="买入",
            signal_detail=f"平空 {total_quantity:.4f} {symbol} @ {price}, 盈亏: {total_pnl:.2f} USDT",
            action="买入",
            price=price,
            quantity=total_quantity,
            simulated_pnl=total_pnl,
            position_effect="平仓",
        )
        db.add(trigger)
        await db.commit()
        await db.refresh(trigger)

        logger.info(f"模拟平空: {symbol} {total_quantity:.4f} @ {price}, PnL: {total_pnl:.2f}")
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
        # 检查所有多头持仓的止盈止损（任一持仓触发则全部平仓）
        result = await db.execute(
            select(Position).where(
                Position.strategy_id == strategy_id,
                Position.symbol == symbol,
                Position.side == "long",
                Position.closed_at.is_(None),
            ).order_by(Position.id)
        )
        long_positions = list(result.scalars().all())

        for position in long_positions:
            entry_price = position.entry_price
            price_change_pct = (current_price - entry_price) / entry_price * 100

            if stop_loss_pct and price_change_pct <= -stop_loss_pct:
                logger.info(f"Stop loss triggered: {price_change_pct:.2f}%")
                trigger = await self.execute_sell(strategy_id, symbol, current_price, db, user_id=user_id)
                trigger.signal_detail = f"[止损] {trigger.signal_detail}"
                await db.commit()
                return trigger

            if take_profit_pct and price_change_pct >= take_profit_pct:
                logger.info(f"Take profit triggered: {price_change_pct:.2f}%")
                trigger = await self.execute_sell(strategy_id, symbol, current_price, db, user_id=user_id)
                trigger.signal_detail = f"[止盈] {trigger.signal_detail}"
                await db.commit()
                return trigger

        # ── 空头止盈止损 ──────────────────────────────────────
        short_result = await db.execute(
            select(Position).where(
                Position.strategy_id == strategy_id,
                Position.symbol == symbol,
                Position.side == "short",
                Position.closed_at.is_(None),
            ).order_by(Position.id)
        )
        short_positions = list(short_result.scalars().all())

        for short_position in short_positions:
            entry_price = short_position.entry_price
            price_change_pct = (current_price - entry_price) / entry_price * 100

            if stop_loss_pct and price_change_pct >= stop_loss_pct:
                logger.info(f"Short stop loss triggered: +{price_change_pct:.2f}%")
                trigger = await self.execute_cover(strategy_id, symbol, current_price, db, user_id=user_id)
                trigger.signal_detail = f"[止损] {trigger.signal_detail}"
                await db.commit()
                return trigger

            if take_profit_pct and price_change_pct <= -take_profit_pct:
                logger.info(f"Short take profit triggered: {price_change_pct:.2f}%")
                trigger = await self.execute_cover(strategy_id, symbol, current_price, db, user_id=user_id)
                trigger.signal_detail = f"[止盈] {trigger.signal_detail}"
                await db.commit()
                return trigger

        return None


# 全局实例
simulator = Simulator()
