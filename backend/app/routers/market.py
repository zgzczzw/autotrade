"""
大盘行情 API
GET /api/market/symbols?q=BTC     — 搜索交易对
GET /api/market/klines            — K 线数据（转为前端格式）
GET /api/market/ticker            — 24h 行情摘要
"""

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query

from app.engine.market_data import market_data_service
from app.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/market", tags=["market"])


def _to_bar(k: dict) -> dict:
    """将后端 kline dict 转换为前端 KlineChartModule 所需格式"""
    open_time = k["open_time"]
    # open_time 是 datetime 对象
    ts = int(open_time.timestamp() * 1000)
    return {
        "timestamp": ts,
        "open":   k["open"],
        "high":   k["high"],
        "low":    k["low"],
        "close":  k["close"],
        "volume": k["volume"],
    }


@router.get("/symbols", response_model=List[str])
async def get_symbols(q: str = Query(default="", description="搜索关键字，如 BTC")):
    """搜索交易对列表，返回最多 50 条"""
    try:
        return await market_data_service.get_symbols(q)
    except Exception as e:
        logger.error(f"get_symbols error: {e}")
        raise HTTPException(status_code=502, detail=f"获取交易对失败: {e}")


@router.get("/klines")
async def get_klines(
    symbol: str = Query(..., description="交易对，如 BTCUSDT"),
    timeframe: str = Query(default="1h", description="时间周期：15m/1h/4h/1d"),
    limit: int = Query(default=200, ge=10, le=1000),
):
    """获取 K 线数据，返回前端 KlineChartModule 格式"""
    try:
        klines = await market_data_service.get_klines(
            symbol=symbol,
            timeframe=timeframe,
            limit=limit,
        )
        return [_to_bar(k) for k in klines]
    except Exception as e:
        logger.error(f"get_klines error [{symbol} {timeframe}]: {e}")
        raise HTTPException(status_code=502, detail=f"获取 K 线失败: {e}")


@router.get("/ticker")
async def get_ticker(symbol: str = Query(..., description="交易对，如 BTCUSDT")):
    """获取 24h 行情摘要"""
    try:
        return await market_data_service.get_ticker(symbol)
    except Exception as e:
        logger.error(f"get_ticker error [{symbol}]: {e}")
        raise HTTPException(status_code=502, detail=f"获取行情失败: {e}")
