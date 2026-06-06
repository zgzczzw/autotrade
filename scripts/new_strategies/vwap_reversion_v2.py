# @name: VWAP 日内回归增强版
# @symbol: BTCUSDT
# @timeframe: 5m
# @position_size: 10
# @position_size_type: percent
# @stop_loss: 3


class Strategy(BaseStrategy):
    """VWAP 日内回归（增强版）：z-score 入场 + 趋势日过滤 + 日末强平。

    增强点（相对 v1 教科书版）：
    1. ±2σ 入场 + 回落/反弹确认（避免顺势单边的"擦边"）
    2. |z|<0.3 止盈、|z|>3 止损（动态、基于波动率）
    3. VWAP 斜率过滤：当日 VWAP 相对开盘价偏移 >1.5% → 单边日，停止新入场
    4. 穿越次数过滤：当日穿越 VWAP <3 次 → 未确认震荡，停止新入场
    5. UTC 23:45 后强制平仓，避开日切失锚
    6. 3 根冷却 + 5% 失效硬止损 fallback
    """

    # 入场/出场阈值
    ENTRY_Z = 2.0       # ±2σ 入场
    EXIT_Z = 0.3        # |z| < 0.3 平仓
    STOP_Z = 3.0        # |z| > 3 止损
    COOLDOWN_BARS = 3   # 平仓后 3 根 K 线不再入场

    # 趋势日过滤
    MAX_VWAP_DRIFT = 0.015   # VWAP 相对开盘偏移 < 1.5%
    MIN_CROSSINGS = 3        # 当日至少穿越 VWAP 3 次才允许入场

    # 日末强平
    FORCE_CLOSE_HOUR = 23
    FORCE_CLOSE_MIN = 45

    # 失效硬止损
    HARD_STOP_PCT = 0.05     # 5%，z-score 止损失效时兜底

    def on_start(self):
        self.entry_price = None
        self.position_side = None
        self.bars_since_exit = 99

    def on_tick(self, data):
        klines = data["klines"]
        price = data["price"]
        if len(klines) < 5:
            return "hold"

        # 取当日所有 K 线（UTC 0 点切日）
        last_time = klines[-1]["open_time"]
        today = last_time.date()
        today_bars = [k for k in klines if k["open_time"].date() == today]
        if len(today_bars) < 3:
            return "hold"

        # 计算 VWAP + σ（cumulative volume-weighted variance）
        vwap, sigma = self._compute_vwap_sigma(today_bars)
        if vwap is None or sigma == 0:
            return "hold"

        z = (price - vwap) / sigma

        # ── 持仓中：处理 z-score 止盈 / z-score 止损 / 硬止损 / 日末强平 ──
        position = self.ctx.get_position()
        if position:
            side = position.side if hasattr(position, "side") else position.get("side")
            # 日末强平
            if self._is_force_close_time(last_time):
                return self._exit("sell" if side == "long" else "buy")
            # 5% 硬止损 fallback（防 σ 极小导致 z-score 止损失灵）
            if self.entry_price:
                if side == "long" and price <= self.entry_price * (1 - self.HARD_STOP_PCT):
                    return self._exit("sell")
                if side == "short" and price >= self.entry_price * (1 + self.HARD_STOP_PCT):
                    return self._exit("buy")
            # z-score 止损 / 止盈
            if side == "long":
                if z >= -self.EXIT_Z:           # 回到 VWAP 附近
                    return self._exit("sell")
                if z <= -self.STOP_Z:           # 继续往下穿 → 趋势确认，止损
                    return self._exit("sell")
            else:  # short
                if z <= self.EXIT_Z:
                    return self._exit("buy")
                if z >= self.STOP_Z:
                    return self._exit("buy")
            return "hold"

        # ── 空仓：检查入场条件 ──
        self.bars_since_exit += 1
        if self.bars_since_exit < self.COOLDOWN_BARS:
            return "hold"
        # 日末不再开新仓
        if self._is_force_close_time(last_time):
            return "hold"
        # 趋势日过滤：VWAP 相对开盘偏移过大
        open_price = today_bars[0]["open"]
        if open_price > 0:
            drift = abs(vwap - open_price) / open_price
            if drift > self.MAX_VWAP_DRIFT:
                return "hold"
        # 趋势日过滤：当日穿越 VWAP 次数过少
        crossings = self._count_vwap_crossings(today_bars, vwap)
        if crossings < self.MIN_CROSSINGS:
            return "hold"

        # 回落/反弹确认（不是擦边）
        prev_close = klines[-2]["close"]
        if z >= self.ENTRY_Z and price < prev_close:
            self._enter(price, "short")
            return "sell"
        if z <= -self.ENTRY_Z and price > prev_close:
            self._enter(price, "long")
            return "buy"
        return "hold"

    # ─── helpers ────────────────────────────────────────────────

    def _compute_vwap_sigma(self, bars):
        """累计 volume-weighted 典型价 → VWAP；σ = sqrt(E[typical²] − VWAP²)."""
        cum_pv = 0.0
        cum_p2v = 0.0
        cum_v = 0.0
        for k in bars:
            typical = (k["high"] + k["low"] + k["close"]) / 3.0
            v = k["volume"]
            cum_pv += typical * v
            cum_p2v += typical * typical * v
            cum_v += v
        if cum_v == 0:
            return None, 0.0
        vwap = cum_pv / cum_v
        variance = max(0.0, cum_p2v / cum_v - vwap * vwap)
        sigma = variance ** 0.5
        return vwap, sigma

    def _count_vwap_crossings(self, bars, vwap):
        """统计当日 close 上下穿 vwap 的次数（粗略估计震荡程度）。"""
        crossings = 0
        prev_above = bars[0]["close"] > vwap
        for k in bars[1:]:
            cur_above = k["close"] > vwap
            if cur_above != prev_above:
                crossings += 1
                prev_above = cur_above
        return crossings

    def _is_force_close_time(self, dt):
        return dt.hour == self.FORCE_CLOSE_HOUR and dt.minute >= self.FORCE_CLOSE_MIN

    def _enter(self, price, side):
        self.entry_price = price
        self.position_side = side
        self.bars_since_exit = 0

    def _exit(self, signal):
        self.entry_price = None
        self.position_side = None
        self.bars_since_exit = 0
        return signal
