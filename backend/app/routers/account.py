"""
账户和持仓路由
"""

import os
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database import get_db
from app.deps import get_current_user
from app.engine.scheduler import scheduler
from app.logger import get_logger
from app.models import Position, SimAccount, Strategy, User
from app.schemas import AccountResponse, MessageResponse, PositionHistoryList, PositionList, PositionResponse

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
    """重置当前用户的模拟账户（余额、持仓、日志、策略状态）"""
    uid = current_user.id

    # 1. 停止所有运行中的策略
    await scheduler.stop_user_strategies(uid)

    # 2. 将所有策略状态改为 stopped
    await db.execute(
        text("UPDATE strategies SET status = 'stopped' WHERE user_id = :uid AND status = 'running'"),
        {"uid": uid},
    )

    # 3. 删除通知日志
    await db.execute(text(
        """
        DELETE FROM notification_logs WHERE trigger_log_id IN (
            SELECT tl.id FROM trigger_logs tl
            JOIN strategies s ON tl.strategy_id = s.id
            WHERE s.user_id = :uid
        )
        """
    ), {"uid": uid})

    # 4. 删除触发日志
    await db.execute(text(
        "DELETE FROM trigger_logs WHERE strategy_id IN (SELECT id FROM strategies WHERE user_id = :uid)"
    ), {"uid": uid})

    # 5. 删除所有持仓（含未平仓和已平仓）
    await db.execute(text("DELETE FROM positions WHERE user_id = :uid"), {"uid": uid})

    # 6. 重置余额和盈亏
    result = await db.execute(
        select(SimAccount).where(SimAccount.user_id == uid)
    )
    account = result.scalar_one_or_none()
    if account:
        account.balance = account.initial_balance
        account.total_pnl = 0.0

    await db.commit()
    logger.info(f"模拟账户已完全重置 (user_id={uid})")
    return MessageResponse(message="账户已重置")


@router.get("/positions/history", response_model=PositionHistoryList)
async def list_position_history(
    strategy_id: Optional[int] = Query(None, description="筛选特定策略"),
    page: int = Query(1, ge=1, description="页码（从 1 开始）"),
    page_size: int = Query(20, ge=1, le=100, description="每页条数"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取当前用户的历史平仓记录（已平仓持仓，分页）"""
    base_query = select(Position).where(
        Position.user_id == current_user.id,
        Position.closed_at.isnot(None),
    )

    if strategy_id:
        base_query = base_query.where(Position.strategy_id == strategy_id)

    # 总数
    count_result = await db.execute(
        select(func.count()).select_from(base_query.subquery())
    )
    total = count_result.scalar_one()

    # 分页查询
    query = base_query.order_by(Position.closed_at.desc())
    query = query.offset((page - 1) * page_size).limit(page_size)

    result = await db.execute(query)
    items = result.scalars().all()

    return PositionHistoryList(
        items=[PositionResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


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
