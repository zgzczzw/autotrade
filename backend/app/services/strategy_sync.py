"""
策略文件同步服务

扫描 /home/autotrade/strategies/ 目录下的 .py 文件，
根据文件头元数据自动同步到数据库（归属 admin 用户）。
"""

import asyncio
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.logger import get_logger
from app.models import Strategy, User

logger = get_logger(__name__)

STRATEGIES_DIR = Path(os.getenv("STRATEGIES_DIR", "/var/tmp/strategies"))
SYNC_INTERVAL = 60  # seconds


def parse_metadata(code: str) -> dict:
    """从策略文件头部注释中解析元数据"""
    meta = {}
    for line in code.splitlines():
        line = line.strip()
        if not line.startswith("#"):
            # 遇到非注释行停止解析头部
            if line:
                break
            continue
        m = re.match(r"^#\s*@(\w+)\s*:\s*(.+)$", line)
        if m:
            meta[m.group(1)] = m.group(2).strip()
    return meta


def scan_strategy_files() -> list[dict]:
    """扫描目录下所有 .py 策略文件"""
    if not STRATEGIES_DIR.is_dir():
        return []

    results = []
    for filepath in STRATEGIES_DIR.glob("*.py"):
        try:
            code = filepath.read_text(encoding="utf-8")
            meta = parse_metadata(code)
            if not meta.get("name"):
                logger.warning(f"策略文件缺少 @name: {filepath.name}")
                continue
            if not meta.get("symbol"):
                logger.warning(f"策略文件缺少 @symbol: {filepath.name}")
                continue
            if not meta.get("timeframe"):
                logger.warning(f"策略文件缺少 @timeframe: {filepath.name}")
                continue

            mtime = datetime.fromtimestamp(filepath.stat().st_mtime, tz=timezone.utc)
            results.append({
                "filepath": filepath,
                "code": code,
                "meta": meta,
                "mtime": mtime,
            })
        except Exception as e:
            logger.error(f"读取策略文件失败 {filepath.name}: {e}")
    return results


async def get_admin_user_id(db: AsyncSession) -> Optional[int]:
    """获取 admin 用户 ID"""
    result = await db.execute(select(User.id).where(User.username == "admin"))
    row = result.scalar_one_or_none()
    return row


async def sync_strategies():
    """执行一次策略文件同步"""
    files = scan_strategy_files()
    if not files:
        return

    async with async_session() as db:
        admin_id = await get_admin_user_id(db)
        if admin_id is None:
            logger.error("未找到 admin 用户，跳过策略同步")
            return

        for entry in files:
            meta = entry["meta"]
            code = entry["code"]
            mtime = entry["mtime"]
            name = meta["name"]

            try:
                # 查找同名策略
                result = await db.execute(
                    select(Strategy).where(
                        Strategy.name == name,
                        Strategy.user_id == admin_id,
                    )
                )
                existing = result.scalar_one_or_none()

                if existing is None:
                    # 新增策略
                    strategy = Strategy(
                        name=name,
                        type="code",
                        code=code,
                        symbol=meta["symbol"],
                        timeframe=meta["timeframe"],
                        position_size=float(meta.get("position_size", 1000)),
                        position_size_type=meta.get("position_size_type", "fixed"),
                        stop_loss=float(meta["stop_loss"]) if meta.get("stop_loss") else None,
                        take_profit=float(meta["take_profit"]) if meta.get("take_profit") else None,
                        sell_size_pct=float(meta.get("sell_size_pct", 100)),
                        status="stopped",
                        user_id=admin_id,
                    )
                    db.add(strategy)
                    logger.info(f"新增策略: {name} ({meta['symbol']} {meta['timeframe']})")
                else:
                    # 检查是否需要更新：文件修改时间 > 数据库更新时间
                    db_updated = existing.updated_at
                    if db_updated is not None:
                        # 数据库时间可能无时区，统一比较
                        if db_updated.tzinfo is None:
                            db_updated = db_updated.replace(tzinfo=timezone.utc)
                        if mtime <= db_updated:
                            continue  # 文件未更新，跳过

                    # 更新策略代码和元数据
                    existing.code = code
                    existing.symbol = meta["symbol"]
                    existing.timeframe = meta["timeframe"]
                    existing.position_size = float(meta.get("position_size", existing.position_size))
                    existing.position_size_type = meta.get("position_size_type", existing.position_size_type)
                    if meta.get("stop_loss"):
                        existing.stop_loss = float(meta["stop_loss"])
                    if meta.get("take_profit"):
                        existing.take_profit = float(meta["take_profit"])
                    if meta.get("sell_size_pct"):
                        existing.sell_size_pct = float(meta["sell_size_pct"])
                    existing.updated_at = datetime.utcnow()
                    logger.info(f"更新策略: {name}")

            except Exception as e:
                logger.error(f"同步策略失败 {name}: {e}")

        await db.commit()


async def strategy_sync_loop():
    """后台循环：每 60 秒同步一次"""
    logger.info(f"策略文件同步服务启动，目录: {STRATEGIES_DIR}，间隔: {SYNC_INTERVAL}s")
    # 启动时立即同步一次
    try:
        await sync_strategies()
    except Exception as e:
        logger.error(f"初始策略同步失败: {e}")

    while True:
        await asyncio.sleep(SYNC_INTERVAL)
        try:
            await sync_strategies()
        except Exception as e:
            logger.error(f"策略同步失败: {e}")
