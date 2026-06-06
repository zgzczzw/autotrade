"""session_window(): 窗口必须覆盖当前 UTC 自然日，否则细周期上日内 VWAP 锚点漂移。

回归点：实盘 executor 与回测 backtester 此前固定喂 100 根 K 线给策略，
5m 周期下一个 UTC 日有 288 根，导致策略的"当日 VWAP"在 08:20 UTC 之后
不再从午夜累计，与前端图表（从 00:00 累计）画出的 VWAP 线对不齐。
"""
from datetime import datetime, timedelta, timezone

from app.engine.market_data import session_window


def test_coarse_timeframes_stay_at_base():
    # EMA/ATR 策略都在 1h/4h/1d —— 必须保持 100，零影响
    for tf in ("30m", "1h", "2h", "4h", "1d"):
        assert session_window(tf) == 100, tf


def test_fine_timeframes_cover_full_utc_day():
    # 一个 UTC 日的 bar 数：5m=288, 1m=1440
    assert session_window("5m") >= 288
    assert session_window("15m") >= 96
    # 1m 受 1000 上限约束（Binance 单次请求最大条数）
    assert session_window("1m") == 1000


def _vwap(bars):
    pv = v = 0.0
    for k in bars:
        typ = (k["high"] + k["low"] + k["close"]) / 3.0
        pv += typ * k["volume"]
        v += k["volume"]
    return pv / v


def _today_bars(window):
    """复刻策略的当日过滤逻辑。"""
    today = window[-1]["open_time"].date()
    return [k for k in window if k["open_time"].date() == today]


def test_session_window_anchors_vwap_at_midnight_on_5m():
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    klines = [
        {
            "open_time": t0 + timedelta(minutes=5 * i),
            "open": 3000.0 + i, "high": 3000.0 + i + 4,
            "low": 3000.0 + i - 4, "close": 3000.0 + i, "volume": 100.0,
        }
        for i in range(600)  # >2 个 UTC 日
    ]
    # day2 20:00 UTC —— 距午夜 240 根（远超 100）
    target = datetime(2026, 1, 2, 20, 0, tzinfo=timezone.utc)
    i = next(idx for idx, k in enumerate(klines) if k["open_time"] == target)
    midnight = target.replace(hour=0, minute=0)

    true_vwap = _vwap([k for k in klines[: i + 1] if k["open_time"] >= midnight])

    old = _today_bars(klines[max(0, i - 99): i + 1])
    assert old[0]["open_time"] != midnight  # 旧的 100 根窗口锚点漂移
    assert abs(_vwap(old) - true_vwap) > 1.0

    w = session_window("5m")
    new = _today_bars(klines[max(0, i - (w - 1)): i + 1])
    assert new[0]["open_time"] == midnight  # 新窗口锚定午夜
    assert abs(_vwap(new) - true_vwap) < 1e-9
