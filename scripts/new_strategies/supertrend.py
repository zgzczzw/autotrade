# @name: SuperTrend 趋势策略
# @symbol: BTCUSDT
# @timeframe: 4h
# @position_size: 15
# @position_size_type: percent
# @stop_loss: 5


class Strategy(BaseStrategy):
    """SuperTrend (ATR 10, multiplier 3) 趋势翻转跟随。"""

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
        if len(klines) < 30:
            return "hold"

        highs = [k["high"] for k in klines]
        lows = [k["low"] for k in klines]
        closes = [k["close"] for k in klines]

        st_value, st_trend, prev_trend = self._supertrend(highs, lows, closes, 10, 3.0)
        if st_value is None:
            return "hold"

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

        if prev_trend == -1 and st_trend == 1:
            self._enter(price, "long", price - 2.5 * atr)
            return "buy"
        if prev_trend == 1 and st_trend == -1:
            self._enter(price, "short", price + 2.5 * atr)
            return "sell"
        return "hold"

    def _supertrend(self, highs, lows, closes, period=10, mult=3.0):
        if len(closes) < period + 2:
            return None, 0, 0
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
        self.entry_price = None
        self.stop_price = None
        self.position_side = None
        self.highest_since_entry = None
        self.lowest_since_entry = None
        self.bars_since_exit = 0
        return signal
