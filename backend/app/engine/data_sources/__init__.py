"""
数据源工厂
"""

from app.engine.data_sources.base import DataSource
from app.engine.data_sources.binance import BinanceSource
from app.engine.data_sources.cryptocompare import CryptoCompareSource
from app.engine.data_sources.mock import MockSource

__all__ = ["DataSource", "BinanceSource", "CryptoCompareSource", "MockSource", "create_data_source"]


def create_data_source(name: str, api_key: str = "") -> DataSource:
    """
    工厂函数：按名称创建数据源实例

    Args:
        name: "binance" | "cryptocompare" | "mock"
        api_key: CryptoCompare API Key（仅 cryptocompare 时使用）

    Returns:
        DataSource 实例
    """
    if name == "cryptocompare":
        return CryptoCompareSource(api_key=api_key)
    elif name == "mock":
        return MockSource()
    else:
        return BinanceSource()
