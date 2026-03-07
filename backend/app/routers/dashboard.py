"""
仪表盘路由
"""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database import get_db
from app.models import SimAccount, Strategy, TriggerLog
from app.schemas import DashboardData, TriggerLogResponse

router = APIRouter(tags=["仪表盘"])


@router.get("/dashboard", response_model=DashboardData)
async def get_dashboard(db: AsyncSession = Depends(get_db)):
    """获取仪表盘数据"""

    # 获取账户信息
    account_result = await db.execute(select(SimAccount).limit(1))
    account = account_result.scalar_one_or_none()

    if not account:
        # 创建默认账户
        account = SimAccount()
        db.add(account)
        await db.commit()
        await db.refresh(account)

    # 运行中策略数
    running_count_result = await db.execute(
        select(func.count()).where(Strategy.status == "running")
    )
    running_strategies = running_count_result.scalar()

    # 今日触发次数
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_triggers_result = await db.execute(
        select(func.count()).where(TriggerLog.triggered_at >= today)
    )
    today_triggers = today_triggers_result.scalar()

    # 最近 10 条触发记录
    recent_result = await db.execute(
        select(TriggerLog)
        .order_by(TriggerLog.triggered_at.desc())
        .limit(10)
    )
    recent_triggers = recent_result.scalars().all()

    # 构建响应
    recent_items = []
    for trigger in recent_triggers:
        # 获取策略名称
        strategy_result = await db.execute(
            select(Strategy.name).where(Strategy.id == trigger.strategy_id)
        )
        strategy_name = strategy_result.scalar()

        item = TriggerLogResponse.model_validate(trigger)
        item.strategy_name = strategy_name
        recent_items.append(item)

    return DashboardData(
        balance=account.balance,
        total_pnl=account.total_pnl,
        running_strategies=running_strategies,
        today_triggers=today_triggers,
        recent_triggers=recent_items,
    )
