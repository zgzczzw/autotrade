# ChartLines — 数字货币技术分析自动画线系统

## 概述

一个完全独立的全栈系统，自动检测并绘制加密货币价格图表上的技术分析线形和形态。支持单币深度分析和多币批量扫描，检测到新形态时推送通知。

**核心特性**：
- 纯自动画线，用户只做筛选（显示/隐藏、置信度阈值）
- 支撑/阻力、趋势线、通道、斐波那契、经典形态识别
- 多币扫描 + 形态通知
- 分析结果持久化，可回看历史

## 技术栈

- **后端**: Python 3.12, FastAPI, SQLAlchemy 2.0 (async), APScheduler, aiosqlite, numpy, pandas
- **前端**: Next.js, React, TypeScript, Tailwind CSS, lightweight-charts (TradingView)
- **数据库**: SQLite
- **数据源**: Binance API（独立接入）

## 项目结构

```
chartlines/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── models.py
│   │   ├── schemas.py
│   │   ├── database.py
│   │   ├── routers/
│   │   │   ├── analysis.py       # 单币分析 API
│   │   │   ├── scanner.py        # 多币扫描 API
│   │   │   ├── market.py         # K线/交易对 API
│   │   │   ├── notify.py         # 通知配置 API
│   │   │   └── settings.py       # 全局设置 API
│   │   ├── engine/
│   │   │   ├── detector.py       # 线形检测总调度
│   │   │   ├── lines/
│   │   │   │   ├── base.py       # 抽象接口
│   │   │   │   ├── support_resistance.py
│   │   │   │   ├── trendline.py
│   │   │   │   ├── channel.py
│   │   │   │   ├── fibonacci.py
│   │   │   │   └── patterns.py   # 形态识别
│   │   │   ├── utils.py          # swing points, clustering, line fitting
│   │   │   └── scanner.py        # 多币扫描调度
│   │   └── services/
│   │       ├── market_data.py    # Binance K线获取+缓存
│   │       └── notify.py         # 通知服务（Bark/Webhook）
│   ├── requirements.txt
│   └── .env
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── page.tsx          # 单币分析页（首页）
│   │   │   ├── scanner/page.tsx  # 多币扫描页
│   │   │   └── settings/page.tsx # 设置页
│   │   ├── components/
│   │   │   ├── analysis-chart/   # K线图+画线渲染
│   │   │   ├── pattern-list/     # 检测结果列表
│   │   │   └── ui/               # 通用 UI 组件
│   │   └── lib/
│   │       ├── api.ts            # API 客户端
│   │       └── utils.ts
│   ├── next.config.ts
│   └── package.json
└── Makefile
```

## 数据模型

### KlineData — K线缓存

| 字段 | 类型 | 说明 |
|------|------|------|
| symbol | str | 交易对，如 "BTCUSDT" |
| timeframe | str | 时间周期，如 "1h" |
| open_time | datetime | K线开盘时间 |
| open, high, low, close | float | OHLC 价格 |
| volume | float | 成交量 |

唯一约束: `(symbol, timeframe, open_time)`

### DetectedLine — 检测到的线形

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 主键 |
| symbol | str | 交易对 |
| timeframe | str | 时间周期 |
| line_type | str | 类型：support, resistance, trendline_up, trendline_down, channel_up, channel_down, fib_retracement, fib_extension |
| points | JSON | 关键点坐标 `[{"time": ..., "price": ...}, ...]` |
| params | JSON | 附加参数（如斐波那契各级别价格） |
| strength | float | 0~1，可信度（触点数 × 时间跨度权重） |
| detected_at | datetime | 检测时间 |
| updated_at | datetime | 最后更新时间 |
| expired | bool | 价格突破后标记过期 |

### DetectedPattern — 检测到的形态

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 主键 |
| symbol | str | 交易对 |
| timeframe | str | 时间周期 |
| pattern_type | str | 类型：head_shoulders, head_shoulders_inv, double_top, double_bottom, triangle_asc, triangle_desc, triangle_sym, wedge_up, wedge_down, flag_bull, flag_bear |
| points | JSON | 形态关键点 |
| target_price | float | 预测目标价（形态量度目标） |
| confidence | float | 0~1，置信度 |
| status | str | forming, completed, triggered, failed |
| detected_at | datetime | 检测时间 |
| updated_at | datetime | 最后更新时间 |

### WatchList — 扫描关注列表

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 主键 |
| symbol | str | 交易对 |
| timeframe | str | 时间周期，默认 "1h" |
| enabled | bool | 是否启用 |
| created_at | datetime | 创建时间 |
| last_scanned_at | datetime | 上次扫描时间 |

### ScanRun — 扫描运行记录

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 主键 |
| started_at | datetime | 开始时间 |
| completed_at | datetime | 完成时间 |
| total_symbols | int | 总交易对数 |
| processed | int | 已处理数 |
| new_patterns | int | 新检测到的形态数 |
| status | str | running, completed, failed |

### NotifyConfig — 通知配置

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 主键 |
| channel | str | bark, webhook |
| name | str | 设备/渠道名称 |
| config | JSON | `{"key": "xxx"}` 或 `{"url": "xxx"}` |
| enabled | bool | 是否启用 |

### NotifyLog — 通知记录

| 字段 | 类型 | 说明 |
|------|------|------|
| id | int | 主键 |
| ref_type | str | 关联类型：pattern, line |
| ref_id | int | 关联的 DetectedPattern 或 DetectedLine ID |
| symbol | str | 交易对 |
| message | str | 通知内容 |
| sent_at | datetime | 发送时间 |
| success | bool | 是否成功 |

## 分析引擎

### 统一接口

```python
class LineDetector(ABC):
    def detect(self, klines: List[dict], params: dict) -> List[DetectedLine]: ...

class PatternDetector(ABC):
    def detect(self, klines: List[dict], params: dict) -> List[DetectedPattern]: ...
```

### 基础工具函数 (`engine/utils.py`)

- `find_swing_points(klines, order=5)` — 找局部极值点（前后各 order 根 K 线比较）
- `cluster_prices(prices, tolerance=0.005)` — 价格聚类（误差容忍 0.5%）
- `fit_line(points)` — 最小二乘法拟合直线，返回斜率和截距

### 算法设计

**支撑线 / 阻力线** (`support_resistance.py`)
- 局部极值法找所有 swing low（支撑候选）和 swing high（阻力候选）
- 对价格聚类（tolerance 0.5%~1%），多次触及同一价位形成水平线
- strength = 触点数 × 时间跨度权重

**趋势线** (`trendline.py`)
- 连续 swing low 之间拟合上升趋势线（至少 3 个触点，2 点成线无法验证）
- 连续 swing high 之间拟合下降趋势线
- 线性回归 + 残差过滤，剔除偏离过大的伪趋势
- 2 个触点的候选线需被第 3 个近似触点（tolerance 内）验证后才输出

**通道线** (`channel.py`)
- 先检测趋势线，再找平行于趋势线的另一侧边界
- 上升通道：低点趋势线 + 平行高点线
- 下降通道：高点趋势线 + 平行低点线

**斐波那契** (`fibonacci.py`)
- 找出最近的显著趋势波段（swing high → swing low 或反之）
- 回撤：计算 0.236, 0.382, 0.5, 0.618, 0.786 级别
- 扩展：计算 1.272, 1.618, 2.0, 2.618 目标位

**形态识别** (`patterns.py`)
- 头肩顶/底：检测"高-更高-高"或"低-更低-低"三波结构，验证颈线
- 双顶/双底：两个接近等高/等低的极值点，中间有明显回撤
- 三角形：高点递降 + 低点递升（对称），或一边水平一边收敛
- 楔形：两边同向收敛
- 旗形：急涨/急跌后的小幅反向平行通道

### 检测调度 (`detector.py`)

`analyze(symbol, timeframe, limit)` 方法：
1. 获取 K 线数据
2. 依次调用所有 LineDetector 和 PatternDetector
3. 合并结果，写入数据库（upsert，避免重复）
4. 返回完整结果

## 多币扫描器

### 扫描流程

```
WatchList（关注列表）
    ↓
APScheduler 定时任务（频率匹配 timeframe）
    ↓
遍历 enabled 的交易对
    ↓
拉取 K 线 → 跑全部检测算法
    ↓
与上次结果对比（diff）
    ↓
新出现的形态 → 写入 DetectedPattern → 触发通知
已消失的线形 → 标记 expired
```

### 扫描策略

- 每个交易对独立扫描，单个失败不影响其他
- 去重：同一 symbol + timeframe + pattern_type，关键点位接近（价格误差 < 1%）视为同一形态，不重复通知
- 频率自适应：1h 周期每小时扫一次，4h 每 4 小时扫一次

## 通知服务

### 支持渠道

- **Bark**: iOS 推送，配置 key
- **Webhook**: 通用 HTTP POST，用户填 URL，payload 为 JSON

### 通知内容

```
📊 BTC/USDT 1h
检测到: 头肩顶 (置信度 85%)
颈线位: 67,500
目标价: 65,200
```

### 防骚扰

- 同一形态同一状态只通知一次
- 每个交易对每小时最多 3 条通知
- NotifyLog 记录所有发送历史

## API 设计

### 分析

```
GET  /api/analyze/{symbol}?timeframe=1h&limit=500
     → { klines: [...], lines: [...], patterns: [...] }

GET  /api/lines/{symbol}?timeframe=1h&type=support,resistance&min_strength=0.5
     → { items: [...] }

GET  /api/patterns/{symbol}?timeframe=1h&type=double_bottom&status=forming
     → { items: [...] }
```

### 扫描

```
GET    /api/watchlist
POST   /api/watchlist              → { symbol, timeframe }
DELETE /api/watchlist/{id}
POST   /api/scanner/run            → 手动触发全量扫描
GET    /api/scanner/results?type=head_shoulders&min_confidence=0.7
GET    /api/scanner/status
```

### 市场数据

```
GET  /api/market/klines/{symbol}?timeframe=1h&limit=500
GET  /api/market/symbols?query=BTC
```

### 系统

```
GET    /api/health                  → 健康检查
```

### 通知 + 设置

```
GET    /api/notify/configs
POST   /api/notify/configs
PUT    /api/notify/configs/{id}
DELETE /api/notify/configs/{id}
POST   /api/notify/test/{id}
GET    /api/notify/logs
GET    /api/settings
PUT    /api/settings
```

## 前端设计

### 单币分析页（首页）

- **顶部**: 交易对选择器 + 时间周期切换
- **主体**: lightweight-charts K 线图，叠加画线图层
- **侧栏/底栏**: 检测结果列表，按类型分组，可切换显示/隐藏

### 多币扫描页

- 关注列表管理（增删交易对、设置周期）
- 扫描结果表格：交易对 | 形态 | 置信度 | 关键价位 | 时间 | 状态
- 可按形态类型筛选
- 点击跳转单币分析页

### 设置页

- 通知渠道管理（Bark/Webhook 增删改）
- 通知历史
- 全局参数：检测灵敏度、最低置信度阈值

### 图表渲染

- K 线：`CandlestickSeries`
- 水平线（支撑/阻力）：`PriceLine`
- 趋势线/通道/形态：需自定义 canvas overlay 插件（lightweight-charts 原生不支持任意两点线段，`LineSeries` 是完整数据序列，`PriceLine` 仅水平线）
- 斐波那契：半透明色块覆盖（同样通过 canvas overlay）

颜色方案：
- 支撑线：绿色 | 阻力线：红色
- 趋势线：蓝色 | 通道：蓝色虚线
- 斐波那契：金色
- 形态：紫色

交互：
- hover 线形 → tooltip（类型、强度、价位）
- 点击结果列表项 → 图表定位到对应区域
- 图例面板 → 按类型一键切换显示/隐藏

## 部署

```bash
# 后端 (port 19000)
cd chartlines/backend
source venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 19000

# 前端 (port 14000)
cd chartlines/frontend
npm run build && npx next start -H 0.0.0.0 -p 14000
```

前端通过 `next.config.ts` 代理 `/api/*` 到后端 19000 端口。

## 设计决策

- **无认证**：单用户本地工具，不设登录/鉴权。如需公网部署，后续可加。
- **K 线缓存策略**：每次分析请求时拉取最新 `limit` 条 K 线并 upsert 到缓存表，确保最新数据始终可用。
- **Settings 存储**：使用 key-value 表 `SystemSetting(key, value)`，存放全局配置（检测灵敏度、最低置信度阈值、扫描频率等）。
- **斐波那契"显著趋势"定义**：默认参数为最少 10% 价格变动、跨度至少 20 根 K 线，可通过 settings 调整。
