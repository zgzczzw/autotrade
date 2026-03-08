"""
数据源抽象基类
"""

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Dict, List, Optional


class DataSource(ABC):
    """数据源抽象接口"""

    @property
    @abstractmethod
    def name(self) -> str:
        """数据源名称标识"""
        ...

    @abstractmethod
    async def fetch_klines(
        self,
        symbol: str,
        timeframe: str,
        since_ms: Optional[int],
        limit: int,
    ) -> List[dict]:
        """
        获取最近 K 线数据（用于策略实时执行）

        Args:
            symbol: 交易对，如 BTCUSDT
            timeframe: 时间周期，如 1h / 4h
            since_ms: 起始时间戳（毫秒），None 表示拉取最新 limit 条
            limit: 返回条数上限

        Returns:
            K 线列表，ASC 顺序，每条包含 open_time/open/high/low/close/volume
        """
        ...

    @abstractmethod
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
            K 线列表，ASC 顺序
        """
        ...

    @abstractmethod
    async def fetch_symbols(self, query: str = "") -> List[str]:
        """
        搜索交易对列表

        Args:
            query: 搜索关键字（如 "BTC"），空字符串返回热门列表

        Returns:
            交易对列表，如 ["BTCUSDT", "ETHUSDT", ...]
        """
        ...

    @abstractmethod
    async def fetch_ticker(self, symbol: str) -> Dict:
        """
        获取交易对 24h 行情摘要

        Returns:
            {symbol, price, change_pct, high_24h, low_24h, volume_24h}
        """
        ...
