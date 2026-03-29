"""
策略管理路由
"""

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database import get_db
from app.deps import get_current_user
from app.engine.scheduler import scheduler
from app.engine.sandbox import validate_code
from app.logger import get_logger
from app.models import Strategy, User
from app.schemas import (
    CodeValidationRequest,
    CodeValidationResponse,
    MessageResponse,
    StrategyCreate,
    StrategyList,
    StrategyResponse,
    StrategyUpdate,
)

logger = get_logger(__name__)
router = APIRouter(tags=["策略管理"])


@router.get("/strategies", response_model=StrategyList)
async def list_strategies(
    status: Optional[str] = Query(None, description="筛选状态: running/stopped/error"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取策略列表"""
    query = select(Strategy).where(Strategy.user_id == current_user.id)

    if status:
        query = query.where(Strategy.status == status)

    # 总数
    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar()

    # 分页
    query = query.offset((page - 1) * page_size).limit(page_size)
    query = query.order_by(Strategy.created_at.desc())

    result = await db.execute(query)
    items = result.scalars().all()

    # 批量查询每个策略的触发次数
    from app.models import TriggerLog
    strategy_ids = [s.id for s in items]
    if strategy_ids:
        tc_result = await db.execute(
            select(TriggerLog.strategy_id, func.count())
            .where(TriggerLog.strategy_id.in_(strategy_ids))
            .group_by(TriggerLog.strategy_id)
        )
        trigger_counts = dict(tc_result.all())
    else:
        trigger_counts = {}

    response_items = []
    for item in items:
        resp = StrategyResponse.model_validate(item)
        resp.trigger_count = trigger_counts.get(item.id, 0)
        response_items.append(resp)

    return StrategyList(
        items=response_items,
        total=total,
        page=page,
        page_size=page_size,
    )


@router.post("/strategies", response_model=StrategyResponse, status_code=status.HTTP_201_CREATED)
async def create_strategy(
    data: StrategyCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """创建新策略"""
    # 验证配置
    if data.type == "visual" and not data.config_json:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="可视化策略必须提供 config_json",
        )
    if data.type == "code" and not data.code:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="代码策略必须提供 code",
        )

    # 代码策略进行语法检查
    if data.type == "code" and data.code:
        is_valid, errors = validate_code(data.code)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"代码验证失败: {'; '.join(errors)}",
            )

    strategy = Strategy(**data.model_dump())
    strategy.user_id = current_user.id
    db.add(strategy)
    await db.commit()
    await db.refresh(strategy)

    logger.info(f"创建策略: {strategy.name} (ID: {strategy.id})")
    return StrategyResponse.model_validate(strategy)


@router.get("/strategies/{strategy_id}", response_model=StrategyResponse)
async def get_strategy(
    strategy_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取策略详情"""
    result = await db.execute(select(Strategy).where(Strategy.id == strategy_id))
    strategy = result.scalar_one_or_none()

    if not strategy or strategy.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="策略不存在",
        )

    # 加载关联统计
    from app.models import TriggerLog, Position

    trigger_count_result = await db.execute(
        select(func.count()).where(TriggerLog.strategy_id == strategy_id)
    )
    position_count_result = await db.execute(
        select(func.count()).where(
            Position.strategy_id == strategy_id,
            Position.closed_at.is_(None)
        )
    )

    response = StrategyResponse.model_validate(strategy)
    response.trigger_count = trigger_count_result.scalar()
    response.position_count = position_count_result.scalar()

    return response


@router.put("/strategies/{strategy_id}", response_model=StrategyResponse)
async def update_strategy(
    strategy_id: int,
    data: StrategyUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新策略（仅 stopped 状态可编辑）"""
    result = await db.execute(select(Strategy).where(Strategy.id == strategy_id))
    strategy = result.scalar_one_or_none()

    if not strategy or strategy.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="策略不存在",
        )

    if strategy.status != "stopped":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="仅 stopped 状态的策略可编辑",
        )

    # 如果更新代码，进行语法检查
    if data.code:
        is_valid, errors = validate_code(data.code)
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"代码验证失败: {'; '.join(errors)}",
            )

    # 更新字段
    update_data = data.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(strategy, key, value)

    await db.commit()
    await db.refresh(strategy)

    logger.info(f"更新策略: {strategy.name} (ID: {strategy.id})")
    return StrategyResponse.model_validate(strategy)


@router.delete("/strategies/{strategy_id}", response_model=MessageResponse)
async def delete_strategy(
    strategy_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除策略（同时清理关联数据）"""
    result = await db.execute(select(Strategy).where(Strategy.id == strategy_id))
    strategy = result.scalar_one_or_none()

    if not strategy or strategy.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="策略不存在",
        )

    # 先停止策略
    if strategy.status == "running":
        scheduler.stop_strategy(strategy_id)

    await db.delete(strategy)
    await db.commit()

    logger.info(f"删除策略: {strategy.name} (ID: {strategy_id})")
    return MessageResponse(message="策略已删除")


@router.post("/strategies/{strategy_id}/start", response_model=MessageResponse)
async def start_strategy(
    strategy_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """启动策略"""
    result = await db.execute(select(Strategy).where(Strategy.id == strategy_id))
    strategy = result.scalar_one_or_none()

    if not strategy or strategy.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="策略不存在",
        )

    if strategy.status == "running":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="策略已在运行中",
        )

    # 更新状态
    strategy.status = "running"
    await db.commit()

    # 启动调度
    success = await scheduler.start_strategy(strategy_id)
    if not success:
        strategy.status = "error"
        await db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="启动策略失败",
        )

    logger.info(f"启动策略: {strategy.name} (ID: {strategy_id})")
    return MessageResponse(message="策略已启动")


@router.post("/strategies/{strategy_id}/stop", response_model=MessageResponse)
async def stop_strategy(
    strategy_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """停止策略"""
    result = await db.execute(select(Strategy).where(Strategy.id == strategy_id))
    strategy = result.scalar_one_or_none()

    if not strategy or strategy.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="策略不存在",
        )

    if strategy.status != "running":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="策略未在运行",
        )

    # 停止调度
    scheduler.stop_strategy(strategy_id)

    # 更新状态
    strategy.status = "stopped"
    await db.commit()

    logger.info(f"停止策略: {strategy.name} (ID: {strategy_id})")
    return MessageResponse(message="策略已停止")


@router.post("/strategies/validate-code", response_model=CodeValidationResponse)
async def validate_code_endpoint(
    data: CodeValidationRequest,
):
    """
    验证代码策略

    检查语法错误和安全问题
    """
    is_valid, errors = validate_code(data.code)

    return CodeValidationResponse(
        valid=is_valid,
        errors=errors,
    )
