# @name: ADX 强趋势通道策略
# @symbol: BTCUSDT
# @timeframe: 4h
# @position_size: 12
# @position_size_type: percent
# @stop_loss: 5


class Strategy(BaseStrategy):
    """ADX(14) > 25 时跟随 Keltner 通道方向。"""

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
        adx_val = sum(dxs[:period]) / period
        for v in dxs[period:]:
            adx_val = (adx_val * (period - 1) + v) / period

        plus_di_last = 100 * plus_s[-1] / atr_s[-1] if atr_s[-1] > 0 else 0.0
        minus_di_last = 100 * minus_s[-1] / atr_s[-1] if atr_s[-1] > 0 else 0.0
        return adx_val, plus_di_last, minus_di_last

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
