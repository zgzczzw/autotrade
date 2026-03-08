"""
CryptoCompare 数据源
- 支持所有时间周期（通过聚合 minute/hour/day 原始数据）
- 单次最多拉 2000 根原始数据，超出自动分页
"""

import asyncio
from datetime import datetime
from typing import List, Optional, Tuple

import httpx

from app.engine.data_sources.base import DataSource
from app.logger import get_logger

logger = get_logger(__name__)

CC_BASE_URL = "https://min-api.cryptocompare.com"
REQUEST_TIMEOUT = 15.0

# timeframe → (endpoint, multiplier)
# multiplier 表示每根聚合 K 线需要多少根原始数据
_TF_MAP: dict = {
    "1m":  ("histominute", 1),
    "3m":  ("histominute", 3),
    "5m":  ("histominute", 5),
    "15m": ("histominute", 15),
    "30m": ("histominute", 30),
    "1h":  ("histohour",   1),
    "2h":  ("histohour",   2),
    "4h":  ("histohour",   4),
    "6h":  ("histohour",   6),
    "8h":  ("histohour",   8),
    "12h": ("histohour",  12),
    "1d":  ("histoday",    1),
    "3d":  ("histoday",    3),
    "1w":  ("histoday",    7),
}

# endpoint → 每根原始 K 线的秒数
_BASE_SECONDS: dict = {
    "histominute": 60,
    "histohour":   3600,
    "histoday":    86400,
}

# 已知计价币（按长度降序，避免 USDT 被误判为 USD）
_QUOTE_CURRENCIES = ["USDT", "BUSD", "USDC", "TUSD", "FDUSD", "BTC", "ETH", "BNB"]


def _split_symbol(symbol: str) -> Tuple[str, str]:
    """将 BTCUSDT 拆分为 (BTC, USDT)"""
    for quote in _QUOTE_CURRENCIES:
        if symbol.upper().endswith(quote):
            base = symbol[: -len(quote)]
            return base.upper(), quote
    # fallback: 后 4 位为计价币
    return symbol[:-4].upper(), symbol[-4:].upper()


class CryptoCompareSource(DataSource):
    """CryptoCompare 数据源（支持全时间周期聚合）"""

    def __init__(self, api_key: str = ""):
        self.api_key = api_key
        self._client = httpx.AsyncClient(
            base_url=CC_BASE_URL,
            timeout=REQUEST_TIMEOUT,
        )

    @property
    def name(self) -> str:
        return "cryptocompare"

    async def fetch_klines(
        self,
        symbol: str,
        timeframe: str,
        since_ms: Optional[int],
        limit: int,
    ) -> List[dict]:
        endpoint, multiplier = _TF_MAP.get(timeframe, ("histohour", 1))
        fsym, tsym = _split_symbol(symbol)

        if since_ms is None:
            # 拉取最新 limit 根聚合 K 线
            raw_limit = min(limit * multiplier, 2000)
            raw_bars = await self._fetch_raw(endpoint, fsym, tsym, raw_limit, to_ts=None)
        else:
            # 拉取 since_ms 之后的数据
            since_s = since_ms // 1000
            now_s = int(datetime.now().timestamp())
            base_s = _BASE_SECONDS[endpoint]
            raw_needed = ((now_s - since_s) // base_s + 1) + multiplier * 2
            raw_limit = min(raw_needed, 2000)
            raw_bars = await self._fetch_raw(endpoint, fsym, tsym, raw_limit, to_ts=None)
            raw_bars = [b for b in raw_bars if b["time"] * 1000 >= since_ms]

        aggregated = self._aggregate(raw_bars, multiplier)
        return aggregated[-limit:]

    async def fetch_historical_klines(
        self,
        symbol: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
    ) -> List[dict]:
        endpoint, multiplier = _TF_MAP.get(timeframe, ("histohour", 1))
        fsym, tsym = _split_symbol(symbol)

        all_raw: List[dict] = []
        to_ts = int(end_date.timestamp())
        start_ts = int(start_date.timestamp())

        while True:
            batch = await self._fetch_raw(endpoint, fsym, tsym, 2000, to_ts=to_ts)
            if not batch:
                break

            all_raw = batch + all_raw  # 旧数据在前（ASC）
            oldest_time = batch[0]["time"]

            if oldest_time <= start_ts:
                break

            to_ts = oldest_time - 1
            await asyncio.sleep(0.1)

        # 过滤到目标范围
        end_ts = int(end_date.timestamp())
        filtered = [b for b in all_raw if start_ts <= b["time"] <= end_ts]
        return self._aggregate(filtered, multiplier)

    async def test_connection(self) -> bool:
        """测试 API Key 是否有效"""
        try:
            raw = await self._fetch_raw("histohour", "BTC", "USDT", 1, to_ts=None)
            return len(raw) > 0
        except Exception as e:
            logger.warning(f"CryptoCompare test_connection failed: {e}")
            return False

    async def _fetch_raw(
        self,
        endpoint: str,
        fsym: str,
        tsym: str,
        limit: int,
        to_ts: Optional[int],
    ) -> List[dict]:
        params: dict = {
            "fsym": fsym,
            "tsym": tsym,
            "limit": min(limit, 2000),
        }
        if self.api_key:
            params["api_key"] = self.api_key
        if to_ts is not None:
            params["toTs"] = to_ts

        try:
            response = await self._client.get(f"/data/v2/{endpoint}", params=params)
            response.raise_for_status()
            data = response.json()

            if data.get("Response") != "Success":
                raise ValueError(f"CryptoCompare API error: {data.get('Message', 'Unknown error')}")

            return data["Data"]["Data"]

        except httpx.HTTPError as e:
            logger.error(f"CryptoCompare HTTP error [{endpoint}]: {e}")
            raise
        except Exception as e:
            logger.error(f"CryptoCompare error [{endpoint}]: {e}")
            raise

    def _aggregate(self, raw_bars: List[dict], multiplier: int) -> List[dict]:
        """将原始 K 线聚合为目标时间周期"""
        if not raw_bars:
            return []

        if multiplier == 1:
            return [self._to_kline(b) for b in raw_bars]

        result = []
        for i in range(0, len(raw_bars), multiplier):
            group = raw_bars[i: i + multiplier]
            if len(group) < multiplier:
                break  # 末尾不完整的组丢弃
            result.append({
                "open_time": datetime.fromtimestamp(group[0]["time"]),
                "open":   group[0]["open"],
                "high":   max(b["high"] for b in group),
                "low":    min(b["low"] for b in group),
                "close":  group[-1]["close"],
                "volume": round(sum(b.get("volumefrom", 0) for b in group), 4),
            })
        return result

    def _to_kline(self, bar: dict) -> dict:
        return {
            "open_time": datetime.fromtimestamp(bar["time"]),
            "open":   bar["open"],
            "high":   bar["high"],
            "low":    bar["low"],
            "close":  bar["close"],
            "volume": round(bar.get("volumefrom", 0), 4),
        }

    async def close(self):
        await self._client.aclose()
