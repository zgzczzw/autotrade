"""
Binance 数据源
提取自 market_data.py 的 BinanceClient 逻辑
"""

import asyncio
import os
from datetime import datetime
from typing import List, Optional

import httpx

from app.engine.data_sources.base import DataSource
from app.logger import get_logger

logger = get_logger(__name__)

BINANCE_BASE_URL = "https://api.binance.com"
REQUEST_TIMEOUT = 10.0

# timeframe → Binance interval
_INTERVAL_MAP = {
    "1m": "1m", "3m": "3m", "5m": "5m", "15m": "15m", "30m": "30m",
    "1h": "1h", "2h": "2h", "4h": "4h", "6h": "6h", "8h": "8h", "12h": "12h",
    "1d": "1d", "3d": "3d", "1w": "1w",
}


class BinanceSource(DataSource):
    """Binance 数据源"""

    def __init__(self):
        https_proxy = os.getenv("HTTPS_PROXY", "")
        mounts = {}
        if https_proxy:
            mounts["https://"] = httpx.AsyncHTTPTransport(proxy=https_proxy)
            logger.info(f"BinanceSource using proxy: {https_proxy}")

        self._client = httpx.AsyncClient(
            base_url=BINANCE_BASE_URL,
            timeout=REQUEST_TIMEOUT,
            mounts=mounts,
        )

    @property
    def name(self) -> str:
        return "binance"

    async def fetch_klines(
        self,
        symbol: str,
        timeframe: str,
        since_ms: Optional[int],
        limit: int,
    ) -> List[dict]:
        interval = _INTERVAL_MAP.get(timeframe, "1h")
        params: dict = {
            "symbol": symbol,
            "interval": interval,
            "limit": min(limit, 1000),
        }
        if since_ms:
            params["startTime"] = since_ms

        try:
            response = await self._client.get("/api/v3/klines", params=params)
            response.raise_for_status()
            return self._parse(response.json())
        except httpx.HTTPError as e:
            logger.error(f"BinanceSource fetch_klines error: {e}")
            raise

    async def fetch_historical_klines(
        self,
        symbol: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
    ) -> List[dict]:
        interval = _INTERVAL_MAP.get(timeframe, "1h")
        all_klines: List[dict] = []
        current_start = int(start_date.timestamp() * 1000)
        end_ts = int(end_date.timestamp() * 1000)

        while current_start < end_ts:
            try:
                params = {
                    "symbol": symbol,
                    "interval": interval,
                    "startTime": current_start,
                    "limit": 1000,
                }
                response = await self._client.get("/api/v3/klines", params=params)
                response.raise_for_status()
                klines = self._parse(response.json())

                if not klines:
                    break

                all_klines.extend(klines)
                last_time = klines[-1]["open_time"]
                current_start = int(last_time.timestamp() * 1000) + 1
                await asyncio.sleep(0.1)

            except Exception as e:
                logger.error(f"BinanceSource fetch_historical_klines error: {e}")
                raise

        return all_klines

    def _parse(self, data: list) -> List[dict]:
        return [
            {
                "open_time": datetime.fromtimestamp(item[0] / 1000),
                "open": float(item[1]),
                "high": float(item[2]),
                "low": float(item[3]),
                "close": float(item[4]),
                "volume": float(item[5]),
            }
            for item in data
        ]

    async def close(self):
        await self._client.aclose()
