"""
市场数据模块
- Binance API 客户端
- K 线数据本地缓存
- 模拟数据支持（用于测试）
"""

import asyncio
import os
from datetime import datetime, timedelta
from typing import List, Optional

import httpx
from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.engine.mock_data import generate_mock_klines
from app.logger import get_logger
from app.models import KlineData

logger = get_logger(__name__)

# Binance API 基础配置
BINANCE_BASE_URL = "https://api.binance.com"
REQUEST_TIMEOUT = 10.0

# 代理配置
HTTPS_PROXY = os.getenv("HTTPS_PROXY", "")

# 是否使用模拟数据
USE_MOCK_DATA = os.getenv("USE_MOCK_DATA", "false").lower() == "true"

if USE_MOCK_DATA:
    logger.warning("=" * 60)
    logger.warning("⚠️  使用模拟数据模式（MOCK DATA MODE）")
    logger.warning("   所有价格数据为随机生成，仅用于测试")
    logger.warning("=" * 60)


class BinanceClient:
    """Binance API 客户端"""

    def __init__(self):
        # 配置代理
        mounts = {}
        if HTTPS_PROXY:
            mounts["https://"] = httpx.AsyncHTTPTransport(proxy=HTTPS_PROXY)
            logger.info(f"Using proxy: {HTTPS_PROXY}")
        
        self.client = httpx.AsyncClient(
            base_url=BINANCE_BASE_URL,
            timeout=REQUEST_TIMEOUT,
            mounts=mounts,
        )

    async def fetch_klines(
        self,
        symbol: str,
        interval: str,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
        limit: int = 1000,
    ) -> List[dict]:
        """
        获取 K 线数据

        Args:
            symbol: 交易对，如 BTCUSDT
            interval: 时间周期，如 1m, 5m, 1h, 1d
            start_time: 开始时间戳（毫秒）
            end_time: 结束时间戳（毫秒）
            limit: 返回条数，最大 1000

        Returns:
            K 线数据列表
        """
        params = {
            "symbol": symbol,
            "interval": interval,
            "limit": min(limit, 1000),
        }
        if start_time:
            params["startTime"] = start_time
        if end_time:
            params["endTime"] = end_time

        try:
            response = await self.client.get("/api/v3/klines", params=params)
            response.raise_for_status()
            data = response.json()

            # 解析 K 线数据
            klines = []
            for item in data:
                klines.append({
                    "open_time": datetime.fromtimestamp(item[0] / 1000),
                    "open": float(item[1]),
                    "high": float(item[2]),
                    "low": float(item[3]),
                    "close": float(item[4]),
                    "volume": float(item[5]),
                })

            return klines

        except httpx.HTTPError as e:
            logger.error(f"Failed to fetch klines from Binance: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error fetching klines: {e}")
            raise

    async def close(self):
        """关闭客户端"""
        await self.client.aclose()


class MarketDataService:
    """市场数据服务"""

    def __init__(self):
        self.binance = BinanceClient()

    async def get_klines(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 100,
        db: Optional[AsyncSession] = None,
    ) -> List[dict]:
        """
        获取 K 线数据（优先从缓存读取）

        Args:
            symbol: 交易对
            timeframe: 时间周期
            limit: 需要返回的条数
            db: 数据库会话（可选）

        Returns:
            K 线数据列表
        """
        # 转换 timeframe 到 Binance interval
        interval = self._timeframe_to_interval(timeframe)

        # 尝试从缓存读取
        cached_data = await self._get_cached_klines(symbol, timeframe, limit, db)

        if len(cached_data) >= limit:
            return cached_data[:limit]

        # 缓存不足，从 Binance 获取
        try:
            # 计算需要获取的起始时间
            if cached_data:
                # 从最后一条缓存数据之后开始获取
                last_time = cached_data[0]["open_time"]
                start_time = int(last_time.timestamp() * 1000)
            else:
                # 获取最近 limit 条
                start_time = None

            new_klines = await self.binance.fetch_klines(
                symbol=symbol,
                interval=interval,
                start_time=start_time,
                limit=limit,
            )

            # 保存到缓存
            await self._save_klines(symbol, timeframe, new_klines, db)

            # 合并缓存和新数据
            all_data = new_klines + cached_data
            return all_data[:limit]

        except Exception as e:
            logger.warning(f"Failed to fetch from Binance, using cache: {e}")
            # 降级：使用缓存数据
            return cached_data[:limit] if cached_data else []

    async def fetch_historical_klines(
        self,
        symbol: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
    ) -> List[dict]:
        """
        批量获取历史 K 线数据（用于回测）

        Args:
            symbol: 交易对
            timeframe: 时间周期
            start_date: 开始日期
            end_date: 结束日期

        Returns:
            K 线数据列表
        """
        # 如果使用模拟数据模式
        if USE_MOCK_DATA:
            logger.info(f"Using mock data for {symbol} {timeframe}")
            klines = generate_mock_klines(symbol, timeframe, start_date, end_date)
            await self._save_klines(symbol, timeframe, klines)
            return klines

        interval = self._timeframe_to_interval(timeframe)
        all_klines = []

        current_start = int(start_date.timestamp() * 1000)
        end_timestamp = int(end_date.timestamp() * 1000)

        while current_start < end_timestamp:
            try:
                klines = await self.binance.fetch_klines(
                    symbol=symbol,
                    interval=interval,
                    start_time=current_start,
                    limit=1000,
                )

                if not klines:
                    break

                all_klines.extend(klines)

                # 更新下一次请求的起始时间
                last_time = klines[-1]["open_time"]
                current_start = int(last_time.timestamp() * 1000) + 1

                # 避免触发限流
                await asyncio.sleep(0.1)

            except Exception as e:
                logger.error(f"Error fetching historical klines: {e}")
                # 如果获取失败，使用模拟数据作为备选
                logger.warning(f"Falling back to mock data for {symbol}")
                klines = generate_mock_klines(symbol, timeframe, start_date, end_date)
                await self._save_klines(symbol, timeframe, klines)
                return klines

        # 保存到缓存
        await self._save_klines(symbol, timeframe, all_klines)

        return all_klines

    async def _get_cached_klines(
        self,
        symbol: str,
        timeframe: str,
        limit: int,
        db: Optional[AsyncSession] = None,
    ) -> List[dict]:
        """从数据库获取缓存的 K 线数据"""
        async with async_session() as session:
            result = await session.execute(
                select(KlineData)
                .where(
                    KlineData.symbol == symbol,
                    KlineData.timeframe == timeframe,
                )
                .order_by(KlineData.open_time.desc())
                .limit(limit)
            )
            rows = result.scalars().all()

            return [
                {
                    "open_time": row.open_time,
                    "open": row.open,
                    "high": row.high,
                    "low": row.low,
                    "close": row.close,
                    "volume": row.volume,
                }
                for row in rows
            ]

    async def _save_klines(
        self,
        symbol: str,
        timeframe: str,
        klines: List[dict],
        db: Optional[AsyncSession] = None,
    ):
        """保存 K 线数据到缓存"""
        if not klines:
            return

        async with async_session() as session:
            for k in klines:
                # 使用 INSERT OR REPLACE 避免重复
                stmt = insert(KlineData).values(
                    symbol=symbol,
                    timeframe=timeframe,
                    open_time=k["open_time"],
                    open=k["open"],
                    high=k["high"],
                    low=k["low"],
                    close=k["close"],
                    volume=k["volume"],
                )
                stmt = stmt.on_conflict_do_nothing(
                    index_elements=["symbol", "timeframe", "open_time"]
                )
                await session.execute(stmt)

            await session.commit()

    def _timeframe_to_interval(self, timeframe: str) -> str:
        """将内部 timeframe 转换为 Binance interval"""
        mapping = {
            "1m": "1m",
            "5m": "5m",
            "1h": "1h",
            "1d": "1d",
        }
        return mapping.get(timeframe, "1h")

    async def close(self):
        """关闭服务"""
        await self.binance.close()


# 全局实例
market_data_service = MarketDataService()
