"""
仪表盘路由
"""

import os
from datetime import datetime, timezone

import zoneinfo

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database import get_db
from app.deps import get_current_user
from app.models import Position, SimAccount, Strategy, SystemSetting, TriggerLog, User
from app.schemas import DashboardData, TriggerLogResponse

router = APIRouter(tags=["仪表盘"])


@router.get("/dashboard", response_model=DashboardData)
async def get_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取当前用户的仪表盘数据"""

    # 获取账户信息
    account_result = await db.execute(
        select(SimAccount).where(SimAccount.user_id == current_user.id)
    )
    account = account_result.scalar_one_or_none()

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

    # 运行中策略数（当前用户）
    running_count_result = await db.execute(
        select(func.count()).where(
            Strategy.status == "running",
            Strategy.user_id == current_user.id,
        )
    )
    running_strategies = running_count_result.scalar()

    # 读取系统时区设置
    tz_result = await db.execute(
        select(SystemSetting.value).where(SystemSetting.key == "timezone")
    )
    tz_name = tz_result.scalar() or "Asia/Shanghai"
    try:
        tz = zoneinfo.ZoneInfo(tz_name)
    except Exception:
        tz = zoneinfo.ZoneInfo("Asia/Shanghai")

    # 今日触发次数（按用户时区计算"今日"）
    now_local = datetime.now(tz)
    today_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    today = today_local.astimezone(timezone.utc).replace(tzinfo=None)
    today_triggers_result = await db.execute(
        select(func.count())
        .select_from(TriggerLog)
        .join(Strategy, TriggerLog.strategy_id == Strategy.id)
        .where(
            TriggerLog.triggered_at >= today,
            Strategy.user_id == current_user.id,
        )
    )
    today_triggers = today_triggers_result.scalar()

    # 最近 10 条触发记录（当前用户的策略）
    recent_result = await db.execute(
        select(TriggerLog)
        .join(Strategy, TriggerLog.strategy_id == Strategy.id)
        .where(Strategy.user_id == current_user.id)
        .order_by(TriggerLog.triggered_at.desc())
        .limit(10)
    )
    recent_triggers = recent_result.scalars().all()

    # 构建响应
    recent_items = []
    for trigger in recent_triggers:
        strategy_result = await db.execute(
            select(Strategy.name).where(Strategy.id == trigger.strategy_id)
        )
        strategy_name = strategy_result.scalar()

        item = TriggerLogResponse.model_validate(trigger)
        item.strategy_name = strategy_name
        recent_items.append(item)

    # 未平仓持仓成本（算入余额）+ 多空策略数
    open_pos_result = await db.execute(
        select(Position.side, func.count(func.distinct(Position.strategy_id)))
        .join(Strategy, Position.strategy_id == Strategy.id)
        .where(Strategy.user_id == current_user.id, Position.closed_at.is_(None))
        .group_by(Position.side)
    )
    open_position_cost_result = await db.execute(
        select(func.coalesce(func.sum(Position.entry_price * Position.quantity), 0))
        .join(Strategy, Position.strategy_id == Strategy.id)
        .where(Strategy.user_id == current_user.id, Position.closed_at.is_(None))
    )
    open_position_cost = open_position_cost_result.scalar()

    side_counts = dict(open_pos_result.all())
    long_strategies = side_counts.get("long", 0)
    short_strategies = side_counts.get("short", 0)

    return DashboardData(
        balance=account.balance + open_position_cost,
        total_pnl=account.total_pnl,
        running_strategies=running_strategies,
        long_strategies=long_strategies,
        short_strategies=short_strategies,
        today_triggers=today_triggers,
        recent_triggers=recent_items,
    )
