# Bark 通知功能设计文档

**日期：** 2026-03-22
**状态：** 已批准

---

## 背景与目标

AutoTrade 已有飞书通知（全局 Webhook URL，env 变量配置）。目标是新增 Bark 推送通知，支持每个用户独立配置自己的 Bark Key，并在侧边栏增加「消息」配置页。

---

## 数据模型

### 新增：`user_settings` 表

```sql
CREATE TABLE user_settings (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id    INTEGER NOT NULL REFERENCES users(id),
    key        VARCHAR(50) NOT NULL,
    value      TEXT,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (user_id, key)
);
```

**设计说明：**
- 键值对结构，支持未来新增通知渠道（Telegram、企业微信等）无需改表
- `UNIQUE(user_id, key)` 保证每个用户每个 key 唯一，upsert 安全

**Bark 相关 key：**

| key | 类型 | 说明 | 默认值 |
|-----|------|------|--------|
| `bark_key` | string | Bark 设备 Key | 空（未配置） |
| `bark_enabled` | string `"true"/"false"` | 是否启用 Bark 通知 | `"false"` |

### NotificationLog.channel

现有 `channel` 字段（VARCHAR，默认 `"feishu"`）无需修改。Bark 通知记录写入时 `channel = "bark"`，与飞书记录并存，历史记录可按 channel 区分。

---

## 后端

### 新增文件

#### `backend/app/models.py` — UserSetting 模型

```python
class UserSetting(Base):
    __tablename__ = "user_settings"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False)
    key        = Column(String(50), nullable=False)
    value      = Column(Text, nullable=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (UniqueConstraint("user_id", "key"),)

    user = relationship("User", back_populates="settings")
```

`User` 模型新增：
```python
settings = relationship("UserSetting", back_populates="user", cascade="all, delete-orphan")
```

#### `backend/app/services/bark.py` — Bark 客户端

```python
class BarkClient:
    BASE_URL = "https://api.day.app"

    async def send(self, key: str, title: str, body: str, group: str = "AutoTrade") -> tuple[bool, Optional[str]]:
        """
        发送 Bark 推送
        URL: https://api.day.app/{key}/{title}/{body}?group={group}
        Returns: (success, error_message)
        """
```

- **使用 per-request `async with httpx.AsyncClient(timeout=5.0)` 模式**（与 `settings.py` 一致），避免持久 client 的生命周期管理问题
- 失败静默降级（返回 False + error_message，不抛异常）
- Bark API 返回 `{"code": 200}` 为成功

#### `backend/app/routers/notifications.py` — 通知配置路由

| 方法 | 路径 | 认证 | 说明 |
|------|------|------|------|
| GET | `/api/notifications/settings` | 当前用户 | 返回用户通知设置 |
| PUT | `/api/notifications/settings` | 当前用户 | 更新 bark_key / bark_enabled |
| POST | `/api/notifications/test` | 当前用户 | 发送一条测试 Bark 推送 |

**GET 响应：**
```json
{
  "bark_key": "xxxxxx",
  "bark_enabled": false
}
```

**PUT 请求体：**
```json
{
  "bark_key": "xxxxxx",
  "bark_enabled": true
}
```

**PUT 行为：** upsert `user_settings` 表，使用 SQLite dialect insert：`insert(...).on_conflict_do_update(index_elements=["user_id","key"], set_={"value":..., "updated_at":...})`，与 `settings.py` 中 `SystemSetting` 的 upsert 模式一致。`bark_key` 和 `bark_enabled` 作为两行分别 upsert。

**POST /test 行为：**
- 读取当前用户的 `bark_key`
- 若未配置或 key 为空，返回 400
- 发送测试消息「AutoTrade 测试通知 — 配置成功！」
- 返回 200（成功）或 400（失败+原因）

### 修改文件

#### `backend/app/database.py`

`user_settings` 表由 `Base.metadata.create_all` 自动创建，只需确保 `UserSetting` 模型在 `init_db()` 执行前已被 import。**无需手动写 `CREATE TABLE IF NOT EXISTS` SQL**，与现有所有模型（`User`、`Strategy` 等）的处理方式一致。

#### `backend/app/services/feishu.py`

`NotificationService.send_strategy_notification` 扩展：

1. **移除 `executor.py` 中的 Feishu 守卫**：`_send_notification` 方法当前有早退逻辑 `if not check_webhook_configured(): return`，此逻辑会同时屏蔽 Bark。需将该守卫删除，改为在 `NotificationService` 内部各自判断（Feishu 有 URL 才发，Bark 有 key 且 enabled 才发）。
2. **新增 `user_id` 参数**：`send_strategy_notification` 接收 `user_id: Optional[int]`，据此从 `user_settings` 查询 Bark 配置。
3. **并行发送**：先发飞书（若 URL 已配置），再发 Bark（若用户启用且 key 非空），各自写入 `NotificationLog`。
4. **返回类型**：改为 `None`（可能写入 0、1 或 2 条 `NotificationLog`）。

**`executor.py` 中 `_send_notification` 改为：**

```python
async def _send_notification(self, trigger, strategy, db):
    try:
        await notification_service.send_strategy_notification(
            trigger_log=trigger,
            strategy_name=strategy.name,
            symbol=strategy.symbol,
            db=db,
            user_id=getattr(strategy, "user_id", None),
        )
    except Exception as e:
        logger.error(f"Failed to send notification: {e}")
```

同时更新 `executor.py` 顶部的 import，移除已不再使用的 `check_webhook_configured`：

```python
# 修改前
from app.services.feishu import check_webhook_configured, notification_service
# 修改后
from app.services.feishu import notification_service
```

#### `backend/app/main.py`

注册 notifications router：
```python
from app.routers import notifications
app.include_router(notifications.router, prefix="/api")
```

### Schemas

添加到 `backend/app/schemas.py`（与所有现有 schema 保持一致）：

```python
class NotificationSettingsResponse(BaseModel):
    bark_key: Optional[str] = None
    bark_enabled: bool = False

class NotificationSettingsUpdate(BaseModel):
    bark_key: Optional[str] = None
    bark_enabled: Optional[bool] = None
```

`POST /test` 成功响应复用已有的 `MessageResponse(message="测试通知已发送")`。

---

## 前端

### 新增页面 `frontend/src/app/notifications/page.tsx`

`"use client"` 组件，使用 shadcn/ui（Card、Input、Label、Button、Switch）。

**布局：**
```
通知设置
└── Bark 推送
    ├── Bark Key 输入框（type="password" 可切换显示）
    ├── 启用通知 Switch 开关
    └── [保存] [测试推送]
```

**交互逻辑：**
- 页面加载时 `GET /api/notifications/settings` 填充表单
- 「保存」→ `PUT /api/notifications/settings` → 显示成功/失败提示
- 「测试推送」→ `POST /api/notifications/test` → 显示结果（成功提示 or 错误原因）
- Switch 变化即时更新本地状态，需点「保存」才提交

### 修改 `frontend/src/components/sidebar.tsx`

在 `navItems` 中插入「消息」：

```typescript
import { LayoutDashboard, Bot, History, BarChart2, Bell, Settings } from "lucide-react";

const navItems = [
  { icon: LayoutDashboard, label: "仪表盘", href: "/" },
  { icon: Bot,             label: "策略",   href: "/strategies" },
  { icon: History,         label: "日志",   href: "/triggers" },
  { icon: BarChart2,       label: "大盘",   href: "/market" },
  { icon: Bell,            label: "消息",   href: "/notifications" },
  { icon: Settings,        label: "设置",   href: "/settings" },
];
```

**移动端底部导航说明：** 桌面端侧边栏和移动端底部导航栏共用同一个 `navItems` 数组，新增 Bell 项后两端均会出现「消息」入口。移动端底部导航由此变为 6 个导航项 + 退出按钮共 7 项，布局在主流手机宽度（375px+）下可正常显示，无需额外处理。

### 修改 `frontend/src/lib/api.ts`

```typescript
// ==================== 通知设置 ====================
export const fetchNotificationSettings = () =>
  apiCall(api.get("/notifications/settings"));

export const updateNotificationSettings = (data: {
  bark_key?: string;
  bark_enabled?: boolean;
}) => apiCall(api.put("/notifications/settings", data));

export const testNotification = () =>
  apiCall(api.post("/notifications/test"));
```

---

## 不在范围内

- 飞书配置迁移到用户级（飞书保持全局 env 变量）
- Bark 以外的新通知渠道（预留扩展，当前不实现）
- 通知历史独立页面（历史记录在策略触发日志页查看）
- 通知消息模板自定义
