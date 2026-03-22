"""
飞书通知服务
"""

import os
from datetime import datetime
from typing import Optional

import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.logger import get_logger
from app.models import NotificationLog, TriggerLog, UserSetting
from app.services.bark import bark_client

logger = get_logger(__name__)

# Webhook URL
FEISHU_WEBHOOK_URL = os.getenv("FEISHU_WEBHOOK_URL", "")


class FeishuClient:
    """飞书 Webhook 客户端"""

    def __init__(self, webhook_url: Optional[str] = None):
        self.webhook_url = webhook_url or FEISHU_WEBHOOK_URL
        self.client = httpx.AsyncClient(timeout=5.0)

    async def send_trade_signal(
        self,
        strategy_name: str,
        signal_type: str,
        signal_detail: str,
        action: str,
        symbol: str,
        price: Optional[float],
        pnl: Optional[float],
    ) -> tuple[bool, Optional[str]]:
        """
        发送交易信号通知

        Returns:
            (是否成功, 错误信息)
        """
        if not self.webhook_url:
            logger.warning("Feishu webhook URL not configured")
            return False, "Webhook URL not configured"

        # 构建富文本卡片
        card = self._build_trade_card(
            strategy_name, signal_type, signal_detail, action, symbol, price, pnl
        )

        try:
            response = await self.client.post(
                self.webhook_url,
                json={"msg_type": "interactive", "card": card},
            )
            response.raise_for_status()
            result = response.json()

            if result.get("code") != 0:
                error_msg = result.get("msg", "Unknown error")
                logger.error(f"Feishu API error: {error_msg}")
                return False, error_msg

            logger.info(f"Feishu notification sent successfully")
            return True, None

        except httpx.TimeoutException:
            logger.error("Feishu webhook timeout")
            return False, "Request timeout"
        except httpx.HTTPError as e:
            logger.error(f"Feishu HTTP error: {e}")
            return False, str(e)
        except Exception as e:
            logger.error(f"Feishu unexpected error: {e}")
            return False, str(e)

    def _build_trade_card(
        self,
        strategy_name: str,
        signal_type: str,
        signal_detail: str,
        action: str,
        symbol: str,
        price: Optional[float],
        pnl: Optional[float],
    ) -> dict:
        """构建交易通知卡片"""
        # 颜色配置
        if action == "buy":
            header_color = "green"
            action_text = "买入"
        elif action == "sell":
            header_color = "red"
            action_text = "卖出"
        else:
            header_color = "grey"
            action_text = "观望"

        # 价格显示
        price_text = f"{price:.2f}" if price else "-"

        # 盈亏显示
        pnl_text = ""
        if pnl is not None:
            pnl_emoji = "📈" if pnl >= 0 else "📉"
            pnl_text = f"\\n{pnl_emoji} 盈亏: {pnl:+.2f} USDT"

        card = {
            "header": {
                "title": {
                    "tag": "plain_text",
                    "content": f"🤖 AutoTrade 策略触发: {strategy_name}",
                },
                "template": header_color,
            },
            "elements": [
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**操作:** {action_text}\\n**交易对:** {symbol}\\n**价格:** {price_text} USDT{pnl_text}",
                    },
                },
                {"tag": "hr"},
                {
                    "tag": "div",
                    "text": {
                        "tag": "lark_md",
                        "content": f"**信号详情:**\\n{signal_detail}",
                    },
                },
                {
                    "tag": "note",
                    "elements": [
                        {
                            "tag": "plain_text",
                            "text": f"触发时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                        }
                    ],
                },
            ],
        }

        return card

    async def close(self):
        """关闭客户端"""
        await self.client.aclose()


class NotificationService:
    """通知服务"""

    def __init__(self):
        self.feishu = FeishuClient()

    async def send_strategy_notification(
        self,
        trigger_log: TriggerLog,
        strategy_name: str,
        symbol: str,
        db: AsyncSession,
        user_id: Optional[int] = None,
    ) -> None:
        """
        发送策略通知（飞书 + Bark，各自独立判断是否发送）

        Args:
            trigger_log: 触发记录
            strategy_name: 策略名称
            symbol: 交易对
            db: 数据库会话
            user_id: 策略所属用户 ID（用于查询 Bark 配置）
        """
        # ── Feishu ──
        if self.feishu.webhook_url:
            success, error_msg = await self.feishu.send_trade_signal(
                strategy_name=strategy_name,
                signal_type=trigger_log.signal_type,
                signal_detail=trigger_log.signal_detail or "",
                action=trigger_log.action or "hold",
                symbol=symbol,
                price=trigger_log.price,
                pnl=trigger_log.simulated_pnl,
            )
            notification = NotificationLog(
                trigger_log_id=trigger_log.id,
                channel="feishu",
                status="sent" if success else "failed",
                error_message=error_msg,
            )
            db.add(notification)
            if success:
                logger.info(f"Feishu notification sent for trigger {trigger_log.id}")
            else:
                logger.error(f"Feishu notification failed: {error_msg}")

        # ── Bark ──
        if user_id is not None:
            bark_key, bark_enabled = await self._get_bark_config(db, user_id)
            if bark_enabled and bark_key:
                action_map = {"buy": "买入", "sell": "卖出", "hold": "观望"}
                action_text = action_map.get(trigger_log.action or "hold", trigger_log.action or "hold")
                price_text = f"{trigger_log.price:.2f}" if trigger_log.price else "-"
                title = f"AutoTrade: {strategy_name}"
                body = f"{action_text} {symbol} @ {price_text} USDT"
                if trigger_log.simulated_pnl is not None:
                    pnl_sign = "+" if trigger_log.simulated_pnl >= 0 else ""
                    body += f"  盈亏: {pnl_sign}{trigger_log.simulated_pnl:.2f}"

                success, error_msg = await bark_client.send(
                    key=bark_key,
                    title=title,
                    body=body,
                )
                bark_log = NotificationLog(
                    trigger_log_id=trigger_log.id,
                    channel="bark",
                    status="sent" if success else "failed",
                    error_message=error_msg,
                )
                db.add(bark_log)
                if success:
                    logger.info(f"Bark notification sent for trigger {trigger_log.id}")
                else:
                    logger.error(f"Bark notification failed: {error_msg}")

        await db.commit()

    async def _get_bark_config(
        self, db: AsyncSession, user_id: int
    ) -> tuple[Optional[str], bool]:
        """读取用户的 Bark 配置，返回 (bark_key, bark_enabled)"""
        result = await db.execute(
            select(UserSetting).where(
                UserSetting.user_id == user_id,
                UserSetting.key.in_(["bark_key", "bark_enabled"]),
            )
        )
        rows = {row.key: row.value for row in result.scalars().all()}
        bark_key = rows.get("bark_key") or None
        bark_enabled = rows.get("bark_enabled", "false").lower() == "true"
        return bark_key, bark_enabled

    async def close(self):
        """关闭服务"""
        await self.feishu.close()


# 全局实例
notification_service = NotificationService()


def check_webhook_configured() -> bool:
    """检查 Webhook 是否已配置"""
    return bool(FEISHU_WEBHOOK_URL)
