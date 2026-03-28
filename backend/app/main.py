"""
AutoTrade FastAPI 入口
"""

import asyncio
import os
import time
from contextlib import asynccontextmanager

from itsdangerous import URLSafeTimedSerializer

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware

from app.database import init_db
from app.engine.scheduler import scheduler
from app.logger import get_access_logger, get_logger, log_startup
from app.routers import account, auth, backtests, dashboard, logs, market, notifications, settings, strategies, triggers
from app.schemas import HealthResponse

logger = get_logger(__name__)
access_logger = get_access_logger()


class AccessLogMiddleware(BaseHTTPMiddleware):
    """访问日志中间件"""

    async def dispatch(self, request: Request, call_next):
        start_time = time.time()

        # 获取客户端 IP
        client_host = request.client.host if request.client else "unknown"
        forwarded_for = request.headers.get("x-forwarded-for")
        if forwarded_for:
            client_ip = forwarded_for.split(",")[0].strip()
        else:
            client_ip = client_host

        # 处理请求
        try:
            response = await call_next(request)
            status_code = response.status_code
        except Exception as exc:
            status_code = 500
            raise exc
        finally:
            # 计算处理时间
            process_time = time.time() - start_time

            # 记录访问日志
            access_logger.info(
                f"{client_ip} - \"{request.method} {request.url.path} {request.scope.get('type', 'http')}\" "
                f"{status_code} - {process_time:.3f}s",
                extra={
                    "client_ip": client_ip,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": status_code,
                    "duration_ms": round(process_time * 1000, 2),
                }
            )

        return response


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

    # 启动策略文件同步后台任务
    from app.services.strategy_sync import strategy_sync_loop
    sync_task = asyncio.create_task(strategy_sync_loop())
    logger.info("✅ 策略文件同步服务已启动")

    logger.info("🚀 AutoTrade 启动完成")

    yield

    # 停止策略文件同步
    sync_task.cancel()
    try:
        await sync_task
    except asyncio.CancelledError:
        pass

    # 关闭调度器
    scheduler.shutdown()
    logger.info("🛑 调度器已关闭")
    logger.info("🛑 AutoTrade 关闭中...")


app = FastAPI(
    title="AutoTrade API",
    description="加密货币自动交易平台 API",
    version="0.3.0",
    lifespan=lifespan,
)

# 访问日志中间件（最先添加，最后执行）
app.add_middleware(AccessLogMiddleware)

# CORS 配置
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:13000",
        "http://localhost:3000",
        "http://127.0.0.1:13000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由 (添加 /api 前缀)
app.include_router(strategies.router, prefix="/api")
app.include_router(triggers.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(account.router, prefix="/api")
app.include_router(backtests.router, prefix="/api")
app.include_router(logs.router, prefix="/api")
app.include_router(settings.router, prefix="/api")
app.include_router(market.router, prefix="/api")
app.include_router(auth.router, prefix="/api")
app.include_router(notifications.router, prefix="/api")


@app.get("/", response_model=HealthResponse)
async def root():
    return HealthResponse(status="ok")


@app.get("/api/health", response_model=HealthResponse)
async def health():
    return HealthResponse(status="ok")
