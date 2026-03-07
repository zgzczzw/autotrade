"""
前端日志接收路由

接收并记录前端发送的日志
"""

from datetime import datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.logger import get_logger
from app.schemas import MessageResponse

logger = get_logger(__name__)
frontend_logger = get_logger("frontend")

router = APIRouter(tags=["日志"])


class LogEntry(BaseModel):
    """前端日志条目"""

    timestamp: str
    level: str
    message: str
    data: Optional[dict] = None
    url: Optional[str] = None
    userAgent: Optional[str] = Field(None, alias="userAgent")

    class Config:
        populate_by_name = True


class LogsCreate(BaseModel):
    """批量日志请求"""

    logs: List[LogEntry]


@router.post("/logs", response_model=MessageResponse)
async def receive_logs(
    data: LogsCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    接收前端日志

    - 接收前端批量发送的日志
    - 根据级别分别记录
    """
    for entry in data.logs:
        level = entry.level.upper()
        message = f"[Frontend] {entry.message}"

        # 添加上下文信息
        context = {
            "timestamp": entry.timestamp,
            "url": entry.url,
            "user_agent": entry.userAgent,
        }
        if entry.data:
            context["data"] = entry.data

        # 根据级别记录
        if level == "DEBUG":
            frontend_logger.debug(f"{message} - {context}")
        elif level == "INFO":
            frontend_logger.info(f"{message} - {context}")
        elif level == "WARN" or level == "WARNING":
            frontend_logger.warning(f"{message} - {context}")
        elif level == "ERROR":
            frontend_logger.error(f"{message} - {context}")
        else:
            frontend_logger.info(f"{message} - {context}")

    return MessageResponse(message=f"已记录 {len(data.logs)} 条日志")


@router.get("/logs/frontend", response_model=dict)
async def get_frontend_logs(
    limit: int = 100,
    level: Optional[str] = None,
):
    """
    获取前端日志（开发调试用）

    - 返回最近的前端日志
    - 支持按级别过滤
    """
    # 注意：实际生产环境应该从日志文件读取或使用 ELK 等日志系统
    # 这里只是一个示例接口
    return {
        "message": "前端日志已写入日志文件",
        "log_file": "logs/autotrade.log",
        "filter": {"limit": limit, "level": level},
    }
