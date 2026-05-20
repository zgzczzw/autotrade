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

        rsi_series = []
        for end in range(15, len(closes) + 1):
            r = calculate_rsi(closes[:end], 14)
            if r is not None:
                rsi_series.append(r)
        if len(rsi_series) < 17:
            return "hold"

        window = rsi_series[-14:]
        rmin = min(window)
        rmax = max(window)
        cur_sr = (rsi_series[-1] - rmin) / (rmax - rmin) * 100 if rmax != rmin else 50.0

        window_prev = rsi_series[-15:-1]
        rmin_p = min(window_prev)
        rmax_p = max(window_prev)
        prev_sr = (rsi_series[-2] - rmin_p) / (rmax_p - rmin_p) * 100 if rmax_p != rmin_p else 50.0

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
