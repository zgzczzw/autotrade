# AutoTrade 常见策略示例

本文档提供10个常见的交易策略，包含可视化配置和代码策略两种形式。

## 策略列表

1. [RSI 超买卖策略](#1-rsi-超买卖策略)
2. [双均线交叉策略](#2-双均线交叉策略)
3. [布林带突破策略](#3-布林带突破策略)
4. [趋势跟踪策略](#4-趋势跟踪策略)
5. [均值回归策略](#5-均值回归策略)
6. [突破交易策略](#6-突破交易策略)
7. [动量策略](#7-动量策略)
8. [多重确认策略](#8-多重确认策略)
9. [网格交易策略](#9-网格交易策略)
10. [波动率突破策略](#10-波动率突破策略)

---

## 1. RSI 超买卖策略

**逻辑**: RSI < 30 超卖买入，RSI > 70 超买卖出

### 可视化配置

```json
{
  "buy_conditions": {
    "logic": "AND",
    "rules": [
      {
        "indicator": "RSI",
        "params": {"period": 14},
        "operator": "<",
        "value": 30
      }
    ]
  },
  "sell_conditions": {
    "logic": "AND",
    "rules": [
      {
        "indicator": "RSI",
        "params": {"period": 14},
        "operator": ">",
        "value": 70
      }
    ]
  }
}
```

### 代码策略

```python
def on_tick(self, data):
    klines = self.ctx.get_klines(limit=20)
    if len(klines) < 14:
        return None
    
    closes = [k["close"] for k in klines]
    rsi = self.calculate_rsi(closes, 14)
    
    position = self.ctx.get_position()
    
    if not position and rsi < 30:
        return "buy"
    elif position and rsi > 70:
        return "sell"
    
    return None

def calculate_rsi(self, data, period=14):
    if len(data) < period + 1:
        return 50
    
    changes = [data[i] - data[i-1] for i in range(1, len(data))]
    gains = [max(c, 0) for c in changes]
    losses = [abs(min(c, 0)) for c in changes]
    
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    
    if avg_loss == 0:
        return 100
    
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))
```

**参数建议**:
- 交易对: BTCUSDT
- 时间周期: 1h
- 仓位大小: 固定 100 USDT
- 止损: 5%
- 止盈: 10%

---

## 2. 双均线交叉策略

**逻辑**: 短期均线上穿长期均线（金叉）买入，下穿（死叉）卖出

### 可视化配置

```json
{
  "buy_conditions": {
    "logic": "AND",
    "rules": [
      {
        "indicator": "MA_CROSS",
        "params": {"fast": 5, "slow": 20},
        "operator": "==",
        "value": "golden"
      }
    ]
  },
  "sell_conditions": {
    "logic": "AND",
    "rules": [
      {
        "indicator": "MA_CROSS",
        "params": {"fast": 5, "slow": 20},
        "operator": "==",
        "value": "death"
      }
    ]
  }
}
```

### 代码策略

```python
def on_tick(self, data):
    klines = self.ctx.get_klines(limit=30)
    if len(klines) < 20:
        return None
    
    closes = [k["close"] for k in klines]
    
    # 计算均线
    fast_ma = sum(closes[-5:]) / 5
    slow_ma = sum(closes[-20:]) / 20
    
    # 上一根K线的均线
    prev_fast_ma = sum(closes[-6:-1]) / 5
    prev_slow_ma = sum(closes[-21:-1]) / 20
    
    position = self.ctx.get_position()
    
    # 金叉: 短期上穿长期
    if not position and prev_fast_ma <= prev_slow_ma and fast_ma > slow_ma:
        return "buy"
    
    # 死叉: 短期下穿长期
    elif position and prev_fast_ma >= prev_slow_ma and fast_ma < slow_ma:
        return "sell"
    
    return None
```

**参数建议**:
- 交易对: BTCUSDT
- 时间周期: 1h
- 仓位大小: 固定 200 USDT
- 止损: 8%
- 止盈: 15%

---

## 3. 布林带突破策略

**逻辑**: 价格突破下轨买入，突破上轨卖出

### 可视化配置

```json
{
  "buy_conditions": {
    "logic": "AND",
    "rules": [
      {
        "indicator": "BOLLINGER",
        "params": {"period": 20, "std_dev": 2.0},
        "operator": "==",
        "value": "below_lower"
      }
    ]
  },
  "sell_conditions": {
    "logic": "AND",
    "rules": [
      {
        "indicator": "BOLLINGER",
        "params": {"period": 20, "std_dev": 2.0},
        "operator": "==",
        "value": "above_upper"
      }
    ]
  }
}
```

### 代码策略

```python
def on_tick(self, data):
    klines = self.ctx.get_klines(limit=25)
    if len(klines) < 20:
        return None
    
    closes = [k["close"] for k in klines]
    current_price = closes[-1]
    
    # 计算布林带
    period = 20
    sma = sum(closes[-period:]) / period
    variance = sum((p - sma) ** 2 for p in closes[-period:]) / period
    std = variance ** 0.5
    
    upper = sma + 2 * std
    lower = sma - 2 * std
    
    position = self.ctx.get_position()
    
    # 突破下轨买入
    if not position and current_price < lower:
        return "buy"
    
    # 突破上轨卖出
    elif position and current_price > upper:
        return "sell"
    
    return None
```

**参数建议**:
- 交易对: ETHUSDT
- 时间周期: 4h
- 仓位大小: 固定 150 USDT
- 止损: 6%
- 止盈: 12%

---

## 4. 趋势跟踪策略

**逻辑**: 价格在均线之上且向上趋势买入，跌破均线卖出

### 代码策略

```python
def on_tick(self, data):
    klines = self.ctx.get_klines(limit=50)
    if len(klines) < 30:
        return None
    
    closes = [k["close"] for k in klines]
    current_price = closes[-1]
    
    # 计算 30 周期均线
    ma30 = sum(closes[-30:]) / 30
    
    # 计算趋势（最近5根K线）
    recent_trend = closes[-1] - closes[-5]
    
    position = self.ctx.get_position()
    
    # 价格在均线上方且趋势向上
    if not position and current_price > ma30 and recent_trend > 0:
        return "buy"
    
    # 价格跌破均线
    elif position and current_price < ma30:
        return "sell"
    
    return None
```

**参数建议**:
- 交易对: BTCUSDT
- 时间周期: 1d
- 仓位大小: 账户 30%
- 止损: 10%
- 止盈: 20%

---

## 5. 均值回归策略

**逻辑**: 价格偏离均线过多时回归均值

### 代码策略

```python
def on_tick(self, data):
    klines = self.ctx.get_klines(limit=30)
    if len(klines) < 20:
        return None
    
    closes = [k["close"] for k in klines]
    current_price = closes[-1]
    
    # 计算均线
    ma20 = sum(closes[-20:]) / 20
    
    # 计算偏离度 (%)
    deviation = (current_price - ma20) / ma20 * 100
    
    position = self.ctx.get_position()
    
    # 价格低于均线3%以上，回归均值买入
    if not position and deviation < -3:
        return "buy"
    
    # 价格回归均线或高于均线2%卖出
    elif position and deviation > 2:
        return "sell"
    
    return None
```

**参数建议**:
- 交易对: BTCUSDT
- 时间周期: 1h
- 仓位大小: 固定 100 USDT
- 止损: 4%
- 止盈: 6%

---

## 6. 突破交易策略

**逻辑**: 突破近期高点买入，跌破近期低点卖出

### 代码策略

```python
def on_tick(self, data):
    klines = self.ctx.get_klines(limit=30)
    if len(klines) < 20:
        return None
    
    closes = [k["close"] for k in klines]
    highs = [k["high"] for k in klines]
    lows = [k["low"] for k in klines]
    
    current_price = closes[-1]
    
    # 计算20周期的高点和低点
    period = 20
    recent_high = max(highs[-period:])
    recent_low = min(lows[-period:])
    
    position = self.ctx.get_position()
    
    # 突破高点买入
    if not position and current_price > recent_high * 0.995:
        return "buy"
    
    # 跌破低点卖出
    elif position and current_price < recent_low * 1.005:
        return "sell"
    
    return None
```

**参数建议**:
- 交易对: BTCUSDT
- 时间周期: 4h
- 仓位大小: 固定 200 USDT
- 止损: 7%
- 止盈: 14%

---

## 7. 动量策略

**逻辑**: 价格上涨动能强劲时追涨，动能衰竭时卖出

### 代码策略

```python
def on_tick(self, data):
    klines = self.ctx.get_klines(limit=15)
    if len(klines) < 10:
        return None
    
    closes = [k["close"] for k in klines]
    volumes = [k["volume"] for k in klines]
    
    # 计算价格变化率 (ROC)
    roc = (closes[-1] - closes[-5]) / closes[-5] * 100
    
    # 计算成交量变化
    avg_volume = sum(volumes[-5:]) / 5
    prev_avg_volume = sum(volumes[-10:-5]) / 5
    volume_ratio = avg_volume / prev_avg_volume if prev_avg_volume > 0 else 1
    
    position = self.ctx.get_position()
    
    # 价格上涨且成交量放大
    if not position and roc > 2 and volume_ratio > 1.2:
        return "buy"
    
    # 价格回调或成交量萎缩
    elif position and (roc < -1 or volume_ratio < 0.8):
        return "sell"
    
    return None
```

**参数建议**:
- 交易对: SOLUSDT
- 时间周期: 1h
- 仓位大小: 固定 150 USDT
- 止损: 6%
- 止盈: 12%

---

## 8. 多重确认策略

**逻辑**: RSI + 均线 + 布林带三重确认

### 可视化配置

```json
{
  "buy_conditions": {
    "logic": "AND",
    "rules": [
      {
        "indicator": "RSI",
        "params": {"period": 14},
        "operator": "<",
        "value": 40
      },
      {
        "indicator": "BOLLINGER",
        "params": {"period": 20, "std_dev": 2.0},
        "operator": "==",
        "value": "below_lower"
      }
    ]
  },
  "sell_conditions": {
    "logic": "AND",
    "rules": [
      {
        "indicator": "RSI",
        "params": {"period": 14},
        "operator": ">",
        "value": 60
      },
      {
        "indicator": "BOLLINGER",
        "params": {"period": 20, "std_dev": 2.0},
        "operator": "==",
        "value": "above_upper"
      }
    ]
  }
}
```

### 代码策略

```python
def on_tick(self, data):
    klines = self.ctx.get_klines(limit=30)
    if len(klines) < 20:
        return None
    
    closes = [k["close"] for k in klines]
    current_price = closes[-1]
    
    # RSI 计算
    rsi = self.calculate_rsi(closes, 14)
    
    # 布林带计算
    ma20 = sum(closes[-20:]) / 20
    std = (sum((p - ma20) ** 2 for p in closes[-20:]) / 20) ** 0.5
    upper = ma20 + 2 * std
    lower = ma20 - 2 * std
    
    # 均线趋势
    ma10 = sum(closes[-10:]) / 10
    trend_up = ma10 > ma20
    
    position = self.ctx.get_position()
    
    # 三重确认买入: RSI低 + 突破下轨 + 均线趋势向上
    if not position and rsi < 40 and current_price < lower and trend_up:
        return "buy"
    
    # 三重确认卖出: RSI高 + 突破上轨
    elif position and rsi > 60 and current_price > upper:
        return "sell"
    
    return None

def calculate_rsi(self, data, period=14):
    if len(data) < period + 1:
        return 50
    changes = [data[i] - data[i-1] for i in range(1, len(data))]
    gains = [max(c, 0) for c in changes]
    losses = [abs(min(c, 0)) for c in changes]
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))
```

**参数建议**:
- 交易对: BTCUSDT
- 时间周期: 1h
- 仓位大小: 固定 300 USDT
- 止损: 5%
- 止盈: 10%

---

## 9. 网格交易策略

**逻辑**: 在价格区间内分批买入卖出

### 代码策略

```python
def on_tick(self, data):
    klines = self.ctx.get_klines(limit=50)
    if len(klines) < 20:
        return None
    
    closes = [k["close"] for k in klines]
    current_price = closes[-1]
    
    # 确定网格区间 (基于近期高低点)
    grid_high = max(closes[-20:])
    grid_low = min(closes[-20:])
    grid_range = grid_high - grid_low
    
    if grid_range == 0:
        return None
    
    # 计算当前价格在网格中的位置 (0-1)
    grid_position = (current_price - grid_low) / grid_range
    
    position = self.ctx.get_position()
    balance = self.ctx.get_balance()
    
    # 网格下部买入
    if not position and grid_position < 0.3 and balance > 100:
        return "buy"
    
    # 网格上部卖出
    elif position and grid_position > 0.7:
        return "sell"
    
    return None
```

**参数建议**:
- 交易对: BTCUSDT
- 时间周期: 15m
- 仓位大小: 固定 100 USDT
- 止损: 不使用（网格策略一般不设止损）
- 止盈: 不使用

---

## 10. 波动率突破策略

**逻辑**: 波动率压缩后突破时交易

### 代码策略

```python
def on_tick(self, data):
    klines = self.ctx.get_klines(limit=30)
    if len(klines) < 20:
        return None
    
    highs = [k["high"] for k in klines]
    lows = [k["low"] for k in klines]
    closes = [k["close"] for k in klines]
    
    current_price = closes[-1]
    
    # 计算 ATR (平均真实波幅)
    atr_period = 14
    tr_list = []
    for i in range(-atr_period, 0):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i-1]),
            abs(lows[i] - closes[i-1])
        )
        tr_list.append(tr)
    atr = sum(tr_list) / len(tr_list)
    
    # 计算近期波动率变化
    recent_atr = sum(tr_list[-5:]) / 5
    prev_atr = sum(tr_list[-10:-5]) / 5
    
    # 布林带宽度 (波动率指标)
    ma20 = sum(closes[-20:]) / 20
    std = (sum((p - ma20) ** 2 for p in closes[-20:]) / 20) ** 0.5
    bb_width = (std * 2) / ma20 * 100  # 布林带宽度百分比
    
    position = self.ctx.get_position()
    
    # 波动率压缩后向上突破
    if not position and bb_width < 5 and closes[-1] > highs[-2]:
        return "buy"
    
    # 波动率扩大后获利了结
    elif position and (bb_width > 10 or recent_atr > prev_atr * 1.5):
        return "sell"
    
    return None
```

**参数建议**:
- 交易对: BTCUSDT
- 时间周期: 1h
- 仓位大小: 固定 200 USDT
- 止损: 8%
- 止盈: 16%

---

## 使用说明

### 创建可视化策略

1. 进入"策略"页面
2. 点击"创建策略"
3. 选择"可视化配置"
4. 在 `config_json` 字段粘贴对应的 JSON 配置
5. 设置交易对、时间周期、仓位大小
6. 保存并启动策略

### 创建代码策略

1. 进入"策略"页面
2. 点击"创建策略"
3. 选择"代码编写"
4. 在 `code` 字段粘贴对应的 Python 代码
5. 设置交易对、时间周期、仓位大小
6. 保存并启动策略

### 注意事项

1. **回测验证**: 建议先用回测功能验证策略效果
2. **参数调整**: 不同市场条件下参数可能需要调整
3. **风险控制**: 始终设置合理的止损
4. **资金管理**: 不要全仓操作，建议单笔风险不超过总资金的 2%
5. **监控日志**: 定期检查触发日志，确保策略按预期运行

---

## 风险提示

⚠️ **加密货币交易风险极高，以上策略仅供学习参考，不构成投资建议。使用任何策略前请充分理解其原理和风险，并在模拟盘中充分测试。**
