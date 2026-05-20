# @name: Z-score 均值回归策略
# @symbol: BTCUSDT
# @timeframe: 1h
# @position_size: 10
# @position_size_type: percent
# @stop_loss: 5


class Strategy(BaseStrategy):
    """Z-score(20) 极端反转。

    - z<-2 → 买；z>+2 → 卖
    - |z|<0.5 → 平仓 + 5% 硬止损
    """

    def on_start(self):
        self.entry_price = None
        self.position_side = None
        self.bars_since_exit = 99

    def on_tick(self, data):
        klines = data["klines"]
        price = data["price"]
        if len(klines) < 25:
            return "hold"

        closes = [k["close"] for k in klines]
        window = closes[-20:]
        mean = sum(window) / 20
        var = sum((c - mean) ** 2 for c in window) / 20
        std = var ** 0.5
        if std == 0:
            return "hold"
        z = (price - mean) / std

        position = self.ctx.get_position()
        if position:
            side = position.side if hasattr(position, "side") else position.get("side")
            if side == "long":
                if self.entry_price and price <= self.entry_price * 0.95:
                    return self._exit("sell")
                if abs(z) < 0.5 or z > 1.0:
                    return self._exit("sell")
            else:
                if self.entry_price and price >= self.entry_price * 1.05:
                    return self._exit("buy")
                if abs(z) < 0.5 or z < -1.0:
                    return self._exit("buy")
            return "hold"

        self.bars_since_exit += 1
        if self.bars_since_exit < 3:
            return "hold"

        if z < -2.0:
            self._enter(price, "long")
            return "buy"
        if z > 2.0:
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
