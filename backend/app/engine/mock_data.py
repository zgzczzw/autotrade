"""
模拟市场数据生成器
用于测试回测功能，无需连接外部 API
"""

import random
from datetime import datetime, timedelta
from typing import List


def generate_mock_klines(
    symbol: str,
    timeframe: str,
    start_date: datetime,
    end_date: datetime,
) -> List[dict]:
    """
    生成模拟 K 线数据
    
    生成随机 walk 价格数据，包含一定的趋势和波动
    """
    # 根据时间周期确定间隔
    interval_minutes = {
        "1m": 1,
        "3m": 3,
        "5m": 5,
        "15m": 15,
        "30m": 30,
        "1h": 60,
        "2h": 120,
        "4h": 240,
        "6h": 360,
        "8h": 480,
        "12h": 720,
        "1d": 1440,
        "3d": 4320,
        "1w": 10080,
    }
    
    minutes = interval_minutes.get(timeframe, 60)
    
    # 生成 K 线列表
    klines = []
    current_time = start_date
    
    # 初始价格 (根据交易对设置合理价格)
    if "BTC" in symbol:
        base_price = 60000.0
    elif "ETH" in symbol:
        base_price = 3000.0
    elif "SOL" in symbol:
        base_price = 150.0
    else:
        base_price = 100.0
    
    # 添加一些随机种子使结果可重复
    random.seed(42)
    
    price = base_price
    
    while current_time <= end_date:
        # 生成随机价格波动 (-2% 到 +2%)
        change_pct = random.uniform(-0.02, 0.02)
        
        # 添加一些趋势性
        trend = 0.001 * (len(klines) % 100 - 50) / 50  # 轻微的趋势
        
        open_price = price
        close_price = price * (1 + change_pct + trend)
        
        # 生成高低点
        high_price = max(open_price, close_price) * (1 + random.uniform(0, 0.01))
        low_price = min(open_price, close_price) * (1 - random.uniform(0, 0.01))
        
        # 生成成交量
        volume = random.uniform(100, 1000)
        
        klines.append({
            "open_time": current_time,
            "open": round(open_price, 2),
            "high": round(high_price, 2),
            "low": round(low_price, 2),
            "close": round(close_price, 2),
            "volume": round(volume, 4),
        })
        
        price = close_price
        current_time += timedelta(minutes=minutes)
    
    return klines
