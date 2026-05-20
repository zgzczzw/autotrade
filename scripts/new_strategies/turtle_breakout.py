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
