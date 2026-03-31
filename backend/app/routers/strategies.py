"""
策略管理路由
"""

import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, status
from fastapi.responses import JSONResponse
from sqlalchemy import delete, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.deps import get_current_user
from app.engine.scheduler import scheduler
from app.engine.sandbox import validate_code
from app.logger import get_logger
from app.models import Strategy, StrategySymbol, User
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


def _strategy_to_response(strategy: Strategy, **extra) -> StrategyResponse:
    """Convert Strategy ORM + symbols relationship to StrategyResponse."""
    data = {c.name: getattr(strategy, c.name) for c in strategy.__table__.columns}
    data["symbols"] = [s.symbol for s in strategy.symbols]
    data.update(extra)
    return StrategyResponse.model_validate(data)


@router.get("/strategies", response_model=StrategyList)
async def list_strategies(
    status: Optional[str] = Query(None, description="筛选状态: running/stopped/error"),
    symbol: Optional[str] = Query(None, description="筛选交易对"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取策略列表"""
    query = select(Strategy).where(Strategy.user_id == current_user.id)

    if status:
        query = query.where(Strategy.status == status)

    if symbol:
        query = query.join(StrategySymbol).where(StrategySymbol.symbol == symbol)

    # 总数
    count_result = await db.execute(select(func.count()).select_from(query.subquery()))
    total = count_result.scalar()

    # 分页
    query = query.options(selectinload(Strategy.symbols))
    query = query.offset((page - 1) * page_size).limit(page_size)
    query = query.order_by(Strategy.created_at.desc())

    result = await db.execute(query)
    items = result.scalars().unique().all()

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
        resp = _strategy_to_response(item, trigger_count=trigger_counts.get(item.id, 0))
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

    strategy_data = data.model_dump()
    symbols = strategy_data.pop("symbols", [])
    strategy_data["symbol"] = symbols[0] if symbols else "BTCUSDT"

    strategy = Strategy(**strategy_data)
    strategy.user_id = current_user.id
    db.add(strategy)
    await db.flush()

    for sym in symbols:
        db.add(StrategySymbol(strategy_id=strategy.id, symbol=sym))

    await db.commit()

    # Reload with symbols relationship
    result = await db.execute(
        select(Strategy)
        .where(Strategy.id == strategy.id)
        .options(selectinload(Strategy.symbols))
    )
    strategy = result.scalar_one()

    logger.info(f"创建策略: {strategy.name} (ID: {strategy.id})")
    return _strategy_to_response(strategy)


# ==================== 备份 & 恢复 ====================

EXPORT_FIELDS = [
    "name", "type", "config_json", "code", "timeframe",
    "position_size", "position_size_type", "stop_loss", "take_profit",
    "sell_size_pct", "notify_enabled",
]


@router.get("/strategies/export")
async def export_strategies(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """导出当前用户的所有策略为 JSON"""
    result = await db.execute(
        select(Strategy)
        .where(Strategy.user_id == current_user.id)
        .options(selectinload(Strategy.symbols))
        .order_by(Strategy.created_at)
    )
    strategies = result.scalars().all()

    data = {
        "version": 1,
        "count": len(strategies),
        "strategies": [
            {
                **{field: getattr(s, field) for field in EXPORT_FIELDS},
                "symbols": [sym.symbol for sym in s.symbols],
            }
            for s in strategies
        ],
    }

    return JSONResponse(
        content=data,
        headers={
            "Content-Disposition": "attachment; filename=autotrade-strategies.json",
        },
    )


@router.post("/strategies/import", response_model=MessageResponse)
async def import_strategies(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """从 JSON 文件导入策略（跳过同名策略）"""
    try:
        content = await file.read()
        data = json.loads(content)
    except (json.JSONDecodeError, UnicodeDecodeError):
        raise HTTPException(status_code=400, detail="无效的 JSON 文件")

    items = data.get("strategies", [])
    if not items:
        raise HTTPException(status_code=400, detail="文件中没有策略数据")

    # 查询已有策略名，避免重复
    existing = await db.execute(
        select(Strategy.name).where(Strategy.user_id == current_user.id)
    )
    existing_names = {row[0] for row in existing.all()}

    imported = 0
    skipped = 0
    for item in items:
        name = item.get("name", "").strip()
        if not name:
            continue
        if name in existing_names:
            skipped += 1
            continue

        syms = item.get("symbols") or [item.get("symbol", "BTCUSDT")]
        strategy = Strategy(
            user_id=current_user.id,
            status="stopped",
            symbol=syms[0],
            **{k: item[k] for k in EXPORT_FIELDS if k in item},
        )
        db.add(strategy)
        await db.flush()

        for sym in syms:
            db.add(StrategySymbol(strategy_id=strategy.id, symbol=sym))

        existing_names.add(name)
        imported += 1

    await db.commit()
    msg = f"导入完成：{imported} 个策略"
    if skipped:
        msg += f"，跳过 {skipped} 个同名策略"
    logger.info(f"{msg} (user_id={current_user.id})")
    return MessageResponse(message=msg)


@router.get("/strategies/{strategy_id}", response_model=StrategyResponse)
async def get_strategy(
    strategy_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取策略详情"""
    result = await db.execute(
        select(Strategy)
        .where(Strategy.id == strategy_id)
        .options(selectinload(Strategy.symbols))
    )
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

    return _strategy_to_response(
        strategy,
        trigger_count=trigger_count_result.scalar(),
        position_count=position_count_result.scalar(),
    )


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
    new_symbols = update_data.pop("symbols", None)

    for key, value in update_data.items():
        setattr(strategy, key, value)

    if new_symbols is not None:
        # Delete existing StrategySymbol rows
        await db.execute(
            delete(StrategySymbol).where(StrategySymbol.strategy_id == strategy_id)
        )
        # Insert new ones
        for sym in new_symbols:
            db.add(StrategySymbol(strategy_id=strategy_id, symbol=sym))
        # Update legacy field
        if new_symbols:
            strategy.symbol = new_symbols[0]

    await db.commit()

    # Reload with symbols relationship
    result = await db.execute(
        select(Strategy)
        .where(Strategy.id == strategy.id)
        .options(selectinload(Strategy.symbols))
    )
    strategy = result.scalar_one()

    logger.info(f"更新策略: {strategy.name} (ID: {strategy.id})")
    return _strategy_to_response(strategy)


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
