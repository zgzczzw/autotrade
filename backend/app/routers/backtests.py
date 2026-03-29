"""
回测路由
"""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database import get_db
from app.deps import get_current_user
from app.engine.backtester import backtest_engine, get_backtest_engine
from app.logger import get_logger
from app.models import BacktestResult, Strategy, User
from app.schemas import BacktestCreate, BacktestList, BacktestResponse, MessageResponse

logger = get_logger(__name__)
router = APIRouter(tags=["回测"])


def convert_to_naive(dt: datetime) -> datetime:
    """将带时区的datetime转换为naive datetime"""
    if dt.tzinfo is not None:
        return dt.replace(tzinfo=None)
    return dt


@router.post("/strategies/{strategy_id}/backtest", response_model=BacktestResponse)
async def create_backtest(
    strategy_id: int,
    data: BacktestCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    发起策略回测

    - symbol 和 timeframe 使用策略自身配置
    - 会拉取历史 K 线数据并执行回测
    - 回测使用独立虚拟账户，不影响模拟盘
    """
    # 获取策略
    result = await db.execute(select(Strategy).where(Strategy.id == strategy_id))
    strategy = result.scalar_one_or_none()

    if not strategy:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="策略不存在",
        )

    if strategy.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="策略不存在",
        )

    # 转换日期为naive datetime（去掉时区信息）
    start_date = convert_to_naive(data.start_date)
    end_date = convert_to_naive(data.end_date)

    # 验证时间范围
    if start_date >= end_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="结束时间必须晚于开始时间",
        )

    if end_date > datetime.utcnow():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="结束时间不能是将来",
        )

    # 运行回测
    try:
        backtest_result = await backtest_engine.run_backtest(
            strategy=strategy,
            symbol=strategy.symbol,
            start_date=start_date,
            end_date=end_date,
            initial_balance=data.initial_balance,
        )

        # 保存结果
        backtest_result.user_id = current_user.id
        db.add(backtest_result)
        await db.commit()
        await db.refresh(backtest_result)

        logger.info(
            f"Backtest created for strategy {strategy_id}: "
            f"PnL={backtest_result.total_pnl:.2f}"
        )

        return BacktestResponse.model_validate(backtest_result)

    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )
    except Exception as e:
        logger.error(f"Backtest failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"回测执行失败: {str(e)}",
        )


@router.get("/backtests/{backtest_id}", response_model=BacktestResponse)
async def get_backtest(
    backtest_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取回测结果详情"""
    result = await db.execute(
        select(BacktestResult).where(BacktestResult.id == backtest_id)
    )
    backtest = result.scalar_one_or_none()

    if not backtest or backtest.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="回测结果不存在",
        )

    return BacktestResponse.model_validate(backtest)


@router.get("/strategies/{strategy_id}/backtests", response_model=BacktestList)
async def list_strategy_backtests(
    strategy_id: int,
    page: int = 1,
    page_size: int = 20,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取某策略的所有回测记录"""
    # 检查策略是否存在并验证归属
    strategy_result = await db.execute(
        select(Strategy).where(Strategy.id == strategy_id)
    )
    strategy = strategy_result.scalar_one_or_none()
    if not strategy or strategy.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="策略不存在",
        )

    # 查询回测记录
    query = select(BacktestResult).where(
        BacktestResult.strategy_id == strategy_id,
        BacktestResult.user_id == current_user.id,
    )

    # 总数
    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar()

    # 分页
    query = query.offset((page - 1) * page_size).limit(page_size)
    query = query.order_by(BacktestResult.created_at.desc())

    result = await db.execute(query)
    items = result.scalars().all()

    return BacktestList(
        items=[BacktestResponse.model_validate(item) for item in items],
        total=total,
        page=page,
        page_size=page_size,
    )


@router.delete("/backtests/{backtest_id}", response_model=MessageResponse)
async def delete_backtest(
    backtest_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除回测结果"""
    result = await db.execute(
        select(BacktestResult).where(BacktestResult.id == backtest_id)
    )
    backtest = result.scalar_one_or_none()

    if not backtest or backtest.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="回测结果不存在",
        )

    await db.delete(backtest)
    await db.commit()

    logger.info(f"Backtest {backtest_id} deleted")
    return MessageResponse(message="回测结果已删除")


@router.post("/strategies/{strategy_id}/backtest/cancel", response_model=MessageResponse)
async def cancel_backtest(
    strategy_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    取消正在运行的回测

    - 如果该策略有回测正在运行，将发送取消信号
    - 回测将在下一次检查点时停止
    """
    # 检查策略是否存在
    result = await db.execute(select(Strategy).where(Strategy.id == strategy_id))
    strategy = result.scalar_one_or_none()

    if not strategy or strategy.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="策略不存在",
        )

    # 尝试取消回测
    engine = get_backtest_engine()
    cancelled = engine.cancel_backtest(strategy_id)

    if not cancelled:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="该策略没有正在运行的回测",
        )

    logger.info(f"Backtest cancellation requested for strategy {strategy_id}")
    return MessageResponse(message="回测取消请求已发送")


@router.get("/strategies/{strategy_id}/backtest/status")
async def get_backtest_status(
    strategy_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    获取策略的回测状态

    Returns:
        - running: 是否正在运行回测
    """
    # 检查策略是否存在
    result = await db.execute(select(Strategy).where(Strategy.id == strategy_id))
    strategy = result.scalar_one_or_none()

    if not strategy or strategy.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="策略不存在",
        )

    engine = get_backtest_engine()
    return {"running": engine.is_running(strategy_id)}
