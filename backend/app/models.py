"""
SQLAlchemy 数据模型
"""

from datetime import datetime

from sqlalchemy import (
    JSON, Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text,
    UniqueConstraint, func
)
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    """用户模型"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), nullable=False, unique=True)
    password_hash = Column(String, nullable=False)
    is_admin = Column(Boolean, nullable=False, default=False)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    # 关系
    strategies = relationship("Strategy", back_populates="user", cascade="all, delete-orphan")
    positions = relationship("Position", back_populates="user", cascade="all, delete-orphan")
    sim_accounts = relationship("SimAccount", back_populates="user", cascade="all, delete-orphan")
    backtest_results = relationship("BacktestResult", back_populates="user", cascade="all, delete-orphan")
    settings = relationship("UserSetting", back_populates="user", cascade="all, delete-orphan")


class UserSetting(Base):
    """用户级设置（键值对）"""
    __tablename__ = "user_settings"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False)
    key        = Column(String(50), nullable=False)
    value      = Column(Text, nullable=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (UniqueConstraint("user_id", "key"),)

    user = relationship("User", back_populates="settings")


class Strategy(Base):
    """策略模型"""
    __tablename__ = "strategies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # nullable during migration
    name = Column(String, nullable=False)
    type = Column(String, nullable=False)  # visual / code
    config_json = Column(Text, nullable=True)
    code = Column(Text, nullable=True)
    symbol = Column(String, nullable=False)
    timeframe = Column(String, nullable=False)
    position_size = Column(Float, nullable=False, default=100.0)
    position_size_type = Column(String, nullable=False, default="fixed")
    stop_loss = Column(Float, nullable=True)
    take_profit = Column(Float, nullable=True)
    sell_size_pct = Column(Float, nullable=False, default=100.0)
    notify_enabled = Column(Boolean, nullable=False, default=True)
    status = Column(String, nullable=False, default="stopped")
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    # 关系
    user = relationship("User", back_populates="strategies")
    trigger_logs = relationship("TriggerLog", back_populates="strategy", cascade="all, delete-orphan")
    positions = relationship("Position", back_populates="strategy", cascade="all, delete-orphan")
    backtest_results = relationship("BacktestResult", back_populates="strategy", cascade="all, delete-orphan")


class TriggerLog(Base):
    """触发记录模型"""
    __tablename__ = "trigger_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    strategy_id = Column(Integer, ForeignKey("strategies.id"), nullable=False)
    triggered_at = Column(DateTime, nullable=False, server_default=func.now())
    signal_type = Column(String, nullable=False)
    signal_detail = Column(Text, nullable=True)
    action = Column(String, nullable=True)
    price = Column(Float, nullable=True)
    quantity = Column(Float, nullable=True)
    simulated_pnl = Column(Float, nullable=True)

    # 关系
    strategy = relationship("Strategy", back_populates="trigger_logs")
    notification_logs = relationship("NotificationLog", back_populates="trigger_log")


class Position(Base):
    """模拟持仓模型"""
    __tablename__ = "positions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # nullable during migration
    strategy_id = Column(Integer, ForeignKey("strategies.id"), nullable=False)
    symbol = Column(String, nullable=False)
    side = Column(String, nullable=False)
    entry_price = Column(Float, nullable=False)
    quantity = Column(Float, nullable=False)
    current_price = Column(Float, nullable=True)
    pnl = Column(Float, nullable=True)
    opened_at = Column(DateTime, nullable=False, server_default=func.now())
    closed_at = Column(DateTime, nullable=True)

    # 关系
    user = relationship("User", back_populates="positions")
    strategy = relationship("Strategy", back_populates="positions")


class NotificationLog(Base):
    """通知记录模型"""
    __tablename__ = "notification_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trigger_log_id = Column(Integer, ForeignKey("trigger_logs.id"), nullable=False)
    channel = Column(String, nullable=False, default="feishu")
    status = Column(String, nullable=False)
    error_message = Column(Text, nullable=True)
    sent_at = Column(DateTime, nullable=False, server_default=func.now())

    # 关系
    trigger_log = relationship("TriggerLog", back_populates="notification_logs")


class SimAccount(Base):
    """模拟账户模型"""
    __tablename__ = "sim_accounts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # nullable during migration
    initial_balance = Column(Float, nullable=False, default=100000.0)
    balance = Column(Float, nullable=False, default=100000.0)
    total_pnl = Column(Float, nullable=False, default=0.0)
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    # 关系
    user = relationship("User", back_populates="sim_accounts")


class KlineData(Base):
    """K线缓存模型"""
    __tablename__ = "kline_data"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String, nullable=False)
    timeframe = Column(String, nullable=False)
    open_time = Column(DateTime, nullable=False)
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=False)

    __table_args__ = (
        UniqueConstraint('symbol', 'timeframe', 'open_time', name='uix_kline'),
    )


class SystemSetting(Base):
    """系统设置（key-value 存储）"""
    __tablename__ = "system_settings"

    key = Column(String, primary_key=True)
    value = Column(Text, nullable=True)
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())


class BacktestResult(Base):
    """回测结果模型"""
    __tablename__ = "backtest_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # nullable during migration
    strategy_id = Column(Integer, ForeignKey("strategies.id"), nullable=False)
    symbol = Column(String, nullable=False)
    timeframe = Column(String, nullable=False)
    start_date = Column(DateTime, nullable=False)
    end_date = Column(DateTime, nullable=False)
    initial_balance = Column(Float, nullable=False)
    final_balance = Column(Float, nullable=False)
    total_pnl = Column(Float, nullable=False)
    pnl_percent = Column(Float, nullable=False)
    win_rate = Column(Float, nullable=False)
    max_drawdown = Column(Float, nullable=False)
    total_trades = Column(Integer, nullable=False)
    avg_hold_time = Column(Integer, nullable=True)
    equity_curve = Column(Text, nullable=False)
    trades = Column(Text, nullable=False)
    klines = Column(Text, nullable=True)
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    # 关系
    user = relationship("User", back_populates="backtest_results")
    strategy = relationship("Strategy", back_populates="backtest_results")
