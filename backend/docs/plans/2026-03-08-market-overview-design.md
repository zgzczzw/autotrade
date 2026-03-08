# 数字货币大盘设计文档

**日期**: 2026-03-08
**状态**: 已确认，待实现

---

## 背景

新增独立的「大盘」页面，支持交易对搜索切换、K 线图展示（15m/1h/4h/1d）、以及 24h 行情摘要，复用项目现有 `KlineChartModule` 组件。

---

## 页面布局

```
┌──────────────────────────────────────────────────┐
│  [BTCUSDT ▾搜索]        [15m] [1h] [4h] [1d]    │
├──────────────────────────────────────────────────┤
│  $67,000  +2.3%  ↑$67,500  ↓$65,200  Vol:1,234  │
├──────────────────────────────────────────────────┤
│                  KlineChartModule                │
└──────────────────────────────────────────────────┘
```

- 左上：交易对搜索下拉（combobox，debounce 300ms 调 API）
- 右上：时间周期切换（15m / 1h / 4h / 1d）
- 行情栏：当前价、24h 涨跌幅（正绿负红）、24h 最高/最低、24h 成交量
- 主体：`KlineChartModule`，复用现有组件，不显示买卖标记

---

## 后端架构

### 新增路由 `app/routers/market.py`

| 端点 | 说明 |
|------|------|
| `GET /api/market/symbols?q=BTC` | 搜索交易对，返回字符串数组 |
| `GET /api/market/klines?symbol=BTCUSDT&timeframe=1h&limit=200` | K 线数据，复用 `market_data_service.get_klines()` |
| `GET /api/market/ticker?symbol=BTCUSDT` | 24h 行情摘要 |

### DataSource 扩展

`DataSource` 基类新增两个抽象方法：

```python
async def fetch_symbols(self, query: str = "") -> List[str]: ...
async def fetch_ticker(self, symbol: str) -> dict: ...
```

Ticker 响应格式：
```json
{
  "symbol": "BTCUSDT",
  "price": 67000.0,
  "change_pct": 2.3,
  "high_24h": 67500.0,
  "low_24h": 65200.0,
  "volume_24h": 1234.5
}
```

### 各数据源实现

**BinanceSource**
- `fetch_symbols`: `/api/v3/exchangeInfo` → 过滤 `quoteAsset=USDT & status=TRADING`，按 query 前缀匹配
- `fetch_ticker`: `/api/v3/ticker/24hr?symbol=BTCUSDT`

**CryptoCompareSource**
- `fetch_symbols`: `/data/top/totaltoptiervolfull?limit=100&tsym=USDT` → 提取 `{Name}USDT`，按 query 过滤
- `fetch_ticker`: `histoday?limit=1` 拉 2 根日线，计算 price/change_pct/high/low/volume

**MockSource**
- `fetch_symbols`: 内置 20 个常用交易对，按 query 过滤
- `fetch_ticker`: 从 `generate_mock_klines` 最近 2 根日线计算

### MarketDataService 扩展

```python
async def get_symbols(self, query: str = "") -> List[str]: ...
async def get_ticker(self, symbol: str) -> dict: ...
```

---

## 前端架构

### 新增文件

| 文件 | 说明 |
|------|------|
| `frontend/src/app/market/page.tsx` | 大盘主页面，管理 symbol/timeframe 状态和数据拉取 |
| `frontend/src/components/symbol-selector.tsx` | 搜索下拉组件（debounce 300ms，调 fetchSymbols） |
| `frontend/src/components/ticker-bar.tsx` | 行情摘要栏（price/change/high/low/volume） |

### 修改文件

| 文件 | 修改内容 |
|------|---------|
| `frontend/src/lib/api.ts` | 新增 `fetchSymbols` / `fetchMarketKlines` / `fetchTicker` |
| `frontend/src/components/sidebar.tsx` | 新增「大盘」导航入口（BarChart2 图标） |
| `backend/app/main.py` | 注册 market router |

### 数据流

```
页面加载
  → fetchSymbols("") 填充下拉列表，默认选中 BTCUSDT
  → fetchTicker("BTCUSDT") 显示行情摘要
  → fetchMarketKlines("BTCUSDT", "1h", 200) 渲染图表

用户选择新 symbol
  → fetchTicker(symbol) + fetchMarketKlines(symbol, timeframe, 200)

用户切换 timeframe
  → fetchMarketKlines(symbol, timeframe, 200)

自动轮询
  → ticker: 每 30s 刷新
  → klines: 每 60s 刷新
```

### Klines 数据转换

后端返回 `open_time`（ISO 字符串），前端转换为 KlineChartModule 接受的格式：

```typescript
const chartData = klines.map((k: any) => ({
  timestamp: new Date(k.open_time).getTime(),
  open: k.open, high: k.high, low: k.low, close: k.close, volume: k.volume,
}));
```

### 涨跌颜色规则

- 正值：`text-green-400`
- 负值：`text-red-400`
- 零：`text-slate-400`

与现有界面风格一致。
