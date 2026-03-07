# AutoTrade - 加密货币自动交易平台设计文档

## 概述

个人使用的加密货币自动交易平台，支持可视化配置和代码编写两种策略创建方式，提供前端管理界面查看策略运行状态和触发历史，策略触发时发送飞书通知。初期使用模拟交易，后续可对接真实交易所。

## 技术栈

| 层级 | 技术选型 | 说明 |
|------|---------|------|
| 后端 | Python + FastAPI | 量化生态成熟，WebSocket 支持好 |
| 前端 | Next.js + React | shadcn/ui 组件库 + Recharts 图表 |
| 数据库 | SQLite | 单用户场景足够，部署简单 |
| 任务调度 | APScheduler | 策略定时执行 |
| 通知 | 飞书 Webhook | 自定义机器人推送 |

## 架构

单体应用架构：

```
┌───────────────┐     ┌───────────────┐
│   Next.js     │─────│   FastAPI     │
│   前端页面    │ API │   后端服务    │
└───────────────┘     └─────┬─────────┘
                            │
                ┌───────────┼───────────┐
                │           │           │
           ┌────┴───┐ ┌────┴───┐ ┌─────┴─────┐
           │ SQLite │ │ 策略   │ │ 飞书      │
           │ 数据库 │ │ 引擎   │ │ 通知      │
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
| signal_type | TEXT | 信号类型（buy/sell） |
| signal_detail | TEXT | 信号详情（如 RSI=28） |
| action | TEXT | 执行操作（buy/sell/hold） |
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

- APScheduler 管理所有策略的定时任务
- 策略启动时注册 cron job，停止时移除
- 每次执行：获取市场数据 -> 运行策略逻辑 -> 记录触发 -> 发送通知
- 市场数据初期用随机模拟生成，后续可接入 CCXT

## 前端页面

| 页面 | 路径 | 内容 |
|------|------|------|
| 仪表盘 | `/` | 模拟账户总览（余额、盈亏、运行中策略数）、最近触发记录 |
| 策略列表 | `/strategies` | 策略卡片，显示名称、状态、盈亏、启停开关 |
| 创建策略 | `/strategies/new` | 两个 Tab：可视化配置 / 代码编辑器 |
| 策略详情 | `/strategies/:id` | 触发历史时间线、模拟持仓、盈亏曲线 |
| 触发日志 | `/triggers` | 全局触发记录表格，支持按策略筛选 |

UI 风格：深色主题仪表盘，shadcn/ui + Recharts。

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
│   │   │   └── market_data.py   # 市场数据（模拟）
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
