"""
代码策略沙箱执行环境
使用受限 exec 执行用户代码
"""

import ast
import signal
import sys
from contextlib import contextmanager
from typing import Any, Dict, List, Optional

from app.engine.base_strategy import BaseStrategy
from app.engine.indicators import (
    calculate_bollinger_bands,
    calculate_ema,
    calculate_macd,
    calculate_rsi,
    calculate_sma,
    check_bollinger_touch,
    check_kdj_signal,
    check_ma_cross,
    check_macd_signal,
    check_volume_spike,
)
from app.logger import get_logger

logger = get_logger(__name__)


class TimeoutException(Exception):
    """执行超时异常"""
    pass


@contextmanager
def time_limit(seconds: int):
    """执行时间限制上下文管理器"""
    def signal_handler(signum, frame):
        raise TimeoutException(f"Execution timed out after {seconds} seconds")

    old_handler = signal.signal(signal.SIGALRM, signal_handler)
    signal.alarm(seconds)

    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)


# 允许使用的内置函数白名单
ALLOWED_BUILTINS = {
    "abs", "all", "any", "bool", "dict", "float", "int", "len", "list",
    "max", "min", "range", "round", "str", "sum", "tuple", "zip",
    "enumerate", "filter", "map", "sorted", "reversed",
    "isinstance", "hasattr", "getattr", "setattr", "print",
    # class 定义需要 __build_class__，property/staticmethod/super 也常用
    "__build_class__", "super", "property", "staticmethod", "classmethod",
    "type", "object", "NotImplemented", "None", "True", "False",
}

# 禁止使用的关键字
FORBIDDEN_KEYWORDS = {
    "import", "from", "open", "exec", "eval", "compile", "__import__", "file",
}


class CodeValidator:
    """代码验证器"""

    @staticmethod
    def validate_syntax(code: str) -> List[str]:
        errors = []
        try:
            ast.parse(code)
        except SyntaxError as e:
            errors.append(f"SyntaxError at line {e.lineno}: {e.msg}")
        except Exception as e:
            errors.append(f"Parse error: {str(e)}")
        return errors

    @staticmethod
    def validate_security(code: str) -> List[str]:
        errors = []
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return errors

        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                errors.append(f"Line {node.lineno}: Import statements are not allowed")
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id in FORBIDDEN_KEYWORDS:
                        errors.append(f"Line {node.lineno}: Function '{node.func.id}' is not allowed")
            elif isinstance(node, ast.Attribute):
                if node.attr.startswith("__") and node.attr.endswith("__"):
                    errors.append(f"Line {node.lineno}: Access to dunder attributes is not allowed")
            elif isinstance(node, ast.Delete):
                errors.append(f"Line {node.lineno}: Delete statements are not allowed")

        return errors


class SandboxExecutor:
    """沙箱执行器"""

    def __init__(self, timeout: int = 10):
        self.timeout = timeout

    def _build_restricted_globals(self) -> dict:
        """构建受限的全局命名空间（注入基类和常用指标函数）"""
        builtins_src = __builtins__ if isinstance(__builtins__, dict) else vars(__builtins__)
        return {
            "__builtins__": {
                name: builtins_src[name]
                for name in ALLOWED_BUILTINS
                if name in builtins_src
            },
            # class 定义需要 __name__ 作为 __module__ 的来源
            "__name__": "<strategy>",
            # 策略基类
            "BaseStrategy": BaseStrategy,
            # 类型注解（策略代码中常用，不能 import 但需要用）
            "List": List,
            "Dict": Dict,
            "Optional": Optional,
            # 技术指标函数
            "calculate_bollinger_bands": calculate_bollinger_bands,
            "calculate_rsi": calculate_rsi,
            "calculate_sma": calculate_sma,
            "calculate_ema": calculate_ema,
            "calculate_macd": calculate_macd,
            "check_bollinger_touch": check_bollinger_touch,
            "check_ma_cross": check_ma_cross,
            "check_macd_signal": check_macd_signal,
            "check_kdj_signal": check_kdj_signal,
            "check_volume_spike": check_volume_spike,
        }

    def create_instance(
        self,
        code: str,
        context: Any,
        strategy_id: int,
    ) -> Any:
        """
        编译代码策略并创建持久化实例，调用 on_start() 初始化。

        用户代码应包含完整的类定义（继承 BaseStrategy），例如：
            class MyStrategy(BaseStrategy):
                def on_tick(self, data): ...

        Returns:
            Strategy 实例（持有 context 引用）
        """
        restricted_globals = self._build_restricted_globals()
        local_namespace: dict = {}

        try:
            with time_limit(self.timeout):
                compiled = compile(code, f"<strategy_{strategy_id}>", "exec")
                exec(compiled, restricted_globals, local_namespace)

                # 找到用户定义的 BaseStrategy 子类
                StrategyClass = None
                for obj in local_namespace.values():
                    if (
                        isinstance(obj, type)
                        and issubclass(obj, BaseStrategy)
                        and obj is not BaseStrategy
                    ):
                        StrategyClass = obj
                        break

                if StrategyClass is None:
                    raise ValueError(
                        "No BaseStrategy subclass found in strategy code. "
                        "Please define a class that inherits from BaseStrategy."
                    )

                instance = StrategyClass(context)

            # on_start 在超时保护外单独调用，失败只 warning 不阻断策略启动
            try:
                instance.on_start()
            except Exception as e:
                logger.warning(
                    f"Strategy {strategy_id} on_start() failed (ignored): {e}"
                )

            logger.info(
                f"Strategy {strategy_id} instance created: {StrategyClass.__name__}"
            )
            return instance

        except TimeoutException:
            logger.error(f"Strategy {strategy_id} create_instance timed out")
            raise
        except Exception as e:
            logger.error(f"Strategy {strategy_id} create_instance error: {e}")
            raise

    def call_on_tick(
        self,
        instance: Any,
        data: dict,
    ) -> Optional[str]:
        """
        在超时保护下调用策略实例的 on_tick。

        Args:
            instance: 由 create_instance 创建的持久化策略实例
            data: 传给 on_tick 的数据字典

        Returns:
            "buy", "sell", 或 None
        """
        try:
            with time_limit(self.timeout):
                signal = instance.on_tick(data)
                if signal in ("buy", "sell"):
                    return signal
                return None
        except TimeoutException:
            logger.error(f"Strategy on_tick timed out")
            raise
        except Exception as e:
            logger.error(f"Strategy on_tick error: {e}")
            raise

    def execute(
        self,
        code: str,
        context: Any,
        strategy_id: int,
        klines: Optional[List[dict]] = None,
        current_kline: Optional[dict] = None,
    ) -> Optional[str]:
        """
        在沙箱中一次性执行代码策略（主要供回测使用）。
        每次调用都创建新实例，不持久化状态。

        Args:
            code: 策略代码
            context: StrategyContext / BacktestContext 实例
            strategy_id: 策略 ID
            klines: 预取的 K 线数据
            current_kline: 当前 K 线

        Returns:
            "buy", "sell", 或 None
        """
        # 兼容 BacktestContext（同步 get_klines）
        if klines is None:
            get_klines_fn = getattr(context, "get_klines", None)
            if callable(get_klines_fn):
                try:
                    klines = get_klines_fn(limit=100)
                except Exception:
                    klines = []
        if current_kline is None:
            current_kline = getattr(context, "current_kline", None)

        try:
            instance = self.create_instance(code, context, strategy_id)
        except Exception:
            return None

        data = {
            "symbol": context.strategy.symbol,
            "timeframe": context.strategy.timeframe,
            "price": current_kline["close"] if current_kline else 0,
            "klines": klines or [],
        }

        try:
            return self.call_on_tick(instance, data)
        except Exception:
            return None


# 全局实例
sandbox_executor = SandboxExecutor()


def validate_code(code: str) -> tuple[bool, List[str]]:
    """
    验证代码

    Returns:
        (是否有效, 错误列表)
    """
    validator = CodeValidator()

    syntax_errors = validator.validate_syntax(code)
    if syntax_errors:
        return False, syntax_errors

    security_errors = validator.validate_security(code)
    if security_errors:
        return False, security_errors

    return True, []
