"""
Fear & Greed Index 数据服务
https://alternative.me/crypto/fear-and-greed-index/
"""

from typing import Optional

import httpx

from app.logger import get_logger

logger = get_logger(__name__)

API_URL = "https://api.alternative.me/fng/"


class FearGreedService:
    """恐惧贪婪指数服务"""

    def __init__(self):
        self._cached_value: Optional[int] = None
        self._cached_class: Optional[str] = None
        self._last_fetch_ts: float = 0

    async def get_index(self) -> Optional[dict]:
        """
        获取当前 Fear & Greed Index。

        Returns:
            {"value": 12, "classification": "Extreme Fear", "timestamp": ...}
            失败返回 None
        """
        import time

        # 缓存 10 分钟（该 API 每天更新一次，不需要频繁拉）
        now = time.time()
        if self._cached_value is not None and now - self._last_fetch_ts < 600:
            return {
                "value": self._cached_value,
                "classification": self._cached_class,
            }

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(API_URL, params={"limit": 1, "format": "json"})
                resp.raise_for_status()
                data = resp.json()

            item = data.get("data", [{}])[0]
            value = int(item.get("value", 50))
            classification = item.get("value_classification", "Neutral")

            self._cached_value = value
            self._cached_class = classification
            self._last_fetch_ts = now

            logger.info(f"Fear & Greed Index: {value} ({classification})")
            return {"value": value, "classification": classification}

        except Exception as e:
            logger.error(f"Failed to fetch Fear & Greed Index: {e}")
            # 返回缓存值（如果有）
            if self._cached_value is not None:
                return {
                    "value": self._cached_value,
                    "classification": self._cached_class,
                }
            return None


fear_greed_service = FearGreedService()
