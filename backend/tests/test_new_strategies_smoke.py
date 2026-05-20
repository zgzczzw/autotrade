"""新策略沙箱冒烟测试。

对每个 scripts/new_strategies/*.py：
1. 通过 sandbox 编译实例化（验证不触发 FORBIDDEN_KEYWORDS / 未声明符号）
2. 用 200 根 mock K 线驱动 on_tick 至少 100 次，确认不抛异常
3. 信号合法（"buy" / "sell" / "hold" / None）
"""
import math
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.engine.sandbox import sandbox_executor

STRATEGIES_DIR = Path(__file__).resolve().parents[2] / "scripts" / "new_strategies"

VALID_SIGNALS = {"buy", "sell", "hold", None}


def _gen_klines(n=200, start_price=40000.0, vol_amplitude=200.0, tf_hours=1):
    klines = []
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i in range(n):
        base = start_price * (1 + 0.1 * math.sin(i / 20.0)) + i * 5
        noise = vol_amplitude * math.sin(i * 1.7)
        close = base + noise
        open_ = base
        high = max(open_, close) + abs(noise) * 0.5 + 1.0
        low = min(open_, close) - abs(noise) * 0.5 - 1.0
        volume = 100 + 50 * abs(math.sin(i / 7.0))
        klines.append({
            "open_time": t0 + timedelta(hours=i * tf_hours),
            "open": open_, "high": high, "low": low,
            "close": close, "volume": volume,
        })
    return klines


def _make_ctx(position=None):
    ctx = MagicMock()
    ctx.get_position = MagicMock(return_value=position)
    return ctx


@pytest.fixture
def daily_klines():
    return _gen_klines(n=250, start_price=40000.0, vol_amplitude=800.0, tf_hours=24)


@pytest.fixture
def hour_klines():
    return _gen_klines(n=200, start_price=40000.0, vol_amplitude=200.0, tf_hours=1)


def _strategy_files():
    if not STRATEGIES_DIR.exists():
        return []
    return sorted(STRATEGIES_DIR.glob("*.py"))


@pytest.mark.parametrize("filepath", _strategy_files(), ids=lambda p: p.stem)
def test_strategy_smoke(filepath, hour_klines, daily_klines):
    code = filepath.read_text(encoding="utf-8")
    ctx = _make_ctx(position=None)
    instance = sandbox_executor.create_instance(
        code=code, context=ctx, strategy_id=0,
    )

    saw_non_hold = False
    for i in range(100, 200):
        data = {
            "symbol": "BTCUSDT",
            "timeframe": "1h",
            "price": hour_klines[i]["close"],
            "klines": hour_klines[:i + 1],
            "daily_klines": daily_klines,
            "fear_greed": {"value": 50, "value_classification": "Neutral"},
        }
        signal = instance.on_tick(data)
        assert signal in VALID_SIGNALS, f"{filepath.name} returned invalid signal: {signal!r}"
        if signal in ("buy", "sell"):
            saw_non_hold = True

    print(f"{filepath.name}: saw_non_hold={saw_non_hold}")
