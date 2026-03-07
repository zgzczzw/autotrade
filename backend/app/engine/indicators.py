"""
技术指标计算模块
纯 Python 实现，无需外部依赖
"""

from typing import List, Optional


def calculate_sma(data: List[float], period: int) -> Optional[float]:
    """
    计算简单移动平均线 (SMA)

    Args:
        data: 价格数据列表（最新的在最后）
        period: 计算周期

    Returns:
        SMA 值，数据不足时返回 None
    """
    if len(data) < period:
        return None

    return sum(data[-period:]) / period


def calculate_ema(data: List[float], period: int) -> Optional[float]:
    """
    计算指数移动平均线 (EMA)

    Args:
        data: 价格数据列表（最新的在最后）
        period: 计算周期

    Returns:
        EMA 值，数据不足时返回 None
    """
    if len(data) < period:
        return None

    # EMA 公式: EMA = Price(t) * k + EMA(y) * (1 - k)
    # k = 2 / (N + 1)
    k = 2 / (period + 1)

    # 初始 EMA 使用 SMA
    ema = sum(data[:period]) / period

    # 计算后续 EMA
    for price in data[period:]:
        ema = price * k + ema * (1 - k)

    return ema


def calculate_rsi(data: List[float], period: int = 14) -> Optional[float]:
    """
    计算相对强弱指数 (RSI)

    Args:
        data: 价格数据列表（最新的在最后）
        period: 计算周期，默认 14

    Returns:
        RSI 值 (0-100)，数据不足时返回 None
    """
    if len(data) < period + 1:
        return None

    # 计算价格变化
    changes = [data[i] - data[i - 1] for i in range(1, len(data))]

    # 分离上涨和下跌
    gains = [max(change, 0) for change in changes]
    losses = [abs(min(change, 0)) for change in changes]

    # 计算平均上涨和平均下跌
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period

    if avg_loss == 0:
        return 100.0

    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))

    return rsi


def calculate_bollinger_bands(
    data: List[float],
    period: int = 20,
    std_dev: float = 2.0,
) -> Optional[dict]:
    """
    计算布林带 (Bollinger Bands)

    Args:
        data: 价格数据列表（最新的在最后）
        period: 计算周期，默认 20
        std_dev: 标准差倍数，默认 2.0

    Returns:
        包含 upper, middle, lower 的字典，数据不足时返回 None
    """
    if len(data) < period:
        return None

    # 中轨是 SMA
    prices = data[-period:]
    middle = sum(prices) / period

    # 计算标准差
    variance = sum((p - middle) ** 2 for p in prices) / period
    std = variance ** 0.5

    upper = middle + std_dev * std
    lower = middle - std_dev * std

    return {
        "upper": upper,
        "middle": middle,
        "lower": lower,
    }


def check_ma_cross(
    data: List[float],
    fast_period: int,
    slow_period: int,
) -> Optional[str]:
    """
    检查均线交叉

    Args:
        data: 价格数据列表（最新的在最后）
        fast_period: 快速均线周期
        slow_period: 慢速均线周期

    Returns:
        "golden" - 金叉（快速上穿慢速）
        "death" - 死叉（快速下穿慢速）
        None - 无交叉
    """
    if len(data) < slow_period + 1:
        return None

    # 计算当前和前一个的均线
    current_fast = sum(data[-fast_period:]) / fast_period
    current_slow = sum(data[-slow_period:]) / slow_period

    prev_fast = sum(data[-fast_period - 1:-1]) / fast_period
    prev_slow = sum(data[-slow_period - 1:-1]) / slow_period

    # 检查交叉
    if prev_fast <= prev_slow and current_fast > current_slow:
        return "golden"  # 金叉
    elif prev_fast >= prev_slow and current_fast < current_slow:
        return "death"  # 死叉

    return None


def check_bollinger_touch(
    data: List[float],
    period: int = 20,
    std_dev: float = 2.0,
) -> Optional[str]:
    """
    检查布林带突破

    Args:
        data: 价格数据列表（最新的在最后）
        period: 计算周期
        std_dev: 标准差倍数

    Returns:
        "above_upper" - 突破上轨
        "below_lower" - 突破下轨
        None - 未突破
    """
    if len(data) < period:
        return None

    bands = calculate_bollinger_bands(data, period, std_dev)
    if not bands:
        return None

    current_price = data[-1]

    if current_price > bands["upper"]:
        return "above_upper"
    elif current_price < bands["lower"]:
        return "below_lower"

    return None


def calculate_macd(
    data: List[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> Optional[dict]:
    """计算 MACD"""
    if len(data) < slow + signal:
        return None

    def ema_series(prices: List[float], period: int) -> List[float]:
        k = 2 / (period + 1)
        result = [sum(prices[:period]) / period]
        for price in prices[period:]:
            result.append(price * k + result[-1] * (1 - k))
        return result

    ema_fast = ema_series(data, fast)
    # 对齐长度：slow 的 EMA 从索引 slow-1 开始
    ema_slow = ema_series(data, slow)
    offset = slow - fast
    dif = [f - s for f, s in zip(ema_fast[offset:], ema_slow)]

    dea_k = 2 / (signal + 1)
    dea = [sum(dif[:signal]) / signal]
    for v in dif[signal:]:
        dea.append(v * dea_k + dea[-1] * (1 - dea_k))

    # 对齐到 dif
    dea_aligned = [None] * (signal - 1) + dea
    histogram = [
        (d - e) * 2 if e is not None else None
        for d, e in zip(dif, dea_aligned)
    ]

    return {
        "dif": dif[-1],
        "dea": dea[-1],
        "histogram": histogram[-1],
        "prev_dif": dif[-2] if len(dif) >= 2 else None,
        "prev_dea": dea[-2] if len(dea) >= 2 else None,
    }


def check_macd_signal(
    data: List[float],
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> Optional[str]:
    """检查 MACD 信号"""
    result = calculate_macd(data, fast, slow, signal)
    if not result:
        return None

    dif, dea = result["dif"], result["dea"]
    prev_dif, prev_dea = result["prev_dif"], result["prev_dea"]
    histogram = result["histogram"]

    if prev_dif is not None and prev_dea is not None:
        if prev_dif <= prev_dea and dif > dea:
            return "golden"
        if prev_dif >= prev_dea and dif < dea:
            return "death"

    if histogram is not None:
        if histogram > 0:
            return "above_zero"
        if histogram < 0:
            return "below_zero"

    return None


def calculate_kdj(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    period: int = 9,
) -> Optional[dict]:
    """计算 KDJ"""
    if len(closes) < period + 1:
        return None

    rsv_list = []
    for i in range(period - 1, len(closes)):
        h = max(highs[i - period + 1: i + 1])
        l = min(lows[i - period + 1: i + 1])
        rsv = (closes[i] - l) / (h - l) * 100 if h != l else 50
        rsv_list.append(rsv)

    k, d = 50.0, 50.0
    prev_k, prev_d = 50.0, 50.0
    for rsv in rsv_list:
        prev_k, prev_d = k, d
        k = k * 2 / 3 + rsv / 3
        d = d * 2 / 3 + k / 3

    j = 3 * k - 2 * d
    return {"k": k, "d": d, "j": j, "prev_k": prev_k, "prev_d": prev_d}


def check_kdj_signal(
    highs: List[float],
    lows: List[float],
    closes: List[float],
    period: int = 9,
) -> Optional[str]:
    """检查 KDJ 信号"""
    result = calculate_kdj(highs, lows, closes, period)
    if not result:
        return None

    k, d = result["k"], result["d"]
    prev_k, prev_d = result["prev_k"], result["prev_d"]

    if prev_k <= prev_d and k > d:
        return "k_cross_up"
    if prev_k >= prev_d and k < d:
        return "k_cross_down"
    if k > 80:
        return "overbought"
    if k < 20:
        return "oversold"

    return None


def check_volume_spike(
    volumes: List[float],
    ma_period: int = 20,
    multiplier: float = 1.5,
) -> bool:
    """检查成交量放大"""
    if len(volumes) < ma_period + 1:
        return False
    avg = sum(volumes[-ma_period - 1:-1]) / ma_period
    return volumes[-1] > avg * multiplier if avg > 0 else False


class IndicatorCalculator:
    """指标计算器"""

    def __init__(self, klines: List[dict]):
        """
        Args:
            klines: K 线数据列表，每项包含 open, high, low, close, volume
        """
        self.klines = klines
        self.closes = [k["close"] for k in klines]
        self.highs = [k["high"] for k in klines]
        self.lows = [k["low"] for k in klines]
        self.volumes = [k["volume"] for k in klines]

    def rsi(self, period: int = 14) -> Optional[float]:
        return calculate_rsi(self.closes, period)

    def sma(self, period: int) -> Optional[float]:
        return calculate_sma(self.closes, period)

    def ema(self, period: int) -> Optional[float]:
        return calculate_ema(self.closes, period)

    def bollinger(self, period: int = 20, std_dev: float = 2.0) -> Optional[dict]:
        return calculate_bollinger_bands(self.closes, period, std_dev)

    def ma_cross(self, fast: int, slow: int) -> Optional[str]:
        return check_ma_cross(self.closes, fast, slow)

    def bollinger_touch(self, period: int = 20, std_dev: float = 2.0) -> Optional[str]:
        return check_bollinger_touch(self.closes, period, std_dev)

    def macd_signal(self, fast: int = 12, slow: int = 26, signal: int = 9) -> Optional[str]:
        return check_macd_signal(self.closes, fast, slow, signal)

    def kdj_signal(self, period: int = 9) -> Optional[str]:
        return check_kdj_signal(self.highs, self.lows, self.closes, period)

    def volume_spike(self, ma_period: int = 20, multiplier: float = 1.5) -> bool:
        return check_volume_spike(self.volumes, ma_period, multiplier)

    def price_change_pct(self) -> Optional[float]:
        """最新K线涨跌幅（%）"""
        if len(self.closes) < 2:
            return None
        prev = self.closes[-2]
        return (self.closes[-1] - prev) / prev * 100 if prev else None

    def current_price(self) -> float:
        return self.closes[-1] if self.closes else 0.0
