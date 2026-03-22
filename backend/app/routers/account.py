"""
账户和持仓路由
"""

import os
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database import get_db
from app.deps import get_current_user
from app.engine.scheduler import scheduler
from app.logger import get_logger
from app.models import Position, SimAccount, User
from app.schemas import AccountResponse, MessageResponse, PositionList, PositionResponse

logger = get_logger(__name__)
router = APIRouter(tags=["账户"])


@router.get("/account", response_model=AccountResponse)
async def get_account(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取当前用户的模拟账户信息"""
    result = await db.execute(
        select(SimAccount).where(SimAccount.user_id == current_user.id)
    )
    account = result.scalar_one_or_none()

    if not account:
        initial_balance = float(os.getenv("SIMULATED_INITIAL_BALANCE", "100000"))
        account = SimAccount(
            user_id=current_user.id,
            initial_balance=initial_balance,
            balance=initial_balance,
            total_pnl=0.0,
        )
        db.add(account)
        await db.commit()
        await db.refresh(account)

    return AccountResponse.model_validate(account)


@router.post("/account/reset", response_model=MessageResponse)
async def reset_account(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """重置当前用户的模拟账户"""
    # 1. Stop all running strategies for this user (flushes scheduler memory)
    await scheduler.stop_user_strategies(current_user.id)

    # 2. Delete notification_logs for this user's trigger_logs
    await db.execute(text(
        """
        DELETE FROM notification_logs WHERE trigger_log_id IN (
            SELECT tl.id FROM trigger_logs tl
            JOIN strategies s ON tl.strategy_id = s.id
            WHERE s.user_id = :uid
        )
        """
    ), {"uid": current_user.id})

    # 3. Delete trigger_logs for this user's strategies
    await db.execute(text(
        """
        DELETE FROM trigger_logs WHERE strategy_id IN (
            SELECT id FROM strategies WHERE user_id = :uid
        )
        """
    ), {"uid": current_user.id})

    # 4. Delete positions for this user
    await db.execute(text(
        "DELETE FROM positions WHERE user_id = :uid"
    ), {"uid": current_user.id})

    # 5. Reset sim_account balance
    result = await db.execute(
        select(SimAccount).where(SimAccount.user_id == current_user.id)
    )
    account = result.scalar_one_or_none()
    if account:
        account.balance = account.initial_balance
        account.total_pnl = 0.0

    await db.commit()
    logger.info(f"模拟账户已重置 (user_id={current_user.id})")
    return MessageResponse(message="模拟账户已重置")


@router.get("/positions", response_model=PositionList)
async def list_positions(
    strategy_id: Optional[int] = Query(None, description="筛选特定策略"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取当前用户的持仓列表"""
    query = select(Position).where(
        Position.user_id == current_user.id,
        Position.closed_at.is_(None),
    )

    if strategy_id:
        query = query.where(Position.strategy_id == strategy_id)

    query = query.order_by(Position.opened_at.desc())

    result = await db.execute(query)
    items = result.scalars().all()

    response_items = []
    for item in items:
        response_item = PositionResponse.model_validate(item)
        if item.current_price:
            if item.side == "long":
                response_item.unrealized_pnl = (item.current_price - item.entry_price) * item.quantity
            else:
                response_item.unrealized_pnl = (item.entry_price - item.current_price) * item.quantity
        response_items.append(response_item)

    return PositionList(items=response_items, total=len(items))
