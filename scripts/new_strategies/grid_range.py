# @name: 区间网格策略
# @symbol: ETHUSDT
# @timeframe: 1h
# @position_size: 1
# @position_size_type: percent


class Strategy(BaseStrategy):
    """区间网格 — center=EMA50, 区间±5%, 10 格。

    - 价格落入新格 → 买入 1% 总仓
    - 价格涨至上一格 → 卖出
    - 价格超出区间 5% → 平仓 + 冷却 24 根 K 线
    - 每 24 根 K 线用最新 EMA50 重置 center
    """

    def on_start(self):
        self.center = None
        self.bars_since_reset = 0
        self.held_grids = {}  # 用 dict 代替 set（sandbox 无 set）
        self.cooldown_bars = 0
        self.grid_count = 10
        self.range_pct = 0.05

    def on_tick(self, data):
        klines = data["klines"]
        price = data["price"]
        if len(klines) < 60:
            return "hold"

        closes = [k["close"] for k in klines]
        ema50 = calculate_ema(closes, 50)
        if ema50 is None:
            return "hold"

        if self.cooldown_bars > 0:
            self.cooldown_bars -= 1
            return "hold"

        if self.center is None or self.bars_since_reset >= 24:
            self.center = ema50
            self.bars_since_reset = 0
        else:
            self.bars_since_reset += 1

        low_bound = self.center * (1 - self.range_pct)
        high_bound = self.center * (1 + self.range_pct)

        if price < low_bound * 0.95 or price > high_bound * 1.05:
            if self.held_grids:
                self.held_grids = {}
                self.cooldown_bars = 24
                return "sell"
            return "hold"

        grid_width = (high_bound - low_bound) / self.grid_count
        if grid_width <= 0:
            return "hold"
        idx = int((price - low_bound) / grid_width)
        if idx < 0:
            idx = 0
        if idx >= self.grid_count:
            idx = self.grid_count - 1

        for held_idx in list(self.held_grids.keys()):
            sell_target = low_bound + (held_idx + 1) * grid_width
            if price >= sell_target:
                self.held_grids.pop(held_idx, None)
                return "sell"

        if idx not in self.held_grids:
            self.held_grids[idx] = price
            return "buy"

        return "hold"
