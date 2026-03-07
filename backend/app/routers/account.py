"""
账户和持仓路由
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database import get_db
from app.logger import get_logger
from app.models import Position, SimAccount, Strategy, TriggerLog
from app.schemas import AccountResponse, MessageResponse, PositionList, PositionResponse

logger = get_logger(__name__)
router = APIRouter(tags=["账户"])


@router.get("/account", response_model=AccountResponse)
async def get_account(db: AsyncSession = Depends(get_db)):
    """获取模拟账户信息"""
    result = await db.execute(select(SimAccount).limit(1))
    account = result.scalar_one_or_none()

    if not account:
        # 创建默认账户
        account = SimAccount()
        db.add(account)
        await db.commit()
        await db.refresh(account)

    return AccountResponse.model_validate(account)


@router.post("/account/reset", response_model=MessageResponse)
async def reset_account(db: AsyncSession = Depends(get_db)):
    """重置模拟账户

    - 停止所有运行中策略
    - 清空持仓和触发记录
    - 恢复初始余额
    """
    # 停止所有运行中策略
    result = await db.execute(select(Strategy).where(Strategy.status == "running"))
    running_strategies = result.scalars().all()

    for strategy in running_strategies:
        # TODO: 第三阶段 - 调用调度器停止
        strategy.status = "stopped"
        logger.info(f"停止策略: {strategy.name} (ID: {strategy.id})")

    # 清空持仓
    await db.execute(Position.__table__.delete())

    # 清空触发记录
    await db.execute(TriggerLog.__table__.delete())

    # 重置账户
    result = await db.execute(select(SimAccount).limit(1))
    account = result.scalar_one_or_none()

    if account:
        account.balance = account.initial_balance
        account.total_pnl = 0

    await db.commit()

    logger.info("模拟账户已重置")
    return MessageResponse(message="模拟账户已重置")


@router.get("/positions", response_model=PositionList)
async def list_positions(
    strategy_id: Optional[int] = Query(None, description="筛选特定策略"),
    db: AsyncSession = Depends(get_db),
):
    """获取当前持仓列表"""
    query = select(Position).where(Position.closed_at.is_(None))

    if strategy_id:
        query = query.where(Position.strategy_id == strategy_id)

    query = query.order_by(Position.opened_at.desc())

    result = await db.execute(query)
    items = result.scalars().all()

    # 计算浮动盈亏（简化版，实际需要获取当前价格）
    response_items = []
    for item in items:
        response_item = PositionResponse.model_validate(item)
        if item.current_price:
            if item.side == "long":
                response_item.unrealized_pnl = (item.current_price - item.entry_price) * item.quantity
            else:
                response_item.unrealized_pnl = (item.entry_price - item.current_price) * item.quantity
        response_items.append(response_item)

    return PositionList(
        items=response_items,
        total=len(items),
    )
