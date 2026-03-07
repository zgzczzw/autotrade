"""
触发日志路由
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database import get_db
from app.models import Strategy, TriggerLog
from app.schemas import TriggerLogList, TriggerLogResponse

router = APIRouter(tags=["触发日志"])


@router.get("/triggers", response_model=TriggerLogList)
async def list_triggers(
    strategy_id: Optional[int] = Query(None, description="筛选特定策略"),
    start_date: Optional[datetime] = Query(None, description="开始时间"),
    end_date: Optional[datetime] = Query(None, description="结束时间"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
):
    """获取触发日志列表"""
    query = select(TriggerLog)

    if strategy_id:
        query = query.where(TriggerLog.strategy_id == strategy_id)

    if start_date:
        query = query.where(TriggerLog.triggered_at >= start_date)

    if end_date:
        query = query.where(TriggerLog.triggered_at <= end_date)

    # 总数
    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar()

    # 分页
    query = query.offset((page - 1) * page_size).limit(page_size)
    query = query.order_by(TriggerLog.triggered_at.desc())

    result = await db.execute(query)
    items = result.scalars().all()

    # 加载策略名称
    response_items = []
    for trigger in items:
        strategy_result = await db.execute(
            select(Strategy.name).where(Strategy.id == trigger.strategy_id)
        )
        strategy_name = strategy_result.scalar()

        item = TriggerLogResponse.model_validate(trigger)
        item.strategy_name = strategy_name
        response_items.append(item)

    return TriggerLogList(
        items=response_items,
        total=total,
        page=page,
        page_size=page_size,
    )
