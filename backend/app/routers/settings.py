"""
系统设置 API
GET /api/settings       — 读取配置
PUT /api/settings       — 更新配置（立即生效）
POST /api/settings/test — 测试数据源连接
"""

from fastapi import APIRouter, Depends
from sqlalchemy import delete, select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_admin_user
from app.models import KlineData, SystemSetting, User
from app.schemas import (
    SettingsResponse,
    SettingsUpdate,
    TestConnectionRequest,
    TestConnectionResponse,
)

router = APIRouter(prefix="/settings", tags=["settings"])


async def _get_setting(key: str, default: str, db: AsyncSession) -> str:
    result = await db.execute(select(SystemSetting).where(SystemSetting.key == key))
    row = result.scalar_one_or_none()
    return row.value if row and row.value is not None else default


async def _upsert_setting(key: str, value: str, db: AsyncSession):
    stmt = insert(SystemSetting).values(key=key, value=value)
    stmt = stmt.on_conflict_do_update(index_elements=["key"], set_={"value": value})
    await db.execute(stmt)


@router.get("", response_model=SettingsResponse)
async def get_settings(db: AsyncSession = Depends(get_db)):
    data_source = await _get_setting("data_source", "binance", db)
    api_key = await _get_setting("cryptocompare_api_key", "", db)
    timezone = await _get_setting("timezone", "Asia/Shanghai", db)
    return SettingsResponse(data_source=data_source, cryptocompare_api_key=api_key, timezone=timezone)


@router.put("", response_model=SettingsResponse)
async def update_settings(
    payload: SettingsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_admin_user),  # admin only
):
    # 检查数据源是否变更
    current_source = await _get_setting("data_source", "binance", db)
    source_changed = current_source != payload.data_source

    await _upsert_setting("data_source", payload.data_source, db)

    api_key = payload.cryptocompare_api_key or ""
    await _upsert_setting("cryptocompare_api_key", api_key, db)

    timezone = payload.timezone or "Asia/Shanghai"
    await _upsert_setting("timezone", timezone, db)

    # 数据源切换时清空 KlineData 缓存，避免旧数据污染新数据源
    if source_changed:
        await db.execute(delete(KlineData))

    await db.commit()

    # 立即切换全局数据源（无需重启）
    from app.engine.market_data import market_data_service
    market_data_service.set_source(payload.data_source, api_key)

    return SettingsResponse(data_source=payload.data_source, cryptocompare_api_key=api_key, timezone=timezone)


@router.post("/test", response_model=TestConnectionResponse)
async def test_connection(payload: TestConnectionRequest):
    """测试数据源连接（保存前验证）"""
    if payload.data_source == "mock":
        return TestConnectionResponse(success=True, message="Mock 数据源无需连接")

    if payload.data_source == "binance":
        import httpx
        try:
            async with httpx.AsyncClient(timeout=8.0) as client:
                resp = await client.get(
                    "https://api.binance.com/api/v3/ping"
                )
                resp.raise_for_status()
            return TestConnectionResponse(success=True, message="Binance 连接成功")
        except Exception as e:
            return TestConnectionResponse(success=False, message=f"Binance 连接失败: {e}")

    if payload.data_source == "cryptocompare":
        from app.engine.data_sources.cryptocompare import CryptoCompareSource
        src = CryptoCompareSource(api_key=payload.api_key or "")
        ok = await src.test_connection()
        await src.close()
        if ok:
            return TestConnectionResponse(success=True, message="CryptoCompare 连接成功")
        else:
            return TestConnectionResponse(success=False, message="CryptoCompare 连接失败，请检查 API Key")

    return TestConnectionResponse(success=False, message="未知数据源")
