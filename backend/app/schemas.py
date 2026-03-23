"""
Pydantic Schema 定义
"""

from datetime import datetime
from typing import Any, List, Optional

from pydantic import BaseModel, ConfigDict, Field


# ==================== 策略相关 ====================

class StrategyBase(BaseModel):
    """策略基础字段"""
    name: str = Field(..., min_length=1, max_length=100)
    type: str = Field(..., pattern="^(visual|code)$")
    symbol: str = Field(..., min_length=1)
    timeframe: str = Field(..., pattern=r"^(\d+[mhdw])(,\d+[mhdw])*$")
    position_size: float = Field(..., gt=0)
    position_size_type: str = Field(..., pattern="^(fixed|percent)$")
    stop_loss: Optional[float] = Field(None, ge=0, le=100)
    take_profit: Optional[float] = Field(None, ge=0, le=1000)
    sell_size_pct: float = Field(100.0, gt=0, le=100)
    notify_enabled: bool = True


class StrategyCreate(StrategyBase):
    """创建策略请求"""
    config_json: Optional[str] = None  # JSON 字符串
    code: Optional[str] = None


class StrategyUpdate(BaseModel):
    """更新策略请求（仅 stopped 状态可编辑）"""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    config_json: Optional[str] = None
    code: Optional[str] = None
    position_size: Optional[float] = Field(None, gt=0)
    position_size_type: Optional[str] = Field(None, pattern="^(fixed|percent)$")
    stop_loss: Optional[float] = Field(None, ge=0, le=100)
    take_profit: Optional[float] = Field(None, ge=0, le=1000)
    sell_size_pct: Optional[float] = Field(None, gt=0, le=100)
    notify_enabled: Optional[bool] = None


class StrategyResponse(StrategyBase):
    """策略响应"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    timeframe: str  # 覆盖基类限制，读库数据不做格式校验
    config_json: Optional[str] = None
    code: Optional[str] = None
    status: str
    created_at: datetime
    updated_at: datetime
    # 统计信息
    trigger_count: Optional[int] = None
    position_count: Optional[int] = None


class StrategyList(BaseModel):
    """策略列表响应"""
    items: List[StrategyResponse]
    total: int
    page: int
    page_size: int


# ==================== 代码验证相关 ====================

class CodeValidationRequest(BaseModel):
    """代码验证请求"""
    code: str


class CodeValidationResponse(BaseModel):
    """代码验证响应"""
    valid: bool
    errors: List[str]


# ==================== 触发日志相关 ====================

class TriggerLogResponse(BaseModel):
    """触发记录响应"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    strategy_id: int
    strategy_name: Optional[str] = None
    triggered_at: datetime
    signal_type: str
    signal_detail: Optional[str] = None
    action: Optional[str] = None
    position_effect: Optional[str] = None
    price: Optional[float] = None
    quantity: Optional[float] = None
    simulated_pnl: Optional[float] = None


class TriggerLogList(BaseModel):
    """触发日志列表响应"""
    items: List[TriggerLogResponse]
    total: int
    page: int
    page_size: int


class TriggerDeleteRequest(BaseModel):
    ids: List[int]


# ==================== 持仓相关 ====================

class PositionResponse(BaseModel):
    """持仓响应"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    strategy_id: int
    symbol: str
    side: str
    entry_price: float
    quantity: float
    current_price: Optional[float] = None
    pnl: Optional[float] = None
    unrealized_pnl: Optional[float] = None  # 计算字段
    opened_at: datetime
    closed_at: Optional[datetime] = None


class PositionList(BaseModel):
    """持仓列表响应"""
    items: List[PositionResponse]
    total: int


class PositionHistoryList(BaseModel):
    """历史持仓列表响应（含分页信息）"""
    items: List[PositionResponse]
    total: int
    page: int
    page_size: int


# ==================== 账户相关 ====================

class AccountResponse(BaseModel):
    """账户响应"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    initial_balance: float
    balance: float
    total_pnl: float
    updated_at: datetime


# ==================== 仪表盘相关 ====================

class DashboardData(BaseModel):
    """仪表盘数据"""
    balance: float
    total_pnl: float
    running_strategies: int
    today_triggers: int
    recent_triggers: List[TriggerLogResponse]


# ==================== 回测相关 ====================

class BacktestCreate(BaseModel):
    """创建回测请求"""
    start_date: datetime
    end_date: datetime
    initial_balance: float = Field(default=100000, gt=0)


class BacktestResponse(BaseModel):
    """回测结果响应"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    strategy_id: int
    symbol: str
    timeframe: str
    start_date: datetime
    end_date: datetime
    initial_balance: float
    final_balance: float
    total_pnl: float
    pnl_percent: float
    win_rate: float
    max_drawdown: float
    total_trades: int
    avg_hold_time: Optional[int] = None
    equity_curve: str  # JSON 字符串
    trades: str  # JSON 字符串
    klines: Optional[str] = None  # JSON 字符串，K线数据
    created_at: datetime


class BacktestList(BaseModel):
    """回测列表响应"""
    items: List[BacktestResponse]
    total: int
    page: int
    page_size: int


# ==================== 系统设置 ====================

class SettingsResponse(BaseModel):
    """系统设置响应"""
    data_source: str  # binance | cryptocompare | mock
    cryptocompare_api_key: str = ""
    timezone: str = "Asia/Shanghai"


class SettingsUpdate(BaseModel):
    """系统设置更新请求"""
    data_source: str = Field(..., pattern="^(binance|cryptocompare|mock)$")
    cryptocompare_api_key: Optional[str] = None
    timezone: Optional[str] = None


class TestConnectionRequest(BaseModel):
    """测试数据源连接请求"""
    data_source: str = Field(..., pattern="^(binance|cryptocompare|mock)$")
    api_key: Optional[str] = None


class TestConnectionResponse(BaseModel):
    """测试连接响应"""
    success: bool
    message: str


# ==================== 通用 ====================

class MessageResponse(BaseModel):
    """通用消息响应"""
    message: str


class ErrorResponse(BaseModel):
    """错误响应"""
    detail: str
    code: Optional[str] = None


class HealthResponse(BaseModel):
    """健康检查响应"""
    status: str


# ==================== 认证相关 ====================

class UserResponse(BaseModel):
    """用户信息响应"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    is_admin: bool
    created_at: datetime


class AuthRequest(BaseModel):
    """登录/注册请求"""
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=6)


class AuthResponse(BaseModel):
    """认证响应"""
    user: UserResponse


class MeResponse(BaseModel):
    """当前用户响应（未登录时 user 为 null）"""
    user: Optional[UserResponse] = None


# ==================== 通知设置 ====================

class NotificationSettingsResponse(BaseModel):
    """通知设置响应"""
    bark_key: Optional[str] = None
    bark_enabled: bool = False


class NotificationSettingsUpdate(BaseModel):
    """通知设置更新请求"""
    bark_key: Optional[str] = None
    bark_enabled: Optional[bool] = None
