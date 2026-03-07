"""
策略调度器
使用 APScheduler AsyncIOScheduler
"""

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.engine.executor import executor
from app.logger import get_logger
from app.models import Strategy

logger = get_logger(__name__)


class StrategyScheduler:
    """策略调度器"""

    def __init__(self):
        self.scheduler = AsyncIOScheduler()
        self.running_jobs = {}  # strategy_id -> job_id

    def start(self):
        """启动调度器"""
        self.scheduler.start()
        logger.info("Strategy scheduler started")

    def shutdown(self):
        """关闭调度器"""
        self.scheduler.shutdown()
        logger.info("Strategy scheduler shutdown")

    async def start_strategy(self, strategy_id: int):
        """
        启动策略调度

        Args:
            strategy_id: 策略 ID
        """
        # 获取策略信息
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

            # 移除已存在的任务
            if strategy_id in self.running_jobs:
                self.stop_strategy(strategy_id)

            # 根据 timeframe 设置执行间隔
            interval = self._timeframe_to_seconds(strategy.timeframe)

            # 添加定时任务
            job = self.scheduler.add_job(
                func=self._execute_strategy,
                trigger=IntervalTrigger(seconds=interval),
                id=f"strategy_{strategy_id}",
                args=[strategy_id],
                replace_existing=True,
            )

            self.running_jobs[strategy_id] = job.id
            logger.info(
                f"Strategy {strategy.name} (ID: {strategy_id}) scheduled to run every {interval}s"
            )
            return True

    def stop_strategy(self, strategy_id: int):
        """
        停止策略调度

        Args:
            strategy_id: 策略 ID
        """
        job_id = self.running_jobs.get(strategy_id)
        if job_id:
            try:
                self.scheduler.remove_job(job_id)
                del self.running_jobs[strategy_id]
                logger.info(f"Strategy {strategy_id} stopped")
            except Exception as e:
                logger.error(f"Error stopping strategy {strategy_id}: {e}")

    async def _execute_strategy(self, strategy_id: int):
        """执行策略任务"""
        async with async_session() as db:
            result = await db.execute(
                select(Strategy).where(Strategy.id == strategy_id)
            )
            strategy = result.scalar_one_or_none()

            if not strategy or strategy.status != "running":
                # 策略已停止，移除任务
                self.stop_strategy(strategy_id)
                return

            try:
                await executor.execute(strategy)
            except Exception as e:
                logger.error(f"Error executing strategy {strategy_id}: {e}")

    async def restore_running_strategies(self):
        """
        应用启动时恢复所有运行中的策略
        """
        async with async_session() as db:
            result = await db.execute(
                select(Strategy).where(Strategy.status == "running")
            )
            strategies = result.scalars().all()

            for strategy in strategies:
                await self.start_strategy(strategy.id)

            logger.info(f"Restored {len(strategies)} running strategies")

    def _timeframe_to_seconds(self, timeframe: str) -> int:
        """
        将 timeframe 转换为秒数

        Args:
            timeframe: 1m, 5m, 1h, 1d

        Returns:
            秒数
        """
        mapping = {
            "1m": 60,
            "5m": 300,
            "1h": 3600,
            "1d": 86400,
        }
        return mapping.get(timeframe, 3600)


# 全局实例
scheduler = StrategyScheduler()
