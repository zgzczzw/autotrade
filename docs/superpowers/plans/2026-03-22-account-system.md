# Account System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add multi-user support with username/password login, Cookie session auth, and per-user data isolation to AutoTrade.

**Architecture:** itsdangerous-signed Cookie session stored in `app.state.serializer`; `get_current_user` FastAPI dependency injected into all routers; `user_id` foreign key added to Strategy/Position/SimAccount/BacktestResult; TriggerLog/NotificationLog scoped via JOIN through strategies.

**Tech Stack:** FastAPI, SQLAlchemy async, SQLite, itsdangerous, passlib[bcrypt], Next.js 16 middleware, shadcn/ui

**Spec:** `docs/superpowers/specs/2026-03-22-account-system-design.md`

---

## File Map

### Backend — New Files
- `backend/app/deps.py` — `get_current_user` FastAPI dependency
- `backend/app/routers/auth.py` — register/login/logout/me endpoints

### Backend — Modified Files
- `backend/requirements.txt` — add itsdangerous, passlib[bcrypt]
- `backend/app/models.py` — add User model; add user_id FK to Strategy/Position/SimAccount/BacktestResult
- `backend/app/database.py` — add ALTER TABLE migrations; remove global SimAccount seed
- `backend/app/schemas.py` — add UserResponse, AuthRequest, AuthResponse
- `backend/app/main.py` — lifespan: SECRET_KEY validation, serializer/cookie_secure init; register auth router
- `backend/app/services/simulator.py` — accept `user_id` param; scope SimAccount queries
- `backend/app/engine/executor.py` — pass `strategy.user_id` to StrategyContext; update `get_balance()`
- `backend/app/engine/scheduler.py` — add `stop_user_strategies(user_id)`
- `backend/app/routers/account.py` — scope to current_user; fix reset (scheduler + scoped deletes + balance restore)
- `backend/app/routers/dashboard.py` — scope to current_user
- `backend/app/routers/strategies.py` — scope to current_user; inject user_id on create
- `backend/app/routers/triggers.py` — scope via JOIN with strategies
- `backend/app/routers/backtests.py` — scope to current_user
- `backend/app/routers/settings.py` — admin gate on PUT

### Frontend — New Files
- `frontend/src/middleware.ts` — Next.js Edge Middleware: cookie check + redirect
- `frontend/src/app/login/page.tsx` — login page
- `frontend/src/app/register/page.tsx` — register page

### Frontend — Modified Files
- `frontend/src/lib/api.ts` — withCredentials, 401 interceptor, auth API functions
- `frontend/src/components/sidebar.tsx` — user info display + logout (desktop + mobile)
- `frontend/src/app/layout.tsx` — fetch /auth/me, pass user to sidebar

---

## Task 1: Add Backend Dependencies

**Files:**
- Modify: `backend/requirements.txt`

- [ ] **Step 1: Add dependencies to requirements.txt**

Edit `backend/requirements.txt` and add two lines:
```
itsdangerous==2.2.*
passlib[bcrypt]==1.7.*
```

- [ ] **Step 2: Install dependencies**

```bash
cd /home/autotrade/autotrade/backend && source venv/bin/activate && pip install itsdangerous==2.2.* "passlib[bcrypt]==1.7.*"
```

Expected: both packages install successfully without errors.

- [ ] **Step 3: Verify imports work**

```bash
cd /home/autotrade/autotrade/backend && source venv/bin/activate && python -c "from itsdangerous import URLSafeTimedSerializer; from passlib.context import CryptContext; print('OK')"
```

Expected: prints `OK`

- [ ] **Step 4: Commit**

```bash
cd /home/autotrade/autotrade && git add backend/requirements.txt && git commit -m "chore: add itsdangerous and passlib[bcrypt] dependencies"
```

---

## Task 2: Add User Model and user_id Columns

**Files:**
- Modify: `backend/app/models.py`

- [ ] **Step 1: Add User model and user_id FK to models.py**

At the top of `backend/app/models.py`, the imports already include what's needed. Add the `User` class after the imports and before `Strategy`. Then add `user_id` columns to Strategy, Position, SimAccount, BacktestResult.

Replace the entire `backend/app/models.py` with:

```python
"""
SQLAlchemy 数据模型
"""

from datetime import datetime

from sqlalchemy import (
    JSON, Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text,
    UniqueConstraint, func
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    """用户模型"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), nullable=False, unique=True)
    password_hash = Column(String, nullable=False)
    is_admin = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    # 关系
    strategies = relationship("Strategy", back_populates="user", cascade="all, delete-orphan")
    positions = relationship("Position", back_populates="user", cascade="all, delete-orphan")
    sim_accounts = relationship("SimAccount", back_populates="user", cascade="all, delete-orphan")
    backtest_results = relationship("BacktestResult", back_populates="user", cascade="all, delete-orphan")


class Strategy(Base):
    """策略模型"""
    __tablename__ = "strategies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # nullable during migration
    name = Column(String, nullable=False)
    type = Column(String, nullable=False)  # visual / code
    config_json = Column(Text, nullable=True)  # 可视化配置 JSON 字符串
    code = Column(Text, nullable=True)  # 代码策略源码
    symbol = Column(String, nullable=False)  # e.g. BTCUSDT
    timeframe = Column(String, nullable=False)  # 1m/5m/1h/1d
    position_size = Column(Float, nullable=False, default=100.0)
    position_size_type = Column(String, nullable=False, default="fixed")  # fixed / percent
    stop_loss = Column(Float, nullable=True)  # 止损百分比
    take_profit = Column(Float, nullable=True)  # 止盈百分比
    sell_size_pct = Column(Float, nullable=False, default=100.0)  # 每次卖出仓位比例 (1-100)
    notify_enabled = Column(Boolean, nullable=False, default=True)
    status = Column(String, nullable=False, default="stopped")  # running/stopped/error
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    # 关系
    user = relationship("User", back_populates="strategies")
    trigger_logs = relationship("TriggerLog", back_populates="strategy", cascade="all, delete-orphan")
    positions = relationship("Position", back_populates="strategy", cascade="all, delete-orphan")
    backtest_results = relationship("BacktestResult", back_populates="strategy", cascade="all, delete-orphan")


class TriggerLog(Base):
    """触发记录模型"""
    __tablename__ = "trigger_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    strategy_id = Column(Integer, ForeignKey("strategies.id"), nullable=False)
    triggered_at = Column(DateTime, nullable=False, server_default=func.now())
    signal_type = Column(String, nullable=False)  # buy / sell / error
    signal_detail = Column(Text, nullable=True)  # 信号详情
    action = Column(String, nullable=True)  # buy / sell / hold (实际执行)
    price = Column(Float, nullable=True)
    quantity = Column(Float, nullable=True)
    simulated_pnl = Column(Float, nullable=True)  # 模拟盈亏

    # 关系
    strategy = relationship("Strategy", back_populates="trigger_logs")
    notification_logs = relationship("NotificationLog", back_populates="trigger_log")


class Position(Base):
    """模拟持仓模型"""
    __tablename__ = "positions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # nullable during migration
    strategy_id = Column(Integer, ForeignKey("strategies.id"), nullable=False)
    symbol = Column(String, nullable=False)
    side = Column(String, nullable=False)  # long / short
    entry_price = Column(Float, nullable=False)
    quantity = Column(Float, nullable=False)
    current_price = Column(Float, nullable=True)  # 当前价格（平仓时写入）
    pnl = Column(Float, nullable=True)  # 已实现盈亏
    opened_at = Column(DateTime, nullable=False, server_default=func.now())
    closed_at = Column(DateTime, nullable=True)

    # 关系
    user = relationship("User", back_populates="positions")
    strategy = relationship("Strategy", back_populates="positions")


class NotificationLog(Base):
    """通知记录模型"""
    __tablename__ = "notification_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trigger_log_id = Column(Integer, ForeignKey("trigger_logs.id"), nullable=False)
    channel = Column(String, nullable=False, default="feishu")  # feishu
    status = Column(String, nullable=False)  # sent / failed
    error_message = Column(Text, nullable=True)
    sent_at = Column(DateTime, nullable=False, server_default=func.now())

    # 关系
    trigger_log = relationship("TriggerLog", back_populates="notification_logs")


class SimAccount(Base):
    """模拟账户模型"""
    __tablename__ = "sim_accounts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # nullable during migration
    initial_balance = Column(Float, nullable=False, default=100000.0)
    balance = Column(Float, nullable=False, default=100000.0)
    total_pnl = Column(Float, nullable=False, default=0.0)
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    # 关系
    user = relationship("User", back_populates="sim_accounts")


class KlineData(Base):
    """K线缓存模型"""
    __tablename__ = "kline_data"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String, nullable=False)
    timeframe = Column(String, nullable=False)  # 1m/5m/1h/1d
    open_time = Column(DateTime, nullable=False)
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=False)

    # 联合唯一索引
    __table_args__ = (
        UniqueConstraint('symbol', 'timeframe', 'open_time', name='uix_kline'),
    )


class SystemSetting(Base):
    """系统设置（key-value 存储）"""
    __tablename__ = "system_settings"

    key = Column(String, primary_key=True)
    value = Column(Text, nullable=True)
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())


class BacktestResult(Base):
    """回测结果模型"""
    __tablename__ = "backtest_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # nullable during migration
    strategy_id = Column(Integer, ForeignKey("strategies.id"), nullable=False)
    symbol = Column(String, nullable=False)
    timeframe = Column(String, nullable=False)
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)
    initial_balance = Column(Float, nullable=False)
    final_balance = Column(Float, nullable=False)
    total_pnl = Column(Float, nullable=False)
    pnl_percent = Column(Float, nullable=False)
    win_rate = Column(Float, nullable=False)
    max_drawdown = Column(Float, nullable=False)
    total_trades = Column(Integer, nullable=False)
    avg_hold_time = Column(Integer, nullable=True)  # 平均持仓时间（秒）
    equity_curve = Column(Text, nullable=False)  # JSON 字符串
    trades = Column(Text, nullable=False)  # JSON 字符串
    klines = Column(Text, nullable=True)  # JSON 字符串，回测用的K线数据
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    # 关系
    user = relationship("User", back_populates="backtest_results")
    strategy = relationship("Strategy", back_populates="backtest_results")
```

- [ ] **Step 2: Verify model imports without errors**

```bash
cd /home/autotrade/autotrade/backend && source venv/bin/activate && python -c "from app.models import User, Strategy, Position, SimAccount, BacktestResult; print('OK')"
```

Expected: prints `OK`

- [ ] **Step 3: Commit**

```bash
cd /home/autotrade/autotrade && git add backend/app/models.py && git commit -m "feat: add User model and user_id FK columns to data models"
```

---

## Task 3: Update database.py (Migrations + Remove SimAccount Seed)

**Files:**
- Modify: `backend/app/database.py`

This task updates `init_db()` to:
1. Remove the global SimAccount seed (must happen before migrations run)
2. Run `CREATE TABLE users` and `ALTER TABLE` to add `user_id` columns
3. Backfill existing data to a default admin user

- [ ] **Step 1: Replace database.py**

```python
import os

from dotenv import load_dotenv
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

load_dotenv()

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./autotrade.db")

engine = create_async_engine(DATABASE_URL, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    async with async_session() as session:
        yield session


async def init_db():
    from app.models import Base

    async with engine.begin() as conn:
        # Create all tables (idempotent)
        await conn.run_sync(Base.metadata.create_all)

        # Incremental migrations (ignore errors if column already exists)
        migrations = [
            "ALTER TABLE strategies ADD COLUMN sell_size_pct REAL NOT NULL DEFAULT 100.0",
            "ALTER TABLE strategies ADD COLUMN user_id INTEGER REFERENCES users(id)",
            "ALTER TABLE positions ADD COLUMN user_id INTEGER REFERENCES users(id)",
            "ALTER TABLE sim_accounts ADD COLUMN user_id INTEGER REFERENCES users(id)",
            "ALTER TABLE backtest_results ADD COLUMN user_id INTEGER REFERENCES users(id)",
        ]
        for sql in migrations:
            try:
                await conn.execute(text(sql))
            except Exception:
                pass  # Column already exists

    # Backfill: ensure admin user exists and all existing data is assigned to them
    async with async_session() as session:
        from sqlalchemy import select
        from app.models import BacktestResult, Position, SimAccount, Strategy, User
        from passlib.context import CryptContext

        pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

        # Check if admin user exists
        result = await session.execute(select(User).where(User.username == "admin"))
        admin = result.scalar_one_or_none()

        if admin is None:
            admin_password = os.getenv("ADMIN_PASSWORD", "changeme")
            admin = User(
                username="admin",
                password_hash=pwd_context.hash(admin_password),
                is_admin=True,
            )
            session.add(admin)
            await session.flush()  # get admin.id

        admin_id = admin.id

        # Backfill strategies
        await session.execute(
            text("UPDATE strategies SET user_id = :uid WHERE user_id IS NULL"),
            {"uid": admin_id},
        )
        # Backfill positions
        await session.execute(
            text("UPDATE positions SET user_id = :uid WHERE user_id IS NULL"),
            {"uid": admin_id},
        )
        # Backfill sim_accounts
        await session.execute(
            text("UPDATE sim_accounts SET user_id = :uid WHERE user_id IS NULL"),
            {"uid": admin_id},
        )
        # Backfill backtest_results
        await session.execute(
            text("UPDATE backtest_results SET user_id = :uid WHERE user_id IS NULL"),
            {"uid": admin_id},
        )

        # If no sim_account exists for admin, create one
        result = await session.execute(
            select(SimAccount).where(SimAccount.user_id == admin_id)
        )
        if result.scalar_one_or_none() is None:
            initial_balance = float(os.getenv("SIMULATED_INITIAL_BALANCE", "100000"))
            session.add(SimAccount(
                user_id=admin_id,
                initial_balance=initial_balance,
                balance=initial_balance,
                total_pnl=0.0,
            ))

        await session.commit()

    # Seed default SystemSetting if empty
    async with async_session() as session:
        from sqlalchemy import select
        from app.models import SystemSetting

        result = await session.execute(
            select(SystemSetting).where(SystemSetting.key == "data_source")
        )
        if result.scalar_one_or_none() is None:
            use_mock = os.getenv("USE_MOCK_DATA", "false").lower() == "true"
            default_source = "mock" if use_mock else "binance"
            session.add(SystemSetting(key="data_source", value=default_source))
            session.add(SystemSetting(key="cryptocompare_api_key", value=""))
            await session.commit()
```

- [ ] **Step 2: Verify database.py imports without errors**

```bash
cd /home/autotrade/autotrade/backend && source venv/bin/activate && python -c "from app.database import init_db; print('OK')"
```

Expected: prints `OK`

- [ ] **Step 3: Commit**

```bash
cd /home/autotrade/autotrade && git add backend/app/database.py && git commit -m "feat: add user migration and backfill logic to init_db"
```

---

## Task 4: Add Auth Schemas

**Files:**
- Modify: `backend/app/schemas.py`

- [ ] **Step 1: Add User/Auth schemas at the end of schemas.py**

Open `backend/app/schemas.py` and append at the end:

```python
# ==================== 认证相关 ====================

class UserResponse(BaseModel):
    """用户信息响应"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    is_admin: bool
    created_at: datetime


class AuthRequest(BaseModel):
    """登录/注册请求"""
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=6)


class AuthResponse(BaseModel):
    """认证响应"""
    user: UserResponse


class MeResponse(BaseModel):
    """当前用户响应（未登录时 user 为 null）"""
    user: Optional[UserResponse] = None
```

- [ ] **Step 2: Verify schemas import**

```bash
cd /home/autotrade/autotrade/backend && source venv/bin/activate && python -c "from app.schemas import UserResponse, AuthRequest, AuthResponse, MeResponse; print('OK')"
```

Expected: prints `OK`

- [ ] **Step 3: Commit**

```bash
cd /home/autotrade/autotrade && git add backend/app/schemas.py && git commit -m "feat: add User/Auth Pydantic schemas"
```

---

## Task 5: Create deps.py (get_current_user)

**Files:**
- Create: `backend/app/deps.py`

- [ ] **Step 1: Create deps.py**

```python
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
```

- [ ] **Step 2: Verify deps.py imports**

```bash
cd /home/autotrade/autotrade/backend && source venv/bin/activate && python -c "from app.deps import get_current_user, get_admin_user; print('OK')"
```

Expected: prints `OK`

- [ ] **Step 3: Commit**

```bash
cd /home/autotrade/autotrade && git add backend/app/deps.py && git commit -m "feat: add get_current_user and get_admin_user FastAPI dependencies"
```

---

## Task 6: Update main.py (SECRET_KEY + auth router)

**Files:**
- Modify: `backend/app/main.py`

- [ ] **Step 1: Update lifespan to validate SECRET_KEY and initialize app.state**

In `backend/app/main.py`, add to imports at the top:
```python
import os
from itsdangerous import URLSafeTimedSerializer
```

Replace the `lifespan` function with:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # Validate SECRET_KEY FIRST — before log_startup() or any other init
    secret_key = os.environ.get("SECRET_KEY")
    if not secret_key:
        raise RuntimeError("SECRET_KEY 环境变量未设置，拒绝启动")
    app.state.serializer = URLSafeTimedSerializer(secret_key)
    app.state.cookie_secure = (os.environ.get("ENV") != "development")

    # 记录启动日志（after SECRET_KEY is validated）
    log_startup()

    logger.info("🚀 AutoTrade 启动中...")
    await init_db()
    logger.info("✅ 数据库初始化完成")

    # 从 DB 读取数据源配置
    from app.engine.market_data import market_data_service
    await market_data_service.init_from_db()
    logger.info(f"✅ 数据源初始化完成: {market_data_service.source_name}")

    # 启动调度器
    scheduler.start()
    logger.info("✅ 调度器启动完成")

    # 恢复运行中的策略
    await scheduler.restore_running_strategies()
    logger.info("✅ 运行中策略已恢复")

    logger.info("🚀 AutoTrade 启动完成")

    yield

    # 关闭调度器
    scheduler.shutdown()
    logger.info("🛑 调度器已关闭")
    logger.info("🛑 AutoTrade 关闭中...")
```

- [ ] **Step 2: Register auth router**

In `backend/app/main.py`, add the auth router import and registration. After the existing router imports line, add:
```python
from app.routers import account, auth, backtests, dashboard, logs, market, settings, strategies, triggers
```

And after the existing `app.include_router` calls, add:
```python
app.include_router(auth.router, prefix="/api")
```

- [ ] **Step 3: Verify main.py imports (SECRET_KEY not set — should fail gracefully on startup only)**

```bash
cd /home/autotrade/autotrade/backend && source venv/bin/activate && python -c "import app.main; print('OK')"
```

Expected: prints `OK` (import succeeds; RuntimeError only fires during lifespan startup)

- [ ] **Step 4: Commit**

```bash
cd /home/autotrade/autotrade && git add backend/app/main.py && git commit -m "feat: validate SECRET_KEY in lifespan and register auth router"
```

---

## Task 7: Create auth.py Router

**Files:**
- Create: `backend/app/routers/auth.py`

- [ ] **Step 1: Create auth router**

```python
"""
认证路由
POST /api/auth/register  — 注册
POST /api/auth/login     — 登录
POST /api/auth/logout    — 退出
GET  /api/auth/me        — 当前用户（未登录返回 {"user": null}）
"""

import os

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.deps import get_current_user
from app.models import SimAccount, User
from app.schemas import AuthRequest, AuthResponse, MeResponse, UserResponse

router = APIRouter(prefix="/auth", tags=["认证"])
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

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
    # Check username uniqueness
    result = await db.execute(select(User).where(User.username == payload.username))
    if result.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="用户名已存在")

    # Create user
    user = User(
        username=payload.username,
        password_hash=pwd_context.hash(payload.password),
        is_admin=False,
    )
    db.add(user)
    await db.flush()  # get user.id

    # Create SimAccount for new user
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

    if not user or not pwd_context.verify(payload.password, user.password_hash):
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
```

- [ ] **Step 2: Verify auth router imports**

```bash
cd /home/autotrade/autotrade/backend && source venv/bin/activate && python -c "from app.routers.auth import router; print('OK')"
```

Expected: prints `OK`

- [ ] **Step 3: Start backend with SECRET_KEY and test auth endpoints**

```bash
cd /home/autotrade/autotrade/backend && source venv/bin/activate && SECRET_KEY=testsecret ENV=development uvicorn app.main:app --port 18001 &
sleep 3
# Register
curl -s -c /tmp/cookies.txt -X POST http://localhost:18001/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"testuser","password":"testpass"}' | python3 -m json.tool
# Me
curl -s -b /tmp/cookies.txt http://localhost:18001/api/auth/me | python3 -m json.tool
# Logout
curl -s -b /tmp/cookies.txt -c /tmp/cookies.txt -X POST http://localhost:18001/api/auth/logout
# Me after logout
curl -s -b /tmp/cookies.txt http://localhost:18001/api/auth/me | python3 -m json.tool
# Kill test server
kill %1 2>/dev/null; rm -f /tmp/cookies.txt
```

Expected:
- Register returns `{"user": {"id": ..., "username": "testuser", "is_admin": false, ...}}`
- Me (logged in) returns same user
- Me (logged out) returns `{"user": null}`

- [ ] **Step 4: Commit**

```bash
cd /home/autotrade/autotrade && git add backend/app/routers/auth.py && git commit -m "feat: add auth router (register/login/logout/me)"
```

---

## Task 8: Update simulator.py (user_id-scoped SimAccount)

**Files:**
- Modify: `backend/app/services/simulator.py`

The simulator currently does `select(SimAccount).limit(1)` — a global query. After multi-user migration, this must find the SimAccount for the strategy's owner.

- [ ] **Step 1: Update execute_buy to accept user_id**

In `backend/app/services/simulator.py`, update `execute_buy` signature to add `user_id: int` parameter and change the SimAccount query:

Change:
```python
async def execute_buy(
    self,
    strategy_id: int,
    symbol: str,
    quantity: float,
    price: float,
    db: AsyncSession,
) -> Optional[TriggerLog]:
```

To:
```python
async def execute_buy(
    self,
    strategy_id: int,
    symbol: str,
    quantity: float,
    price: float,
    db: AsyncSession,
    user_id: Optional[int] = None,
) -> Optional[TriggerLog]:
```

Change the SimAccount query inside `execute_buy` from:
```python
account_result = await db.execute(select(SimAccount).limit(1))
account = account_result.scalar_one()
```

To:
```python
if user_id is not None:
    account_result = await db.execute(
        select(SimAccount).where(SimAccount.user_id == user_id)
    )
else:
    account_result = await db.execute(select(SimAccount).limit(1))
account = account_result.scalar_one()
```

- [ ] **Step 2: Update execute_sell to accept user_id**

Same pattern for `execute_sell`:

Change signature to add `user_id: Optional[int] = None`

Change both SimAccount queries inside `execute_sell` (there are two: one for balance check, one for returns) from:
```python
account_result = await db.execute(select(SimAccount).limit(1))
account = account_result.scalar_one()
```

To:
```python
if user_id is not None:
    account_result = await db.execute(
        select(SimAccount).where(SimAccount.user_id == user_id)
    )
else:
    account_result = await db.execute(select(SimAccount).limit(1))
account = account_result.scalar_one()
```

- [ ] **Step 3: Update check_stop_loss_take_profit to accept user_id**

Add `user_id: Optional[int] = None` parameter to `check_stop_loss_take_profit`. Then update **both** internal `self.execute_sell(...)` calls inside the method to pass `user_id`. The existing calls look like:

```python
trigger = await self.execute_sell(strategy_id, symbol, current_price, db)
```

Change both to:

```python
trigger = await self.execute_sell(strategy_id, symbol, current_price, db, user_id=user_id)
```

- [ ] **Step 4: Verify simulator imports**

```bash
cd /home/autotrade/autotrade/backend && source venv/bin/activate && python -c "from app.services.simulator import simulator; print('OK')"
```

Expected: prints `OK`

- [ ] **Step 5: Commit**

```bash
cd /home/autotrade/autotrade && git add backend/app/services/simulator.py && git commit -m "feat: scope SimAccount queries by user_id in simulator"
```

---

## Task 9: Update executor.py (pass user_id through StrategyContext)

**Files:**
- Modify: `backend/app/engine/executor.py`

`StrategyContext` needs the strategy's `user_id` to pass to simulator and to query the correct SimAccount.

- [ ] **Step 1: Update StrategyContext.get_balance() to use user_id**

In `backend/app/engine/executor.py`, update `get_balance`:

```python
async def get_balance(self) -> float:
    """获取账户余额（当前用户的 SimAccount）"""
    from app.models import SimAccount

    user_id = getattr(self.strategy, "user_id", None)
    if user_id is not None:
        result = await self.db.execute(
            select(SimAccount).where(SimAccount.user_id == user_id)
        )
    else:
        result = await self.db.execute(select(SimAccount).limit(1))
    account = result.scalar_one()
    return account.balance
```

- [ ] **Step 2: Update StrategyContext.buy() to pass user_id to simulator**

In `buy()`, update the `simulator.execute_buy` call to pass `user_id`:

```python
return await simulator.execute_buy(
    strategy_id=self.strategy.id,
    symbol=self.strategy.symbol,
    quantity=qty,
    price=price,
    db=self.db,
    user_id=getattr(self.strategy, "user_id", None),
)
```

- [ ] **Step 3: Update StrategyContext.sell() to pass user_id to simulator**

In `sell()`, update the `simulator.execute_sell` call to pass `user_id`:

```python
return await simulator.execute_sell(
    strategy_id=self.strategy.id,
    symbol=self.strategy.symbol,
    price=price,
    db=self.db,
    sell_size_pct=sell_size_pct,
    user_id=getattr(self.strategy, "user_id", None),
)
```

- [ ] **Step 4: Update StrategyExecutor.execute() check_stop_loss_take_profit call to pass user_id**

In `execute()`, update the `simulator.check_stop_loss_take_profit` call:

```python
sl_tp_trigger = await simulator.check_stop_loss_take_profit(
    strategy_id=strategy.id,
    symbol=strategy.symbol,
    current_price=current_price,
    stop_loss_pct=strategy.stop_loss,
    take_profit_pct=strategy.take_profit,
    db=db,
    user_id=getattr(strategy, "user_id", None),
)
```

- [ ] **Step 5: Verify executor imports**

```bash
cd /home/autotrade/autotrade/backend && source venv/bin/activate && python -c "from app.engine.executor import executor; print('OK')"
```

Expected: prints `OK`

- [ ] **Step 6: Commit**

```bash
cd /home/autotrade/autotrade && git add backend/app/engine/executor.py && git commit -m "feat: pass user_id through StrategyContext to simulator"
```

---

## Task 10: Update scheduler.py (add stop_user_strategies)

**Files:**
- Modify: `backend/app/engine/scheduler.py`

- [ ] **Step 1: Add stop_user_strategies method to StrategyScheduler**

In `backend/app/engine/scheduler.py`, add this method to the `StrategyScheduler` class after `stop_strategy`:

```python
async def stop_user_strategies(self, user_id: int):
    """
    停止某用户所有运行中的策略并重置状态为 stopped。
    在 account reset 前调用，确保 scheduler 内存状态和 DB 一致。
    """
    async with async_session() as db:
        result = await db.execute(
            select(Strategy).where(
                Strategy.user_id == user_id,
                Strategy.status == "running",
            )
        )
        strategies = result.scalars().all()

        for strategy in strategies:
            self.stop_strategy(strategy.id)
            strategy.status = "stopped"

        await db.commit()
        logger.info(f"Stopped {len(strategies)} strategies for user {user_id}")
```

- [ ] **Step 2: Verify scheduler imports**

```bash
cd /home/autotrade/autotrade/backend && source venv/bin/activate && python -c "from app.engine.scheduler import scheduler; print('OK')"
```

Expected: prints `OK`

- [ ] **Step 3: Commit**

```bash
cd /home/autotrade/autotrade && git add backend/app/engine/scheduler.py && git commit -m "feat: add stop_user_strategies to scheduler for account reset"
```

---

## Task 11: Update account.py Router

**Files:**
- Modify: `backend/app/routers/account.py`

- [ ] **Step 1: Replace account.py with user-scoped version**

```python
"""
账户和持仓路由
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database import get_db
from app.deps import get_current_user
from app.engine.scheduler import scheduler
from app.logger import get_logger
from app.models import Position, SimAccount, User
from app.schemas import AccountResponse, MessageResponse, PositionList, PositionResponse

logger = get_logger(__name__)
router = APIRouter(tags=["账户"])


@router.get("/account", response_model=AccountResponse)
async def get_account(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取当前用户的模拟账户信息"""
    result = await db.execute(
        select(SimAccount).where(SimAccount.user_id == current_user.id)
    )
    account = result.scalar_one_or_none()

    if not account:
        # 懒创建（用户注册时应已创建，此处作为兜底）
        import os
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

    return AccountResponse.model_validate(account)


@router.post("/account/reset", response_model=MessageResponse)
async def reset_account(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """重置当前用户的模拟账户"""
    # 1. Stop all running strategies for this user (flushes scheduler memory)
    await scheduler.stop_user_strategies(current_user.id)

    # 2. Delete notification_logs for this user's trigger_logs
    await db.execute(text(
        """
        DELETE FROM notification_logs WHERE trigger_log_id IN (
            SELECT tl.id FROM trigger_logs tl
            JOIN strategies s ON tl.strategy_id = s.id
            WHERE s.user_id = :uid
        )
        """
    ), {"uid": current_user.id})

    # 3. Delete trigger_logs for this user's strategies
    await db.execute(text(
        """
        DELETE FROM trigger_logs WHERE strategy_id IN (
            SELECT id FROM strategies WHERE user_id = :uid
        )
        """
    ), {"uid": current_user.id})

    # 4. Delete positions for this user
    await db.execute(text(
        "DELETE FROM positions WHERE user_id = :uid"
    ), {"uid": current_user.id})

    # 5. Reset sim_account balance
    result = await db.execute(
        select(SimAccount).where(SimAccount.user_id == current_user.id)
    )
    account = result.scalar_one_or_none()
    if account:
        account.balance = account.initial_balance
        account.total_pnl = 0.0

    await db.commit()
    logger.info(f"模拟账户已重置 (user_id={current_user.id})")
    return MessageResponse(message="模拟账户已重置")


@router.get("/positions", response_model=PositionList)
async def list_positions(
    strategy_id: Optional[int] = Query(None, description="筛选特定策略"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取当前用户的持仓列表"""
    query = select(Position).where(
        Position.user_id == current_user.id,
        Position.closed_at.is_(None),
    )

    if strategy_id:
        query = query.where(Position.strategy_id == strategy_id)

    query = query.order_by(Position.opened_at.desc())

    result = await db.execute(query)
    items = result.scalars().all()

    response_items = []
    for item in items:
        response_item = PositionResponse.model_validate(item)
        if item.current_price:
            if item.side == "long":
                response_item.unrealized_pnl = (item.current_price - item.entry_price) * item.quantity
            else:
                response_item.unrealized_pnl = (item.entry_price - item.current_price) * item.quantity
        response_items.append(response_item)

    return PositionList(items=response_items, total=len(items))
```

- [ ] **Step 2: Verify account router imports**

```bash
cd /home/autotrade/autotrade/backend && source venv/bin/activate && python -c "from app.routers.account import router; print('OK')"
```

Expected: prints `OK`

- [ ] **Step 3: Commit**

```bash
cd /home/autotrade/autotrade && git add backend/app/routers/account.py && git commit -m "feat: scope account and positions endpoints to current user"
```

---

## Task 12: Update dashboard.py Router

**Files:**
- Modify: `backend/app/routers/dashboard.py`

- [ ] **Step 1: Add current_user scoping to dashboard.py**

Replace entire `backend/app/routers/dashboard.py`:

```python
"""
仪表盘路由
"""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database import get_db
from app.deps import get_current_user
from app.models import SimAccount, Strategy, TriggerLog, User
from app.schemas import DashboardData, TriggerLogResponse

router = APIRouter(tags=["仪表盘"])


@router.get("/dashboard", response_model=DashboardData)
async def get_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取当前用户的仪表盘数据"""

    # 获取账户信息
    import os
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

    # 今日触发次数（当前用户的策略）
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
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

    return DashboardData(
        balance=account.balance,
        total_pnl=account.total_pnl,
        running_strategies=running_strategies,
        today_triggers=today_triggers,
        recent_triggers=recent_items,
    )
```

- [ ] **Step 2: Verify dashboard router imports**

```bash
cd /home/autotrade/autotrade/backend && source venv/bin/activate && python -c "from app.routers.dashboard import router; print('OK')"
```

Expected: prints `OK`

- [ ] **Step 3: Commit**

```bash
cd /home/autotrade/autotrade && git add backend/app/routers/dashboard.py && git commit -m "feat: scope dashboard endpoint to current user"
```

---

## Task 13: Update strategies.py, triggers.py, backtests.py Routers

**Files:**
- Modify: `backend/app/routers/strategies.py`
- Modify: `backend/app/routers/triggers.py`
- Modify: `backend/app/routers/backtests.py`

### strategies.py

- [ ] **Step 1: Add current_user dep import to strategies.py**

In `backend/app/routers/strategies.py`, add to imports:
```python
from app.deps import get_current_user
from app.models import Strategy, User
```

- [ ] **Step 2: Update list_strategies to filter by user_id**

Update `list_strategies` signature and query:
```python
async def list_strategies(
    status: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    query = select(Strategy).where(Strategy.user_id == current_user.id)
    if status:
        query = query.where(Strategy.status == status)
    # ... rest unchanged
```

- [ ] **Step 3: Update create_strategy to inject user_id**

In the create endpoint, before `db.add(strategy)`, add:
```python
strategy.user_id = current_user.id
```

Also add `current_user: User = Depends(get_current_user)` to the function signature.

- [ ] **Step 4: Update get_strategy, update_strategy, delete_strategy, start_strategy, stop_strategy**

For each of these 5 endpoints, add `current_user: User = Depends(get_current_user)` to the function signature, then add the ownership check immediately after the existing 404 check. For example, `get_strategy` becomes:

```python
@router.get("/strategies/{strategy_id}", response_model=StrategyResponse)
async def get_strategy(
    strategy_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await db.execute(select(Strategy).where(Strategy.id == strategy_id))
    strategy = result.scalar_one_or_none()

    if not strategy or strategy.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="策略不存在")

    # ... rest of function unchanged
```

Apply the same pattern to `update_strategy`, `delete_strategy`, `start_strategy`, and `stop_strategy`. The ownership check `strategy.user_id != current_user.id` should be combined with the existing `not strategy` check using `or`, so a foreign user gets a 404 (not 403) — this prevents information leakage about strategy IDs.

### triggers.py

- [ ] **Step 5: Update triggers.py to scope via JOIN**

In `backend/app/routers/triggers.py`, add imports:
```python
from app.deps import get_current_user
from app.models import Strategy, TriggerLog, User
```

Replace `list_triggers` with the full implementation (the count query must be rewritten to handle the JOIN correctly):

```python
@router.get("/triggers", response_model=TriggerLogList)
async def list_triggers(
    strategy_id: Optional[int] = Query(None, description="筛选特定策略"),
    start_date: Optional[datetime] = Query(None, description="开始时间"),
    end_date: Optional[datetime] = Query(None, description="结束时间"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取当前用户的触发日志列表"""
    # Base query: JOIN with strategies to filter by user
    base_query = (
        select(TriggerLog)
        .join(Strategy, TriggerLog.strategy_id == Strategy.id)
        .where(Strategy.user_id == current_user.id)
    )

    if strategy_id:
        base_query = base_query.where(TriggerLog.strategy_id == strategy_id)
    if start_date:
        base_query = base_query.where(TriggerLog.triggered_at >= start_date)
    if end_date:
        base_query = base_query.where(TriggerLog.triggered_at <= end_date)

    # Count using the filtered base query as subquery
    count_result = await db.execute(
        select(func.count()).select_from(base_query.subquery())
    )
    total = count_result.scalar()

    # Paginate
    paged_query = (
        base_query
        .order_by(TriggerLog.triggered_at.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    result = await db.execute(paged_query)
    items = result.scalars().all()

    # Build response (same as existing code)
    response_items = []
    for item in items:
        strategy_result = await db.execute(
            select(Strategy.name).where(Strategy.id == item.strategy_id)
        )
        strategy_name = strategy_result.scalar()
        response_item = TriggerLogResponse.model_validate(item)
        response_item.strategy_name = strategy_name
        response_items.append(response_item)

    return TriggerLogList(
        items=response_items,
        total=total,
        page=page,
        page_size=page_size,
    )
```

### backtests.py

- [ ] **Step 6: Update backtests.py to scope to current user**

In `backend/app/routers/backtests.py`, add imports:
```python
from app.deps import get_current_user
from app.models import BacktestResult, Strategy, User
```

Apply these changes:

**`create_backtest`:** Add `current_user: User = Depends(get_current_user)` to signature. After fetching the strategy, add ownership check:
```python
if strategy.user_id != current_user.id:
    raise HTTPException(status_code=404, detail="策略不存在")
```
After `backtest_engine.run_backtest(...)` returns `backtest_result` (note: the variable is named `backtest_result`, NOT `result`), set the user_id before `db.add(...)`:
```python
backtest_result.user_id = current_user.id
db.add(backtest_result)
```

**`get_backtest`:** Add `current_user: User = Depends(get_current_user)`. After fetching `backtest`, add:
```python
if backtest.user_id != current_user.id:
    raise HTTPException(status_code=404, detail="回测结果不存在")
```

**`list_strategy_backtests`:** Add `current_user: User = Depends(get_current_user)`. After verifying the strategy exists, add ownership check on the strategy. Change the `query` to:
```python
query = select(BacktestResult).where(
    BacktestResult.strategy_id == strategy_id,
    BacktestResult.user_id == current_user.id,
)
```

**`delete_backtest`:** Add `current_user: User = Depends(get_current_user)`. After fetching `backtest`, add:
```python
if backtest.user_id != current_user.id:
    raise HTTPException(status_code=404, detail="回测结果不存在")
```

**`cancel_backtest` and `get_backtest_status`:** Add `current_user: User = Depends(get_current_user)`. After fetching strategy, add ownership check.

- [ ] **Step 7: Verify all three routers import cleanly**

```bash
cd /home/autotrade/autotrade/backend && source venv/bin/activate && python -c "
from app.routers.strategies import router as sr
from app.routers.triggers import router as tr
from app.routers.backtests import router as br
print('OK')
"
```

Expected: prints `OK`

- [ ] **Step 8: Commit**

```bash
cd /home/autotrade/autotrade && git add backend/app/routers/strategies.py backend/app/routers/triggers.py backend/app/routers/backtests.py && git commit -m "feat: scope strategies/triggers/backtests endpoints to current user"
```

---

## Task 13b: Exempt logs.py from Auth

**Files:**
- No changes needed — `logs.py` must NOT get `get_current_user`

`backend/app/routers/logs.py` handles `POST /api/logs` (frontend client-side log ingestion) and `GET /api/logs/frontend` (debug endpoint). These endpoints must remain unauthenticated because:
1. The frontend may call `POST /api/logs` before a session cookie exists (e.g., logging errors during login)
2. Adding auth would require the frontend logger to handle 401 responses specially

**Action:** Do not modify `logs.py`. Leave it as-is with no `get_current_user` dependency.

---

## Task 14: Update settings.py (Admin Gate)

**Files:**
- Modify: `backend/app/routers/settings.py`

- [ ] **Step 1: Add admin gate to PUT /api/settings**

In `backend/app/routers/settings.py`, add import:
```python
from app.deps import get_admin_user
from app.models import User
```

Update `update_settings` signature:
```python
async def update_settings(
    payload: SettingsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_admin_user),  # admin only
):
```

- [ ] **Step 2: Verify settings router imports**

```bash
cd /home/autotrade/autotrade/backend && source venv/bin/activate && python -c "from app.routers.settings import router; print('OK')"
```

Expected: prints `OK`

- [ ] **Step 3: Verify full app starts successfully with SECRET_KEY**

```bash
cd /home/autotrade/autotrade/backend && source venv/bin/activate && SECRET_KEY=testsecret ENV=development uvicorn app.main:app --port 18001 &
sleep 3
curl -s http://localhost:18001/api/health
kill %1
```

Expected: `{"status":"ok"}`

- [ ] **Step 4: Commit**

```bash
cd /home/autotrade/autotrade && git add backend/app/routers/settings.py && git commit -m "feat: add admin-only gate to PUT /api/settings"
```

---

## Task 15: Update Frontend api.ts

**Files:**
- Modify: `frontend/src/lib/api.ts`

- [ ] **Step 1: Update axios instance and add auth API functions**

In `backend/app/routers/backtests.py` update is done. Now update `frontend/src/lib/api.ts`:

Replace the axios instance and response interceptor with:

```typescript
const api = axios.create({
  baseURL: `${API_BASE_URL}/api`,
  headers: {
    "Content-Type": "application/json",
  },
  withCredentials: true,  // send Cookie on every request
});

// Response interceptor
api.interceptors.response.use(
  (response: AxiosResponse) => response.data,
  (error) => {
    const url: string = error.config?.url ?? "";
    // Redirect to login on 401, but NOT for /auth/* paths (avoid redirect loop)
    if (error.response?.status === 401 && !url.startsWith("/auth/")) {
      if (typeof window !== "undefined") {
        window.location.href = "/login";
      }
    }
    console.error("API Error:", error.response?.data || error.message);
    return Promise.reject(error);
  }
);
```

- [ ] **Step 2: Add auth API functions at the end of api.ts**

```typescript
// ==================== 认证 ====================

export const authMe = () => apiCall<{ user: any | null }>(api.get("/auth/me"));

export const authLogin = (data: { username: string; password: string }) =>
  apiCall<{ user: any }>(api.post("/auth/login", data));

export const authRegister = (data: { username: string; password: string }) =>
  apiCall<{ user: any }>(api.post("/auth/register", data));

export const authLogout = () => apiCall(api.post("/auth/logout"));
```

- [ ] **Step 3: Verify frontend builds without TypeScript errors**

```bash
cd /home/autotrade/autotrade/frontend && npx tsc --noEmit 2>&1 | head -20
```

Expected: no errors (or only pre-existing errors unrelated to api.ts)

- [ ] **Step 4: Commit**

```bash
cd /home/autotrade/autotrade && git add frontend/src/lib/api.ts && git commit -m "feat: add withCredentials, 401 interceptor, and auth API functions"
```

---

## Task 16: Create middleware.ts

**Files:**
- Create: `frontend/src/middleware.ts`

- [ ] **Step 1: Create middleware.ts**

```typescript
import { NextResponse } from "next/server";
import type { NextRequest } from "next/server";

const PUBLIC_PATHS = ["/login", "/register"];
const EXEMPT_PREFIXES = ["/api/auth", "/_next", "/favicon.ico"];

export function middleware(request: NextRequest) {
  const { pathname } = request.nextUrl;

  // Exempt static assets, Next.js internals, and auth API
  if (EXEMPT_PREFIXES.some((prefix) => pathname.startsWith(prefix))) {
    return NextResponse.next();
  }

  const hasSession = request.cookies.has("session");

  // Already logged in → redirect away from login/register
  if (hasSession && PUBLIC_PATHS.includes(pathname)) {
    return NextResponse.redirect(new URL("/", request.url));
  }

  // Not logged in → redirect to login
  if (!hasSession && !PUBLIC_PATHS.includes(pathname)) {
    return NextResponse.redirect(new URL("/login", request.url));
  }

  return NextResponse.next();
}

export const config = {
  // Match all routes except static files
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
```

- [ ] **Step 2: Verify TypeScript**

```bash
cd /home/autotrade/autotrade/frontend && npx tsc --noEmit 2>&1 | head -20
```

Expected: no new errors

- [ ] **Step 3: Commit**

```bash
cd /home/autotrade/autotrade && git add frontend/src/middleware.ts && git commit -m "feat: add Next.js middleware for route protection"
```

---

## Task 17: Create Login Page

**Files:**
- Create: `frontend/src/app/login/page.tsx`

- [ ] **Step 1: Create login page directory and file**

```bash
mkdir -p /home/autotrade/autotrade/frontend/src/app/login
```

Create `frontend/src/app/login/page.tsx`:

```tsx
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Bot } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { authLogin } from "@/lib/api";

export default function LoginPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await authLogin({ username, password });
      router.push("/");
    } catch (err: any) {
      setError(err.response?.data?.detail ?? "登录失败，请检查用户名和密码");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-slate-950 flex items-center justify-center p-4">
      <Card className="w-full max-w-sm bg-slate-900 border-slate-800">
        <CardHeader className="text-center">
          <div className="flex justify-center mb-2">
            <Bot className="w-8 h-8 text-blue-400" />
          </div>
          <CardTitle className="text-white">AutoTrade</CardTitle>
          <CardDescription className="text-slate-400">登录你的账号</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="username" className="text-slate-300">用户名</Label>
              <Input
                id="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="bg-slate-800 border-slate-700 text-white"
                required
                autoFocus
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="password" className="text-slate-300">密码</Label>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="bg-slate-800 border-slate-700 text-white"
                required
              />
            </div>
            {error && <p className="text-red-400 text-sm">{error}</p>}
            <Button type="submit" className="w-full" disabled={loading}>
              {loading ? "登录中..." : "登录"}
            </Button>
          </form>
          <p className="mt-4 text-center text-sm text-slate-400">
            没有账号？{" "}
            <Link href="/register" className="text-blue-400 hover:underline">
              立即注册
            </Link>
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript**

```bash
cd /home/autotrade/autotrade/frontend && npx tsc --noEmit 2>&1 | head -20
```

- [ ] **Step 3: Commit**

```bash
cd /home/autotrade/autotrade && git add frontend/src/app/login/ && git commit -m "feat: add login page"
```

---

## Task 18: Create Register Page

**Files:**
- Create: `frontend/src/app/register/page.tsx`

- [ ] **Step 1: Create register page directory and file**

```bash
mkdir -p /home/autotrade/autotrade/frontend/src/app/register
```

Create `frontend/src/app/register/page.tsx`:

```tsx
"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import Link from "next/link";
import { Bot } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { authRegister } from "@/lib/api";

export default function RegisterPage() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError("");
    if (password !== confirm) {
      setError("两次输入的密码不一致");
      return;
    }
    setLoading(true);
    try {
      await authRegister({ username, password });
      router.push("/");
    } catch (err: any) {
      setError(err.response?.data?.detail ?? "注册失败，请重试");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="min-h-screen bg-slate-950 flex items-center justify-center p-4">
      <Card className="w-full max-w-sm bg-slate-900 border-slate-800">
        <CardHeader className="text-center">
          <div className="flex justify-center mb-2">
            <Bot className="w-8 h-8 text-blue-400" />
          </div>
          <CardTitle className="text-white">AutoTrade</CardTitle>
          <CardDescription className="text-slate-400">创建新账号</CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="username" className="text-slate-300">用户名</Label>
              <Input
                id="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
                className="bg-slate-800 border-slate-700 text-white"
                required
                autoFocus
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="password" className="text-slate-300">密码（至少 6 位）</Label>
              <Input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                className="bg-slate-800 border-slate-700 text-white"
                required
                minLength={6}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="confirm" className="text-slate-300">确认密码</Label>
              <Input
                id="confirm"
                type="password"
                value={confirm}
                onChange={(e) => setConfirm(e.target.value)}
                className="bg-slate-800 border-slate-700 text-white"
                required
              />
            </div>
            {error && <p className="text-red-400 text-sm">{error}</p>}
            <Button type="submit" className="w-full" disabled={loading}>
              {loading ? "注册中..." : "注册"}
            </Button>
          </form>
          <p className="mt-4 text-center text-sm text-slate-400">
            已有账号？{" "}
            <Link href="/login" className="text-blue-400 hover:underline">
              立即登录
            </Link>
          </p>
        </CardContent>
      </Card>
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript**

```bash
cd /home/autotrade/autotrade/frontend && npx tsc --noEmit 2>&1 | head -20
```

- [ ] **Step 3: Commit**

```bash
cd /home/autotrade/autotrade && git add frontend/src/app/register/ && git commit -m "feat: add register page"
```

---

## Task 19: Update layout.tsx and sidebar.tsx (User Info + Logout)

**Files:**
- Modify: `frontend/src/app/layout.tsx`
- Modify: `frontend/src/components/sidebar.tsx`

### layout.tsx

- [ ] **Step 1: Update layout.tsx to fetch user and pass to Sidebar**

Replace `frontend/src/app/layout.tsx`:

```tsx
import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { AppShell } from "@/components/app-shell";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "AutoTrade - 加密货币自动交易平台",
  description: "支持可视化配置和代码编写的策略交易平台",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN" className="dark">
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased bg-slate-950 text-slate-100`}
      >
        <AppShell>{children}</AppShell>
      </body>
    </html>
  );
}
```

- [ ] **Step 2: Create AppShell component**

Create `frontend/src/components/app-shell.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { Sidebar } from "@/components/sidebar";
import { authMe } from "@/lib/api";

const AUTH_PATHS = ["/login", "/register"];

export function AppShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [username, setUsername] = useState<string | null>(null);
  const isAuthPage = AUTH_PATHS.includes(pathname);

  useEffect(() => {
    if (!isAuthPage) {
      authMe().then((res) => {
        setUsername(res.user?.username ?? null);
      }).catch(() => {});
    }
  }, [isAuthPage]);

  if (isAuthPage) {
    return <>{children}</>;
  }

  return (
    <div className="flex h-screen">
      <Sidebar username={username} />
      <main className="flex-1 overflow-auto p-4 md:p-8 pb-20 md:pb-8">
        {children}
      </main>
    </div>
  );
}
```

### sidebar.tsx

- [ ] **Step 3: Update Sidebar to accept username prop and show logout**

Replace `frontend/src/components/sidebar.tsx`:

```tsx
"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { usePathname } from "next/navigation";
import { LayoutDashboard, Bot, History, BarChart2, Settings, LogOut, User } from "lucide-react";
import { authLogout } from "@/lib/api";

const navItems = [
  { icon: LayoutDashboard, label: "仪表盘", href: "/" },
  { icon: Bot, label: "策略", href: "/strategies" },
  { icon: History, label: "日志", href: "/triggers" },
  { icon: BarChart2, label: "大盘", href: "/market" },
  { icon: Settings, label: "设置", href: "/settings" },
];

interface SidebarProps {
  username?: string | null;
}

export function Sidebar({ username }: SidebarProps) {
  const pathname = usePathname();
  const router = useRouter();

  const isActive = (href: string) =>
    href === "/" ? pathname === "/" : pathname === href || pathname?.startsWith(`${href}/`);

  async function handleLogout() {
    try {
      await authLogout();
    } finally {
      router.push("/login");
    }
  }

  return (
    <>
      {/* 桌面端侧边栏 */}
      <aside className="hidden md:flex w-64 bg-slate-900 border-r border-slate-800 flex-col">
        <div className="p-6">
          <h1 className="text-xl font-bold text-white flex items-center gap-2">
            <Bot className="w-6 h-6" />
            AutoTrade
          </h1>
          <p className="text-xs text-slate-400 mt-1">加密货币自动交易平台</p>
        </div>

        <nav className="flex-1 px-4">
          <ul className="space-y-2">
            {navItems.map((item) => (
              <li key={item.href}>
                <Link
                  href={item.href}
                  className={`flex items-center gap-3 px-4 py-3 rounded-lg transition-colors ${
                    isActive(item.href)
                      ? "bg-blue-600 text-white"
                      : "text-slate-400 hover:bg-slate-800 hover:text-slate-100"
                  }`}
                >
                  <item.icon className="w-5 h-5" />
                  {item.label}
                </Link>
              </li>
            ))}
          </ul>
        </nav>

        <div className="p-4 border-t border-slate-800 space-y-2">
          {username && (
            <div className="flex items-center gap-2 px-2 py-1 text-slate-400">
              <User className="w-4 h-4" />
              <span className="text-sm truncate">{username}</span>
            </div>
          )}
          <button
            onClick={handleLogout}
            className="flex items-center gap-2 w-full px-2 py-1 text-slate-400 hover:text-red-400 transition-colors text-sm"
          >
            <LogOut className="w-4 h-4" />
            退出登录
          </button>
        </div>
      </aside>

      {/* 移动端底部导航栏 */}
      <nav className="md:hidden fixed bottom-0 left-0 right-0 z-50 bg-slate-900 border-t border-slate-800">
        <ul className="flex items-center justify-around">
          {navItems.map((item) => (
            <li key={item.href} className="flex-1">
              <Link
                href={item.href}
                className={`flex flex-col items-center gap-1 py-2 transition-colors ${
                  isActive(item.href)
                    ? "text-blue-400"
                    : "text-slate-500 hover:text-slate-300"
                }`}
              >
                <item.icon className="w-5 h-5" />
                <span className="text-[10px]">{item.label}</span>
              </Link>
            </li>
          ))}
          <li className="flex-1">
            <button
              onClick={handleLogout}
              className="flex flex-col items-center gap-1 py-2 w-full text-slate-500 hover:text-red-400 transition-colors"
            >
              <LogOut className="w-5 h-5" />
              <span className="text-[10px]">退出</span>
            </button>
          </li>
        </ul>
      </nav>
    </>
  );
}
```

- [ ] **Step 4: Verify TypeScript**

```bash
cd /home/autotrade/autotrade/frontend && npx tsc --noEmit 2>&1 | head -20
```

- [ ] **Step 5: Commit**

```bash
cd /home/autotrade/autotrade && git add frontend/src/app/layout.tsx frontend/src/components/app-shell.tsx frontend/src/components/sidebar.tsx && git commit -m "feat: add user info and logout to sidebar, extract AppShell"
```

---

## Task 20: Set SECRET_KEY and End-to-End Test

**Files:**
- Modify: `backend/.env` (create if not exists)
- Modify: `start.py` or `.env`

- [ ] **Step 1: Add SECRET_KEY to backend .env**

Check if `.env` exists:
```bash
ls /home/autotrade/autotrade/backend/.env 2>/dev/null || echo "not found"
```

If not found, create it:
```bash
echo "SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')" >> /home/autotrade/autotrade/backend/.env
echo "ENV=development" >> /home/autotrade/autotrade/backend/.env
```

If found, append:
```bash
echo "SECRET_KEY=$(python3 -c 'import secrets; print(secrets.token_hex(32))')" >> /home/autotrade/autotrade/backend/.env
echo "ENV=development" >> /home/autotrade/autotrade/backend/.env
```

- [ ] **Step 2: Start the full stack and run end-to-end smoke test**

```bash
cd /home/autotrade/autotrade && python start.py &
sleep 5

# Test register
curl -s -c /tmp/e2e_cookies.txt -X POST http://localhost:18000/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"smoketest","password":"testpass123"}' | python3 -m json.tool

# Test me (logged in)
curl -s -b /tmp/e2e_cookies.txt http://localhost:18000/api/auth/me | python3 -m json.tool

# Test dashboard (should work)
curl -s -b /tmp/e2e_cookies.txt http://localhost:18000/api/dashboard | python3 -m json.tool

# Test without cookie (should return 401)
curl -s -o /dev/null -w "%{http_code}" http://localhost:18000/api/dashboard

# Test logout
curl -s -b /tmp/e2e_cookies.txt -c /tmp/e2e_cookies.txt -X POST http://localhost:18000/api/auth/logout

# Test me after logout (should return {"user": null})
curl -s -b /tmp/e2e_cookies.txt http://localhost:18000/api/auth/me | python3 -m json.tool

kill %1 2>/dev/null; rm -f /tmp/e2e_cookies.txt
```

Expected:
- Register: `{"user": {"id": ..., "username": "smoketest", ...}}`
- Me logged in: same user
- Dashboard: returns dashboard data
- Dashboard without cookie: `401`
- Me after logout: `{"user": null}`

- [ ] **Step 3: Commit .env (only if it doesn't contain real secrets beyond SECRET_KEY)**

> ⚠️ Do NOT commit `.env` if it contains real API keys. If `.env` is already in `.gitignore`, skip this step.

```bash
grep -q ".env" /home/autotrade/autotrade/.gitignore && echo "Already in gitignore - skip commit" || echo "Add to gitignore first"
```

If not in gitignore, add it:
```bash
echo "backend/.env" >> /home/autotrade/autotrade/.gitignore
git add .gitignore && git commit -m "chore: add backend/.env to gitignore"
```

- [ ] **Step 4: Final commit**

```bash
cd /home/autotrade/autotrade && git add -A && git status
# Review what's staged, then commit
git commit -m "feat: complete multi-user account system implementation"
```

---

## Summary

After all tasks are complete, the system will have:

1. **Backend:** `User` model, `users` table, `user_id` FK on 4 models, Cookie Session auth with signed tokens, `get_current_user` dependency on all routers, scoped queries throughout, `stop_user_strategies` for safe reset
2. **Frontend:** Login/Register pages, Next.js middleware route protection, Sidebar with username + logout (desktop + mobile), `withCredentials` on all API calls, 401 auto-redirect
3. **Migration:** Existing data backfilled to auto-created `admin` user; new users get their own `SimAccount` on registration

**Admin credentials (first run):**
- Username: `admin`
- Password: value of `ADMIN_PASSWORD` env var (default: `changeme`) — **change this immediately in production**
