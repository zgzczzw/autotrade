"""
Bark 推送通知服务
https://bark.day.app
"""

from typing import Optional
from urllib.parse import quote

import httpx

from app.logger import get_logger

logger = get_logger(__name__)


class BarkClient:
    """Bark 推送客户端"""

    BASE_URL = "https://api.day.app"

    async def send(
        self,
        key: str,
        title: str,
        body: str,
        group: str = "AutoTrade",
        url: Optional[str] = None,
    ) -> tuple[bool, Optional[str]]:
        """
        发送 Bark 推送通知

        URL: https://api.day.app/{key}/{title}/{body}?group={group}&url={url}

        Returns:
            (success, error_message)
        """
        if not key:
            return False, "Bark key is empty"

        api_url = f"{self.BASE_URL}/{quote(key)}/{quote(title)}/{quote(body)}"
        params = {"group": group}
        if url:
            params["url"] = url

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(api_url, params=params)
                response.raise_for_status()
                result = response.json()

                if result.get("code") != 200:
                    error_msg = result.get("message", "Unknown error")
                    logger.error(f"Bark API error: {error_msg}")
                    return False, error_msg

                logger.info("Bark notification sent successfully")
                return True, None

        except httpx.TimeoutException:
            logger.error("Bark request timeout")
            return False, "Request timeout"
        except httpx.HTTPError as e:
            logger.error(f"Bark HTTP error: {e}")
            return False, str(e)
        except Exception as e:
            logger.error(f"Bark unexpected error: {e}")
            return False, str(e)


bark_client = BarkClient()
