"""
策略基类和上下文
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, List, Optional

if TYPE_CHECKING:
    from app.engine.executor import StrategyContext


class BaseStrategy(ABC):
    """
    策略基类

    所有代码策略都应该继承此类
    """

    def __init__(self, context: "StrategyContext"):
        self.ctx = context

    @abstractmethod
    def on_tick(self, data: dict) -> Optional[str]:
        """
        每个周期调用

        Args:
            data: 包含当前 K 线数据的字典
                {
                    "symbol": str,
                    "timeframe": str,
                    "price": float,
                    "klines": List[dict],
                }

        Returns:
            交易信号: "buy", "sell", 或 None
        """
        pass

    def on_start(self):
        """策略启动时调用"""
        pass

    def on_stop(self):
        """策略停止时调用"""
        pass
