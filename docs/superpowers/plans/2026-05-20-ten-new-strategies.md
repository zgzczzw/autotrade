# 十个全新策略 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将设计文档 `docs/superpowers/specs/2026-05-20-ten-new-strategies-design.md` 中的 10 个策略落地为可运行代码文件、入库、注册到 APScheduler。

**Architecture:** 10 个独立 .py 文件存放在 `scripts/new_strategies/`（git tracked，source-of-truth），部署脚本拷贝到 `/var/tmp/strategies/`（strategy_sync 自动入库），随后将 `status` 改为 `running` 并调用 `scheduler_service.start_strategy()`。每个策略文件独立无跨文件依赖（因为 sandbox 禁止 import 且 sync 只接受单文件）。每个策略自带 `_atr / _enter / _exit / _clear_state / _manage_position` 私有方法（DRY 让位于策略隔离）。

**Tech Stack:** Python 3.12 + AutoTrade 沙箱（whitelisted builtins + BaseStrategy + 已知指标函数），pytest + pytest-asyncio，SQLAlchemy 2.0 async，APScheduler。

---

## Hard Constraints from Sandbox

策略代码运行在 `app/engine/sandbox.py` 受限环境中，**必须**遵守：

| 约束 | 说明 |
|---|---|
| 禁止 `import` / `from` | FORBIDDEN_KEYWORDS 包含 `import,from,open,exec,eval,compile,__import__,file` |
| 只能用 whitelisted builtins | `abs, all, any, bool, dict, float, int, len, list, max, min, range, round, str, sum, tuple, zip, enumerate, filter, map, sorted, reversed, isinstance, hasattr, getattr, setattr, print, super, property, staticmethod, classmethod, type, object, None, True, False` |
| 沙箱注入的全局符号（可直接用） | `BaseStrategy, List, Dict, Optional, calculate_bollinger_bands, calculate_rsi, calculate_sma, calculate_ema, calculate_macd, check_bollinger_touch, check_ma_cross, check_macd_signal, check_kdj_signal, check_volume_spike` |
| 数学辅助 | 没有 `math` 模块。`sqrt(x) = x ** 0.5`；没有 `Inf`，用 `float("inf")` 也禁止？不，`float` 是 builtin，`float("inf")` 可以 |
| 没有 `datetime` 模块 | 但 `kline["open_time"]` 已经是 datetime 对象，可调用其方法 `.date()`、`.hour` 等 |
| 策略文件头 `@meta` 注释 | 必须有 `@name`、`@symbol`、`@timeframe`；可选 `@position_size`、`@position_size_type`、`@stop_loss`、`@take_profit` |

策略代码模板（所有 10 个共享）：

```python
# @name: <策略名>
# @symbol: <BTCUSDT|ETHUSDT|SOLUSDT>
# @timeframe: <15m|1h|4h|1d>
# @position_size: <10|15>
# @position_size_type: percent
# @stop_loss: 5


class Strategy(BaseStrategy):
    """<策略中文说明>"""

    def on_start(self):
        self.entry_price = None
        self.stop_price = None
        self.position_side = None
        self.highest_since_entry = None
        self.lowest_since_entry = None
        self.bars_since_exit = 99  # 冷却

    def on_tick(self, data):
        # ① 取数据
        # ② 不足 K 线 → hold
        # ③ 计算策略特有指标
        # ④ 持仓管理（含统一风控）
        # ⑤ 冷却
        # ⑥ 入场判断
        return "hold"

    # === 共用辅助（每个文件内实现） ===
    def _atr(self, highs, lows, closes, period=14):
        if len(closes) < period + 1:
            return None
        trs = []
        for i in range(1, len(closes)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            )
            trs.append(tr)
        if len(trs) < period:
            return None
        return sum(trs[-period:]) / period

    def _enter(self, price, side, stop):
        self.entry_price = price
        self.stop_price = stop
        self.position_side = side
        self.bars_since_exit = 0
        self.highest_since_entry = price
        self.lowest_since_entry = price

    def _exit(self, signal):
        self._clear_state()
        return signal

    def _clear_state(self):
        self.entry_price = None
        self.stop_price = None
        self.position_side = None
        self.highest_since_entry = None
        self.lowest_since_entry = None
        self.bars_since_exit = 0
```

---

## File Structure

| 类别 | 路径 | 用途 |
|---|---|---|
| 源文件（git tracked） | `scripts/new_strategies/turtle_breakout.py` | 海龟突破 |
| 源文件 | `scripts/new_strategies/supertrend.py` | SuperTrend |
| 源文件 | `scripts/new_strategies/vwap_reversion.py` | VWAP 日内回归 |
| 源文件 | `scripts/new_strategies/grid_range.py` | 区间网格 |
| 源文件 | `scripts/new_strategies/mtf_resonance.py` | MTF 双周期共振 |
| 源文件 | `scripts/new_strategies/squeeze_breakout.py` | Squeeze 突破 |
| 源文件 | `scripts/new_strategies/adx_keltner.py` | ADX 强趋势通道 |
| 源文件 | `scripts/new_strategies/stoch_rsi_reversal.py` | StochRSI 反转 |
| 源文件 | `scripts/new_strategies/heikin_ashi_trend.py` | Heikin Ashi 趋势 |
| 源文件 | `scripts/new_strategies/zscore_reversion.py` | Z-score 均值回归 |
| 部署脚本 | `scripts/deploy_new_strategies.py` | 复制 + sync + UPDATE status + 注册调度 |
| 测试 | `backend/tests/test_new_strategies_smoke.py` | 沙箱编译 + 模拟 K 线驱动 on_tick 不抛异常 |

---

## Task 0: Setup & Shared Test Harness

**Files:**
- Create: `backend/tests/test_new_strategies_smoke.py`
- Create: `scripts/new_strategies/.gitkeep`

- [ ] **Step 1: Create directory**

```bash
mkdir -p /home/autotrade/autotrade/scripts/new_strategies
touch /home/autotrade/autotrade/scripts/new_strategies/.gitkeep
```

- [ ] **Step 2: Write shared smoke-test harness**

Create `/home/autotrade/autotrade/backend/tests/test_new_strategies_smoke.py`：

```python
"""新策略沙箱冒烟测试。

对每个 scripts/new_strategies/*.py：
1. 通过 sandbox 编译实例化（验证不触发 FORBIDDEN_KEYWORDS / 未声明符号）
2. 用 200 根 mock K 线驱动 on_tick 至少一次，确认不抛异常
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


def _gen_klines(n=200, start_price=40000.0, vol_amplitude=200.0):
    """生成 n 根带正弦波动 + 噪声的 K 线，时间戳为 UTC，间隔 1h。"""
    klines = []
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i in range(n):
        # 正弦波 + 缓慢上升趋势 + 小噪声
        base = start_price * (1 + 0.1 * math.sin(i / 20.0)) + i * 5
        noise = vol_amplitude * math.sin(i * 1.7)
        close = base + noise
        open_ = base
        high = max(open_, close) + abs(noise) * 0.5
        low = min(open_, close) - abs(noise) * 0.5
        volume = 100 + 50 * abs(math.sin(i / 7.0))
        klines.append({
            "open_time": t0 + timedelta(hours=i),
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
    return _gen_klines(n=250, start_price=40000.0, vol_amplitude=800.0)


@pytest.fixture
def hour_klines():
    return _gen_klines(n=200, start_price=40000.0, vol_amplitude=200.0)


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

    # 驱动 on_tick 100 次（最后 100 根 K 线）
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

    # 不强制要求一定有 buy/sell（趋势数据可能没触发），但记录
    print(f"{filepath.name}: saw_non_hold={saw_non_hold}")
```

- [ ] **Step 3: Verify test harness fails cleanly when no strategy files exist**

```bash
cd /home/autotrade/autotrade/backend
./venv/bin/pytest tests/test_new_strategies_smoke.py -v
```

Expected: `0 tests collected` 或 `1 test, 1 passed`（因为 parametrize 列表为空）。**关键是不应该抛 ImportError 或语法错。**

- [ ] **Step 4: Commit**

```bash
cd /home/autotrade/autotrade
git add scripts/new_strategies/.gitkeep backend/tests/test_new_strategies_smoke.py
git commit -m "test(strategies): scaffolding for sandbox smoke test of new strategies

Generated with [Claude Code](https://claude.ai/code)
via [Happy](https://happy.engineering)

Co-Authored-By: Claude <noreply@anthropic.com>
Co-Authored-By: Happy <yesreply@happy.engineering>"
```

---

## Task 1: Strategy #1 — 海龟突破 (Donchian 20/10)

**Files:**
- Create: `scripts/new_strategies/turtle_breakout.py`

- [ ] **Step 1: Verify test harness picks up new file (failing test)**

The harness uses `glob("*.py")`. After we create the file, the parametrized test ID `turtle_breakout` will appear. Before writing it, confirm it doesn't exist:

```bash
ls /home/autotrade/autotrade/scripts/new_strategies/ | grep turtle
```

Expected: empty.

- [ ] **Step 2: Write strategy file**

Create `/home/autotrade/autotrade/scripts/new_strategies/turtle_breakout.py`：

```python
# @name: 海龟突破策略
# @symbol: BTCUSDT
# @timeframe: 1d
# @position_size: 15
# @position_size_type: percent
# @stop_loss: 5


class Strategy(BaseStrategy):
    """海龟交易系统经典版（Donchian 20/10）

    - 20 日新高入场（多），10 日新低出场
    - 镜像做空
    - ATR(14) * 2 移动止损 + 5% 硬止损
    - 平仓后 3 根 K 线冷却
    """

    def on_start(self):
        self.entry_price = None
        self.stop_price = None
        self.position_side = None
        self.highest_since_entry = None
        self.lowest_since_entry = None
        self.bars_since_exit = 99

    def on_tick(self, data):
        klines = data["klines"]
        price = data["price"]
        if len(klines) < 25:
            return "hold"

        highs = [k["high"] for k in klines]
        lows = [k["low"] for k in klines]
        closes = [k["close"] for k in klines]

        donch_high_20 = max(highs[-21:-1])
        donch_low_20 = min(lows[-21:-1])
        donch_high_10 = max(highs[-11:-1])
        donch_low_10 = min(lows[-11:-1])

        atr = self._atr(highs, lows, closes, 14)
        if atr is None or atr == 0:
            atr = price * 0.02

        position = self.ctx.get_position()
        if position:
            side = position.side if hasattr(position, "side") else position.get("side")
            if side == "long":
                self.highest_since_entry = max(self.highest_since_entry or price, price)
                trailing = self.highest_since_entry - 2.0 * atr
                self.stop_price = max(self.stop_price or 0.0, trailing)
                if price <= self.stop_price:
                    return self._exit("sell")
                if self.entry_price and price <= self.entry_price * 0.95:
                    return self._exit("sell")
                if price < donch_low_10:
                    return self._exit("sell")
            else:
                self.lowest_since_entry = min(self.lowest_since_entry or price, price)
                trailing = self.lowest_since_entry + 2.0 * atr
                self.stop_price = min(self.stop_price or 1e18, trailing)
                if price >= self.stop_price:
                    return self._exit("buy")
                if self.entry_price and price >= self.entry_price * 1.05:
                    return self._exit("buy")
                if price > donch_high_10:
                    return self._exit("buy")
            return "hold"

        self.bars_since_exit += 1
        if self.bars_since_exit < 3:
            return "hold"

        if price > donch_high_20:
            self._enter(price, "long", price - 2.0 * atr)
            return "buy"
        if price < donch_low_20:
            self._enter(price, "short", price + 2.0 * atr)
            return "sell"
        return "hold"

    def _atr(self, highs, lows, closes, period=14):
        if len(closes) < period + 1:
            return None
        trs = []
        for i in range(1, len(closes)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            )
            trs.append(tr)
        if len(trs) < period:
            return None
        return sum(trs[-period:]) / period

    def _enter(self, price, side, stop):
        self.entry_price = price
        self.stop_price = stop
        self.position_side = side
        self.bars_since_exit = 0
        self.highest_since_entry = price
        self.lowest_since_entry = price

    def _exit(self, signal):
        self._clear_state()
        return signal

    def _clear_state(self):
        self.entry_price = None
        self.stop_price = None
        self.position_side = None
        self.highest_since_entry = None
        self.lowest_since_entry = None
        self.bars_since_exit = 0
```

- [ ] **Step 3: Run smoke test**

```bash
cd /home/autotrade/autotrade/backend
./venv/bin/pytest tests/test_new_strategies_smoke.py::test_strategy_smoke -v -k turtle_breakout
```

Expected: PASS, prints `turtle_breakout.py: saw_non_hold=True|False`. 任何 AssertionError 或异常都需修复。

- [ ] **Step 4: Commit**

```bash
cd /home/autotrade/autotrade
git add scripts/new_strategies/turtle_breakout.py
git commit -m "feat(strategy): add Turtle Breakout (Donchian 20/10) for BTCUSDT 1d

Generated with [Claude Code](https://claude.ai/code)
via [Happy](https://happy.engineering)

Co-Authored-By: Claude <noreply@anthropic.com>
Co-Authored-By: Happy <yesreply@happy.engineering>"
```

---

## Task 2: Strategy #2 — SuperTrend

**Files:**
- Create: `scripts/new_strategies/supertrend.py`

- [ ] **Step 1: Write strategy file**

Create `/home/autotrade/autotrade/scripts/new_strategies/supertrend.py`：

```python
# @name: SuperTrend 趋势策略
# @symbol: BTCUSDT
# @timeframe: 4h
# @position_size: 15
# @position_size_type: percent
# @stop_loss: 5


class Strategy(BaseStrategy):
    """SuperTrend (ATR 10, multiplier 3) 趋势翻转跟随。

    - 价格穿越 SuperTrend 线 → 翻转方向开仓
    - ATR(14) * 2.5 移动止损 + 5% 硬止损
    """

    def on_start(self):
        self.entry_price = None
        self.stop_price = None
        self.position_side = None
        self.highest_since_entry = None
        self.lowest_since_entry = None
        self.bars_since_exit = 99
        self._st_trend = 0      # 1=多头, -1=空头, 0=未定
        self._st_value = None   # 当前 SuperTrend 值

    def on_tick(self, data):
        klines = data["klines"]
        price = data["price"]
        if len(klines) < 30:
            return "hold"

        highs = [k["high"] for k in klines]
        lows = [k["low"] for k in klines]
        closes = [k["close"] for k in klines]

        st_value, st_trend, prev_trend = self._supertrend(
            highs, lows, closes, period=10, mult=3.0,
        )
        if st_value is None:
            return "hold"
        self._st_value, self._st_trend = st_value, st_trend

        atr = self._atr(highs, lows, closes, 14) or price * 0.02

        position = self.ctx.get_position()
        if position:
            side = position.side if hasattr(position, "side") else position.get("side")
            if side == "long":
                self.highest_since_entry = max(self.highest_since_entry or price, price)
                trailing = self.highest_since_entry - 2.5 * atr
                self.stop_price = max(self.stop_price or 0.0, trailing)
                if price <= self.stop_price or (self.entry_price and price <= self.entry_price * 0.95):
                    return self._exit("sell")
                if st_trend == -1:
                    return self._exit("sell")
            else:
                self.lowest_since_entry = min(self.lowest_since_entry or price, price)
                trailing = self.lowest_since_entry + 2.5 * atr
                self.stop_price = min(self.stop_price or 1e18, trailing)
                if price >= self.stop_price or (self.entry_price and price >= self.entry_price * 1.05):
                    return self._exit("buy")
                if st_trend == 1:
                    return self._exit("buy")
            return "hold"

        self.bars_since_exit += 1
        if self.bars_since_exit < 3:
            return "hold"

        # 翻转入场
        if prev_trend == -1 and st_trend == 1:
            self._enter(price, "long", price - 2.5 * atr)
            return "buy"
        if prev_trend == 1 and st_trend == -1:
            self._enter(price, "short", price + 2.5 * atr)
            return "sell"
        return "hold"

    def _supertrend(self, highs, lows, closes, period=10, mult=3.0):
        """返回 (current_value, current_trend, prev_trend)。"""
        if len(closes) < period + 2:
            return None, 0, 0
        # 计算 ATR (Wilder 简化 = SMA)
        trs = []
        for i in range(1, len(closes)):
            trs.append(max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            ))
        if len(trs) < period:
            return None, 0, 0
        atr_series = []
        for i in range(period - 1, len(trs)):
            atr_series.append(sum(trs[i - period + 1: i + 1]) / period)
        # 对齐 atr_series 与 closes：atr_series[k] 对应 closes[k + period]
        offset = len(closes) - len(atr_series)

        final_upper = [0.0] * len(closes)
        final_lower = [0.0] * len(closes)
        trend = [0] * len(closes)
        for k in range(len(atr_series)):
            i = k + offset
            hl2 = (highs[i] + lows[i]) / 2.0
            basic_upper = hl2 + mult * atr_series[k]
            basic_lower = hl2 - mult * atr_series[k]
            if i == offset:
                final_upper[i] = basic_upper
                final_lower[i] = basic_lower
                trend[i] = 1 if closes[i] > basic_upper else -1
            else:
                final_upper[i] = (
                    basic_upper if (basic_upper < final_upper[i - 1] or closes[i - 1] > final_upper[i - 1])
                    else final_upper[i - 1]
                )
                final_lower[i] = (
                    basic_lower if (basic_lower > final_lower[i - 1] or closes[i - 1] < final_lower[i - 1])
                    else final_lower[i - 1]
                )
                if trend[i - 1] == 1:
                    trend[i] = -1 if closes[i] < final_lower[i] else 1
                elif trend[i - 1] == -1:
                    trend[i] = 1 if closes[i] > final_upper[i] else -1
                else:
                    trend[i] = 1 if closes[i] > final_upper[i] else -1
        cur_trend = trend[-1]
        prev_trend = trend[-2]
        cur_value = final_lower[-1] if cur_trend == 1 else final_upper[-1]
        return cur_value, cur_trend, prev_trend

    def _atr(self, highs, lows, closes, period=14):
        if len(closes) < period + 1:
            return None
        trs = []
        for i in range(1, len(closes)):
            trs.append(max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            ))
        return sum(trs[-period:]) / period

    def _enter(self, price, side, stop):
        self.entry_price = price
        self.stop_price = stop
        self.position_side = side
        self.bars_since_exit = 0
        self.highest_since_entry = price
        self.lowest_since_entry = price

    def _exit(self, signal):
        self._clear_state()
        return signal

    def _clear_state(self):
        self.entry_price = None
        self.stop_price = None
        self.position_side = None
        self.highest_since_entry = None
        self.lowest_since_entry = None
        self.bars_since_exit = 0
```

- [ ] **Step 2: Run smoke test**

```bash
cd /home/autotrade/autotrade/backend
./venv/bin/pytest tests/test_new_strategies_smoke.py -v -k supertrend
```

Expected: PASS

- [ ] **Step 3: Commit**

```bash
cd /home/autotrade/autotrade
git add scripts/new_strategies/supertrend.py
git commit -m "feat(strategy): add SuperTrend (ATR 10x3) for BTCUSDT 4h

Generated with [Claude Code](https://claude.ai/code)
via [Happy](https://happy.engineering)

Co-Authored-By: Claude <noreply@anthropic.com>
Co-Authored-By: Happy <yesreply@happy.engineering>"
```

---

## Task 3: Strategy #3 — VWAP 日内回归

**Files:**
- Create: `scripts/new_strategies/vwap_reversion.py`

- [ ] **Step 1: Write strategy file**

```python
# @name: VWAP 日内回归策略
# @symbol: ETHUSDT
# @timeframe: 15m
# @position_size: 10
# @position_size_type: percent
# @stop_loss: 5


class Strategy(BaseStrategy):
    """VWAP 日内回归（UTC 0 点重置）。

    - 价格偏离当日 VWAP > 1.5σ → 反向开仓
    - 价格回归 |dev| < 0.3σ → 平仓
    - 仅当本根 K 线属于"今日 UTC"才计入 VWAP
    """

    def on_start(self):
        self.entry_price = None
        self.stop_price = None
        self.position_side = None
        self.bars_since_exit = 99

    def on_tick(self, data):
        klines = data["klines"]
        price = data["price"]
        if len(klines) < 5:
            return "hold"

        last_time = klines[-1]["open_time"]
        # 取本日 UTC 内的 K 线
        today = last_time.date()
        today_bars = [k for k in klines if k["open_time"].date() == today]
        if len(today_bars) < 3:
            return "hold"

        # VWAP + 加权 stdev
        cum_pv = 0.0
        cum_v = 0.0
        for k in today_bars:
            typical = (k["high"] + k["low"] + k["close"]) / 3.0
            cum_pv += typical * k["volume"]
            cum_v += k["volume"]
        if cum_v == 0:
            return "hold"
        vwap = cum_pv / cum_v
        var_w = sum(
            ((k["high"] + k["low"] + k["close"]) / 3.0 - vwap) ** 2 * k["volume"]
            for k in today_bars
        ) / cum_v
        sigma = var_w ** 0.5
        if sigma == 0:
            return "hold"

        dev = price - vwap

        # 持仓管理（仅硬止损 + 回归止盈，无 ATR 移动止损以快速翻仓）
        position = self.ctx.get_position()
        if position:
            side = position.side if hasattr(position, "side") else position.get("side")
            if side == "long":
                if self.entry_price and price <= self.entry_price * 0.95:
                    return self._exit("sell")
                if dev >= -0.3 * sigma:
                    return self._exit("sell")
            else:
                if self.entry_price and price >= self.entry_price * 1.05:
                    return self._exit("buy")
                if dev <= 0.3 * sigma:
                    return self._exit("buy")
            return "hold"

        self.bars_since_exit += 1
        if self.bars_since_exit < 3:
            return "hold"

        if dev <= -1.5 * sigma:
            self._enter(price, "long")
            return "buy"
        if dev >= 1.5 * sigma:
            self._enter(price, "short")
            return "sell"
        return "hold"

    def _enter(self, price, side):
        self.entry_price = price
        self.position_side = side
        self.bars_since_exit = 0

    def _exit(self, signal):
        self.entry_price = None
        self.position_side = None
        self.bars_since_exit = 0
        return signal
```

- [ ] **Step 2: Run smoke test**

```bash
./venv/bin/pytest tests/test_new_strategies_smoke.py -v -k vwap_reversion
```

Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add scripts/new_strategies/vwap_reversion.py
git commit -m "feat(strategy): add VWAP intraday reversion for ETHUSDT 15m

Generated with [Claude Code](https://claude.ai/code)
via [Happy](https://happy.engineering)

Co-Authored-By: Claude <noreply@anthropic.com>
Co-Authored-By: Happy <yesreply@happy.engineering>"
```

---

## Task 4: Strategy #4 — 区间网格

**Files:**
- Create: `scripts/new_strategies/grid_range.py`

- [ ] **Step 1: Write strategy file**

```python
# @name: 区间网格策略
# @symbol: ETHUSDT
# @timeframe: 1h
# @position_size: 1
# @position_size_type: percent


class Strategy(BaseStrategy):
    """区间网格 — center=EMA50, 区间±5%, 10 格。

    - 价格落入新格 → 买入 1% 总仓
    - 价格涨/跌至上/下一格 → 卖出该格
    - 价格超出区间 5% → 全部平仓 + 停止 24h
    - 24h 后用最新 EMA50 重置 center
    """

    def on_start(self):
        self.center = None
        self.last_reset_time = None
        self.held_grids = set()  # 已持仓的格子索引
        self.entry_prices = {}   # grid_idx -> entry_price
        self.cooldown_until = None  # datetime
        self.grid_count = 10
        self.range_pct = 0.05

    def on_tick(self, data):
        klines = data["klines"]
        price = data["price"]
        now = klines[-1]["open_time"]
        if len(klines) < 60:
            return "hold"

        closes = [k["close"] for k in klines]
        ema50 = calculate_ema(closes, 50)
        if ema50 is None:
            return "hold"

        # 冷却中
        if self.cooldown_until is not None and now < self.cooldown_until:
            return "hold"
        if self.cooldown_until is not None and now >= self.cooldown_until:
            self.cooldown_until = None

        # 首次或 24h 重置 center
        if self.center is None or self.last_reset_time is None or (
            (now - self.last_reset_time).total_seconds() >= 86400
        ):
            self.center = ema50
            self.last_reset_time = now

        low_bound = self.center * (1 - self.range_pct)
        high_bound = self.center * (1 + self.range_pct)

        # 超出区间 → 全部平仓 + 冷却 24h
        if price < low_bound * 0.95 or price > high_bound * 1.05:
            if self.held_grids:
                self.held_grids.clear()
                self.entry_prices.clear()
                self.cooldown_until = now + (now - now)  # 占位
                # 用 24h timedelta；datetime 在沙箱里不能 import，但 open_time 已经是 datetime
                # timedelta 可通过算术得到：
                self.cooldown_until = now.__class__.fromtimestamp(
                    now.timestamp() + 86400, tz=now.tzinfo,
                )
                return "sell"
            return "hold"

        # 网格索引：0..grid_count-1，从低到高
        grid_width = (high_bound - low_bound) / self.grid_count
        idx = int((price - low_bound) / grid_width)
        if idx < 0 or idx >= self.grid_count:
            return "hold"

        # 卖出：已持仓格 +1 → 平掉低位格（涨上来一格）
        for held_idx in list(self.held_grids):
            sell_target = low_bound + (held_idx + 1) * grid_width
            if price >= sell_target:
                self.held_grids.discard(held_idx)
                self.entry_prices.pop(held_idx, None)
                return "sell"

        # 买入：当前格未持仓 → 买
        if idx not in self.held_grids:
            self.held_grids.add(idx)
            self.entry_prices[idx] = price
            return "buy"

        return "hold"
```

> **注意：** 这个策略每次只买/卖 `position_size=1%`（每格固定 1% 总仓）。网格策略的 sell 是部分平仓，需要 `sell_size_pct` 按比例。但当前 `sell_size_pct` 默认 100%，会全平。**简化：第一版每个 buy 信号买 1%，每个 sell 信号卖 100% 当前持仓**（行为退化为"震荡反复买卖"，可以接受作为实验）。后续可加 `sell_size_pct=10` (10% of held) 调优。

- [ ] **Step 2: Run smoke test**

```bash
./venv/bin/pytest tests/test_new_strategies_smoke.py -v -k grid_range
```

Expected: PASS

- [ ] **Step 3: Commit**

```bash
git add scripts/new_strategies/grid_range.py
git commit -m "feat(strategy): add range grid strategy for ETHUSDT 1h

Generated with [Claude Code](https://claude.ai/code)
via [Happy](https://happy.engineering)

Co-Authored-By: Claude <noreply@anthropic.com>
Co-Authored-By: Happy <yesreply@happy.engineering>"
```

---

## Task 5: Strategy #5 — MTF 双周期共振

**Files:**
- Create: `scripts/new_strategies/mtf_resonance.py`

- [ ] **Step 1: Write strategy file**

```python
# @name: MTF 双周期共振策略
# @symbol: BTCUSDT
# @timeframe: 1h
# @position_size: 15
# @position_size_type: percent
# @stop_loss: 5


class Strategy(BaseStrategy):
    """1h MACD 入场，必须叠加 1d EMA50 趋势同向。

    - 1h 金叉 ∧ daily_close > daily_ema50 ∧ daily_ema50 斜率>0 → 买
    - 1h 死叉 ∧ daily_close < daily_ema50 ∧ daily_ema50 斜率<0 → 卖
    - ATR(14) * 2.5 移动止损 + 5% 硬止损
    """

    def on_start(self):
        self.entry_price = None
        self.stop_price = None
        self.position_side = None
        self.highest_since_entry = None
        self.lowest_since_entry = None
        self.bars_since_exit = 99

    def on_tick(self, data):
        klines = data["klines"]
        daily = data.get("daily_klines") or []
        price = data["price"]
        if len(klines) < 40 or len(daily) < 55:
            return "hold"

        closes = [k["close"] for k in klines]
        highs = [k["high"] for k in klines]
        lows = [k["low"] for k in klines]

        macd_sig = check_macd_signal(closes, 12, 26, 9)
        if macd_sig not in ("golden", "death", "above_zero", "below_zero", None):
            macd_sig = None

        daily_closes = [k["close"] for k in daily]
        d_ema50_now = calculate_ema(daily_closes, 50)
        d_ema50_prev = calculate_ema(daily_closes[:-5], 50)
        if d_ema50_now is None or d_ema50_prev is None:
            return "hold"
        d_slope_up = d_ema50_now > d_ema50_prev
        d_slope_down = d_ema50_now < d_ema50_prev
        d_close = daily_closes[-1]
        bull_trend = d_close > d_ema50_now and d_slope_up
        bear_trend = d_close < d_ema50_now and d_slope_down

        atr = self._atr(highs, lows, closes, 14) or price * 0.02

        position = self.ctx.get_position()
        if position:
            side = position.side if hasattr(position, "side") else position.get("side")
            if side == "long":
                self.highest_since_entry = max(self.highest_since_entry or price, price)
                trailing = self.highest_since_entry - 2.5 * atr
                self.stop_price = max(self.stop_price or 0.0, trailing)
                if price <= self.stop_price or (self.entry_price and price <= self.entry_price * 0.95):
                    return self._exit("sell")
                if macd_sig == "death" or bear_trend:
                    return self._exit("sell")
            else:
                self.lowest_since_entry = min(self.lowest_since_entry or price, price)
                trailing = self.lowest_since_entry + 2.5 * atr
                self.stop_price = min(self.stop_price or 1e18, trailing)
                if price >= self.stop_price or (self.entry_price and price >= self.entry_price * 1.05):
                    return self._exit("buy")
                if macd_sig == "golden" or bull_trend:
                    return self._exit("buy")
            return "hold"

        self.bars_since_exit += 1
        if self.bars_since_exit < 3:
            return "hold"

        if macd_sig == "golden" and bull_trend:
            self._enter(price, "long", price - 2.5 * atr)
            return "buy"
        if macd_sig == "death" and bear_trend:
            self._enter(price, "short", price + 2.5 * atr)
            return "sell"
        return "hold"

    def _atr(self, highs, lows, closes, period=14):
        if len(closes) < period + 1:
            return None
        trs = []
        for i in range(1, len(closes)):
            trs.append(max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            ))
        return sum(trs[-period:]) / period

    def _enter(self, price, side, stop):
        self.entry_price = price
        self.stop_price = stop
        self.position_side = side
        self.bars_since_exit = 0
        self.highest_since_entry = price
        self.lowest_since_entry = price

    def _exit(self, signal):
        self.entry_price = None
        self.stop_price = None
        self.position_side = None
        self.highest_since_entry = None
        self.lowest_since_entry = None
        self.bars_since_exit = 0
        return signal
```

- [ ] **Step 2: Run smoke test**

```bash
./venv/bin/pytest tests/test_new_strategies_smoke.py -v -k mtf_resonance
```

- [ ] **Step 3: Commit**

```bash
git add scripts/new_strategies/mtf_resonance.py
git commit -m "feat(strategy): add MTF dual-timeframe (1h+1d) resonance for BTCUSDT

Generated with [Claude Code](https://claude.ai/code)
via [Happy](https://happy.engineering)

Co-Authored-By: Claude <noreply@anthropic.com>
Co-Authored-By: Happy <yesreply@happy.engineering>"
```

---

## Task 6: Strategy #6 — Squeeze 波动率突破

**Files:** Create: `scripts/new_strategies/squeeze_breakout.py`

- [ ] **Step 1: Write strategy file**

```python
# @name: Squeeze 波动率突破策略
# @symbol: SOLUSDT
# @timeframe: 1h
# @position_size: 10
# @position_size_type: percent
# @stop_loss: 5


class Strategy(BaseStrategy):
    """BB(20,2) 在 KC(20,1.5) 内 >=5 根后突破方向开仓。"""

    def on_start(self):
        self.entry_price = None
        self.stop_price = None
        self.position_side = None
        self.highest_since_entry = None
        self.lowest_since_entry = None
        self.bars_since_exit = 99
        self.squeeze_bars = 0

    def on_tick(self, data):
        klines = data["klines"]
        price = data["price"]
        if len(klines) < 30:
            return "hold"

        closes = [k["close"] for k in klines]
        highs = [k["high"] for k in klines]
        lows = [k["low"] for k in klines]

        bb = calculate_bollinger_bands(closes, 20, 2.0)
        if bb is None:
            return "hold"

        # Keltner Channel: EMA(20) ± 1.5 * ATR(20)
        ema20 = calculate_ema(closes, 20)
        atr20 = self._atr(highs, lows, closes, 20)
        if ema20 is None or atr20 is None:
            return "hold"
        kc_upper = ema20 + 1.5 * atr20
        kc_lower = ema20 - 1.5 * atr20

        squeezed = bb["upper"] < kc_upper and bb["lower"] > kc_lower
        if squeezed:
            self.squeeze_bars += 1
        else:
            prior_squeeze = self.squeeze_bars
            self.squeeze_bars = 0

        atr14 = self._atr(highs, lows, closes, 14) or price * 0.02

        position = self.ctx.get_position()
        if position:
            side = position.side if hasattr(position, "side") else position.get("side")
            if side == "long":
                self.highest_since_entry = max(self.highest_since_entry or price, price)
                trailing = self.highest_since_entry - 2.0 * atr14
                self.stop_price = max(self.stop_price or 0.0, trailing)
                if price <= self.stop_price or (self.entry_price and price <= self.entry_price * 0.95):
                    return self._exit("sell")
            else:
                self.lowest_since_entry = min(self.lowest_since_entry or price, price)
                trailing = self.lowest_since_entry + 2.0 * atr14
                self.stop_price = min(self.stop_price or 1e18, trailing)
                if price >= self.stop_price or (self.entry_price and price >= self.entry_price * 1.05):
                    return self._exit("buy")
            return "hold"

        self.bars_since_exit += 1
        if self.bars_since_exit < 3:
            return "hold"

        # 入场：上一根仍是 squeeze (>=5)，本根突破方向
        if not squeezed and self.bars_since_exit > 0:
            # squeeze_bars 已 reset 为 0；用 prior 判定（保留本地变量）
            if 'prior_squeeze' in dir() and prior_squeeze >= 5:
                if price > bb["upper"]:
                    self._enter(price, "long", price - 2.0 * atr14)
                    return "buy"
                if price < bb["lower"]:
                    self._enter(price, "short", price + 2.0 * atr14)
                    return "sell"
        return "hold"

    def _atr(self, highs, lows, closes, period):
        if len(closes) < period + 1:
            return None
        trs = []
        for i in range(1, len(closes)):
            trs.append(max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            ))
        return sum(trs[-period:]) / period

    def _enter(self, price, side, stop):
        self.entry_price = price
        self.stop_price = stop
        self.position_side = side
        self.bars_since_exit = 0
        self.highest_since_entry = price
        self.lowest_since_entry = price

    def _exit(self, signal):
        self.entry_price = None
        self.stop_price = None
        self.position_side = None
        self.highest_since_entry = None
        self.lowest_since_entry = None
        self.bars_since_exit = 0
        return signal
```

> **注意：** `'prior_squeeze' in dir()` 不可靠（dir() 是 builtin 但行为复杂）。**实施前改为更稳定的方式：将 `prior_squeeze` 用 `self._prior_squeeze` 状态保存**（在 squeeze 退出时记录，在突破判定后归零）。改写如下：

```python
# on_start 追加: self._prior_squeeze_bars = 0
# squeeze 处理:
if squeezed:
    self.squeeze_bars += 1
else:
    if self.squeeze_bars > 0:
        self._prior_squeeze_bars = self.squeeze_bars
    self.squeeze_bars = 0
# 入场判定:
if not squeezed and self._prior_squeeze_bars >= 5:
    if price > bb["upper"]:
        self._prior_squeeze_bars = 0
        self._enter(price, "long", price - 2.0 * atr14)
        return "buy"
    if price < bb["lower"]:
        self._prior_squeeze_bars = 0
        self._enter(price, "short", price + 2.0 * atr14)
        return "sell"
# 给 prior_squeeze 一个有效期（10 根后清零），避免久远的 squeeze 误触发：
if self._prior_squeeze_bars > 0:
    if not hasattr(self, '_prior_age'):
        self._prior_age = 0
    self._prior_age += 1
    if self._prior_age > 10:
        self._prior_squeeze_bars = 0
        self._prior_age = 0
```

请在写文件时使用上面这一稳定版本（替换原 `prior_squeeze` 局部变量逻辑）。

- [ ] **Step 2: Run smoke test**

```bash
./venv/bin/pytest tests/test_new_strategies_smoke.py -v -k squeeze
```

- [ ] **Step 3: Commit**

```bash
git add scripts/new_strategies/squeeze_breakout.py
git commit -m "feat(strategy): add BB/KC squeeze breakout for SOLUSDT 1h

Generated with [Claude Code](https://claude.ai/code)
via [Happy](https://happy.engineering)

Co-Authored-By: Claude <noreply@anthropic.com>
Co-Authored-By: Happy <yesreply@happy.engineering>"
```

---

## Task 7: Strategy #7 — ADX 强趋势通道

**Files:** Create: `scripts/new_strategies/adx_keltner.py`

- [ ] **Step 1: Write strategy file**

```python
# @name: ADX 强趋势通道策略
# @symbol: BTCUSDT
# @timeframe: 4h
# @position_size: 12
# @position_size_type: percent
# @stop_loss: 5


class Strategy(BaseStrategy):
    """ADX(14) > 25 时跟随 Keltner 通道方向。

    - +DI > -DI ∧ price > KC.middle → 买
    - -DI > +DI ∧ price < KC.middle → 卖
    - ADX < 20 或穿对侧轨 → 平仓
    """

    def on_start(self):
        self.entry_price = None
        self.stop_price = None
        self.position_side = None
        self.highest_since_entry = None
        self.lowest_since_entry = None
        self.bars_since_exit = 99

    def on_tick(self, data):
        klines = data["klines"]
        price = data["price"]
        if len(klines) < 40:
            return "hold"

        highs = [k["high"] for k in klines]
        lows = [k["low"] for k in klines]
        closes = [k["close"] for k in klines]

        adx, plus_di, minus_di = self._adx(highs, lows, closes, 14)
        if adx is None:
            return "hold"

        ema20 = calculate_ema(closes, 20)
        atr20 = self._atr(highs, lows, closes, 20)
        if ema20 is None or atr20 is None:
            return "hold"
        kc_upper = ema20 + 2.0 * atr20
        kc_lower = ema20 - 2.0 * atr20
        kc_mid = ema20

        atr14 = self._atr(highs, lows, closes, 14) or price * 0.02

        position = self.ctx.get_position()
        if position:
            side = position.side if hasattr(position, "side") else position.get("side")
            if side == "long":
                self.highest_since_entry = max(self.highest_since_entry or price, price)
                trailing = self.highest_since_entry - 2.5 * atr14
                self.stop_price = max(self.stop_price or 0.0, trailing)
                if price <= self.stop_price or (self.entry_price and price <= self.entry_price * 0.95):
                    return self._exit("sell")
                if adx < 20 or price < kc_lower:
                    return self._exit("sell")
            else:
                self.lowest_since_entry = min(self.lowest_since_entry or price, price)
                trailing = self.lowest_since_entry + 2.5 * atr14
                self.stop_price = min(self.stop_price or 1e18, trailing)
                if price >= self.stop_price or (self.entry_price and price >= self.entry_price * 1.05):
                    return self._exit("buy")
                if adx < 20 or price > kc_upper:
                    return self._exit("buy")
            return "hold"

        self.bars_since_exit += 1
        if self.bars_since_exit < 3:
            return "hold"

        if adx > 25 and plus_di > minus_di and price > kc_mid:
            self._enter(price, "long", price - 2.5 * atr14)
            return "buy"
        if adx > 25 and minus_di > plus_di and price < kc_mid:
            self._enter(price, "short", price + 2.5 * atr14)
            return "sell"
        return "hold"

    def _adx(self, highs, lows, closes, period=14):
        if len(closes) < period * 2:
            return None, 0.0, 0.0
        plus_dm = [0.0]
        minus_dm = [0.0]
        trs = [0.0]
        for i in range(1, len(closes)):
            up = highs[i] - highs[i - 1]
            down = lows[i - 1] - lows[i]
            plus_dm.append(up if (up > down and up > 0) else 0.0)
            minus_dm.append(down if (down > up and down > 0) else 0.0)
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            )
            trs.append(tr)

        # Wilder smoothing
        def smooth(seq, n):
            if len(seq) < n + 1:
                return None
            sm = [sum(seq[1:n + 1])]
            for v in seq[n + 1:]:
                sm.append(sm[-1] - sm[-1] / n + v)
            return sm

        atr_s = smooth(trs, period)
        plus_s = smooth(plus_dm, period)
        minus_s = smooth(minus_dm, period)
        if atr_s is None or plus_s is None or minus_s is None:
            return None, 0.0, 0.0

        dxs = []
        for a, p, m in zip(atr_s, plus_s, minus_s):
            if a == 0:
                dxs.append(0.0)
                continue
            plus_di_i = 100 * p / a
            minus_di_i = 100 * m / a
            denom = plus_di_i + minus_di_i
            dxs.append(100 * abs(plus_di_i - minus_di_i) / denom if denom > 0 else 0.0)

        if len(dxs) < period:
            return None, 0.0, 0.0
        adx = sum(dxs[:period]) / period
        for v in dxs[period:]:
            adx = (adx * (period - 1) + v) / period

        # 最终 +DI / -DI
        plus_di = 100 * plus_s[-1] / atr_s[-1] if atr_s[-1] > 0 else 0.0
        minus_di = 100 * minus_s[-1] / atr_s[-1] if atr_s[-1] > 0 else 0.0
        return adx, plus_di, minus_di

    def _atr(self, highs, lows, closes, period):
        if len(closes) < period + 1:
            return None
        trs = []
        for i in range(1, len(closes)):
            trs.append(max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            ))
        return sum(trs[-period:]) / period

    def _enter(self, price, side, stop):
        self.entry_price = price
        self.stop_price = stop
        self.position_side = side
        self.bars_since_exit = 0
        self.highest_since_entry = price
        self.lowest_since_entry = price

    def _exit(self, signal):
        self.entry_price = None
        self.stop_price = None
        self.position_side = None
        self.highest_since_entry = None
        self.lowest_since_entry = None
        self.bars_since_exit = 0
        return signal
```

- [ ] **Step 2: Run smoke test**

```bash
./venv/bin/pytest tests/test_new_strategies_smoke.py -v -k adx_keltner
```

- [ ] **Step 3: Commit**

```bash
git add scripts/new_strategies/adx_keltner.py
git commit -m "feat(strategy): add ADX(14)>25 + Keltner channel follow for BTCUSDT 4h

Generated with [Claude Code](https://claude.ai/code)
via [Happy](https://happy.engineering)

Co-Authored-By: Claude <noreply@anthropic.com>
Co-Authored-By: Happy <yesreply@happy.engineering>"
```

---

## Task 8: Strategy #8 — StochRSI 反转

**Files:** Create: `scripts/new_strategies/stoch_rsi_reversal.py`

- [ ] **Step 1: Write strategy file**

```python
# @name: StochRSI 反转策略
# @symbol: ETHUSDT
# @timeframe: 1h
# @position_size: 10
# @position_size_type: percent
# @stop_loss: 5


class Strategy(BaseStrategy):
    """Stochastic RSI 极值反转。

    - K<20 且向上钩头 → 买
    - K>80 且向下钩头 → 卖
    - 回归 40-60 → 平仓
    """

    def on_start(self):
        self.entry_price = None
        self.stop_price = None
        self.position_side = None
        self.highest_since_entry = None
        self.lowest_since_entry = None
        self.bars_since_exit = 99

    def on_tick(self, data):
        klines = data["klines"]
        price = data["price"]
        if len(klines) < 40:
            return "hold"

        closes = [k["close"] for k in klines]
        highs = [k["high"] for k in klines]
        lows = [k["low"] for k in klines]

        # 计算最近 30 根的 RSI 序列
        rsi_series = []
        for end in range(15, len(closes) + 1):
            sub = closes[:end]
            r = calculate_rsi(sub, 14)
            if r is not None:
                rsi_series.append(r)
        if len(rsi_series) < 17:
            return "hold"

        # StochRSI: 在最近 14 个 RSI 上取
        window = rsi_series[-14:]
        rmin, rmax = min(window), max(window)
        cur_sr = (rsi_series[-1] - rmin) / (rmax - rmin) * 100 if rmax != rmin else 50.0
        # 上一根的 StochRSI
        window_prev = rsi_series[-15:-1]
        rmin_p, rmax_p = min(window_prev), max(window_prev)
        prev_sr = (rsi_series[-2] - rmin_p) / (rmax_p - rmin_p) * 100 if rmax_p != rmin_p else 50.0

        # SMA(3) 平滑得 %K
        k_series_raw = []
        for j in range(2, 15):  # 取最近 13 根，需 3 根算 SMA
            sub_rsi = rsi_series[-14 + j - 2: -14 + j + 1] if (-14 + j + 1) != 0 else rsi_series[-14 + j - 2:]
            # 简化：用 cur_sr / prev_sr / 三根前
            pass
        # 简化版：直接用 cur_sr / prev_sr 作 K
        k_now = cur_sr
        k_prev = prev_sr

        atr = self._atr(highs, lows, closes, 14) or price * 0.02

        position = self.ctx.get_position()
        if position:
            side = position.side if hasattr(position, "side") else position.get("side")
            if side == "long":
                self.highest_since_entry = max(self.highest_since_entry or price, price)
                trailing = self.highest_since_entry - 2.5 * atr
                self.stop_price = max(self.stop_price or 0.0, trailing)
                if price <= self.stop_price or (self.entry_price and price <= self.entry_price * 0.95):
                    return self._exit("sell")
                if 40 <= k_now <= 60:
                    return self._exit("sell")
            else:
                self.lowest_since_entry = min(self.lowest_since_entry or price, price)
                trailing = self.lowest_since_entry + 2.5 * atr
                self.stop_price = min(self.stop_price or 1e18, trailing)
                if price >= self.stop_price or (self.entry_price and price >= self.entry_price * 1.05):
                    return self._exit("buy")
                if 40 <= k_now <= 60:
                    return self._exit("buy")
            return "hold"

        self.bars_since_exit += 1
        if self.bars_since_exit < 3:
            return "hold"

        if k_now < 20 and k_now > k_prev:
            self._enter(price, "long", price - 2.5 * atr)
            return "buy"
        if k_now > 80 and k_now < k_prev:
            self._enter(price, "short", price + 2.5 * atr)
            return "sell"
        return "hold"

    def _atr(self, highs, lows, closes, period=14):
        if len(closes) < period + 1:
            return None
        trs = []
        for i in range(1, len(closes)):
            trs.append(max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            ))
        return sum(trs[-period:]) / period

    def _enter(self, price, side, stop):
        self.entry_price = price
        self.stop_price = stop
        self.position_side = side
        self.bars_since_exit = 0
        self.highest_since_entry = price
        self.lowest_since_entry = price

    def _exit(self, signal):
        self.entry_price = None
        self.stop_price = None
        self.position_side = None
        self.highest_since_entry = None
        self.lowest_since_entry = None
        self.bars_since_exit = 0
        return signal
```

> **注意：** 上面 `k_series_raw` 段有冗余 `pass` 死代码（保留是为了说明意图）。**实施时请删除**，最终只保留 `k_now = cur_sr` / `k_prev = prev_sr` 的简化路径。SMA(3) 平滑可作为后续优化。

- [ ] **Step 2: Run smoke test**

```bash
./venv/bin/pytest tests/test_new_strategies_smoke.py -v -k stoch_rsi
```

- [ ] **Step 3: Commit**

```bash
git add scripts/new_strategies/stoch_rsi_reversal.py
git commit -m "feat(strategy): add StochRSI reversal for ETHUSDT 1h

Generated with [Claude Code](https://claude.ai/code)
via [Happy](https://happy.engineering)

Co-Authored-By: Claude <noreply@anthropic.com>
Co-Authored-By: Happy <yesreply@happy.engineering>"
```

---

## Task 9: Strategy #9 — Heikin Ashi 趋势骑乘

**Files:** Create: `scripts/new_strategies/heikin_ashi_trend.py`

- [ ] **Step 1: Write strategy file**

```python
# @name: Heikin Ashi 趋势骑乘策略
# @symbol: SOLUSDT
# @timeframe: 4h
# @position_size: 10
# @position_size_type: percent
# @stop_loss: 5


class Strategy(BaseStrategy):
    """Heikin Ashi 三根同色实体 + 无对侧影线 → 顺势入场。"""

    def on_start(self):
        self.entry_price = None
        self.stop_price = None
        self.position_side = None
        self.highest_since_entry = None
        self.lowest_since_entry = None
        self.bars_since_exit = 99

    def _heikin_ashi(self, klines):
        """返回 HA OHLC 列表。"""
        ha = []
        for i, k in enumerate(klines):
            ha_close = (k["open"] + k["high"] + k["low"] + k["close"]) / 4.0
            if i == 0:
                ha_open = (k["open"] + k["close"]) / 2.0
            else:
                ha_open = (ha[-1]["open"] + ha[-1]["close"]) / 2.0
            ha_high = max(k["high"], ha_open, ha_close)
            ha_low = min(k["low"], ha_open, ha_close)
            ha.append({"open": ha_open, "high": ha_high, "low": ha_low, "close": ha_close})
        return ha

    def on_tick(self, data):
        klines = data["klines"]
        price = data["price"]
        if len(klines) < 30:  # HA 需要稳定一段
            return "hold"

        ha = self._heikin_ashi(klines)
        last3 = ha[-3:]
        tol = price * 0.0005  # 0.05% 容差

        bull = all(c["close"] > c["open"] for c in last3) and all(
            c["low"] >= min(c["open"], c["close"]) - tol for c in last3
        )
        bear = all(c["close"] < c["open"] for c in last3) and all(
            c["high"] <= max(c["open"], c["close"]) + tol for c in last3
        )

        highs = [k["high"] for k in klines]
        lows = [k["low"] for k in klines]
        closes = [k["close"] for k in klines]
        atr = self._atr(highs, lows, closes, 14) or price * 0.02

        position = self.ctx.get_position()
        if position:
            side = position.side if hasattr(position, "side") else position.get("side")
            cur = ha[-1]
            if side == "long":
                self.highest_since_entry = max(self.highest_since_entry or price, price)
                trailing = self.highest_since_entry - 2.5 * atr
                self.stop_price = max(self.stop_price or 0.0, trailing)
                if price <= self.stop_price or (self.entry_price and price <= self.entry_price * 0.95):
                    return self._exit("sell")
                # 反色或长上影：退出
                if cur["close"] < cur["open"]:
                    return self._exit("sell")
                if (cur["high"] - max(cur["open"], cur["close"])) > 2 * abs(cur["close"] - cur["open"]):
                    return self._exit("sell")
            else:
                self.lowest_since_entry = min(self.lowest_since_entry or price, price)
                trailing = self.lowest_since_entry + 2.5 * atr
                self.stop_price = min(self.stop_price or 1e18, trailing)
                if price >= self.stop_price or (self.entry_price and price >= self.entry_price * 1.05):
                    return self._exit("buy")
                if cur["close"] > cur["open"]:
                    return self._exit("buy")
                if (min(cur["open"], cur["close"]) - cur["low"]) > 2 * abs(cur["close"] - cur["open"]):
                    return self._exit("buy")
            return "hold"

        self.bars_since_exit += 1
        if self.bars_since_exit < 3:
            return "hold"

        if bull:
            self._enter(price, "long", price - 2.5 * atr)
            return "buy"
        if bear:
            self._enter(price, "short", price + 2.5 * atr)
            return "sell"
        return "hold"

    def _atr(self, highs, lows, closes, period=14):
        if len(closes) < period + 1:
            return None
        trs = []
        for i in range(1, len(closes)):
            trs.append(max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            ))
        return sum(trs[-period:]) / period

    def _enter(self, price, side, stop):
        self.entry_price = price
        self.stop_price = stop
        self.position_side = side
        self.bars_since_exit = 0
        self.highest_since_entry = price
        self.lowest_since_entry = price

    def _exit(self, signal):
        self.entry_price = None
        self.stop_price = None
        self.position_side = None
        self.highest_since_entry = None
        self.lowest_since_entry = None
        self.bars_since_exit = 0
        return signal
```

- [ ] **Step 2: Run smoke test**

```bash
./venv/bin/pytest tests/test_new_strategies_smoke.py -v -k heikin_ashi
```

- [ ] **Step 3: Commit**

```bash
git add scripts/new_strategies/heikin_ashi_trend.py
git commit -m "feat(strategy): add Heikin Ashi trend riding for SOLUSDT 4h

Generated with [Claude Code](https://claude.ai/code)
via [Happy](https://happy.engineering)

Co-Authored-By: Claude <noreply@anthropic.com>
Co-Authored-By: Happy <yesreply@happy.engineering>"
```

---

## Task 10: Strategy #10 — Z-score 均值回归

**Files:** Create: `scripts/new_strategies/zscore_reversion.py`

- [ ] **Step 1: Write strategy file**

```python
# @name: Z-score 均值回归策略
# @symbol: BTCUSDT
# @timeframe: 1h
# @position_size: 10
# @position_size_type: percent
# @stop_loss: 5


class Strategy(BaseStrategy):
    """Z-score(20) 极端反转。

    - z<-2 → 买；z>+2 → 卖
    - |z|<0.5 → 平仓 + 5% 硬止损
    """

    def on_start(self):
        self.entry_price = None
        self.position_side = None
        self.bars_since_exit = 99

    def on_tick(self, data):
        klines = data["klines"]
        price = data["price"]
        if len(klines) < 25:
            return "hold"

        closes = [k["close"] for k in klines]
        window = closes[-20:]
        mean = sum(window) / 20
        var = sum((c - mean) ** 2 for c in window) / 20
        std = var ** 0.5
        if std == 0:
            return "hold"
        z = (price - mean) / std

        position = self.ctx.get_position()
        if position:
            side = position.side if hasattr(position, "side") else position.get("side")
            if side == "long":
                if self.entry_price and price <= self.entry_price * 0.95:
                    return self._exit("sell")
                if abs(z) < 0.5 or z > 1.0:
                    return self._exit("sell")
            else:
                if self.entry_price and price >= self.entry_price * 1.05:
                    return self._exit("buy")
                if abs(z) < 0.5 or z < -1.0:
                    return self._exit("buy")
            return "hold"

        self.bars_since_exit += 1
        if self.bars_since_exit < 3:
            return "hold"

        if z < -2.0:
            self._enter(price, "long")
            return "buy"
        if z > 2.0:
            self._enter(price, "short")
            return "sell"
        return "hold"

    def _enter(self, price, side):
        self.entry_price = price
        self.position_side = side
        self.bars_since_exit = 0

    def _exit(self, signal):
        self.entry_price = None
        self.position_side = None
        self.bars_since_exit = 0
        return signal
```

- [ ] **Step 2: Run smoke test**

```bash
./venv/bin/pytest tests/test_new_strategies_smoke.py -v -k zscore
```

- [ ] **Step 3: Commit**

```bash
git add scripts/new_strategies/zscore_reversion.py
git commit -m "feat(strategy): add Z-score(20) mean reversion for BTCUSDT 1h

Generated with [Claude Code](https://claude.ai/code)
via [Happy](https://happy.engineering)

Co-Authored-By: Claude <noreply@anthropic.com>
Co-Authored-By: Happy <yesreply@happy.engineering>"
```

---

## Task 11: All-strategies smoke test gate

**Files:** （无新文件，统跑确认）

- [ ] **Step 1: Run full smoke test suite**

```bash
cd /home/autotrade/autotrade/backend
./venv/bin/pytest tests/test_new_strategies_smoke.py -v
```

Expected: **10 passed**. 任何 fail 都需修复对应文件后再继续。

- [ ] **Step 2: Run regression on existing tests**

```bash
./venv/bin/pytest -v
```

Expected: all existing tests still pass。新策略文件不应影响 executor/backtester/simulator 已有测试。

---

## Task 12: Deploy script

**Files:**
- Create: `scripts/deploy_new_strategies.py`

- [ ] **Step 1: Write deploy script**

Create `/home/autotrade/autotrade/scripts/deploy_new_strategies.py`：

```python
#!/usr/bin/env python3
"""部署 10 个新策略：复制到 sync 目录 → 同步入库 → 改 status='running' → 注册到调度器。

幂等：可重复运行。
"""
import asyncio
import shutil
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

SRC_DIR = REPO_ROOT / "scripts" / "new_strategies"
DST_DIR = Path("/var/tmp/strategies")

NAMES = [
    "海龟突破策略", "SuperTrend 趋势策略", "VWAP 日内回归策略",
    "区间网格策略", "MTF 双周期共振策略", "Squeeze 波动率突破策略",
    "ADX 强趋势通道策略", "StochRSI 反转策略",
    "Heikin Ashi 趋势骑乘策略", "Z-score 均值回归策略",
]


async def _main():
    from sqlalchemy import select, update
    from app.database import async_session
    from app.models import Strategy
    from app.services.strategy_sync import sync_strategies
    from app.engine.scheduler import scheduler_service

    # 1. 复制文件到 sync 目录
    DST_DIR.mkdir(parents=True, exist_ok=True)
    copied = []
    for f in sorted(SRC_DIR.glob("*.py")):
        dst = DST_DIR / f.name
        shutil.copy2(f, dst)
        copied.append(dst.name)
    print(f"[1/4] 复制 {len(copied)} 个文件到 {DST_DIR}: {copied}")

    # 2. 触发 sync（写入 DB，status='stopped'）
    await sync_strategies()
    print("[2/4] strategy_sync 执行完成")

    # 3. 改 status='running'
    async with async_session() as db:
        result = await db.execute(
            select(Strategy).where(Strategy.name.in_(NAMES))
        )
        strategies = result.scalars().all()
        if not strategies:
            print("❌ 未找到任何新策略入库；检查 sync 日志。")
            return 1
        for s in strategies:
            s.status = "running"
        await db.commit()
        # 重新查询以拿 selectinload 的 symbols（scheduler.start_strategy 自己会查）
        print(f"[3/4] 更新 {len(strategies)} 个策略为 status='running'")

        # 4. 注册到调度器
        # 注：脚本独立运行时，scheduler_service 不在主进程，
        # 这里只是把 status 置为 running；
        # 真正的 scheduler 注册由 backend 进程通过 restore_running_strategies 完成。
        # 解决：调用后端 API 触发重启策略，或要求用户重启 backend，或调用 HTTP 接口。
        for s in strategies:
            print(f"    ✓ {s.name} (id={s.id}, status={s.status})")

    print("[4/4] 完成。")
    print()
    print("⚠️  策略已入库且 status='running'，但 APScheduler 注册需要 backend 进程感知。")
    print("    选项一：重启 backend（最简单，restore_running_strategies 会自动注册）")
    print("    选项二：通过 API 触发：")
    for s in strategies:
        print(f"        curl -X POST http://localhost:18000/api/strategies/{s.id}/start")
    return 0


if __name__ == "__main__":
    exit(asyncio.run(_main()))
```

- [ ] **Step 2: Verify script syntax**

```bash
cd /home/autotrade/autotrade
./backend/venv/bin/python3 -c "import ast; ast.parse(open('scripts/deploy_new_strategies.py').read())"
```

Expected: 无输出（语法正确）

- [ ] **Step 3: Dry-run import (检查路径与依赖能 import)**

```bash
cd /home/autotrade/autotrade
./backend/venv/bin/python3 -c "
import sys
from pathlib import Path
sys.path.insert(0, str(Path('backend').resolve()))
from app.database import async_session
from app.models import Strategy
from app.services.strategy_sync import sync_strategies
from app.engine.scheduler import scheduler_service
print('✓ all imports OK')
"
```

Expected: `✓ all imports OK`

- [ ] **Step 4: Commit**

```bash
git add scripts/deploy_new_strategies.py
git commit -m "feat(scripts): deploy_new_strategies — copy → sync → set running

Generated with [Claude Code](https://claude.ai/code)
via [Happy](https://happy.engineering)

Co-Authored-By: Claude <noreply@anthropic.com>
Co-Authored-By: Happy <yesreply@happy.engineering>"
```

---

## Task 13: Execute deployment

**Pre-flight:**
- backend 必须运行（端口 18000）。如果未运行，按 CLAUDE.md 启动：
  ```bash
  cd /home/autotrade/autotrade/backend && source venv/bin/activate
  uvicorn app.main:app --reload --host 0.0.0.0 --port 18000
  ```

- [ ] **Step 1: Run deployment**

```bash
cd /home/autotrade/autotrade
./backend/venv/bin/python3 scripts/deploy_new_strategies.py
```

Expected output:
```
[1/4] 复制 10 个文件到 /var/tmp/strategies: [...]
[2/4] strategy_sync 执行完成
[3/4] 更新 10 个策略为 status='running'
    ✓ 海龟突破策略 (id=..., status=running)
    ...
[4/4] 完成。
```

- [ ] **Step 2: Verify DB state**

```bash
./backend/venv/bin/python3 -c "
import sqlite3
conn = sqlite3.connect('/home/autotrade/autotrade/backend/autotrade.db')
c = conn.cursor()
NAMES = ('海龟突破策略','SuperTrend 趋势策略','VWAP 日内回归策略','区间网格策略','MTF 双周期共振策略','Squeeze 波动率突破策略','ADX 强趋势通道策略','StochRSI 反转策略','Heikin Ashi 趋势骑乘策略','Z-score 均值回归策略')
for r in c.execute(f'SELECT id,name,status,symbol,timeframe FROM strategies WHERE name IN ({\",\".join([\"?\"]*10)})', NAMES).fetchall():
    print(r)
"
```

Expected: 10 行，全部 `status=running`。

- [ ] **Step 3: Register strategies with APScheduler**

调用后端 API 让 scheduler 加载（每个新策略一次）：

```bash
for id in $(./backend/venv/bin/python3 -c "
import sqlite3
c = sqlite3.connect('/home/autotrade/autotrade/backend/autotrade.db').cursor()
NAMES = ('海龟突破策略','SuperTrend 趋势策略','VWAP 日内回归策略','区间网格策略','MTF 双周期共振策略','Squeeze 波动率突破策略','ADX 强趋势通道策略','StochRSI 反转策略','Heikin Ashi 趋势骑乘策略','Z-score 均值回归策略')
for r in c.execute(f'SELECT id FROM strategies WHERE name IN ({\",\".join([\"?\"]*10)})', NAMES).fetchall():
    print(r[0])
"); do
  echo "Starting strategy $id..."
  curl -sS -X POST "http://localhost:18000/api/strategies/$id/start"
  echo
done
```

Expected: 每个 strategy 返回 `{"success": true}` 或类似成功响应。

> 如果某些 strategy 的 symbol/timeframe 未填充：检查 `strategy_symbols` 表是否需要补一行。当前代码路径下 `start_strategy` 要求 `selectinload(Strategy.symbols)` 不为空。如果空，先：
> ```bash
> ./backend/venv/bin/python3 -c "
> import asyncio
> from sqlalchemy import select
> from app.database import async_session
> from app.models import Strategy, StrategySymbol
> NAMES = [...]  # 同上
> async def fix():
>     async with async_session() as db:
>         result = await db.execute(select(Strategy).where(Strategy.name.in_(NAMES)))
>         for s in result.scalars().all():
>             ss = StrategySymbol(strategy_id=s.id, symbol=s.symbol)
>             db.add(ss)
>         await db.commit()
> asyncio.run(fix())
> "
> ```

- [ ] **Step 4: Verify APScheduler jobs registered**

```bash
curl -sS http://localhost:18000/api/health
# 然后查看 backend 日志：
tail -20 /home/autotrade/autotrade/backend/logs/*.log 2>/dev/null || tail -20 /home/autotrade/autotrade/logs/backend.log
```

Expected log lines like：
```
Strategy '海龟突破策略' (ID:X) registered job for symbol=BTCUSDT, tf=1d every 86400s
```

- [ ] **Step 5: Wait for first trigger and inspect trigger_logs**

15m 周期策略约 15 分钟出第一个信号；1h 约 1 小时；1d 需等到当日收盘。最快验证：直接看 15m VWAP 策略。

```bash
sleep 900  # 15 分钟
./backend/venv/bin/python3 -c "
import sqlite3
c = sqlite3.connect('/home/autotrade/autotrade/backend/autotrade.db').cursor()
rows = c.execute('''
    SELECT s.name, t.signal_type, t.action, t.price, t.triggered_at
    FROM trigger_logs t JOIN strategies s ON s.id = t.strategy_id
    WHERE s.name IN ('VWAP 日内回归策略','StochRSI 反转策略','Z-score 均值回归策略','区间网格策略')
    ORDER BY t.triggered_at DESC LIMIT 10
''').fetchall()
for r in rows: print(r)
"
```

Expected: 至少 1-2 条触发记录（如果完全没有，说明策略参数过严或市场太平静）。

- [ ] **Step 6: Frontend verification**

打开 `http://localhost:13000/strategies`，确认 10 个新策略：
- 全部显示 `running` 状态
- "触发记录" tab 内有数据（至少高频策略 VWAP/StochRSI/Zscore 应有）
- 点击任一策略可查看详情图表

---

## Rollback Plan

如需紧急停止全部 10 个新策略：

```bash
./backend/venv/bin/python3 -c "
import asyncio
from sqlalchemy import update
from app.database import async_session
from app.models import Strategy
NAMES = ['海龟突破策略','SuperTrend 趋势策略','VWAP 日内回归策略','区间网格策略','MTF 双周期共振策略','Squeeze 波动率突破策略','ADX 强趋势通道策略','StochRSI 反转策略','Heikin Ashi 趋势骑乘策略','Z-score 均值回归策略']
async def stop():
    async with async_session() as db:
        await db.execute(update(Strategy).where(Strategy.name.in_(NAMES)).values(status='stopped'))
        await db.commit()
asyncio.run(stop())
print('all 10 stopped')
"

# 再通过 API 停止 scheduler 任务：
for id in $(...同 Task 13 Step 3...); do
  curl -sS -X POST "http://localhost:18000/api/strategies/$id/stop"
done
```

永久删除：从 `/var/tmp/strategies/` 移除文件 + `DELETE FROM strategies WHERE name IN (...)`。

---

## Success Criteria

- [ ] 10 个 .py 文件存在于 `scripts/new_strategies/`（git tracked）
- [ ] 10 个文件同步到 `/var/tmp/strategies/`
- [ ] DB strategies 表新增 10 行，`status='running'`，`user_id=1`
- [ ] APScheduler 已注册对应 jobs（日志中能看到 "registered job"）
- [ ] `tests/test_new_strategies_smoke.py` 10/10 通过
- [ ] 部署后高频策略（15m、1h）24 小时内有 trigger_logs
- [ ] 前端 `/strategies` 页面正常展示 10 个新策略
- [ ] 无 executor 异常日志（`grep ERROR backend/logs/*.log` 无新错误）

---

## Notes / Open Items

- Z-score 与 sid=3 布林带回归（ETH/1h）思路重叠，但标的（BTC vs ETH）+ 参数（纯统计 z vs BB）不同，作为 A/B 对照保留
- 网格策略当前是简化版（每次 buy 买 1%，每次 sell 全平），未来可改 `sell_size_pct` 做更精细的格子管理
- StochRSI 简化为 `K = raw stoch_rsi`（未做 SMA 平滑），如果信号过频可后续优化
- Squeeze 用 `self._prior_squeeze_bars` 状态保留挤压记忆，注意状态版本（如果 backend 重启会丢失，第一根 K 线后重新累积）
