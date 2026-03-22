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

### 现有模型加 `user_id` 外键

以下模型新增 `user_id INTEGER NOT NULL REFERENCES users(id)`，实现数据隔离：

- `strategies`
- `trigger_logs`
- `positions`
- `sim_accounts`
- `backtest_results`
- `notification_logs`

### 全局共享模型（不加 user_id）

- `kline_data` — 行情缓存，所有用户共享
- `system_settings` — 系统级配置，由管理员管理

### 数据迁移策略

1. Alembic migration：新增 `users` 表
2. Alembic migration：给上述模型加 `user_id`（先允许 NULL）
3. 迁移脚本：自动创建第一个 admin 用户（用户名 `admin`，密码从环境变量 `ADMIN_PASSWORD` 读取，默认 `changeme`）
4. 将所有现有数据的 `user_id` 设为 admin 的 id
5. 将 `user_id` 列改为 NOT NULL

---

## 认证层（后端）

### Session 机制

- 库：`itsdangerous.URLSafeTimedSerializer`
- Cookie 名：`session`
- Cookie 属性：`HttpOnly=True`，`SameSite=Lax`，`Max-Age=604800`（7 天）
- 内容：签名后的 `user_id`
- 密钥：从环境变量 `SECRET_KEY` 读取；不存在则启动时抛出异常

### 新增路由：`/api/auth/`

| 方法 | 路径 | 请求体 | 响应 | 说明 |
|------|------|--------|------|------|
| POST | `/api/auth/register` | `{username, password}` | 用户信息 + Set-Cookie | 注册并自动登录 |
| POST | `/api/auth/login` | `{username, password}` | 用户信息 + Set-Cookie | 登录 |
| POST | `/api/auth/logout` | — | 200 + 清除 Cookie | 退出 |
| GET  | `/api/auth/me` | — | 用户信息 | 获取当前用户 |

### FastAPI 依赖注入

```python
async def get_current_user(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    session_cookie = request.cookies.get("session")
    if not session_cookie:
        raise HTTPException(status_code=401, detail="未登录")
    try:
        user_id = serializer.loads(session_cookie, max_age=604800)
    except Exception:
        raise HTTPException(status_code=401, detail="Session 无效或已过期")
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    return user
```

所有现有 router 函数签名加 `current_user: User = Depends(get_current_user)`，查询时过滤 `user_id = current_user.id`。

### 密码安全

- 使用 `passlib[bcrypt]` 进行密码哈希
- 注册校验：用户名唯一，密码最短 6 位
- 登录校验：用户名存在 + 密码匹配（常量时间比较，防时序攻击）

---

## 前端

### 新增页面

| 路径 | 说明 |
|------|------|
| `/login` | 用户名+密码登录表单，成功跳转首页 |
| `/register` | 注册表单（用户名、密码、确认密码），成功自动登录跳转首页 |

### 路由保护

`middleware.ts`（Next.js Edge Middleware）：

- 检查请求中是否包含 `session` Cookie
- 未登录访问任意页面 → `redirect('/login')`
- 已登录访问 `/login` 或 `/register` → `redirect('/')`
- `/api/auth/*` 路径豁免（不做重定向）

### Sidebar 改动

- 底部新增：当前用户名显示 + 退出登录按钮
- 点击退出：调用 `POST /api/auth/logout` → 跳转 `/login`
- 用户信息通过 `GET /api/auth/me` 在 layout 层获取并注入

### API 客户端

`lib/api.ts` 中 axios 实例：

```typescript
const api = axios.create({
  baseURL: '/api',
  withCredentials: true,  // 新增：携带 Cookie
});

// 新增：401 拦截器
api.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
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
