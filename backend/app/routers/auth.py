"""
认证路由
POST /api/auth/register  — 注册
POST /api/auth/login     — 登录
POST /api/auth/logout    — 退出
GET  /api/auth/me        — 当前用户（未登录返回 {"user": null}）
"""

import os

import bcrypt as _bcrypt

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user
from app.models import SimAccount, User
from app.schemas import AuthRequest, AuthResponse, MeResponse, UserResponse

router = APIRouter(prefix="/auth", tags=["认证"])


def _hash_password(password: str) -> str:
    """Hash password using bcrypt directly (passlib incompatible with bcrypt 5.x)."""
    return _bcrypt.hashpw(password.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")


def _verify_password(password: str, password_hash: str) -> bool:
    """Verify password against bcrypt hash."""
    try:
        return _bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except Exception:
        return False

COOKIE_NAME = "session"
COOKIE_MAX_AGE = 604800  # 7 days


def _set_session_cookie(response: Response, request: Request, user_id: int):
    """在响应中设置签名 Cookie"""
    serializer = request.app.state.serializer
    cookie_secure = request.app.state.cookie_secure
    token = serializer.dumps(user_id)
    response.set_cookie(
        key=COOKIE_NAME,
        value=token,
        max_age=COOKIE_MAX_AGE,
        httponly=True,
        samesite="lax",
        secure=cookie_secure,
    )


@router.post("/register", response_model=AuthResponse)
async def register(
    payload: AuthRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """注册新用户，自动登录并创建 SimAccount"""
    result = await db.execute(select(User).where(User.username == payload.username))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="用户名已存在")

    user = User(
        username=payload.username,
        password_hash=_hash_password(payload.password),
        is_admin=False,
    )
    db.add(user)
    await db.flush()  # get user.id

    initial_balance = float(os.getenv("SIMULATED_INITIAL_BALANCE", "100000"))
    db.add(SimAccount(
        user_id=user.id,
        initial_balance=initial_balance,
        balance=initial_balance,
        total_pnl=0.0,
    ))
    await db.commit()
    await db.refresh(user)

    _set_session_cookie(response, request, user.id)
    return AuthResponse(user=UserResponse.model_validate(user))


@router.post("/login", response_model=AuthResponse)
async def login(
    payload: AuthRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    """登录"""
    result = await db.execute(select(User).where(User.username == payload.username))
    user = result.scalar_one_or_none()

    if not user or not _verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="用户名或密码错误")

    _set_session_cookie(response, request, user.id)
    return AuthResponse(user=UserResponse.model_validate(user))


@router.post("/logout")
async def logout(response: Response):
    """退出登录，清除 Cookie"""
    response.delete_cookie(key=COOKIE_NAME)
    return {"message": "已退出登录"}


@router.get("/me", response_model=MeResponse)
async def me(request: Request, db: AsyncSession = Depends(get_db)):
    """
    返回当前用户信息。
    未登录时返回 {"user": null}，不返回 401（避免前端拦截器触发重定向循环）。
    """
    session_cookie = request.cookies.get(COOKIE_NAME)
    if not session_cookie:
        return MeResponse(user=None)

    try:
        user_id = request.app.state.serializer.loads(session_cookie, max_age=604800)
    except Exception:
        return MeResponse(user=None)

    user = await db.get(User, user_id)
    if not user:
        return MeResponse(user=None)

    return MeResponse(user=UserResponse.model_validate(user))
