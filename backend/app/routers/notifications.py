"""
通知设置路由
GET  /api/notifications/settings  — 读取当前用户通知设置
PUT  /api/notifications/settings  — 更新当前用户通知设置
POST /api/notifications/test      — 发送测试 Bark 推送
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database import get_db
from app.deps import get_current_user
from app.models import User, UserSetting
from app.schemas import MessageResponse, NotificationSettingsResponse, NotificationSettingsUpdate
from app.services.bark import bark_client

router = APIRouter(prefix="/notifications", tags=["通知"])


async def _get_setting(db: AsyncSession, user_id: int, key: str) -> str | None:
    """读取单个用户设置"""
    result = await db.execute(
        select(UserSetting).where(
            UserSetting.user_id == user_id,
            UserSetting.key == key,
        )
    )
    row = result.scalar_one_or_none()
    return row.value if row else None


async def _upsert_setting(db: AsyncSession, user_id: int, key: str, value: str):
    """Upsert 单个用户设置（SQLite dialect）"""
    stmt = insert(UserSetting).values(
        user_id=user_id,
        key=key,
        value=value,
        updated_at=datetime.utcnow(),
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["user_id", "key"],
        set_={"value": value, "updated_at": datetime.utcnow()},
    )
    await db.execute(stmt)


@router.get("/settings", response_model=NotificationSettingsResponse)
async def get_notification_settings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取当前用户的通知设置"""
    bark_key = await _get_setting(db, current_user.id, "bark_key")
    bark_enabled_str = await _get_setting(db, current_user.id, "bark_enabled")
    bark_enabled = (bark_enabled_str or "false").lower() == "true"
    return NotificationSettingsResponse(bark_key=bark_key, bark_enabled=bark_enabled)


@router.put("/settings", response_model=NotificationSettingsResponse)
async def update_notification_settings(
    payload: NotificationSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新当前用户的通知设置"""
    if payload.bark_key is not None:
        await _upsert_setting(db, current_user.id, "bark_key", payload.bark_key)
    if payload.bark_enabled is not None:
        await _upsert_setting(
            db, current_user.id, "bark_enabled", "true" if payload.bark_enabled else "false"
        )
    await db.commit()

    # 返回最新状态
    bark_key = await _get_setting(db, current_user.id, "bark_key")
    bark_enabled_str = await _get_setting(db, current_user.id, "bark_enabled")
    bark_enabled = (bark_enabled_str or "false").lower() == "true"
    return NotificationSettingsResponse(bark_key=bark_key, bark_enabled=bark_enabled)


@router.post("/test", response_model=MessageResponse)
async def test_notification(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """发送测试 Bark 推送"""
    bark_key = await _get_setting(db, current_user.id, "bark_key")
    if not bark_key:
        raise HTTPException(status_code=400, detail="Bark Key 未配置，请先保存设置")

    success, error_msg = await bark_client.send(
        key=bark_key,
        title="AutoTrade 测试通知",
        body="配置成功！推送正常工作。",
    )
    if not success:
        raise HTTPException(status_code=400, detail=f"推送失败: {error_msg}")

    return MessageResponse(message="测试通知已发送")
