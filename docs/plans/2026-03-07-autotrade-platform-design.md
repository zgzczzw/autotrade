# AutoTrade - 加密货币自动交易平台设计文档

## 概述

个人使用的加密货币自动交易平台，支持可视化配置和代码编写两种策略创建方式，提供前端管理界面查看策略运行状态和触发历史，策略触发时发送飞书通知。使用 Binance 真实行情数据进行模拟交易（Paper Trading），支持策略历史回测。

## 技术栈

| 层级 | 技术选型 | 说明 |
|------|---------|------|
| 后端 | Python + FastAPI | 量化生态成熟，WebSocket 支持好 |
| 前端 | Next.js + React | shadcn/ui 组件库 + Recharts 图表 |
| 数据库 | SQLite | 单用户场景足够，部署简单 |
| 任务调度 | APScheduler | 策略定时执行 |
| 行情数据 | Binance REST API | 公开 API，无需认证即可获取 K 线 |
| 通知 | 飞书 Webhook | 自定义机器人推送 |

## 架构

单体应用架构：

```
┌───────────────┐     ┌───────────────┐     ┌───────────────┐
│   Next.js     │─────│   FastAPI     │─────│  Binance API  │
│   前端页面    │ API │   后端服务    │     │  真实行情数据  │
└───────────────┘     └─────┬─────────┘     └───────────────┘
                            │
                ┌───────────┼───────────┐
                │           │           │
           ┌────┴───┐ ┌────┴───┐ ┌─────┴─────┐
           │ SQLite │ │ 策略   │ │ 飞书      │
           │ 数据库 │ │ 引擎   │ │ 通知      │
           │+ K线缓存│ │+ 回测  │ │           │
           └────────┘ └────────┘ └───────────┘
```

## 数据模型

### Strategy (策略)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 主键 |
| name | TEXT | 策略名称 |
| type | TEXT | visual / code |
| config_json | JSON | 可视化策略的配置（指标、条件、参数） |
| code | TEXT | 代码策略的 Python 源码 |
| symbol | TEXT | 交易对，如 BTC/USDT |
| timeframe | TEXT | 时间周期：1m/5m/1h/1d |
| position_size | REAL | 仓位大小 |
| position_size_type | TEXT | 仓位模式：fixed（固定金额）/ percent（账户百分比） |
| stop_loss | REAL | 止损百分比 |
| take_profit | REAL | 止盈百分比 |
| notify_enabled | BOOLEAN | 是否开启飞书通知 |
| status | TEXT | running / stopped / error |
| created_at | DATETIME | 创建时间 |
| updated_at | DATETIME | 更新时间 |

### TriggerLog (触发记录)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 主键 |
| strategy_id | INTEGER FK | 关联策略 |
| triggered_at | DATETIME | 触发时间 |
| signal_type | TEXT | 策略产生的信号（buy/sell/error） |
| signal_detail | TEXT | 信号详情（如 RSI=28，低于阈值 30） |
| action | TEXT | 实际执行操作（buy/sell/hold）。信号与操作可能不同，如信号为 buy 但余额不足则 action=hold |
| price | REAL | 触发时价格 |
| quantity | REAL | 交易数量 |
| simulated_pnl | REAL | 模拟盈亏 |

### Position (模拟持仓)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 主键 |
| strategy_id | INTEGER FK | 关联策略 |
| symbol | TEXT | 交易对 |
| side | TEXT | long / short |
| entry_price | REAL | 开仓价格 |
| quantity | REAL | 持仓数量 |
| current_price | REAL | 当前价格 |
| pnl | REAL | 浮动盈亏 |
| opened_at | DATETIME | 开仓时间 |
| closed_at | DATETIME | 平仓时间（NULL 表示未平仓） |

### NotificationLog (通知记录)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 主键 |
| trigger_log_id | INTEGER FK | 关联触发记录 |
| channel | TEXT | 通知渠道（feishu） |
| status | TEXT | sent / failed |
| error_message | TEXT | 失败原因 |
| sent_at | DATETIME | 发送时间 |

### SimAccount (模拟账户)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 主键 |
| initial_balance | REAL | 初始资金 |
| balance | REAL | 当前余额 |
| total_pnl | REAL | 总盈亏 |
| updated_at | DATETIME | 更新时间 |

### KlineData (K 线缓存)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 主键 |
| symbol | TEXT | 交易对（BTCUSDT） |
| timeframe | TEXT | 时间周期（1m/5m/1h/1d） |
| open_time | DATETIME | K 线开盘时间 |
| open | REAL | 开盘价 |
| high | REAL | 最高价 |
| low | REAL | 最低价 |
| close | REAL | 收盘价 |
| volume | REAL | 成交量 |

`(symbol, timeframe, open_time)` 联合唯一索引，upsert 避免重复。

### BacktestResult (回测结果)

| 字段 | 类型 | 说明 |
|------|------|------|
| id | INTEGER PK | 主键 |
| strategy_id | INTEGER FK | 关联策略 |
| symbol | TEXT | 交易对 |
| timeframe | TEXT | 时间周期 |
| start_date | DATETIME | 回测开始时间 |
| end_date | DATETIME | 回测结束时间 |
| initial_balance | REAL | 初始资金 |
| final_balance | REAL | 最终资金 |
| total_pnl | REAL | 总盈亏 |
| pnl_percent | REAL | 盈亏百分比 |
| win_rate | REAL | 胜率 |
| max_drawdown | REAL | 最大回撤 |
| total_trades | INTEGER | 总交易笔数 |
| avg_hold_time | INTEGER | 平均持仓时间（秒） |
| equity_curve | JSON | 资金曲线 `[{time, balance}]` |
| trades | JSON | 交易明细 `[{time, side, price, quantity, pnl}]` |
| created_at | DATETIME | 创建时间 |

> **并发说明**：多个策略 job 可能同时执行并修改 SimAccount 余额。所有余额变更操作需在数据库事务中完成，使用 `SELECT ... FOR UPDATE` 语义（SQLite 单写者模式下天然串行化，但代码中仍需确保事务完整性）。

## 策略引擎

### 可视化策略

用户在前端通过表单配置：
- 交易对（如 BTC/USDT）
- 时间周期（1m/5m/1h/1d）
- 指标条件组合：
  - RSI < 30 买入 / RSI > 70 卖出
  - MA(短周期) 上穿 MA(长周期) 买入 / 下穿卖出
  - 价格突破布林带上/下轨
- 仓位大小（固定金额或百分比）
- 止盈止损

配置以 JSON 格式存储，后端解析并执行。

**config_json schema 定义：**

```json
{
  "buy_conditions": {
    "logic": "AND",
    "rules": [
      { "indicator": "RSI", "params": { "period": 14 }, "operator": "<", "value": 30 },
      { "indicator": "MA_CROSS", "params": { "fast": 5, "slow": 20 }, "operator": "==", "value": "golden" }
    ]
  },
  "sell_conditions": {
    "logic": "AND",
    "rules": [
      { "indicator": "RSI", "params": { "period": 14 }, "operator": ">", "value": 70 }
    ]
  }
}
```

- `logic`：条件组合方式，`AND`（全部满足）或 `OR`（任一满足）
- `indicator`：指标类型，可选 `RSI`、`MA_CROSS`（均线交叉）、`BOLLINGER`（布林带突破）
- `operator`：比较运算符，`<`、`>`、`==`、`<=`、`>=`
- `value`：阈值。MA_CROSS 的 value 为 `golden`（金叉/买入信号）或 `death`（死叉/卖出信号）；BOLLINGER 的 value 为 `above_upper`（突破上轨）或 `below_lower`（突破下轨）

### 代码策略

提供 Python 代码编辑器（前端 Monaco Editor），策略继承基类：

```python
class BaseStrategy:
    def __init__(self, context):
        self.ctx = context  # 提供 API 访问

    def on_tick(self, data):
        """每个周期调用，data 包含K线数据"""
        raise NotImplementedError
```

context API 包括：
- `ctx.get_klines(symbol, timeframe, limit)` - 获取K线
- `ctx.buy(symbol, quantity)` - 模拟买入
- `ctx.sell(symbol, quantity)` - 模拟卖出
- `ctx.get_position(symbol)` - 查询持仓
- `ctx.get_balance()` - 查询余额

代码在后端受限 exec 环境中执行。

### 调度执行

- 使用 APScheduler **AsyncIOScheduler**（而非默认的 BackgroundScheduler），使 job 函数可以直接使用 async/await，与 FastAPI 的 async SQLAlchemy session 兼容
- 策略启动时注册 cron job，停止时移除
- 每次执行：获取市场数据 -> 运行策略逻辑 -> 记录触发 -> 发送通知

### 市场数据（Binance API）

- 使用 Binance 公开 REST API `GET /api/v3/klines` 获取真实 K 线数据，无需 API Key
- 用 `httpx` 异步请求，与现有技术栈一致
- **本地缓存**：K 线数据写入 `KlineData` 表，避免重复请求，同时为回测提供历史数据
- **增量拉取**：每次执行策略时，检查本地最新 K 线时间，仅拉取之后的增量数据
- **降级策略**：API 请求失败时使用本地缓存的最近数据，记录 WARNING 日志
- **请求限制**：Binance API 限制 1200 次/分钟，单次最多返回 1000 根 K 线。回测拉取大量历史数据时需分批请求，间隔 100ms

### 策略回测

回测复用策略引擎的执行逻辑，仅数据源从实时变为历史：

1. 用户选择策略 + 时间范围 + 初始资金
2. 后端从 Binance 批量拉取历史 K 线并缓存到本地
3. 按时间顺序逐根 K 线执行策略（复用 executor 逻辑）
4. 使用独立的虚拟账户，不影响模拟盘 SimAccount
5. 记录每笔虚拟交易，计算统计指标，保存到 BacktestResult

**回测结果指标：**
- 总盈亏、盈亏百分比
- 胜率（盈利交易数 / 总交易数）
- 最大回撤（峰值到谷值的最大跌幅）
- 总交易笔数、平均持仓时间
- 资金曲线数据点（供前端绘图）

## 前端页面

| 页面 | 路径 | 内容 |
|------|------|------|
| 仪表盘 | `/` | 模拟账户总览（余额、盈亏、运行中策略数）、最近触发记录 |
| 策略列表 | `/strategies` | 策略卡片，显示名称、状态、盈亏、启停开关 |
| 创建策略 | `/strategies/new` | 两个 Tab：可视化配置 / 代码编辑器 |
| 策略详情 | `/strategies/:id` | 触发历史时间线、模拟持仓、盈亏曲线、回测 Tab |
| 触发日志 | `/triggers` | 全局触发记录表格，支持按策略筛选 |

UI 风格：深色主题仪表盘，shadcn/ui + Recharts。

**数据实时性**：使用 React Query 的 `refetchInterval` 实现自动轮询，仪表盘和策略详情页每 10 秒刷新一次，策略列表页每 30 秒刷新一次。

## 飞书通知

使用飞书自定义机器人 Webhook，策略触发时发送富文本卡片：

- 策略名称
- 触发信号（如 RSI=28，低于阈值 30）
- 执行操作（买入/卖出）
- 交易对和价格
- 模拟盈亏

可在策略配置中单独开关通知。

## API 设计

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/dashboard` | 仪表盘数据汇总 |
| GET | `/api/strategies` | 策略列表 |
| POST | `/api/strategies` | 创建策略 |
| GET | `/api/strategies/{id}` | 策略详情 |
| PUT | `/api/strategies/{id}` | 更新策略 |
| DELETE | `/api/strategies/{id}` | 删除策略 |
| POST | `/api/strategies/{id}/start` | 启动策略 |
| POST | `/api/strategies/{id}/stop` | 停止策略 |
| GET | `/api/triggers` | 触发日志（支持 strategy_id 筛选） |
| GET | `/api/positions` | 当前模拟持仓 |
| GET | `/api/account` | 模拟账户信息 |
| POST | `/api/account/reset` | 重置模拟账户（清空持仓、触发记录，恢复初始余额） |
| POST | `/api/strategies/{id}/backtest` | 发起回测（参数：symbol, timeframe, start_date, end_date, initial_balance） |
| GET | `/api/backtests/{id}` | 获取回测结果详情 |
| GET | `/api/strategies/{id}/backtests` | 获取某策略的所有回测记录 |

## 日志

使用 Python `logging` 模块，分级别输出：
- `INFO`：策略启动/停止、交易执行、通知发送
- `WARNING`：飞书 Webhook 未配置、余额不足跳过交易
- `ERROR`：策略执行异常、通知发送失败

日志同时输出到控制台和文件（`backend/logs/autotrade.log`），按天轮转。

## 项目结构

```
autotrade/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI 入口
│   │   ├── models.py            # SQLAlchemy 模型
│   │   ├── database.py          # 数据库连接
│   │   ├── routers/
│   │   │   ├── strategies.py    # 策略 API
│   │   │   ├── triggers.py      # 触发日志 API
│   │   │   ├── dashboard.py     # 仪表盘 API
│   │   │   └── account.py       # 账户 API
│   │   ├── engine/
│   │   │   ├── scheduler.py     # APScheduler 调度
│   │   │   ├── executor.py      # 策略执行器
│   │   │   ├── base_strategy.py # 策略基类
│   │   │   ├── market_data.py   # Binance K 线数据获取与缓存
│   │   │   └── backtester.py    # 回测引擎
│   │   └── services/
│   │       ├── feishu.py        # 飞书通知
│   │       └── simulator.py     # 模拟交易引擎
│   ├── requirements.txt
│   └── .env
├── frontend/
│   ├── src/
│   │   ├── app/                 # Next.js App Router
│   │   │   ├── page.tsx         # 仪表盘
│   │   │   ├── strategies/
│   │   │   ├── triggers/
│   │   │   └── layout.tsx
│   │   ├── components/          # 共享组件
│   │   └── lib/                 # API 客户端等
│   ├── package.json
│   └── .env.local
└── docs/
    └── plans/
```
