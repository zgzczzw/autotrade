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

    # 设置信号处理器
    old_handler = signal.signal(signal.SIGALRM, signal_handler)
    signal.alarm(seconds)

    try:
        yield
    finally:
        signal.alarm(0)
        signal.signal(signal.SIGALRM, old_handler)


# 允许使用的内置函数白名单
ALLOWED_BUILTINS = {
    "abs",
    "all",
    "any",
    "bool",
    "dict",
    "float",
    "int",
    "len",
    "list",
    "max",
    "min",
    "range",
    "round",
    "str",
    "sum",
    "tuple",
    "zip",
    "enumerate",
    "filter",
    "map",
    "sorted",
    "reversed",
    "isinstance",
    "hasattr",
    "getattr",
    "setattr",
    "print",  # 允许打印用于调试
}

# 禁止使用的关键字
FORBIDDEN_KEYWORDS = {
    "import",
    "from",
    "open",
    "exec",
    "eval",
    "compile",
    "__import__",
    "file",
}


class CodeValidator:
    """代码验证器"""

    @staticmethod
    def validate_syntax(code: str) -> List[str]:
        """
        验证代码语法

        Returns:
            错误列表，空列表表示语法正确
        """
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
        """
        验证代码安全性

        Returns:
            错误列表，空列表表示通过安全检查
        """
        errors = []

        try:
            tree = ast.parse(code)
        except SyntaxError:
            return errors  # 语法错误已在 validate_syntax 中检查

        for node in ast.walk(tree):
            # 检查 Import
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                errors.append(f"Line {node.lineno}: Import statements are not allowed")

            # 检查函数调用
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id in FORBIDDEN_KEYWORDS:
                        errors.append(f"Line {node.lineno}: Function '{node.func.id}' is not allowed")

            # 检查属性访问（防止访问 __import__ 等）
            elif isinstance(node, ast.Attribute):
                if node.attr.startswith("__") and node.attr.endswith("__"):
                    errors.append(f"Line {node.lineno}: Access to dunder attributes is not allowed")

            # 检查 Delete
            elif isinstance(node, ast.Delete):
                errors.append(f"Line {node.lineno}: Delete statements are not allowed")

        return errors


class SandboxExecutor:
    """沙箱执行器"""

    def __init__(self, timeout: int = 10):
        self.timeout = timeout

    def execute(
        self,
        code: str,
        context: Any,
        strategy_id: int,
    ) -> Optional[str]:
        """
        在沙箱中执行代码策略

        Args:
            code: 策略代码
            context: StrategyContext 实例
            strategy_id: 策略 ID

        Returns:
            交易信号: "buy", "sell", 或 None
        """
        # 创建受限的全局命名空间
        restricted_globals = {
            "__builtins__": {
                name: __builtins__[name]
                for name in ALLOWED_BUILTINS
                if name in __builtins__
            },
        }

        # 创建局部命名空间
        local_namespace = {
            "ctx": context,
            "signal": None,
        }

        # 包装代码，捕获信号
        wrapped_code = f"""
class Strategy(BaseStrategy):
{self._indent_code(code)}

# 执行策略
strategy = Strategy(ctx)
signal = strategy.on_tick({{
    "symbol": ctx.strategy.symbol,
    "timeframe": ctx.strategy.timeframe,
    "price": ctx.current_kline["close"] if hasattr(ctx, "current_kline") else 0,
    "klines": ctx.get_klines(limit=100),
}})
"""

        try:
            with time_limit(self.timeout):
                # 编译代码
                compiled_code = compile(wrapped_code, f"<strategy_{strategy_id}>", "exec")

                # 执行代码
                exec(compiled_code, restricted_globals, local_namespace)

                # 获取信号
                signal = local_namespace.get("signal")

                if signal in ("buy", "sell"):
                    return signal
                return None

        except TimeoutException:
            logger.error(f"Strategy {strategy_id} execution timed out")
            raise
        except Exception as e:
            logger.error(f"Strategy {strategy_id} execution error: {e}")
            raise

    def _indent_code(self, code: str, indent: int = 4) -> str:
        """为代码添加缩进"""
        lines = code.strip().split("\n")
        indented_lines = [(" " * indent) + line for line in lines]
        return "\n".join(indented_lines)


# 全局实例
sandbox_executor = SandboxExecutor()


def validate_code(code: str) -> tuple[bool, List[str]]:
    """
    验证代码

    Returns:
        (是否有效, 错误列表)
    """
    validator = CodeValidator()

    # 语法检查
    syntax_errors = validator.validate_syntax(code)
    if syntax_errors:
        return False, syntax_errors

    # 安全检查
    security_errors = validator.validate_security(code)
    if security_errors:
        return False, security_errors

    return True, []
