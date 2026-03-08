# 数据源切换设计文档

**日期**: 2026-03-08
**状态**: 已确认，待实现

---

## 背景

系统当前使用 Binance API 作为唯一数据源。为支持无 Binance 账号的用户以及开发测试场景，需要增加数据源切换能力，支持三种数据源：

- **Binance**：现有实现，保留
- **CryptoCompare**：新增，提供真实 OHLCV 历史数据
- **Mock**：现有实现，保留，用于开发/测试

切换粒度为**全局**，通过**前端设置页**实时切换，无需重启服务。

---

## 架构设计

### Strategy Pattern

`MarketDataService` 保持不变的对外接口，内部持有可替换的 `DataSource` 实现：

```
MarketDataService
  active_source: DataSource  (in-memory，从 DB 初始化)
  get_klines(symbol, tf, limit) → KlineCache → active_source.fetch()

DataSource (abstract)
  ├── BinanceSource       现有逻辑提取封装
  ├── CryptoCompareSource 新增，含聚合 + Symbol 映射
  └── MockSource          封装现有 mock_data.py
```

### 数据流

```
get_klines(symbol, tf, limit)
  │
  ├─ 1. 查 KlineCache（SQLite，现有逻辑）
  │     命中且有最新数据 → 直接返回
  │
  ├─ 2. 未命中 → active_source.fetch(symbol, tf, since, limit)
  │     Binance: 现有 HTTP 调用
  │     CryptoCompare: histominute/histohour/histoday + 本地聚合
  │     Mock: generate_mock_klines()（跳过缓存写入）
  │
  └─ 3. 写 KlineCache（Mock 跳过），返回合并结果
```

---

## CryptoCompare 实现细节

### Symbol 映射

Binance 格式 `BTCUSDT` → CryptoCompare 格式 `fsym=BTC&tsym=USDT`

按已知计价币拆分（USDT / BTC / ETH / BNB），例如：
- `BTCUSDT` → `BTC / USDT`
- `ETHBTC` → `ETH / BTC`

### Timeframe 聚合策略

| timeframe | 拉取端点 | 拉取倍数 |
|-----------|---------|---------|
| 1m | histominute | ×1 |
| 3m / 5m / 15m / 30m | histominute | ×N |
| 1h | histohour | ×1 |
| 2h / 4h / 6h / 8h / 12h | histohour | ×N |
| 1d | histoday | ×1 |
| 3d | histoday | ×3 |
| 1w | histoday | ×7 |

聚合规则（OHLCV merge）：
- `open` = 第一根 open
- `high` = max(high)
- `low` = min(low)
- `close` = 最后一根 close
- `volume` = sum(volume)

单次最多拉取 2000 根原始数据，超出自动分页。

### API Key

明文存储在 `SystemSetting` 表，key = `cryptocompare_api_key`。

---

## 缓存设计

复用现有 `KlineCache` SQLite 表，缓存策略不变：
- 查询最新缓存时间，仅拉取增量数据
- TTL 隐含：下一根 K 线收盘前缓存仍有效
- Mock 数据不写缓存（每次重新生成）

---

## 设置存储

新增 `SystemSetting` 表（key/value）：

| key | 值域 | 说明 |
|-----|------|------|
| `data_source` | `binance` \| `cryptocompare` \| `mock` | 当前活跃数据源 |
| `cryptocompare_api_key` | string | CryptoCompare API Key |

默认值：`data_source = binance`

---

## API

新增 `GET/PUT /api/settings`：

- `GET /api/settings` → 返回所有系统配置
- `PUT /api/settings` → 更新配置，立即生效（同步更新 `MarketDataService.active_source`）

---

## 前端设置页

`/settings` 页面包含：
- 数据源选择（Binance / CryptoCompare / Mock，单选）
- CryptoCompare API Key 输入框（仅当选择 CryptoCompare 时显示）
- 「测试连接」按钮（验证 API Key 是否有效）
- 保存按钮（调用 PUT /api/settings）

---

## 文件变更清单

| 操作 | 文件 |
|------|------|
| 新建 | `app/engine/data_sources/__init__.py` |
| 新建 | `app/engine/data_sources/base.py` |
| 新建 | `app/engine/data_sources/binance.py` |
| 新建 | `app/engine/data_sources/cryptocompare.py` |
| 新建 | `app/engine/data_sources/mock.py` |
| 新建 | `app/routers/settings.py` |
| 修改 | `app/engine/market_data.py` |
| 修改 | `app/models.py` |
| 修改 | `app/main.py` |
| 新建 | `frontend/src/app/settings/page.tsx` 及相关组件 |

---

## 回测影响

回测通过 `market_data_service.get_klines()` 取数，自动跟随全局数据源：
- Mock 数据源 → 随机模拟数据回测
- CryptoCompare → 真实历史数据回测
- Binance → 真实历史数据回测
