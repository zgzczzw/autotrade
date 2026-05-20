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
    """

    def on_start(self):
        self.entry_price = None
        self.position_side = None
        self.bars_since_exit = 99

    def on_tick(self, data):
        klines = data["klines"]
        price = data["price"]
        if len(klines) < 5:
            return "hold"

        last_time = klines[-1]["open_time"]
        today = last_time.date()
        today_bars = [k for k in klines if k["open_time"].date() == today]
        if len(today_bars) < 3:
            return "hold"

        cum_pv = 0.0
        cum_v = 0.0
        for k in today_bars:
            typical = (k["high"] + k["low"] + k["close"]) / 3.0
            cum_pv += typical * k["volume"]
            cum_v += k["volume"]
        if cum_v == 0:
            return "hold"
        vwap = cum_pv / cum_v
        var_w = 0.0
        for k in today_bars:
            typical = (k["high"] + k["low"] + k["close"]) / 3.0
            var_w += ((typical - vwap) ** 2) * k["volume"]
        var_w = var_w / cum_v
        sigma = var_w ** 0.5
        if sigma == 0:
            return "hold"

        dev = price - vwap

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
