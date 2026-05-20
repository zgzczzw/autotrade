# @name: MTF 双周期共振策略
# @symbol: BTCUSDT
# @timeframe: 1h
# @position_size: 15
# @position_size_type: percent
# @stop_loss: 5


class Strategy(BaseStrategy):
    """1h MACD 入场，必须叠加 1d EMA50 趋势同向。"""

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
