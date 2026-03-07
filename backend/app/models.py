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


class Strategy(Base):
    """策略模型"""
    __tablename__ = "strategies"

    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, nullable=False)
    type = Column(String, nullable=False)  # visual / code
    config_json = Column(Text, nullable=True)  # 可视化配置 JSON 字符串
    code = Column(Text, nullable=True)  # 代码策略源码
    symbol = Column(String, nullable=False)  # e.g. BTCUSDT
    timeframe = Column(String, nullable=False)  # 1m/5m/1h/1d
    position_size = Column(Float, nullable=False, default=100.0)
    position_size_type = Column(String, nullable=False, default="fixed")  # fixed / percent
    stop_loss = Column(Float, nullable=True)  # 止损百分比
    take_profit = Column(Float, nullable=True)  # 止盈百分比
    sell_size_pct = Column(Float, nullable=False, default=100.0)  # 每次卖出仓位比例 (1-100)
    notify_enabled = Column(Boolean, nullable=False, default=True)
    status = Column(String, nullable=False, default="stopped")  # running/stopped/error
    created_at = Column(DateTime, nullable=False, server_default=func.now())
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())

    # 关系
    trigger_logs = relationship("TriggerLog", back_populates="strategy", cascade="all, delete-orphan")
    positions = relationship("Position", back_populates="strategy", cascade="all, delete-orphan")
    backtest_results = relationship("BacktestResult", back_populates="strategy", cascade="all, delete-orphan")


class TriggerLog(Base):
    """触发记录模型"""
    __tablename__ = "trigger_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    strategy_id = Column(Integer, ForeignKey("strategies.id"), nullable=False)
    triggered_at = Column(DateTime, nullable=False, server_default=func.now())
    signal_type = Column(String, nullable=False)  # buy / sell / error
    signal_detail = Column(Text, nullable=True)  # 信号详情
    action = Column(String, nullable=True)  # buy / sell / hold (实际执行)
    price = Column(Float, nullable=True)
    quantity = Column(Float, nullable=True)
    simulated_pnl = Column(Float, nullable=True)  # 模拟盈亏

    # 关系
    strategy = relationship("Strategy", back_populates="trigger_logs")
    notification_logs = relationship("NotificationLog", back_populates="trigger_log")


class Position(Base):
    """模拟持仓模型"""
    __tablename__ = "positions"

    id = Column(Integer, primary_key=True, autoincrement=True)
    strategy_id = Column(Integer, ForeignKey("strategies.id"), nullable=False)
    symbol = Column(String, nullable=False)
    side = Column(String, nullable=False)  # long / short
    entry_price = Column(Float, nullable=False)
    quantity = Column(Float, nullable=False)
    current_price = Column(Float, nullable=True)  # 当前价格（平仓时写入）
    pnl = Column(Float, nullable=True)  # 已实现盈亏
    opened_at = Column(DateTime, nullable=False, server_default=func.now())
    closed_at = Column(DateTime, nullable=True)

    # 关系
    strategy = relationship("Strategy", back_populates="positions")


class NotificationLog(Base):
    """通知记录模型"""
    __tablename__ = "notification_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    trigger_log_id = Column(Integer, ForeignKey("trigger_logs.id"), nullable=False)
    channel = Column(String, nullable=False, default="feishu")  # feishu
    status = Column(String, nullable=False)  # sent / failed
    error_message = Column(Text, nullable=True)
    sent_at = Column(DateTime, nullable=False, server_default=func.now())

    # 关系
    trigger_log = relationship("TriggerLog", back_populates="notification_logs")


class SimAccount(Base):
    """模拟账户模型"""
    __tablename__ = "sim_accounts"

    id = Column(Integer, primary_key=True, autoincrement=True)
    initial_balance = Column(Float, nullable=False, default=100000.0)
    balance = Column(Float, nullable=False, default=100000.0)
    total_pnl = Column(Float, nullable=False, default=0.0)
    updated_at = Column(DateTime, nullable=False, server_default=func.now(), onupdate=func.now())


class KlineData(Base):
    """K线缓存模型"""
    __tablename__ = "kline_data"

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String, nullable=False)
    timeframe = Column(String, nullable=False)  # 1m/5m/1h/1d
    open_time = Column(DateTime, nullable=False)
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=False)

    # 联合唯一索引
    __table_args__ = (
        UniqueConstraint('symbol', 'timeframe', 'open_time', name='uix_kline'),
    )


class BacktestResult(Base):
    """回测结果模型"""
    __tablename__ = "backtest_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
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
    avg_hold_time = Column(Integer, nullable=True)  # 平均持仓时间（秒）
    equity_curve = Column(Text, nullable=False)  # JSON 字符串
    trades = Column(Text, nullable=False)  # JSON 字符串
    klines = Column(Text, nullable=True)  # JSON 字符串，回测用的K线数据
    created_at = Column(DateTime, nullable=False, server_default=func.now())

    # 关系
    strategy = relationship("Strategy", back_populates="backtest_results")
