# AutoTrade - 加密货币自动交易平台

个人使用的加密货币自动交易平台，支持可视化配置和代码编写两种策略创建方式，提供前端管理界面查看策略运行状态和触发历史，策略触发时发送飞书通知。使用 Binance 真实行情数据进行模拟交易（Paper Trading），支持策略历史回测。

## 功能特性

- 🎯 **双模式策略创建**：可视化配置 + Python 代码编写
- 📊 **实时仪表盘**：账户余额、盈亏统计、触发记录
- 🤖 **策略管理**：创建、编辑、启停、删除策略
- 📝 **触发日志**：完整的策略执行历史记录
- 📈 **历史回测**：基于真实 K 线数据的策略回测
- 🔔 **飞书通知**：策略触发时自动推送消息

## 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 后端 | Python + FastAPI | 量化生态成熟，WebSocket 支持好 |
| 前端 | Next.js 16 + React 19 | shadcn/ui 组件库 + Recharts 图表 |
| 数据库 | SQLite + SQLAlchemy Async | 单用户场景，部署简单 |
| 任务调度 | APScheduler | 策略定时执行 |
| 行情数据 | Binance REST API | 公开 API，无需认证 |
| 通知 | 飞书 Webhook | 自定义机器人推送 |

## 快速开始

### 环境要求

- Python 3.10+
- Node.js 18+
- SQLite

### 1. 克隆项目

```bash
git clone <repository-url>
cd autotrade
```

### 2. 安装依赖

```bash
# 后端
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 前端
cd ../frontend
npm install
```

### 3. 配置环境变量

```bash
# 后端
cd backend
cp .env.example .env
# 编辑 .env 文件（可选）

# 前端
cd ../frontend
echo "NEXT_PUBLIC_API_URL=http://localhost:8000" > .env.local
```

### 4. 启动服务

#### 方式一：一键启动（推荐）

```bash
# Python 脚本（跨平台）
python start.py

# 或 Shell 脚本（Mac/Linux）
./start.sh

# 或 Makefile
make dev
# 或
make start
```

#### 方式二：手动启动

```bash
# 终端 1：启动后端
cd backend
source venv/bin/activate
uvicorn app.main:app --reload

# 终端 2：启动前端
cd frontend
npm run dev
```

#### 一键启动脚本参数

```bash
# Python 脚本（推荐）
python start.py --help

# 常用选项
python start.py                     # 启动全部（默认端口 18000/13000）
python start.py --no-backend        # 只启动前端
python start.py --no-frontend       # 只启动后端
python start.py --no-auto-kill      # 不自动结束占用端口的进程
python start.py --backend-port 8001 --frontend-port 3001  # 自定义端口

# Shell 脚本
./start.sh --no-backend
./start.sh --backend-port 8001
```

### 5. 访问应用

- 前端: http://localhost:13000
- 后端 API: http://localhost:18000
- API 文档: http://localhost:18000/docs

## 项目结构

```
autotrade/
├── backend/
│   ├── app/
│   │   ├── main.py              # FastAPI 入口
│   │   ├── models.py            # SQLAlchemy 数据模型
│   │   ├── schemas.py           # Pydantic 数据验证
│   │   ├── database.py          # 数据库连接
│   │   ├── logger.py            # 日志配置
│   │   ├── routers/             # API 路由
│   │   │   ├── strategies.py    # 策略管理 API
│   │   │   ├── triggers.py      # 触发日志 API
│   │   │   ├── dashboard.py     # 仪表盘 API
│   │   │   └── account.py       # 账户/持仓 API
│   │   ├── engine/              # 策略引擎（第三阶段）
│   │   └── services/            # 业务服务
│   ├── requirements.txt
│   └── .env
├── frontend/
│   ├── src/
│   │   ├── app/                 # Next.js App Router
│   │   │   ├── page.tsx         # 仪表盘
│   │   │   ├── strategies/      # 策略页面
│   │   │   └── triggers/        # 触发日志页面
│   │   ├── components/          # React 组件
│   │   │   ├── ui/              # shadcn/ui 组件
│   │   │   └── sidebar.tsx      # 侧边栏导航
│   │   └── lib/                 # 工具函数
│   │       ├── api.ts           # API 客户端
│   │       └── utils.ts         # 工具函数
│   ├── package.json
│   └── .env.local
└── docs/
    └── plans/
        ├── PROGRESS.md          # 项目进度
        ├── 2026-03-07-autotrade-implementation-plan.md
        └── 2026-03-07-autotrade-platform-design.md
```

## 开发计划

项目分为 7 个阶段实施：

1. ✅ **项目脚手架搭建** - FastAPI + Next.js + shadcn/ui
2. ✅ **数据库模型与基础 API** - 完整的数据模型和 REST API
3. ⏳ **策略引擎** - 调度器、执行器、市场数据
4. ⏳ **策略回测** - 历史数据回测
5. ⏳ **前端页面实现** - 完整的 UI 界面
6. ⏳ **飞书通知集成** - Webhook 消息推送
7. ⏳ **代码策略支持** - Monaco Editor + 沙箱执行

查看 [PROGRESS.md](docs/plans/PROGRESS.md) 了解详细进度。

## 开发规范

### 后端规范
- 使用 async/await 处理 IO 操作
- 数据库操作使用 SQLAlchemy async session
- API 响应使用 Pydantic schema 验证
- 日志使用 `app.logger.get_logger(__name__)`

### 前端规范
- 使用 axios 进行 API 请求
- 图表使用 Recharts
- UI 组件使用 shadcn/ui
- 深色主题为主

### Git 规范
- 按阶段提交，每阶段一个 commit
- commit message 格式：`phase{N}: 简短描述`

## 常用命令

```bash
# 启动开发服务器
make backend    # 启动后端
make frontend   # 启动前端

# 数据库
make db-reset   # 重置数据库

# 代码质量
make format     # 格式化代码
make test       # 运行测试
make clean      # 清理临时文件

# 查看帮助
make help
```

## 使用指南

### 快速导入预置策略

平台提供10个常见交易策略模板，可一键导入：

```bash
# 导入所有预置策略
python scripts/import_strategies.py

# 清空并重新导入
python scripts/import_strategies.py --clear
```

### 预置策略列表

| 策略名称 | 类型 | 说明 |
|----------|------|------|
| RSI超买卖策略 | 可视化 | RSI<30买入，RSI>70卖出 |
| 双均线交叉策略 | 可视化 | 金叉买入，死叉卖出 |
| 布林带突破策略 | 可视化 | 突破下轨买入，突破上轨卖出 |
| 多重确认策略 | 可视化 | RSI+布林带双重确认 |
| 趋势跟踪策略 | 代码 | 均线之上且趋势向上买入 |
| 均值回归策略 | 代码 | 价格偏离均线后回归 |
| 突破交易策略 | 代码 | 突破近期高点买入 |
| 动量策略 | 代码 | 价格动量强劲时追涨 |
| 网格交易策略 | 代码 | 价格区间内低买高卖 |
| 波动率突破策略 | 代码 | 波动率压缩后突破 |

详细策略配置请参考 `docs/strategies.md`

### 手动创建策略

1. **创建策略**: 在"策略"页面点击"创建策略"
2. **选择类型**: 可视化配置或代码编写
3. **配置参数**: 设置交易对、时间周期、仓位大小、止盈止损
4. **保存启动**: 保存后在策略卡片上点击开关启动
5. **查看触发**: 在"触发日志"页面查看执行记录
6. **回测验证**: 在策略详情页"回测"Tab发起回测

### 飞书通知配置

1. 在飞书群创建自定义机器人，获取 Webhook URL
2. 编辑 `backend/.env`，添加：
   ```
   FEISHU_WEBHOOK_URL=https://open.feishu.cn/open-apis/bot/v2/hook/xxxxxx
   ```
3. 创建策略时开启"飞书通知"开关

## 日志系统

项目提供完善的日志记录，方便问题排查：

### 日志文件位置
```
logs/
├── launcher.log           # 启动脚本日志
├── autotrade.log          # 主应用日志
├── autotrade.error.log    # 错误日志（带堆栈）
└── access.log             # HTTP 访问日志
```

### 查看日志
```bash
# 实时查看所有日志
tail -f logs/*.log

# 仅查看错误
tail -f logs/autotrade.error.log

# 过滤特定内容
tail -f logs/autotrade.log | grep "策略"
```

### 日志配置
编辑 `backend/.env`：
```bash
LOG_LEVEL=INFO           # DEBUG/INFO/WARNING/ERROR
LOG_FORMAT=text          # text 或 json
LOG_MAX_BYTES=10         # 单个文件大小(MB)
LOG_BACKUP_COUNT=10      # 保留文件数
```

详细说明请参考 [docs/logging.md](docs/logging.md)

## 故障排查

### 后端启动失败
1. 检查 `backend/.env` 是否存在
2. 检查依赖是否安装：`pip install -r requirements.txt`
3. 检查端口是否被占用：`lsof -i :18000`
4. 查看日志：`tail -f logs/autotrade.log`

### 端口被占用
脚本会自动尝试结束占用默认端口的进程。如果不想自动结束进程，使用：
```bash
python3 start.py --no-auto-kill
```

或手动指定其他端口：
```bash
python3 start.py --backend-port 8001 --frontend-port 3001
```

### 前端启动失败
1. 检查 `frontend/.env.local` 是否存在
2. 检查依赖是否安装：`npm install`
3. 检查端口是否被占用：`lsof -i :3000`

### 数据库问题
1. 删除 `backend/autotrade.db` 重新初始化
2. 检查模型定义是否正确

### 查看详细错误
```bash
# 查看后端错误日志
tail -100 logs/autotrade.error.log

# 查看启动日志
tail -100 logs/launcher.log

# 查看 API 请求日志
tail -100 logs/access.log
```

## 许可证

MIT

## 致谢

- [FastAPI](https://fastapi.tiangolo.com/)
- [Next.js](https://nextjs.org/)
- [shadcn/ui](https://ui.shadcn.com/)
- [Binance API](https://binance-docs.github.io/apidocs/)
