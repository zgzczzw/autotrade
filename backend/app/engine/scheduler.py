"""
策略调度器
使用 APScheduler AsyncIOScheduler

支持多时间周期策略：
- timeframe="1h"     → 注册 1 个 job，每小时触发
- timeframe="3m,15m,4h" → 注册 3 个 job，各自按节奏触发，
                           每次触发时把当前周期传给 executor
"""

from typing import Dict, List

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select

from app.database import async_session
from app.engine.executor import executor
from app.logger import get_logger
from app.models import Strategy

logger = get_logger(__name__)

# timeframe → 秒数映射（完整版）
TIMEFRAME_SECONDS: Dict[str, int] = {
    "1m":  60,
    "3m":  180,
    "5m":  300,
    "15m": 900,
    "30m": 1800,
    "1h":  3600,
    "2h":  7200,
    "4h":  14400,
    "6h":  21600,
    "8h":  28800,
    "12h": 43200,
    "1d":  86400,
    "3d":  259200,
    "1w":  604800,
}


class StrategyScheduler:
    """策略调度器"""

    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        # strategy_id → [job_id, ...]  （多时间周期可能有多个 job）
        self.running_jobs: Dict[int, List[str]] = {}

    def start(self):
        """启动调度器"""
        self.scheduler.start()
        logger.info("Strategy scheduler started")

    def shutdown(self):
        """关闭调度器"""
        self.scheduler.shutdown()
        logger.info("Strategy scheduler shutdown")

    async def start_strategy(self, strategy_id: int) -> bool:
        """
        启动策略调度。

        多时间周期策略（timeframe="3m,15m,4h"）会注册多个 job，
        各 job 分别按对应周期的间隔触发，触发时携带自己的 timeframe。

        Returns:
            bool: 是否成功启动
        """
        async with async_session() as db:
            result = await db.execute(
                select(Strategy).where(Strategy.id == strategy_id)
            )
            strategy = result.scalar_one_or_none()

            if not strategy:
                logger.error(f"Strategy {strategy_id} not found")
                return False

            if strategy.status != "running":
                logger.warning(f"Strategy {strategy_id} is not in running status")
                return False

            # 先清理旧 job（含持久化实例）
            if strategy_id in self.running_jobs:
                self.stop_strategy(strategy_id)

            # 解析时间周期列表
            timeframes = [tf.strip() for tf in strategy.timeframe.split(",") if tf.strip()]

            job_ids: List[str] = []
            for tf in timeframes:
                interval = self._timeframe_to_seconds(tf)
                job_id = f"strategy_{strategy_id}_{tf}"

                self.scheduler.add_job(
                    func=self._execute_strategy,
                    trigger=IntervalTrigger(seconds=interval),
                    id=job_id,
                    args=[strategy_id, tf],
                    replace_existing=True,
                )
                job_ids.append(job_id)
                logger.info(
                    f"Strategy '{strategy.name}' (ID:{strategy_id}) "
                    f"registered job for tf={tf} every {interval}s"
                )

            self.running_jobs[strategy_id] = job_ids
            logger.info(
                f"Strategy '{strategy.name}' (ID:{strategy_id}) "
                f"started with {len(timeframes)} timeframe(s): {strategy.timeframe}"
            )
            return True

    def stop_strategy(self, strategy_id: int):
        """
        停止策略调度，清除所有相关 job 并释放持久化实例。
        """
        job_ids = self.running_jobs.get(strategy_id, [])
        for job_id in job_ids:
            try:
                self.scheduler.remove_job(job_id)
            except Exception as e:
                logger.warning(f"Error removing job {job_id}: {e}")

        if strategy_id in self.running_jobs:
            del self.running_jobs[strategy_id]

        # 释放代码策略的持久化实例，触发 on_stop()
        executor.release_instance(strategy_id)

        logger.info(f"Strategy {strategy_id} stopped, all jobs removed")

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

    async def _execute_strategy(self, strategy_id: int, timeframe: str):
        """执行策略任务（由调度器按时间周期触发）"""
        async with async_session() as db:
            result = await db.execute(
                select(Strategy).where(Strategy.id == strategy_id)
            )
            strategy = result.scalar_one_or_none()

            if not strategy or strategy.status != "running":
                self.stop_strategy(strategy_id)
                return

            try:
                await executor.execute(strategy, timeframe=timeframe)
            except Exception as e:
                logger.error(
                    f"Error executing strategy {strategy_id} (tf={timeframe}): {e}"
                )

    async def restore_running_strategies(self):
        """应用启动时恢复所有运行中的策略"""
        async with async_session() as db:
            result = await db.execute(
                select(Strategy).where(Strategy.status == "running")
            )
            strategies = result.scalars().all()

            for strategy in strategies:
                await self.start_strategy(strategy.id)

            logger.info(f"Restored {len(strategies)} running strategies")

    def _timeframe_to_seconds(self, timeframe: str) -> int:
        """将 timeframe 转换为秒数，未知周期默认 1 小时"""
        return TIMEFRAME_SECONDS.get(timeframe.strip(), 3600)


# 全局实例
scheduler = StrategyScheduler()
