"""
市场数据服务
- 统一数据源接口（Binance / CryptoCompare / Mock）
- K 线本地缓存（KlineData 表）
- Mock 数据源跳过缓存
"""

from datetime import datetime
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import async_session
from app.engine.data_sources import DataSource, BinanceSource, create_data_source
from app.logger import get_logger
from app.models import KlineData

logger = get_logger(__name__)


class MarketDataService:
    """市场数据服务（数据源可全局切换）"""

    def __init__(self):
        self._source: DataSource = BinanceSource()

    @property
    def source_name(self) -> str:
        return self._source.name

    def set_source(self, name: str, api_key: str = "") -> None:
        """切换数据源（立即生效，无需重启）"""
        self._source = create_data_source(name, api_key)
        logger.info(f"Data source switched to: {name}")

    async def init_from_db(self) -> None:
        """应用启动时从 DB 读取数据源配置并初始化"""
        async with async_session() as db:
            from app.models import SystemSetting
            result = await db.execute(
                select(SystemSetting).where(SystemSetting.key == "data_source")
            )
            ds_row = result.scalar_one_or_none()
            if not ds_row:
                return

            data_source = ds_row.value or "binance"
            api_key = ""

            if data_source == "cryptocompare":
                key_result = await db.execute(
                    select(SystemSetting).where(SystemSetting.key == "cryptocompare_api_key")
                )
                key_row = key_result.scalar_one_or_none()
                api_key = key_row.value if key_row and key_row.value else ""

            self.set_source(data_source, api_key)

    async def get_klines(
        self,
        symbol: str,
        timeframe: str,
        limit: int = 100,
        db: Optional[AsyncSession] = None,
    ) -> List[dict]:
        """
        获取 K 线数据（优先从缓存读取）

        Mock 数据源不使用缓存，直接生成并返回。
        """
        # 多时间周期策略取主周期
        primary_tf = timeframe.split(",")[0].strip()

        # Mock 数据源：跳过缓存，直接生成
        if self._source.name == "mock":
            return await self._source.fetch_klines(symbol, primary_tf, None, limit)

        # 尝试从缓存读取
        cached_data = await self._get_cached_klines(symbol, primary_tf, limit)

        if len(cached_data) >= limit:
            return cached_data[-limit:]

        # 缓存不足，从数据源拉取增量数据
        try:
            since_ms: Optional[int] = None
            if cached_data:
                last_time = cached_data[-1]["open_time"]
                since_ms = int(last_time.timestamp() * 1000) + 1

            new_klines = await self._source.fetch_klines(symbol, primary_tf, since_ms, limit)
            await self._save_klines(symbol, primary_tf, new_klines)

            all_data = cached_data + new_klines
            return all_data[-limit:]

        except Exception as e:
            logger.warning(
                f"Failed to fetch from {self._source.name}, using cache: {e}"
            )
            return cached_data[-limit:] if cached_data else []

    async def fetch_historical_klines(
        self,
        symbol: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
    ) -> List[dict]:
        """
        批量获取历史 K 线数据（用于回测）
        结果写入缓存（Mock 除外）
        """
        klines = await self._source.fetch_historical_klines(
            symbol, timeframe, start_date, end_date
        )

        if self._source.name != "mock" and klines:
            await self._save_klines(symbol, timeframe, klines)

        return klines

    async def _get_cached_klines(
        self,
        symbol: str,
        timeframe: str,
        limit: int,
    ) -> List[dict]:
        """从 KlineData 表读取缓存（ASC 顺序，最旧在前）"""
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
                "open":   row.open,
                "high":   row.high,
                "low":    row.low,
                "close":  row.close,
                "volume": row.volume,
            }
            for row in reversed(rows)  # DESC→ASC
        ]

    async def _save_klines(
        self,
        symbol: str,
        timeframe: str,
        klines: List[dict],
    ):
        """将 K 线数据写入缓存（upsert，忽略重复）"""
        if not klines:
            return

        async with async_session() as session:
            for k in klines:
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

    async def get_symbols(self, query: str = "") -> list:
        """搜索交易对列表"""
        return await self._source.fetch_symbols(query)

    async def get_ticker(self, symbol: str) -> dict:
        """获取 24h 行情摘要"""
        return await self._source.fetch_ticker(symbol)

    async def close(self):
        """关闭底层 HTTP 客户端（如有）"""
        if hasattr(self._source, "close"):
            await self._source.close()


# 全局实例
market_data_service = MarketDataService()
