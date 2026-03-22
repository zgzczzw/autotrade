# 账号体系设计文档

**日期：** 2026-03-22
**状态：** 已批准
**方案：** 方案 A — Cookie Session（itsdangerous 签名）

---

## 背景与目标

AutoTrade 当前是无认证的单用户系统，所有 API 端点公开。目标是引入多用户支持，每个用户的数据（策略、持仓、日志等）相互隔离，同时保持架构简单。

---

## 数据模型

### 新增：`users` 表

```sql
CREATE TABLE users (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    username   VARCHAR(50) NOT NULL UNIQUE,
    password_hash VARCHAR NOT NULL,
    is_admin   BOOLEAN NOT NULL DEFAULT FALSE,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```

`is_admin` 字段当前用于保护高影响力端点（如 `PUT /api/settings` 数据源切换），同时为未来扩展保留。

### 现有模型加 `user_id` 外键

以下模型新增直接 `user_id INTEGER NOT NULL REFERENCES users(id)`：

- `strategies`
- `positions`
- `sim_accounts`
- `backtest_results`

`trigger_logs` 和 `notification_logs` **不加** `user_id`，通过 JOIN 实现隔离：

- `trigger_logs`：`trigger_logs.strategy_id → strategies.user_id`
- `notification_logs`：`notification_logs.trigger_log_id → trigger_logs.strategy_id → strategies.user_id`

所有涉及这两张表的查询需通过 JOIN 验证归属，避免冗余列带来的数据不一致风险。

### 全局共享模型（不加 user_id）

- `kline_data` — 行情缓存，所有用户共享
- `system_settings` — 系统级配置，仅管理员可修改

### 数据迁移策略

**步骤顺序严格，代码变更与迁移必须同步部署：**

1. **代码变更（先于迁移部署）：** 更新 `init_db()` 停止自动 seed 全局 `SimAccount`（否则迁移运行时可能产生无 `user_id` 的孤立行，导致步骤 5 的 NOT NULL 约束失败）
2. Alembic migration：新增 `users` 表
3. Alembic migration：给 `strategies`、`positions`、`sim_accounts`、`backtest_results` 加 `user_id`（先允许 NULL）
4. 迁移数据脚本：自动创建第一个 admin 用户（用户名 `admin`，密码从环境变量 `ADMIN_PASSWORD` 读取，默认 `changeme`）；将所有现有数据的 `user_id` 设为 admin 的 id
5. Alembic migration：将 `user_id` 列改为 NOT NULL
6. 注册流程更新：在 `POST /api/auth/register` 中为新用户自动创建 `SimAccount`

### SimAccount 生命周期

- 注册时：自动为新用户创建一条 `SimAccount`（初始余额从配置读取，默认 100,000 USDT）
- `dashboard.py` 中懒创建 `SimAccount` 的逻辑需更新为按 `user_id` 查找或创建

---

## 认证层（后端）

### SECRET_KEY 校验

`SECRET_KEY` **必须**在 `main.py` 的 `lifespan` 启动函数中校验：

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    secret_key = os.environ.get("SECRET_KEY")
    if not secret_key:
        raise RuntimeError("SECRET_KEY 环境变量未设置，拒绝启动")
    # 初始化 serializer
    app.state.serializer = URLSafeTimedSerializer(secret_key)
    ...
```

不在模块级初始化 serializer，避免 import 时崩溃产生误导性错误。

### Session 机制

- 库：`itsdangerous.URLSafeTimedSerializer`
- Cookie 名：`session`
- Cookie 属性：`HttpOnly=True`，`SameSite=Lax`，`Max-Age=604800`（7 天）
- `Secure=True`（生产环境）；本地开发通过 `ENV=development` 环境变量禁用
- **实现方式：** 在 `lifespan` 启动时读取 `ENV`，计算 `COOKIE_SECURE = (os.environ.get("ENV") != "development")`，存入 `app.state.cookie_secure`。`login` 和 `register` handler 统一从 `request.app.state.cookie_secure` 读取，不在各路由中重复判断。
- 内容：签名后的 `user_id`

### 新增路由：`/api/auth/`

| 方法 | 路径 | 请求体 | 响应 | 说明 |
|------|------|--------|------|------|
| POST | `/api/auth/register` | `{username, password}` | 用户信息 + Set-Cookie | 注册并自动登录，同时创建 SimAccount |
| POST | `/api/auth/login` | `{username, password}` | 用户信息 + Set-Cookie | 登录 |
| POST | `/api/auth/logout` | — | 200 + 清除 Cookie | 退出 |
| GET  | `/api/auth/me` | — | 用户信息 或 `{"user": null}` | 已登录返回用户信息（200），未登录返回 `{"user": null}`（200，不返回 401）|

**注册开放性：** 注册端点当前无访问控制，任何能访问服务器的人均可注册。这是已知的权衡，适用于内部/可信网络环境。生产部署建议在反向代理（nginx/Caddy）层限制访问来源，或在未来版本中通过 `ALLOW_REGISTRATION` 环境变量控制开关。

### FastAPI 依赖注入

```python
async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    session_cookie = request.cookies.get("session")
    if not session_cookie:
        raise HTTPException(status_code=401, detail="未登录")
    try:
        user_id = request.app.state.serializer.loads(session_cookie, max_age=604800)
    except itsdangerous.BadData:
        # 仅捕获签名/过期相关异常（BadSignature、SignatureExpired 的父类）
        # 其他异常（如 AttributeError）应向上传播为 500
        raise HTTPException(status_code=401, detail="Session 无效或已过期")
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    return user
```

所有现有 router 函数签名加 `current_user: User = Depends(get_current_user)`，查询时过滤 `user_id = current_user.id`。

### 高权限端点保护

`is_admin=True` 才可访问：

- `PUT /api/settings` — 修改数据源（会清空 kline 缓存，影响所有用户）

### 危险端点改造

`POST /api/account/reset`（当前无 WHERE 子句，会删除全表数据）必须改为：

```sql
-- 1. 停止当前用户所有运行中的策略（通知 scheduler 取消任务）
-- 2. 删除历史数据
DELETE FROM positions WHERE user_id = current_user.id;
DELETE FROM trigger_logs WHERE strategy_id IN (
    SELECT id FROM strategies WHERE user_id = current_user.id
);
DELETE FROM notification_logs WHERE trigger_log_id IN (
    SELECT tl.id FROM trigger_logs tl
    JOIN strategies s ON tl.strategy_id = s.id
    WHERE s.user_id = current_user.id
);
-- 3. 重置 sim_accounts 余额至初始值（从 SystemSetting 或默认值读取）
UPDATE sim_accounts SET balance = 100000, total_pnl = 0
WHERE user_id = current_user.id;
```

**调度器交互：** reset 前必须先调用 `scheduler.stop_user_strategies(user_id)` 停止该用户所有运行中的策略，flush 其内存中的 `StrategyContext`，再执行 DB 清理。策略状态重置为 `stopped`。

### 调度器多用户适配

`engine/scheduler.py` 的 `restore_running_strategies()` 和 `StrategyContext.get_balance()` 当前是全局查询，需更新：

- `restore_running_strategies`：查询策略时保留 `user_id`，传入 `StrategyContext`
- `StrategyContext.get_balance()`：改为 `SELECT * FROM sim_accounts WHERE user_id = strategy.user_id`
- `simulator.py` 的 `execute_buy`/`execute_sell`：通过 `sim_account_id` 关联，而非 `LIMIT 1` 全局查询

### 密码安全

- 使用 `passlib[bcrypt]` 进行密码哈希
- 注册校验：用户名唯一，密码最短 6 位
- 登录校验：用户名存在 + 密码匹配（常量时间比较，防时序攻击）
- 速率限制：登录/注册端点无内置限速，建议生产环境通过反向代理配置（超出范围，已知风险）

---

## 前端

### 新增页面

| 路径 | 说明 |
|------|------|
| `/login` | 用户名+密码登录表单，成功跳转首页 |
| `/register` | 注册表单（用户名、密码、确认密码），成功自动登录跳转首页 |

### 路由保护

`middleware.ts`（Next.js Edge Middleware）：

- 检查请求中是否包含 `session` Cookie（仅检查存在性，不验签）
- 未登录访问任意页面 → `redirect('/login')`
- 已登录访问 `/login` 或 `/register` → `redirect('/')`
- 豁免路径：`/api/auth/*`、`/_next/*`、`/favicon.ico`

> **已知限制：** middleware 只检查 Cookie 存在性，不验证签名。伪造 Cookie 可绕过重定向，但后端 API 调用仍会返回 401。结合 401 拦截器，实际安全性不受影响。

### Sidebar 改动

**桌面端和移动端均需更新：**

- 桌面端 Sidebar 底部：当前用户名显示 + 退出登录按钮
- 移动端底部导航栏：同样添加用户名显示 + 退出登录入口
- 点击退出：调用 `POST /api/auth/logout` → 跳转 `/login`
- 用户信息通过 `GET /api/auth/me` 在 layout 层获取并注入

### API 客户端

`lib/api.ts` 中 axios 实例：

```typescript
const api = axios.create({
  baseURL: '/api',
  withCredentials: true,  // 新增：携带 Cookie
});

// 新增：401 拦截器（豁免 /auth/* 路径，避免重定向循环）
api.interceptors.response.use(
  (res) => res,
  (err) => {
    const url = err.config?.url ?? '';
    if (err.response?.status === 401 && !url.startsWith('/auth/')) {
      window.location.href = '/login';
    }
    return Promise.reject(err);
  }
);
```

### UI 样式

- 复用现有 shadcn/ui 组件：`Input`、`Button`、`Card`、`Label`
- 风格与现有页面保持一致（暗色主题）

---

## 依赖变更

### 后端新增

```
itsdangerous
passlib[bcrypt]
```

### 前端

无新增依赖（复用已有 axios 和 shadcn/ui）

---

## 不在范围内

- 忘记密码 / 邮件验证
- OAuth / 第三方登录
- 用户角色细分（仅 admin / 普通用户两级）
- 管理员后台界面（用户管理通过 API 或直接操作 DB）
- SystemSetting 的用户级隔离
- 注册速率限制（由反向代理处理）
- 注册开关控制（`ALLOW_REGISTRATION` 环境变量，未来版本实现）
