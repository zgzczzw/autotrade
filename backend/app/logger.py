"""
日志配置模块

提供统一的日志配置，支持：
- 控制台输出
- 文件记录（按时间轮转）
- 分级存储（INFO/DEBUG/ERROR 分离）
- JSON 格式（可选，便于日志分析）
- 从环境变量配置

日志文件结构：
- logs/
  - autotrade.log          # 当前主日志（INFO及以上）
  - autotrade.error.log    # 错误日志（ERROR及以上）
  - autotrade.debug.log    # 调试日志（DEBUG及以上，仅开发）
  - autotrade.{date}.log   # 历史日志（自动轮转）
  - access.log             # HTTP 访问日志
"""

import json
import logging
import os
import sys
from datetime import datetime
from logging.handlers import RotatingFileHandler, TimedRotatingFileHandler
from pathlib import Path
from typing import Any, Dict, Optional

# 日志目录
LOG_DIR = Path(__file__).parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

# 从环境变量读取配置
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_FORMAT = os.getenv("LOG_FORMAT", "text")  # text 或 json
LOG_MAX_BYTES = int(os.getenv("LOG_MAX_BYTES", "10")) * 1024 * 1024  # 10MB
LOG_BACKUP_COUNT = int(os.getenv("LOG_BACKUP_COUNT", "10"))
LOG_CONSOLE = os.getenv("LOG_CONSOLE", "true").lower() == "true"


class JSONFormatter(logging.Formatter):
    """JSON 格式日志格式化器"""

    def format(self, record: logging.LogRecord) -> str:
        log_data: Dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
        }

        # 添加额外字段
        if hasattr(record, "extra_data"):
            log_data.update(record.extra_data)

        # 添加异常信息
        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data, ensure_ascii=False, default=str)


def get_formatter(fmt: Optional[str] = None) -> logging.Formatter:
    """获取日志格式化器"""
    if LOG_FORMAT == "json":
        return JSONFormatter()

    # 文本格式
    if fmt is None:
        fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"

    return logging.Formatter(
        fmt=fmt,
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _setup_handler(
    handler: logging.Handler,
    level: int,
    formatter: logging.Formatter,
) -> logging.Handler:
    """配置处理器"""
    handler.setLevel(level)
    handler.setFormatter(formatter)
    return handler


class LoggerManager:
    """日志管理器"""

    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        if LoggerManager._initialized:
            return

        self.log_dir = LOG_DIR
        self.loggers: Dict[str, logging.Logger] = {}

        # 创建各类处理器
        self._setup_handlers()

        # 配置根日志器
        self._setup_root_logger()

        LoggerManager._initialized = True

    def _setup_handlers(self):
        """设置日志处理器"""
        formatter = get_formatter()
        detailed_formatter = get_formatter(
            "%(asctime)s [%(levelname)s] %(name)s:%(funcName)s:%(lineno)d - %(message)s"
        )

        # 1. 控制台处理器
        self.console_handler = None
        if LOG_CONSOLE:
            self.console_handler = logging.StreamHandler(sys.stdout)
            _setup_handler(self.console_handler, logging.DEBUG, formatter)

        # 2. 主日志文件（INFO及以上，按天轮转）
        self.main_file_handler = TimedRotatingFileHandler(
            filename=self.log_dir / "autotrade.log",
            when="midnight",
            interval=1,
            backupCount=30,
            encoding="utf-8",
        )
        _setup_handler(self.main_file_handler, logging.INFO, formatter)

        # 3. 错误日志文件（ERROR及以上，按大小轮转）
        self.error_file_handler = RotatingFileHandler(
            filename=self.log_dir / "autotrade.error.log",
            maxBytes=LOG_MAX_BYTES,
            backupCount=LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
        _setup_handler(self.error_file_handler, logging.ERROR, detailed_formatter)

        # 4. 调试日志文件（DEBUG级别，仅开发环境）
        if LOG_LEVEL == "DEBUG":
            self.debug_file_handler = TimedRotatingFileHandler(
                filename=self.log_dir / "autotrade.debug.log",
                when="midnight",
                interval=1,
                backupCount=7,
                encoding="utf-8",
            )
            _setup_handler(self.debug_file_handler, logging.DEBUG, detailed_formatter)
        else:
            self.debug_file_handler = None

        # 5. 访问日志文件（单独记录 HTTP 请求）
        self.access_file_handler = TimedRotatingFileHandler(
            filename=self.log_dir / "access.log",
            when="midnight",
            interval=1,
            backupCount=30,
            encoding="utf-8",
        )
        _setup_handler(self.access_file_handler, logging.INFO, formatter)

    def _setup_root_logger(self):
        """配置根日志器"""
        root_logger = logging.getLogger()
        root_logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

        # 添加处理器
        if self.console_handler:
            root_logger.addHandler(self.console_handler)
        root_logger.addHandler(self.main_file_handler)
        root_logger.addHandler(self.error_file_handler)
        if self.debug_file_handler:
            root_logger.addHandler(self.debug_file_handler)

    def get_logger(self, name: str) -> logging.Logger:
        """获取命名日志器"""
        if name not in self.loggers:
            logger = logging.getLogger(name)
            logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

            # 确保不重复添加处理器
            if not logger.handlers:
                if self.console_handler:
                    logger.addHandler(self.console_handler)
                logger.addHandler(self.main_file_handler)
                logger.addHandler(self.error_file_handler)
                if self.debug_file_handler:
                    logger.addHandler(self.debug_file_handler)

            # 防止日志向上传播到根日志器（避免重复记录）
            logger.propagate = False

            self.loggers[name] = logger

        return self.loggers[name]

    def get_access_logger(self) -> logging.Logger:
        """获取访问日志器（用于 HTTP 请求日志）"""
        logger = logging.getLogger("autotrade.access")

        if not any(isinstance(h, TimedRotatingFileHandler) and "access" in str(h.baseFilename)
                   for h in logger.handlers):
            logger.setLevel(logging.INFO)
            logger.addHandler(self.access_file_handler)
            logger.propagate = False

        return logger

    def log_startup(self):
        """记录系统启动日志"""
        logger = self.get_logger(__name__)
        logger.info("=" * 60)
        logger.info("AutoTrade 系统启动")
        logger.info(f"日志级别: {LOG_LEVEL}")
        logger.info(f"日志格式: {LOG_FORMAT}")
        logger.info(f"日志目录: {self.log_dir}")
        logger.info("=" * 60)


# 全局日志管理器实例
_logger_manager = LoggerManager()


def get_logger(name: str) -> logging.Logger:
    """
    获取命名日志器

    用法:
        from app.logger import get_logger
        logger = get_logger(__name__)
        logger.info("消息")
        logger.error("错误", exc_info=True)
    """
    return _logger_manager.get_logger(name)


def get_access_logger() -> logging.Logger:
    """获取 HTTP 访问日志器"""
    return _logger_manager.get_access_logger()


def log_startup():
    """记录系统启动信息"""
    _logger_manager.log_startup()


def log_exception(logger: logging.Logger, msg: str, exc: Exception, extra: Optional[Dict] = None):
    """
    记录异常信息（包含堆栈）

    Args:
        logger: 日志器
        msg: 错误消息
        exc: 异常对象
        extra: 额外数据
    """
    if extra:
        logger.error(f"{msg} - {extra}", exc_info=exc)
    else:
        logger.error(msg, exc_info=exc)


# 兼容旧接口
setup_logging = log_startup
