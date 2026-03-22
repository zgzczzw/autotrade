"""
FastAPI 依赖注入
"""

import itsdangerous
from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import User


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    从 Cookie 中读取 session，验证签名，返回当前用户。
    失败时抛出 401。
    """
    session_cookie = request.cookies.get("session")
    if not session_cookie:
        raise HTTPException(status_code=401, detail="未登录")

    serializer = request.app.state.serializer
    try:
        user_id = serializer.loads(session_cookie, max_age=604800)
    except itsdangerous.BadData:
        raise HTTPException(status_code=401, detail="Session 无效或已过期")

    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")

    return user


async def get_admin_user(
    current_user: User = Depends(get_current_user),
) -> User:
    """
    要求当前用户为管理员，否则抛出 403。
    """
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return current_user
