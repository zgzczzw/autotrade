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
        if len(klines) < 30:
            return "hold"

        ha = self._heikin_ashi(klines)
        last3 = ha[-3:]
        tol = price * 0.0005

        bull_bodies = all(c["close"] > c["open"] for c in last3)
        bull_no_lower = all(c["low"] >= min(c["open"], c["close"]) - tol for c in last3)
        bull = bull_bodies and bull_no_lower

        bear_bodies = all(c["close"] < c["open"] for c in last3)
        bear_no_upper = all(c["high"] <= max(c["open"], c["close"]) + tol for c in last3)
        bear = bear_bodies and bear_no_upper

        highs = [k["high"] for k in klines]
        lows = [k["low"] for k in klines]
        closes = [k["close"] for k in klines]
        atr = self._atr(highs, lows, closes, 14) or price * 0.02

        position = self.ctx.get_position()
        if position:
            side = position.side if hasattr(position, "side") else position.get("side")
            cur = ha[-1]
            body = abs(cur["close"] - cur["open"])
            if side == "long":
                self.highest_since_entry = max(self.highest_since_entry or price, price)
                trailing = self.highest_since_entry - 2.5 * atr
                self.stop_price = max(self.stop_price or 0.0, trailing)
                if price <= self.stop_price or (self.entry_price and price <= self.entry_price * 0.95):
                    return self._exit("sell")
                if cur["close"] < cur["open"]:
                    return self._exit("sell")
                upper_wick = cur["high"] - max(cur["open"], cur["close"])
                if upper_wick > 2 * body and body > 0:
                    return self._exit("sell")
            else:
                self.lowest_since_entry = min(self.lowest_since_entry or price, price)
                trailing = self.lowest_since_entry + 2.5 * atr
                self.stop_price = min(self.stop_price or 1e18, trailing)
                if price >= self.stop_price or (self.entry_price and price >= self.entry_price * 1.05):
                    return self._exit("buy")
                if cur["close"] > cur["open"]:
                    return self._exit("buy")
                lower_wick = min(cur["open"], cur["close"]) - cur["low"]
                if lower_wick > 2 * body and body > 0:
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
