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
from app.deps import get_current_user
from app.models import Strategy, TriggerLog, User
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
    current_user: User = Depends(get_current_user),
):
    """获取当前用户的触发日志列表"""
    base_query = (
        select(TriggerLog)
        .join(Strategy, TriggerLog.strategy_id == Strategy.id)
        .where(Strategy.user_id == current_user.id)
    )

    if strategy_id:
        base_query = base_query.where(TriggerLog.strategy_id == strategy_id)
    if start_date:
        base_query = base_query.where(TriggerLog.triggered_at >= start_date)
    if end_date:
        base_query = base_query.where(TriggerLog.triggered_at <= end_date)

    count_result = await db.execute(
        select(func.count()).select_from(base_query.subquery())
    )
    total = count_result.scalar()

    paged_query = (
        base_query
        .order_by(TriggerLog.triggered_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(paged_query)
    items = result.scalars().all()

    response_items = []
    for item in items:
        strategy_result = await db.execute(
            select(Strategy.name).where(Strategy.id == item.strategy_id)
        )
        strategy_name = strategy_result.scalar()
        response_item = TriggerLogResponse.model_validate(item)
        response_item.strategy_name = strategy_name
        response_items.append(response_item)

    return TriggerLogList(
        items=response_items,
        total=total,
        page=page,
        page_size=page_size,
    )
