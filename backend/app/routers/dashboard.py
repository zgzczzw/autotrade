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
from app.models import Position, SimAccount, Strategy, StrategySymbol, SystemSetting, TriggerLog, User
from app.schemas import DashboardData, StrategyRankingItem, TriggerLogResponse

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

    # 未平仓持仓 + 多空策略数
    open_pos_result = await db.execute(
        select(Position.side, func.count(func.distinct(Position.strategy_id)))
        .join(Strategy, Position.strategy_id == Strategy.id)
        .where(Strategy.user_id == current_user.id, Position.closed_at.is_(None))
        .group_by(Position.side)
    )

    # 查询所有未平仓持仓，计算成本和浮动盈亏
    open_positions_result = await db.execute(
        select(Position)
        .join(Strategy, Position.strategy_id == Strategy.id)
        .where(Strategy.user_id == current_user.id, Position.closed_at.is_(None))
    )
    open_positions = open_positions_result.scalars().all()

    open_position_cost = 0.0
    unrealized_pnl = 0.0
    for pos in open_positions:
        cost = pos.entry_price * pos.quantity
        open_position_cost += cost
        if pos.current_price:
            if pos.side == "long":
                unrealized_pnl += (pos.current_price - pos.entry_price) * pos.quantity
            else:
                unrealized_pnl += (pos.entry_price - pos.current_price) * pos.quantity

    side_counts = dict(open_pos_result.all())
    long_strategies = side_counts.get("long", 0)
    short_strategies = side_counts.get("short", 0)

    # 运行中策略的绩效排名
    rankings = await _build_strategy_rankings(db, current_user.id)

    return DashboardData(
        balance=account.balance + open_position_cost,
        total_pnl=account.total_pnl + unrealized_pnl,
        unrealized_pnl=unrealized_pnl,
        running_strategies=running_strategies,
        long_strategies=long_strategies,
        short_strategies=short_strategies,
        today_triggers=today_triggers,
        recent_triggers=recent_items,
        strategy_rankings=rankings,
    )


async def _build_strategy_rankings(
    db: AsyncSession, user_id: int
) -> list[StrategyRankingItem]:
    """聚合每个运行中策略的已实现/未实现盈亏、胜率与持仓信息，按总盈亏降序。"""

    strategies_result = await db.execute(
        select(Strategy).where(
            Strategy.user_id == user_id,
            Strategy.status == "running",
        )
    )
    strategies = strategies_result.scalars().all()
    if not strategies:
        return []

    strat_ids = [s.id for s in strategies]

    # 一次性拉取所有 symbol、trigger、open position
    symbols_rows = (
        await db.execute(
            select(StrategySymbol.strategy_id, StrategySymbol.symbol).where(
                StrategySymbol.strategy_id.in_(strat_ids)
            )
        )
    ).all()
    symbols_by_strat: dict[int, list[str]] = {}
    for sid, sym in symbols_rows:
        symbols_by_strat.setdefault(sid, []).append(sym)

    triggers_rows = (
        await db.execute(
            select(TriggerLog.strategy_id, TriggerLog.simulated_pnl).where(
                TriggerLog.strategy_id.in_(strat_ids)
            )
        )
    ).all()
    triggers_by_strat: dict[int, list[float]] = {}
    for sid, pnl in triggers_rows:
        triggers_by_strat.setdefault(sid, []).append(pnl or 0.0)

    open_positions_result = await db.execute(
        select(Position).where(
            Position.strategy_id.in_(strat_ids),
            Position.closed_at.is_(None),
        )
    )
    positions_by_strat: dict[int, list[Position]] = {}
    for pos in open_positions_result.scalars().all():
        positions_by_strat.setdefault(pos.strategy_id, []).append(pos)

    items: list[StrategyRankingItem] = []
    for s in strategies:
        symbols = symbols_by_strat.get(s.id) or ([s.symbol] if s.symbol else [])

        pnls = triggers_by_strat.get(s.id, [])
        realized = sum(pnls)
        wins = sum(1 for p in pnls if p > 0)
        losses = sum(1 for p in pnls if p < 0)
        closed = wins + losses
        win_rate = (wins / closed * 100.0) if closed else None

        positions = positions_by_strat.get(s.id, [])
        locked = sum(p.entry_price * p.quantity for p in positions)
        unreal = 0.0
        for p in positions:
            if p.current_price:
                if p.side == "long":
                    unreal += (p.current_price - p.entry_price) * p.quantity
                else:
                    unreal += (p.entry_price - p.current_price) * p.quantity

        items.append(
            StrategyRankingItem(
                id=s.id,
                name=s.name,
                symbols=symbols,
                timeframe=s.timeframe or "",
                realized_pnl=realized,
                unrealized_pnl=unreal,
                total_pnl=realized + unreal,
                closed_trades=closed,
                win_rate=win_rate,
                open_positions=len(positions),
                locked_capital=locked,
            )
        )

    items.sort(key=lambda x: x.total_pnl, reverse=True)
    return items
