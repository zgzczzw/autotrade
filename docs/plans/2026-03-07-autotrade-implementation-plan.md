# AutoTrade 实施计划

> 基于 [设计文档](./2026-03-07-autotrade-platform-design.md) 制定的分阶段实施方案。
> 每个阶段独立可测试/可运行，按依赖关系排序。

---

## 第一阶段：项目脚手架搭建

### 目标
完成前后端项目初始化、依赖安装、基础配置，确保两端可独立启动。

### 任务清单

#### 1.1 后端项目初始化

| # | 任务 | 文件路径 | 说明 |
|---|------|---------|------|
| 1 | 创建后端目录结构 | `backend/` | 创建 `app/`、`app/routers/`、`app/engine/`、`app/services/` 目录 |
| 2 | 编写 requirements.txt | `backend/requirements.txt` | 依赖：`fastapi`, `uvicorn[standard]`, `sqlalchemy[asyncio]`, `apscheduler`, `httpx`, `pydantic`, `python-dotenv`, `aiosqlite` |
| 3 | 创建环境变量模板 | `backend/.env.example` | 包含 `DATABASE_URL=sqlite:///./autotrade.db`、`FEISHU_WEBHOOK_URL=`、`SIMULATED_INITIAL_BALANCE=100000` |
| 4 | 编写 FastAPI 入口 | `backend/app/main.py` | 创建 FastAPI app 实例，配置 CORS（允许前端 `localhost:3000`），注册生命周期事件（启动时初始化数据库和调度器），挂载路由占位 |
| 5 | 编写数据库连接模块 | `backend/app/database.py` | SQLAlchemy async engine + sessionmaker，提供 `get_db` 依赖注入函数，`init_db()` 建表函数 |
| 6 | 创建空路由文件 | `backend/app/routers/__init__.py` | 空 `__init__.py`，后续阶段填充 |
| 7 | 配置日志模块 | `backend/app/logger.py` | 配置 Python logging：INFO 级别，同时输出到控制台（StreamHandler）和文件（`backend/logs/autotrade.log`，TimedRotatingFileHandler 按天轮转）。提供 `get_logger(name)` 工厂函数 |

#### 1.2 前端项目初始化

| # | 任务 | 文件路径 | 说明 |
|---|------|---------|------|
| 1 | 初始化 Next.js 项目 | `frontend/` | `npx create-next-app@latest frontend --typescript --tailwind --eslint --app --src-dir` |
| 2 | 安装 shadcn/ui | `frontend/` | `npx shadcn@latest init`，选择深色主题 |
| 3 | 安装核心依赖 | `frontend/package.json` | 追加：`recharts`, `lucide-react`, `@tanstack/react-query`, `date-fns`（日期格式化，shadcn DatePicker 依赖） |
| 4 | 配置 API 客户端 | `frontend/src/lib/api.ts` | 封装 fetch 工具函数，base URL 读取自环境变量 `NEXT_PUBLIC_API_URL` (默认 `http://localhost:8000`) |
| 5 | 创建环境变量 | `frontend/.env.local` | `NEXT_PUBLIC_API_URL=http://localhost:8000` |
| 6 | 创建全局布局 | `frontend/src/app/layout.tsx` | 深色主题，侧边栏导航（仪表盘、策略、触发日志），使用 shadcn/ui 的 `Sidebar` 组件 |
| 7 | 创建占位页面 | `frontend/src/app/page.tsx` | 仪表盘占位页面，显示 "AutoTrade Dashboard" 标题 |

#### 1.3 开发环境配置

| # | 任务 | 文件路径 | 说明 |
|---|------|---------|------|
| 1 | 创建根目录 README | `README.md` | 项目说明、启动方式 |
| 2 | 创建 .gitignore | `.gitignore` | 忽略 `node_modules/`, `__pycache__/`, `.env`, `*.db`, `.next/`, `venv/` |
| 3 | 创建启动脚本（可选） | `Makefile` | `make backend` 启动后端，`make frontend` 启动前端，`make dev` 同时启动 |

### 验收标准

- [ ] 执行 `cd backend && pip install -r requirements.txt && uvicorn app.main:app --reload`，后端在 `localhost:8000` 启动，访问 `/docs` 可见 Swagger UI
- [ ] 执行 `cd frontend && npm install && npm run dev`，前端在 `localhost:3000` 启动，可见带侧边栏导航的深色主题页面
- [ ] 前端页面可成功请求后端（CORS 无报错）
- [ ] 数据库文件 `autotrade.db` 在后端启动后自动创建

---

## 第二阶段：数据库模型与基础 API

### 目标
完成所有数据库模型定义，实现策略 CRUD API 和账户 API，前端可通过 API 创建和管理策略。

### 任务清单

#### 2.1 数据库模型

| # | 任务 | 文件路径 | 说明 |
|---|------|---------|------|
| 1 | 定义 SQLAlchemy 模型 | `backend/app/models.py` | 实现 5 个模型：`Strategy`（含 `position_size_type` 字段）, `TriggerLog`, `Position`, `NotificationLog`, `SimAccount`，字段严格按设计文档 |
| 2 | 定义 Pydantic schema | `backend/app/schemas.py` | 为每个模型创建 `Create`、`Update`、`Response` schema，用于请求验证和响应序列化 |
| 3 | 初始化种子数据 | `backend/app/database.py` | 在 `init_db()` 中检查 SimAccount 表是否为空，为空则创建默认模拟账户（初始余额 100,000 USDT） |

#### 2.2 策略 CRUD API

| # | 任务 | 文件路径 | 说明 |
|---|------|---------|------|
| 1 | 策略路由 | `backend/app/routers/strategies.py` | `GET /api/strategies` - 列表（支持分页、状态筛选） |
|   |  |  | `POST /api/strategies` - 创建策略（区分 visual/code 类型） |
|   |  |  | `GET /api/strategies/{id}` - 详情（含关联的 position 和 trigger 统计） |
|   |  |  | `PUT /api/strategies/{id}` - 更新（仅 stopped 状态可编辑） |
|   |  |  | `DELETE /api/strategies/{id}` - 删除（同时清理关联数据） |
| 2 | 策略启停（占位） | `backend/app/routers/strategies.py` | `POST /api/strategies/{id}/start`（允许从 stopped 和 error 状态启动）和 `stop`，本阶段仅更新 status 字段，调度逻辑在第三阶段实现 |

#### 2.3 账户与持仓 API

| # | 任务 | 文件路径 | 说明 |
|---|------|---------|------|
| 1 | 账户路由 | `backend/app/routers/account.py` | `GET /api/account` - 返回模拟账户信息；`POST /api/account/reset` - 重置模拟账户（停止所有运行中策略、清空持仓和触发记录、恢复初始余额） |
| 2 | 持仓路由 | `backend/app/routers/account.py` | `GET /api/positions` - 返回当前未平仓持仓列表（支持 strategy_id 筛选）。浮动盈亏在 API 返回时根据本地缓存的最新 K 线价格实时计算，不持久化到数据库 |

#### 2.4 触发日志 API

| # | 任务 | 文件路径 | 说明 |
|---|------|---------|------|
| 1 | 触发日志路由 | `backend/app/routers/triggers.py` | `GET /api/triggers` - 返回触发日志列表（支持 strategy_id 筛选、分页、时间范围） |

#### 2.5 仪表盘 API

| # | 任务 | 文件路径 | 说明 |
|---|------|---------|------|
| 1 | 仪表盘路由 | `backend/app/routers/dashboard.py` | `GET /api/dashboard` - 聚合返回：账户余额、总盈亏、运行中策略数、今日触发次数、最近 10 条触发记录 |

#### 2.6 注册路由

| # | 任务 | 文件路径 | 说明 |
|---|------|---------|------|
| 1 | 挂载所有路由到 app | `backend/app/main.py` | 在 main.py 中 `include_router` 注册所有路由模块 |

### 验收标准

- [ ] 通过 Swagger UI (`/docs`) 可成功创建 visual 和 code 两种类型的策略
- [ ] 策略的 CRUD 操作全部正常，包括列表筛选、更新、删除
- [ ] 创建策略后，`GET /api/strategies` 返回正确数据
- [ ] `GET /api/account` 返回初始余额 100,000 的模拟账户
- [ ] `GET /api/dashboard` 返回正确的聚合数据
- [ ] 删除策略时关联的 TriggerLog、Position 数据一并清理
- [ ] 所有 API 均有合理的错误处理（404、422 等）

---

## 第三阶段：策略引擎（调度、执行、真实市场数据）

### 目标
实现策略的定时调度执行，包括 Binance 真实 K 线数据获取与缓存、可视化策略解析执行、模拟交易（开仓/平仓/盈亏计算）。

### 任务清单

#### 3.1 市场数据（Binance API）

| # | 任务 | 文件路径 | 说明 |
|---|------|---------|------|
| 1 | 定义 KlineData 模型 | `backend/app/models.py` | 新增 `KlineData` 模型，字段按设计文档。`(symbol, timeframe, open_time)` 联合唯一索引 |
| 2 | 实现 Binance K 线客户端 | `backend/app/engine/market_data.py` | 使用 httpx 异步调用 `GET https://api.binance.com/api/v3/klines`。实现 `fetch_klines(symbol, timeframe, start_time, end_time, limit)` 方法，返回标准化 K 线数组。全系统统一使用 Binance 原生 symbol 格式（BTCUSDT），无需转换 |
| 3 | 实现本地缓存层 | `backend/app/engine/market_data.py` | 实现 `get_klines(symbol, timeframe, limit)` 接口：先查本地 KlineData 表，缺失则从 Binance 拉取并 upsert 到本地。增量拉取：只请求本地最新 K 线之后的数据 |
| 4 | 实现批量历史数据拉取 | `backend/app/engine/market_data.py` | 实现 `fetch_historical_klines(symbol, timeframe, start_date, end_date)` 供回测使用。Binance 单次最多 1000 根，需分批请求，间隔 100ms 避免触发限流 |
| 5 | 降级与错误处理 | `backend/app/engine/market_data.py` | API 请求失败时返回本地缓存的最近数据，记录 WARNING 日志。网络超时设置 10 秒 |
| 6 | 实现技术指标计算 | `backend/app/engine/indicators.py` | 纯 Python 实现基础指标：RSI、SMA/EMA（移动平均线）、布林带（Bollinger Bands）。输入为 K 线数组，输出为指标值数组 |

#### 3.2 策略基类与上下文

| # | 任务 | 文件路径 | 说明 |
|---|------|---------|------|
| 1 | 实现策略基类 | `backend/app/engine/base_strategy.py` | 定义 `BaseStrategy` 抽象类，包含 `on_tick(data)` 方法。定义 `StrategyContext` 类，提供设计文档中的 API：`get_klines()`, `buy()`, `sell()`, `get_position()`, `get_balance()` |
| 2 | 实现模拟交易引擎 | `backend/app/services/simulator.py` | 处理模拟买入/卖出逻辑：创建 Position 记录、更新 SimAccount 余额、计算盈亏、检查止盈止损。`execute_buy(strategy_id, symbol, quantity, price)` 和 `execute_sell(...)` |

#### 3.3 策略执行器

| # | 任务 | 文件路径 | 说明 |
|---|------|---------|------|
| 1 | 实现可视化策略执行器 | `backend/app/engine/executor.py` | 解析 `config_json`（按设计文档定义的 schema），获取市场数据，计算指标，按 `logic`（AND/OR）评估条件组合，产生交易信号。支持的条件类型：RSI 阈值、MA_CROSS 均线交叉（golden/death）、BOLLINGER 布林带突破（above_upper/below_lower） |
| 2 | 实现执行结果记录 | `backend/app/engine/executor.py` | 策略执行后写入 TriggerLog 记录，包含信号类型、详情、执行操作、价格、数量、模拟盈亏 |
| 3 | 实现止盈止损检查 | `backend/app/engine/executor.py` | 每次执行时检查现有持仓是否触及止盈/止损线，触及则自动平仓 |

#### 3.4 任务调度

| # | 任务 | 文件路径 | 说明 |
|---|------|---------|------|
| 1 | 实现调度管理器 | `backend/app/engine/scheduler.py` | 使用 APScheduler 的 **AsyncIOScheduler**（非 BackgroundScheduler），使 job 直接支持 async/await。提供 `start_strategy(strategy_id)` 和 `stop_strategy(strategy_id)` 方法。根据策略的 timeframe 设置 interval 触发间隔（1m/5m/1h/1d）。应用启动时恢复所有 running 状态的策略 |
| 2 | 对接策略启停 API | `backend/app/routers/strategies.py` | 更新 start/stop 端点，调用 scheduler 的 `start_strategy` / `stop_strategy`，失败时设置策略状态为 error |

#### 3.5 应用生命周期

| # | 任务 | 文件路径 | 说明 |
|---|------|---------|------|
| 1 | 启动时初始化引擎 | `backend/app/main.py` | FastAPI lifespan：启动时初始化数据库、启动调度器、恢复运行中策略；关闭时优雅停止调度器 |

### 验收标准

- [ ] 创建一个可视化策略（如 RSI < 30 买入、RSI > 70 卖出），启动后调度器按 timeframe 定时执行
- [ ] 策略执行时从 Binance API 获取真实 K 线数据、缓存到本地、计算指标、产生交易信号
- [ ] K 线数据正确写入 KlineData 表，重复数据不会插入
- [ ] Binance API 不可用时，使用本地缓存数据继续执行
- [ ] 交易信号触发后正确创建 TriggerLog 记录
- [ ] 模拟买入后 Position 表有记录，SimAccount 余额减少
- [ ] 模拟卖出（平仓）后 Position 标记已关闭，SimAccount 余额更新，盈亏正确计算
- [ ] 止盈止损触发后自动平仓并记录
- [ ] 后端重启后，running 状态的策略自动恢复调度
- [ ] 停止策略后调度任务被正确移除

---

## 第四阶段：策略回测

### 目标
实现策略历史回测功能，用户可选择时间范围回测策略表现，查看盈亏指标和资金曲线。

### 任务清单

#### 4.1 回测引擎

| # | 任务 | 文件路径 | 说明 |
|---|------|---------|------|
| 1 | 定义 BacktestResult 模型 | `backend/app/models.py` | 新增 `BacktestResult` 模型，字段按设计文档。`equity_curve` 和 `trades` 为 JSON 字段 |
| 2 | 定义回测 Pydantic schema | `backend/app/schemas.py` | 新增 `BacktestCreate`（请求参数：start_date, end_date, initial_balance；symbol 和 timeframe 取策略自身配置）和 `BacktestResponse` schema |
| 3 | 实现回测引擎 | `backend/app/engine/backtester.py` | 核心回测逻辑：接收策略 + 历史 K 线数组，创建独立虚拟账户，按时间顺序逐根 K 线调用 executor 逻辑，记录每笔交易，计算统计指标（总盈亏、胜率、最大回撤、平均持仓时间），生成资金曲线数据点。复用 `executor.py` 中的策略评估逻辑 |
| 4 | 实现最大回撤计算 | `backend/app/engine/backtester.py` | 遍历资金曲线，计算峰值到谷值的最大跌幅百分比 |

#### 4.2 回测 API

| # | 任务 | 文件路径 | 说明 |
|---|------|---------|------|
| 1 | 回测路由 | `backend/app/routers/backtests.py` | `POST /api/strategies/{id}/backtest` - 发起回测：从策略读取 symbol 和 timeframe，校验 start_date/end_date/initial_balance，调用 `market_data.fetch_historical_klines` 获取历史数据，调用回测引擎，保存结果到 BacktestResult |
|   |  |  | `GET /api/backtests/{id}` - 获取回测结果详情 |
|   |  |  | `GET /api/strategies/{id}/backtests` - 获取某策略所有回测记录（按时间倒序） |
| 2 | 注册路由 | `backend/app/main.py` | 挂载 backtests router |

### 验收标准

- [ ] 通过 API 发起回测，指定 BTC/USDT 最近 30 天的数据，回测成功完成
- [ ] 回测结果包含正确的统计指标：总盈亏、胜率、最大回撤、交易笔数
- [ ] 资金曲线数据点数量与 K 线数量一致
- [ ] 回测使用独立虚拟账户，不影响模拟盘 SimAccount
- [ ] 历史 K 线数据正确缓存，重复回测同一时间段不会重复请求 Binance
- [ ] 回测记录持久化，可通过 API 查询历史回测结果

---

## 第五阶段：前端页面实现

### 目标
实现全部 5 个前端页面，与后端 API 完成联调，用户可通过 Web 界面完整管理策略。

### 任务清单

#### 5.1 前置组件与工具

| # | 任务 | 文件路径 | 说明 |
|---|------|---------|------|
| 1 | 安装 shadcn/ui 组件 | - | `npx shadcn@latest add button card table badge switch tabs input select dialog toast separator calendar popover`（calendar + popover 用于 DatePicker） |
| 2 | API hooks 封装 | `frontend/src/lib/api.ts` | 使用 React Query 封装所有 API 调用：`useStrategies()`, `useStrategy(id)`, `useDashboard()`, `useTriggers()`, `useAccount()`, `usePositions()`。仪表盘和策略详情 hooks 设置 `refetchInterval: 10000`（10秒），策略列表设置 `refetchInterval: 30000`（30秒） |
| 3 | 类型定义 | `frontend/src/lib/types.ts` | 定义 TypeScript 接口：`Strategy`, `TriggerLog`, `Position`, `SimAccount`, `DashboardData`, `BacktestResult`, `BacktestCreate`。提供 `formatSymbol(symbol: string)` 工具函数将 BTCUSDT 转为 BTC/USDT 供展示用 |
| 4 | React Query Provider | `frontend/src/app/providers.tsx` | 创建 QueryClientProvider 包裹应用 |
| 5 | 更新 layout | `frontend/src/app/layout.tsx` | 引入 providers，完善侧边栏导航样式（图标、活跃状态高亮） |

#### 5.2 仪表盘页面

| # | 任务 | 文件路径 | 说明 |
|---|------|---------|------|
| 1 | 统计卡片组件 | `frontend/src/components/stat-card.tsx` | 可复用统计卡片：标题、数值、趋势指示 |
| 2 | 最近触发列表组件 | `frontend/src/components/recent-triggers.tsx` | 表格形式展示最近触发记录 |
| 3 | 仪表盘页面 | `frontend/src/app/page.tsx` | 布局：顶部 4 个统计卡片（余额、总盈亏、运行策略数、今日触发数）+ 下方最近触发列表 |

#### 5.3 策略列表页面

| # | 任务 | 文件路径 | 说明 |
|---|------|---------|------|
| 1 | 策略卡片组件 | `frontend/src/components/strategy-card.tsx` | 展示：策略名称、类型标签（visual/code）、交易对、状态 badge、模拟盈亏、启停 Switch 开关 |
| 2 | 策略列表页面 | `frontend/src/app/strategies/page.tsx` | 卡片网格布局，顶部有"创建策略"按钮和状态筛选，点击卡片跳转详情 |
| 3 | 启停开关逻辑 | `frontend/src/app/strategies/page.tsx` | Switch 切换时调用 start/stop API，乐观更新 + 错误回滚 |

#### 5.4 创建策略页面

| # | 任务 | 文件路径 | 说明 |
|---|------|---------|------|
| 1 | 基础配置表单组件 | `frontend/src/components/strategy-form-base.tsx` | 通用字段：策略名称、交易对选择（BTC/USDT, ETH/USDT 等）、时间周期、仓位大小、止盈止损、通知开关 |
| 2 | 可视化配置组件 | `frontend/src/components/visual-config.tsx` | 条件配置器：分别配置买入条件和卖出条件，每组条件选择组合逻辑（AND/OR），然后添加规则：选择指标类型（RSI/MA_CROSS/BOLLINGER）-> 填写参数 -> 设置比较运算和阈值。配置结果按设计文档定义的 config_json schema 序列化为 JSON |
| 3 | 代码编辑器占位 | `frontend/src/components/code-editor-placeholder.tsx` | 本阶段用 textarea 占位，第七阶段替换为 Monaco Editor |
| 4 | 创建策略页面 | `frontend/src/app/strategies/new/page.tsx` | Tabs 切换"可视化配置"和"代码编写"，底部提交按钮，成功后跳转策略列表 |

#### 5.5 策略详情页面

| # | 任务 | 文件路径 | 说明 |
|---|------|---------|------|
| 1 | 盈亏曲线图组件 | `frontend/src/components/pnl-chart.tsx` | Recharts 折线图，展示策略累计盈亏随时间变化 |
| 2 | 触发历史时间线组件 | `frontend/src/components/trigger-timeline.tsx` | 时间线形式展示触发记录：时间、信号、操作、价格 |
| 3 | 持仓信息组件 | `frontend/src/components/position-info.tsx` | 展示当前策略的模拟持仓：方向、开仓价、数量、浮动盈亏 |
| 4 | 策略详情页面 | `frontend/src/app/strategies/[id]/page.tsx` | 顶部：策略信息卡片（名称、状态、配置摘要、启停按钮、编辑按钮）。中部：盈亏曲线图。下部：Tab 切换"触发历史"、"持仓信息"和"回测" |
| 5 | 策略编辑页面 | `frontend/src/app/strategies/[id]/edit/page.tsx` | 复用创建页面的表单组件，预填数据，提交调用 PUT API |
| 6 | 回测面板组件 | `frontend/src/components/backtest-panel.tsx` | 回测配置表单（时间范围日期选择器、初始资金输入、发起回测按钮）+ 结果展示：统计指标卡片（总盈亏、胜率、最大回撤、交易笔数）+ 资金曲线图（Recharts）+ 交易明细表格。支持查看历史回测记录列表 |

#### 5.6 触发日志页面

| # | 任务 | 文件路径 | 说明 |
|---|------|---------|------|
| 1 | 触发日志页面 | `frontend/src/app/triggers/page.tsx` | 全局触发记录表格（shadcn Table），列：时间、策略名称、信号类型、信号详情、操作、价格、数量、模拟盈亏。支持按策略筛选（下拉框）、分页 |

### 验收标准

- [ ] 仪表盘正确显示账户余额、总盈亏、运行策略数量、最近触发记录
- [ ] 策略列表以卡片形式展示所有策略，启停 Switch 可实时切换策略状态
- [ ] 可通过可视化配置表单创建策略，JSON 配置正确保存到后端
- [ ] 策略详情页展示盈亏曲线（Recharts）、触发历史时间线、持仓信息、回测面板
- [ ] 回测面板可配置时间范围和初始资金，发起回测后展示统计指标和资金曲线
- [ ] 可查看历史回测记录列表
- [ ] 触发日志页面支持策略筛选和分页
- [ ] 所有页面在深色主题下视觉一致
- [ ] 页面间导航流畅，侧边栏活跃状态正确高亮
- [ ] API 请求失败时显示 toast 错误提示

---

## 第六阶段：飞书通知集成

### 目标
实现策略触发时自动发送飞书富文本卡片通知，通知记录可追溯。

### 任务清单

#### 6.1 飞书通知服务

| # | 任务 | 文件路径 | 说明 |
|---|------|---------|------|
| 1 | 实现飞书 Webhook 客户端 | `backend/app/services/feishu.py` | 使用 httpx 异步发送飞书自定义机器人消息。实现 `send_trade_signal(strategy_name, signal_type, signal_detail, action, symbol, price, pnl)` 方法。消息格式为飞书交互卡片（interactive card），包含策略名称、信号信息、操作详情、价格和盈亏，使用颜色区分买入（绿色）和卖出（红色） |
| 2 | 通知记录持久化 | `backend/app/services/feishu.py` | 发送后写入 NotificationLog 表，记录 status（sent/failed）和 error_message |
| 3 | 异常处理与重试 | `backend/app/services/feishu.py` | Webhook 请求超时（5秒）、失败时记录错误但不中断策略执行，可选重试 1 次 |

#### 6.2 集成到策略执行流程

| # | 任务 | 文件路径 | 说明 |
|---|------|---------|------|
| 1 | 执行器中调用通知 | `backend/app/engine/executor.py` | 策略触发交易信号后，检查 `notify_enabled`，若开启则异步调用飞书通知服务 |

#### 6.3 通知配置管理

| # | 任务 | 文件路径 | 说明 |
|---|------|---------|------|
| 1 | 环境变量配置 | `backend/.env.example` | 添加 `FEISHU_WEBHOOK_URL` 配置项 |
| 2 | 配置校验 | `backend/app/services/feishu.py` | 启动时校验 Webhook URL 格式，未配置时记录警告但不阻止启动 |

### 验收标准

- [ ] 配置 Webhook URL 后，策略触发时飞书群收到富文本卡片消息
- [ ] 卡片内容包含：策略名称、触发信号、执行操作、交易对、价格、盈亏
- [ ] 买入信号和卖出信号使用不同颜色区分
- [ ] 通知发送记录写入 NotificationLog 表
- [ ] 通知发送失败时：不影响策略正常执行，NotificationLog 记录 failed 状态和错误原因
- [ ] 策略的 `notify_enabled=false` 时不发送通知
- [ ] 未配置 Webhook URL 时应用正常启动，控制台输出警告

---

## 第七阶段：代码策略支持

### 目标
实现前端 Monaco Editor 代码编辑器和后端沙箱执行环境，用户可用 Python 代码编写自定义策略。

### 任务清单

#### 7.1 前端代码编辑器

| # | 任务 | 文件路径 | 说明 |
|---|------|---------|------|
| 1 | 安装 Monaco Editor | `frontend/package.json` | 添加 `@monaco-editor/react` 依赖 |
| 2 | 实现代码编辑器组件 | `frontend/src/components/code-editor.tsx` | 基于 Monaco Editor，Python 语法高亮，深色主题（vs-dark），预置策略模板代码（包含 BaseStrategy 骨架和注释说明），自动补全 context API 方法（`ctx.get_klines`, `ctx.buy`, `ctx.sell`, `ctx.get_position`, `ctx.get_balance`） |
| 3 | 替换占位编辑器 | `frontend/src/app/strategies/new/page.tsx` | 将 textarea 占位组件替换为 Monaco Editor 组件 |
| 4 | 策略模板 | `frontend/src/lib/strategy-template.ts` | 导出默认策略代码模板字符串，包含完整的 BaseStrategy 示例和 context API 使用说明注释 |

#### 7.2 后端沙箱执行

| # | 任务 | 文件路径 | 说明 |
|---|------|---------|------|
| 1 | 实现代码策略执行器 | `backend/app/engine/executor.py` | 添加 `execute_code_strategy(strategy)` 方法。使用 `RestrictedPython` 或受限 `exec` 执行用户代码。限制措施：禁用 `import`（仅允许白名单模块如 `math`）、禁用文件 I/O、禁用网络访问、设置执行超时（10秒）、限制内存使用 |
| 2 | 安全沙箱模块 | `backend/app/engine/sandbox.py` | 封装安全执行环境：自定义 `__builtins__` 白名单、受限全局命名空间、超时装饰器（使用 `signal.alarm` 或 `threading.Timer`）、异常捕获与格式化错误信息 |
| 3 | 代码策略的 StrategyContext | `backend/app/engine/base_strategy.py` | 确保 StrategyContext 在沙箱中正确传递，代码策略通过 `self.ctx` 调用所有 API |
| 4 | 更新 requirements.txt | `backend/requirements.txt` | 添加 `RestrictedPython`（如选用） |

#### 7.3 代码验证与错误处理

| # | 任务 | 文件路径 | 说明 |
|---|------|---------|------|
| 1 | 代码语法检查 API | `backend/app/routers/strategies.py` | 新增 `POST /api/strategies/validate-code` 端点，接收 Python 代码，进行语法检查（`ast.parse`）和安全检查（禁用的 import、函数调用），返回错误列表 |
| 2 | 前端语法检查集成 | `frontend/src/components/code-editor.tsx` | 编辑器失焦或手动点击"验证"按钮时调用验证 API，在编辑器中标记错误行 |
| 3 | 执行错误处理 | `backend/app/engine/executor.py` | 代码策略执行出错时：记录错误到 TriggerLog（signal_type='error'）、策略状态设为 error、发送飞书错误通知（如开启通知） |

### 验收标准

- [ ] 创建策略页面"代码编写"Tab 显示 Monaco Editor，有 Python 语法高亮和深色主题
- [ ] 编辑器预填策略模板代码，包含完整的 BaseStrategy 骨架
- [ ] context API 方法有自动补全提示
- [ ] 代码验证 API 能检测语法错误和禁用的 import 语句
- [ ] 代码策略可正常创建、保存、启动执行
- [ ] 代码策略在沙箱中执行，无法进行文件 I/O 或网络访问
- [ ] 代码执行超时（>10秒）时被强制终止，策略标记为 error
- [ ] 代码策略通过 `ctx` 对象可正常调用模拟交易 API
- [ ] 代码策略执行错误时有清晰的错误信息，不影响其他策略运行

---

## 附录

### 技术决策记录

| 决策 | 选择 | 原因 |
|------|------|------|
| 数据库 ORM | SQLAlchemy (async) | FastAPI 生态推荐，async 支持好 |
| API 数据验证 | Pydantic v2 | FastAPI 原生集成 |
| 前端状态管理 | React Query | 服务端状态为主，缓存和重新获取策略简单 |
| 代码编辑器 | Monaco Editor | VS Code 同款引擎，Python 支持完善 |
| 技术指标计算 | 自行实现 | 仅需 RSI/MA/Bollinger 三种，避免引入 TA-Lib 等重依赖 |
| 代码沙箱 | RestrictedPython + exec | 单用户场景安全性要求适中，容器隔离过重 |
| 调度器 | APScheduler AsyncIOScheduler | 与 FastAPI async 生态兼容，job 中可直接使用 async session |
| 日志 | Python logging + TimedRotatingFileHandler | 按天轮转，同时输出控制台和文件 |

### 完整文件清单

```
autotrade/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py
│   │   ├── database.py
│   │   ├── models.py
│   │   ├── schemas.py
│   │   ├── routers/
│   │   │   ├── __init__.py
│   │   │   ├── strategies.py
│   │   │   ├── triggers.py
│   │   │   ├── dashboard.py
│   │   │   ├── account.py
│   │   │   └── backtests.py
│   │   ├── engine/
│   │   │   ├── __init__.py
│   │   │   ├── scheduler.py
│   │   │   ├── executor.py
│   │   │   ├── base_strategy.py
│   │   │   ├── market_data.py
│   │   │   ├── indicators.py
│   │   │   ├── backtester.py
│   │   │   └── sandbox.py
│   │   └── services/
│   │       ├── __init__.py
│   │       ├── feishu.py
│   │       └── simulator.py
│   ├── requirements.txt
│   ├── .env.example
│   └── .env
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── layout.tsx
│   │   │   ├── page.tsx
│   │   │   ├── providers.tsx
│   │   │   ├── strategies/
│   │   │   │   ├── page.tsx
│   │   │   │   ├── new/
│   │   │   │   │   └── page.tsx
│   │   │   │   └── [id]/
│   │   │   │       ├── page.tsx
│   │   │   │       └── edit/
│   │   │   │           └── page.tsx
│   │   │   └── triggers/
│   │   │       └── page.tsx
│   │   ├── components/
│   │   │   ├── stat-card.tsx
│   │   │   ├── recent-triggers.tsx
│   │   │   ├── strategy-card.tsx
│   │   │   ├── strategy-form-base.tsx
│   │   │   ├── visual-config.tsx
│   │   │   ├── code-editor.tsx
│   │   │   ├── pnl-chart.tsx
│   │   │   ├── trigger-timeline.tsx
│   │   │   ├── position-info.tsx
│   │   │   └── backtest-panel.tsx
│   │   └── lib/
│   │       ├── api.ts
│   │       ├── types.ts
│   │       └── strategy-template.ts
│   ├── package.json
│   ├── .env.local
│   └── tailwind.config.ts
├── .gitignore
├── README.md
├── Makefile
└── docs/
    └── plans/
        ├── 2026-03-07-autotrade-platform-design.md
        └── 2026-03-07-autotrade-implementation-plan.md
```
