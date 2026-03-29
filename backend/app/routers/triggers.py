"""
触发日志路由
"""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database import get_db
from app.deps import get_current_user
from app.models import Strategy, TriggerLog, User
from app.schemas import MessageResponse, TriggerDeleteRequest, TriggerLogList, TriggerLogResponse

router = APIRouter(tags=["触发日志"])


@router.get("/triggers", response_model=TriggerLogList)
async def list_triggers(
    strategy_id: Optional[int] = Query(None, description="筛选特定策略"),
    start_date: Optional[datetime] = Query(None, description="开始时间"),
    end_date: Optional[datetime] = Query(None, description="结束时间"),
    symbol: Optional[str] = Query(None, description="筛选交易对"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=500),
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
    if symbol:
        base_query = base_query.where(TriggerLog.symbol == symbol)

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


@router.delete("/triggers/{trigger_id}", response_model=MessageResponse)
async def delete_trigger(
    trigger_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除单条触发日志"""
    result = await db.execute(
        select(TriggerLog)
        .join(Strategy, TriggerLog.strategy_id == Strategy.id)
        .where(TriggerLog.id == trigger_id, Strategy.user_id == current_user.id)
    )
    trigger = result.scalar_one_or_none()

    if not trigger:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="触发记录不存在",
        )

    await db.delete(trigger)
    await db.commit()
    return MessageResponse(message="触发记录已删除")


@router.post("/triggers/batch-delete", response_model=dict)
async def batch_delete_triggers(
    request: TriggerDeleteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """批量删除触发日志"""
    result = await db.execute(
        select(TriggerLog)
        .join(Strategy, TriggerLog.strategy_id == Strategy.id)
        .where(TriggerLog.id.in_(request.ids), Strategy.user_id == current_user.id)
    )
    triggers = result.scalars().all()

    for trigger in triggers:
        await db.delete(trigger)
    await db.commit()

    return {"deleted": len(triggers)}
