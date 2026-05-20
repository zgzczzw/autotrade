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
        self._prior_squeeze_bars = 0
        self._prior_age = 0

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
            if self.squeeze_bars > 0:
                self._prior_squeeze_bars = self.squeeze_bars
                self._prior_age = 0
            self.squeeze_bars = 0

        if self._prior_squeeze_bars > 0 and not squeezed:
            self._prior_age += 1
            if self._prior_age > 10:
                self._prior_squeeze_bars = 0
                self._prior_age = 0

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

        if not squeezed and self._prior_squeeze_bars >= 5:
            if price > bb["upper"]:
                self._prior_squeeze_bars = 0
                self._prior_age = 0
                self._enter(price, "long", price - 2.0 * atr14)
                return "buy"
            if price < bb["lower"]:
                self._prior_squeeze_bars = 0
                self._prior_age = 0
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
