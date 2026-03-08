"""
Mock 数据源
封装 mock_data.py 的随机 K 线生成，用于开发测试
不写缓存，每次重新生成
"""

from datetime import datetime, timedelta
from typing import List, Optional

from app.engine.data_sources.base import DataSource
from app.engine.mock_data import generate_mock_klines
from app.logger import get_logger

logger = get_logger(__name__)

# timeframe → 分钟数
_MINUTES_MAP = {
    "1m": 1, "3m": 3, "5m": 5, "15m": 15, "30m": 30,
    "1h": 60, "2h": 120, "4h": 240, "6h": 360, "8h": 480, "12h": 720,
    "1d": 1440, "3d": 4320, "1w": 10080,
}


class MockSource(DataSource):
    """Mock 数据源（随机生成，不使用缓存）"""

    @property
    def name(self) -> str:
        return "mock"

    async def fetch_klines(
        self,
        symbol: str,
        timeframe: str,
        since_ms: Optional[int],
        limit: int,
    ) -> List[dict]:
        minutes = _MINUTES_MAP.get(timeframe, 60)
        end_date = datetime.now()
        start_date = end_date - timedelta(minutes=minutes * limit)
        klines = generate_mock_klines(symbol, timeframe, start_date, end_date)
        return klines[-limit:]

    async def fetch_historical_klines(
        self,
        symbol: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
    ) -> List[dict]:
        logger.info(f"MockSource: generating mock data for {symbol} {timeframe}")
        return generate_mock_klines(symbol, timeframe, start_date, end_date)
