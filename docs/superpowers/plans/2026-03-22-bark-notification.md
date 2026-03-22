# Bark Notification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add per-user Bark push notifications to AutoTrade, with a user-level settings page in the sidebar.

**Architecture:** `UserSetting` key-value model stores each user's `bark_key` / `bark_enabled`. A new `BarkClient` service sends push notifications via `https://api.day.app/{key}/{title}/{body}`. `NotificationService` is updated to send Bark in addition to Feishu, scoped by `user_id`. A new `/api/notifications` router handles config CRUD and a test-push endpoint. Frontend adds a「消息」tab (Bell icon) to the sidebar and a config page.

**Tech Stack:** FastAPI, SQLAlchemy async (SQLite), httpx, itsdangerous Cookie auth, Next.js 16, shadcn/ui (Switch, Card, Input, Button, Label)

**Spec:** `docs/superpowers/specs/2026-03-22-bark-notification-design.md`

---

## File Map

### Backend — New Files
- `backend/app/services/bark.py` — `BarkClient.send()` via httpx per-request

### Backend — Modified Files
- `backend/app/models.py` — add `UserSetting` model; add `settings` relationship to `User`
- `backend/app/schemas.py` — add `NotificationSettingsResponse`, `NotificationSettingsUpdate`
- `backend/app/services/feishu.py` — extend `NotificationService.send_strategy_notification` to also send Bark
- `backend/app/engine/executor.py` — remove Feishu guard; pass `user_id`; clean up import
- `backend/app/routers/notifications.py` — new router: GET/PUT settings, POST test
- `backend/app/main.py` — register notifications router

### Frontend — New Files
- `frontend/src/app/notifications/page.tsx` — notification settings page

### Frontend — Modified Files
- `frontend/src/lib/api.ts` — add `fetchNotificationSettings`, `updateNotificationSettings`, `testNotification`
- `frontend/src/components/sidebar.tsx` — add Bell nav item

---

## Task 1: Add UserSetting Model

**Files:**
- Modify: `backend/app/models.py`

`UserSetting` is a key-value table scoped per user. `Base.metadata.create_all` will create it automatically on next startup — no manual SQL needed.

- [ ] **Step 1: Add UserSetting class to models.py**

Open `backend/app/models.py`. After the `User` class (around line 33), add:

```python
class UserSetting(Base):
    """用户级设置（键值对）"""
    __tablename__ = "user_settings"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    user_id    = Column(Integer, ForeignKey("users.id"), nullable=False)
    key        = Column(String(50), nullable=False)
    value      = Column(Text, nullable=True)
    updated_at = Column(DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (UniqueConstraint("user_id", "key"),)

    user = relationship("User", back_populates="settings")
```

- [ ] **Step 2: Add `settings` relationship to User**

In the `User` class, after the existing `backtest_results` relationship line, add:

```python
    settings = relationship("UserSetting", back_populates="user", cascade="all, delete-orphan")
```

- [ ] **Step 3: Verify import**

```bash
cd /home/autotrade/autotrade/backend && python3 -c "from app.models import UserSetting; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
cd /home/autotrade/autotrade && git add backend/app/models.py && git commit -m "$(cat <<'EOF'
feat: add UserSetting model for per-user key-value settings

Generated with [Claude Code](https://claude.ai/code)
via [Happy](https://happy.engineering)

Co-Authored-By: Claude <noreply@anthropic.com>
Co-Authored-By: Happy <yesreply@happy.engineering>
EOF
)"
```

---

## Task 2: Add Notification Schemas

**Files:**
- Modify: `backend/app/schemas.py`

- [ ] **Step 1: Append notification schemas at the end of schemas.py**

Open `backend/app/schemas.py` and append at the very end:

```python
# ==================== 通知设置 ====================

class NotificationSettingsResponse(BaseModel):
    """通知设置响应"""
    bark_key: Optional[str] = None
    bark_enabled: bool = False


class NotificationSettingsUpdate(BaseModel):
    """通知设置更新请求"""
    bark_key: Optional[str] = None
    bark_enabled: Optional[bool] = None
```

- [ ] **Step 2: Verify import**

```bash
cd /home/autotrade/autotrade/backend && python3 -c "from app.schemas import NotificationSettingsResponse, NotificationSettingsUpdate; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
cd /home/autotrade/autotrade && git add backend/app/schemas.py && git commit -m "$(cat <<'EOF'
feat: add NotificationSettings schemas

Generated with [Claude Code](https://claude.ai/code)
via [Happy](https://happy.engineering)

Co-Authored-By: Claude <noreply@anthropic.com>
Co-Authored-By: Happy <yesreply@happy.engineering>
EOF
)"
```

---

## Task 3: Create BarkClient Service

**Files:**
- Create: `backend/app/services/bark.py`

Bark API: `GET https://api.day.app/{key}/{encoded_title}/{encoded_body}?group=AutoTrade`
Returns JSON `{"code": 200, "message": "success"}` on success.
Use per-request `async with httpx.AsyncClient()` — no persistent client needed.

- [ ] **Step 1: Create bark.py**

```python
"""
Bark 推送通知服务
https://bark.day.app
"""

from typing import Optional
from urllib.parse import quote

import httpx

from app.logger import get_logger

logger = get_logger(__name__)


class BarkClient:
    """Bark 推送客户端"""

    BASE_URL = "https://api.day.app"

    async def send(
        self,
        key: str,
        title: str,
        body: str,
        group: str = "AutoTrade",
    ) -> tuple[bool, Optional[str]]:
        """
        发送 Bark 推送通知

        URL: https://api.day.app/{key}/{title}/{body}?group={group}

        Returns:
            (success, error_message)
        """
        if not key:
            return False, "Bark key is empty"

        url = f"{self.BASE_URL}/{quote(key)}/{quote(title)}/{quote(body)}"

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(url, params={"group": group})
                response.raise_for_status()
                result = response.json()

                if result.get("code") != 200:
                    error_msg = result.get("message", "Unknown error")
                    logger.error(f"Bark API error: {error_msg}")
                    return False, error_msg

                logger.info("Bark notification sent successfully")
                return True, None

        except httpx.TimeoutException:
            logger.error("Bark request timeout")
            return False, "Request timeout"
        except httpx.HTTPError as e:
            logger.error(f"Bark HTTP error: {e}")
            return False, str(e)
        except Exception as e:
            logger.error(f"Bark unexpected error: {e}")
            return False, str(e)


bark_client = BarkClient()
```

- [ ] **Step 2: Verify import**

```bash
cd /home/autotrade/autotrade/backend && python3 -c "from app.services.bark import bark_client; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
cd /home/autotrade/autotrade && git add backend/app/services/bark.py && git commit -m "$(cat <<'EOF'
feat: add BarkClient service for push notifications

Generated with [Claude Code](https://claude.ai/code)
via [Happy](https://happy.engineering)

Co-Authored-By: Claude <noreply@anthropic.com>
Co-Authored-By: Happy <yesreply@happy.engineering>
EOF
)"
```

---

## Task 4: Update NotificationService (Add Bark Support)

**Files:**
- Modify: `backend/app/services/feishu.py`

`send_strategy_notification` gains a `user_id` parameter. If the user has `bark_enabled=true` and a non-empty `bark_key` in `user_settings`, a Bark notification is sent in addition to Feishu. Return type changes to `None`.

- [ ] **Step 1: Update feishu.py imports**

At the top of `backend/app/services/feishu.py`, add these imports after the existing ones:

```python
from sqlalchemy.future import select
from app.models import UserSetting
from app.services.bark import bark_client
```

Also add `Optional` to the `typing` import if not already present (it already is).

- [ ] **Step 2: Replace send_strategy_notification method**

Replace the entire `send_strategy_notification` method in `NotificationService` with:

```python
async def send_strategy_notification(
    self,
    trigger_log: TriggerLog,
    strategy_name: str,
    symbol: str,
    db: AsyncSession,
    user_id: Optional[int] = None,
) -> None:
    """
    发送策略通知（飞书 + Bark，各自独立判断是否发送）

    Args:
        trigger_log: 触发记录
        strategy_name: 策略名称
        symbol: 交易对
        db: 数据库会话
        user_id: 策略所属用户 ID（用于查询 Bark 配置）
    """
    # ── Feishu ──
    if self.feishu.webhook_url:
        success, error_msg = await self.feishu.send_trade_signal(
            strategy_name=strategy_name,
            signal_type=trigger_log.signal_type,
            signal_detail=trigger_log.signal_detail or "",
            action=trigger_log.action or "hold",
            symbol=symbol,
            price=trigger_log.price,
            pnl=trigger_log.simulated_pnl,
        )
        notification = NotificationLog(
            trigger_log_id=trigger_log.id,
            channel="feishu",
            status="sent" if success else "failed",
            error_message=error_msg,
        )
        db.add(notification)
        if success:
            logger.info(f"Feishu notification sent for trigger {trigger_log.id}")
        else:
            logger.error(f"Feishu notification failed: {error_msg}")

    # ── Bark ──
    if user_id is not None:
        bark_key, bark_enabled = await self._get_bark_config(db, user_id)
        if bark_enabled and bark_key:
            action_map = {"buy": "买入", "sell": "卖出", "hold": "观望"}
            action_text = action_map.get(trigger_log.action or "hold", trigger_log.action or "hold")
            price_text = f"{trigger_log.price:.2f}" if trigger_log.price else "-"
            title = f"AutoTrade: {strategy_name}"
            body = f"{action_text} {symbol} @ {price_text} USDT"
            if trigger_log.simulated_pnl is not None:
                pnl_sign = "+" if trigger_log.simulated_pnl >= 0 else ""
                body += f"  盈亏: {pnl_sign}{trigger_log.simulated_pnl:.2f}"

            success, error_msg = await bark_client.send(
                key=bark_key,
                title=title,
                body=body,
            )
            bark_log = NotificationLog(
                trigger_log_id=trigger_log.id,
                channel="bark",
                status="sent" if success else "failed",
                error_message=error_msg,
            )
            db.add(bark_log)
            if success:
                logger.info(f"Bark notification sent for trigger {trigger_log.id}")
            else:
                logger.error(f"Bark notification failed: {error_msg}")

    await db.commit()
```

- [ ] **Step 3: Add _get_bark_config helper to NotificationService**

Add this private method to `NotificationService` (after `send_strategy_notification`):

```python
async def _get_bark_config(
    self, db: AsyncSession, user_id: int
) -> tuple[Optional[str], bool]:
    """读取用户的 Bark 配置，返回 (bark_key, bark_enabled)"""
    result = await db.execute(
        select(UserSetting).where(
            UserSetting.user_id == user_id,
            UserSetting.key.in_(["bark_key", "bark_enabled"]),
        )
    )
    rows = {row.key: row.value for row in result.scalars().all()}
    bark_key = rows.get("bark_key") or None
    bark_enabled = rows.get("bark_enabled", "false").lower() == "true"
    return bark_key, bark_enabled
```

- [ ] **Step 4: Verify feishu.py imports**

```bash
cd /home/autotrade/autotrade/backend && python3 -c "from app.services.feishu import notification_service; print('OK')"
```

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
cd /home/autotrade/autotrade && git add backend/app/services/feishu.py && git commit -m "$(cat <<'EOF'
feat: extend NotificationService to send Bark per-user notifications

Generated with [Claude Code](https://claude.ai/code)
via [Happy](https://happy.engineering)

Co-Authored-By: Claude <noreply@anthropic.com>
Co-Authored-By: Happy <yesreply@happy.engineering>
EOF
)"
```

---

## Task 5: Update executor.py

**Files:**
- Modify: `backend/app/engine/executor.py`

Remove the Feishu-only guard from `_send_notification` (it blocks Bark). Update the import to drop `check_webhook_configured`. Pass `user_id` to `send_strategy_notification`.

- [ ] **Step 1: Update the import line in executor.py**

Find line 21 in `backend/app/engine/executor.py`:
```python
from app.services.feishu import check_webhook_configured, notification_service
```

Replace with:
```python
from app.services.feishu import notification_service
```

- [ ] **Step 2: Replace _send_notification method**

Find the `_send_notification` method (around line 219). Replace the entire method:

```python
async def _send_notification(
    self,
    trigger: TriggerLog,
    strategy: Strategy,
    db: AsyncSession,
):
    """发送通知（Feishu + Bark，各自独立判断）"""
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

- [ ] **Step 3: Verify executor imports**

```bash
cd /home/autotrade/autotrade/backend && python3 -c "from app.engine.executor import executor; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: Commit**

```bash
cd /home/autotrade/autotrade && git add backend/app/engine/executor.py && git commit -m "$(cat <<'EOF'
feat: remove Feishu guard from executor, pass user_id to notification service

Generated with [Claude Code](https://claude.ai/code)
via [Happy](https://happy.engineering)

Co-Authored-By: Claude <noreply@anthropic.com>
Co-Authored-By: Happy <yesreply@happy.engineering>
EOF
)"
```

---

## Task 6: Create notifications.py Router

**Files:**
- Create: `backend/app/routers/notifications.py`

- [ ] **Step 1: Create notifications.py**

```python
"""
通知设置路由
GET  /api/notifications/settings  — 读取当前用户通知设置
PUT  /api/notifications/settings  — 更新当前用户通知设置
POST /api/notifications/test      — 发送测试 Bark 推送
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select

from app.database import get_db
from app.deps import get_current_user
from app.models import User, UserSetting
from app.schemas import MessageResponse, NotificationSettingsResponse, NotificationSettingsUpdate
from app.services.bark import bark_client

router = APIRouter(prefix="/notifications", tags=["通知"])


async def _get_setting(db: AsyncSession, user_id: int, key: str) -> str | None:
    """读取单个用户设置"""
    result = await db.execute(
        select(UserSetting).where(
            UserSetting.user_id == user_id,
            UserSetting.key == key,
        )
    )
    row = result.scalar_one_or_none()
    return row.value if row else None


async def _upsert_setting(db: AsyncSession, user_id: int, key: str, value: str):
    """Upsert 单个用户设置（SQLite dialect）"""
    stmt = insert(UserSetting).values(
        user_id=user_id,
        key=key,
        value=value,
        updated_at=datetime.utcnow(),
    )
    stmt = stmt.on_conflict_do_update(
        index_elements=["user_id", "key"],
        set_={"value": value, "updated_at": datetime.utcnow()},
    )
    await db.execute(stmt)


@router.get("/settings", response_model=NotificationSettingsResponse)
async def get_notification_settings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """获取当前用户的通知设置"""
    bark_key = await _get_setting(db, current_user.id, "bark_key")
    bark_enabled_str = await _get_setting(db, current_user.id, "bark_enabled")
    bark_enabled = (bark_enabled_str or "false").lower() == "true"
    return NotificationSettingsResponse(bark_key=bark_key, bark_enabled=bark_enabled)


@router.put("/settings", response_model=NotificationSettingsResponse)
async def update_notification_settings(
    payload: NotificationSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """更新当前用户的通知设置"""
    if payload.bark_key is not None:
        await _upsert_setting(db, current_user.id, "bark_key", payload.bark_key)
    if payload.bark_enabled is not None:
        await _upsert_setting(
            db, current_user.id, "bark_enabled", "true" if payload.bark_enabled else "false"
        )
    await db.commit()

    # 返回最新状态
    bark_key = await _get_setting(db, current_user.id, "bark_key")
    bark_enabled_str = await _get_setting(db, current_user.id, "bark_enabled")
    bark_enabled = (bark_enabled_str or "false").lower() == "true"
    return NotificationSettingsResponse(bark_key=bark_key, bark_enabled=bark_enabled)


@router.post("/test", response_model=MessageResponse)
async def test_notification(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """发送测试 Bark 推送"""
    bark_key = await _get_setting(db, current_user.id, "bark_key")
    if not bark_key:
        raise HTTPException(status_code=400, detail="Bark Key 未配置，请先保存设置")

    success, error_msg = await bark_client.send(
        key=bark_key,
        title="AutoTrade 测试通知",
        body="配置成功！推送正常工作。",
    )
    if not success:
        raise HTTPException(status_code=400, detail=f"推送失败: {error_msg}")

    return MessageResponse(message="测试通知已发送")
```

- [ ] **Step 2: Verify router imports**

```bash
cd /home/autotrade/autotrade/backend && python3 -c "from app.routers.notifications import router; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
cd /home/autotrade/autotrade && git add backend/app/routers/notifications.py && git commit -m "$(cat <<'EOF'
feat: add /api/notifications router for Bark config and test push

Generated with [Claude Code](https://claude.ai/code)
via [Happy](https://happy.engineering)

Co-Authored-By: Claude <noreply@anthropic.com>
Co-Authored-By: Happy <yesreply@happy.engineering>
EOF
)"
```

---

## Task 7: Register Router + Verify Full App Import

**Files:**
- Modify: `backend/app/main.py`

- [ ] **Step 1: Add notifications router to main.py**

In `backend/app/main.py`, update the router imports line (line 18):

```python
from app.routers import account, auth, backtests, dashboard, logs, market, notifications, settings, strategies, triggers
```

Then after the last `app.include_router(...)` call (after the auth router line), add:

```python
app.include_router(notifications.router, prefix="/api")
```

- [ ] **Step 2: Verify full app import**

```bash
cd /home/autotrade/autotrade/backend && python3 -c "import app.main; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Verify notifications route is registered**

```bash
SECRET_KEY=testsecret ENV=development python3 -m uvicorn app.main:app --port 18003 &
sleep 4
curl -s http://localhost:18003/openapi.json | python3 -c "import sys,json; paths=json.load(sys.stdin)['paths']; print([p for p in paths if 'notification' in p])"
kill %1
```

Expected: `['/api/notifications/settings', '/api/notifications/test']`

- [ ] **Step 4: Commit**

```bash
cd /home/autotrade/autotrade && git add backend/app/main.py && git commit -m "$(cat <<'EOF'
feat: register notifications router in main.py

Generated with [Claude Code](https://claude.ai/code)
via [Happy](https://happy.engineering)

Co-Authored-By: Claude <noreply@anthropic.com>
Co-Authored-By: Happy <yesreply@happy.engineering>
EOF
)"
```

---

## Task 8: Update Frontend api.ts and sidebar.tsx

**Files:**
- Modify: `frontend/src/lib/api.ts`
- Modify: `frontend/src/components/sidebar.tsx`

- [ ] **Step 1: Add notification API functions to api.ts**

Open `frontend/src/lib/api.ts` and append at the very end:

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

- [ ] **Step 2: Update sidebar.tsx navItems**

Open `frontend/src/components/sidebar.tsx`.

Update the import line to add `Bell`:
```typescript
import { LayoutDashboard, Bot, History, BarChart2, Settings, LogOut, User, Bell } from "lucide-react";
```

Replace the `navItems` array with:
```typescript
const navItems = [
  { icon: LayoutDashboard, label: "仪表盘", href: "/" },
  { icon: Bot, label: "策略", href: "/strategies" },
  { icon: History, label: "日志", href: "/triggers" },
  { icon: BarChart2, label: "大盘", href: "/market" },
  { icon: Bell, label: "消息", href: "/notifications" },
  { icon: Settings, label: "设置", href: "/settings" },
];
```

- [ ] **Step 3: Verify TypeScript**

```bash
cd /home/autotrade/autotrade/frontend && npx tsc --noEmit 2>&1 | head -20
```

Expected: no new errors

- [ ] **Step 4: Commit**

```bash
cd /home/autotrade/autotrade && git add frontend/src/lib/api.ts frontend/src/components/sidebar.tsx && git commit -m "$(cat <<'EOF'
feat: add notification API functions and Bell nav item to sidebar

Generated with [Claude Code](https://claude.ai/code)
via [Happy](https://happy.engineering)

Co-Authored-By: Claude <noreply@anthropic.com>
Co-Authored-By: Happy <yesreply@happy.engineering>
EOF
)"
```

---

## Task 9: Create Notifications Page

**Files:**
- Create: `frontend/src/app/notifications/page.tsx`

Uses shadcn/ui Switch, Card, Input, Label, Button. Loads settings on mount, saves on button click, sends test push on test button click.

**Note:** shadcn/ui Switch component may need to be installed. Check first:
```bash
ls /home/autotrade/autotrade/frontend/src/components/ui/switch.tsx 2>/dev/null || echo "not found"
```

If not found, install it:
```bash
cd /home/autotrade/autotrade/frontend && npx shadcn@latest add switch --yes 2>&1 | tail -5
```

- [ ] **Step 1: Create notifications directory and page**

```bash
mkdir -p /home/autotrade/autotrade/frontend/src/app/notifications
```

Create `frontend/src/app/notifications/page.tsx`:

```tsx
"use client";

import { useEffect, useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import {
  fetchNotificationSettings,
  updateNotificationSettings,
  testNotification,
} from "@/lib/api";

export default function NotificationsPage() {
  const [barkKey, setBarkKey] = useState("");
  const [barkEnabled, setBarkEnabled] = useState(false);
  const [showKey, setShowKey] = useState(false);
  const [saveStatus, setSaveStatus] = useState<"idle" | "saving" | "saved" | "error">("idle");
  const [testStatus, setTestStatus] = useState<"idle" | "sending" | "success" | "error">("idle");
  const [testError, setTestError] = useState("");

  useEffect(() => {
    fetchNotificationSettings().then((res: any) => {
      setBarkKey(res.bark_key ?? "");
      setBarkEnabled(res.bark_enabled ?? false);
    }).catch(() => {});
  }, []);

  async function handleSave() {
    setSaveStatus("saving");
    try {
      await updateNotificationSettings({ bark_key: barkKey, bark_enabled: barkEnabled });
      setSaveStatus("saved");
      setTimeout(() => setSaveStatus("idle"), 2000);
    } catch {
      setSaveStatus("error");
      setTimeout(() => setSaveStatus("idle"), 3000);
    }
  }

  async function handleTest() {
    setTestStatus("sending");
    setTestError("");
    try {
      await testNotification();
      setTestStatus("success");
      setTimeout(() => setTestStatus("idle"), 3000);
    } catch (err: any) {
      setTestStatus("error");
      setTestError(err.response?.data?.detail ?? "推送失败，请检查 Bark Key");
      setTimeout(() => { setTestStatus("idle"); setTestError(""); }, 5000);
    }
  }

  return (
    <div className="max-w-xl space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-white">通知设置</h1>
        <p className="text-slate-400 text-sm mt-1">配置策略触发时的推送通知</p>
      </div>

      <Card className="bg-slate-900 border-slate-800">
        <CardHeader>
          <CardTitle className="text-white text-lg">Bark 推送</CardTitle>
          <CardDescription className="text-slate-400">
            使用 Bark App 接收 iOS 推送通知。在 Bark App 中复制你的 Key 填入下方。
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="bark-key" className="text-slate-300">Bark Key</Label>
            <div className="relative">
              <Input
                id="bark-key"
                type={showKey ? "text" : "password"}
                value={barkKey}
                onChange={(e) => setBarkKey(e.target.value)}
                placeholder="粘贴你的 Bark Key"
                className="bg-slate-800 border-slate-700 text-white pr-10"
              />
              <button
                type="button"
                onClick={() => setShowKey(!showKey)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-200"
              >
                {showKey ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
              </button>
            </div>
          </div>

          <div className="flex items-center justify-between py-1">
            <Label htmlFor="bark-enabled" className="text-slate-300 cursor-pointer">
              启用通知
            </Label>
            <Switch
              id="bark-enabled"
              checked={barkEnabled}
              onCheckedChange={setBarkEnabled}
            />
          </div>

          <div className="flex gap-3 pt-2">
            <Button
              onClick={handleSave}
              disabled={saveStatus === "saving"}
              className="flex-1"
            >
              {saveStatus === "saving" ? "保存中..." : saveStatus === "saved" ? "已保存 ✓" : saveStatus === "error" ? "保存失败" : "保存"}
            </Button>
            <Button
              variant="outline"
              onClick={handleTest}
              disabled={testStatus === "sending" || !barkKey}
              className="flex-1 border-slate-700 text-slate-300 hover:text-white hover:bg-slate-800"
            >
              {testStatus === "sending" ? "发送中..." : testStatus === "success" ? "发送成功 ✓" : testStatus === "error" ? "发送失败" : "测试推送"}
            </Button>
          </div>

          {testError && (
            <p className="text-red-400 text-sm">{testError}</p>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
```

- [ ] **Step 2: Verify TypeScript**

```bash
cd /home/autotrade/autotrade/frontend && npx tsc --noEmit 2>&1 | head -20
```

Expected: no new errors

- [ ] **Step 3: Commit**

```bash
cd /home/autotrade/autotrade && git add frontend/src/app/notifications/ && git commit -m "$(cat <<'EOF'
feat: add Bark notification settings page

Generated with [Claude Code](https://claude.ai/code)
via [Happy](https://happy.engineering)

Co-Authored-By: Claude <noreply@anthropic.com>
Co-Authored-By: Happy <yesreply@happy.engineering>
EOF
)"
```

---

## Task 10: Rebuild Frontend + End-to-End Smoke Test

**Files:**
- None (verification only)

- [ ] **Step 1: Restart backend (picks up new UserSetting model + notifications router)**

```bash
# Restart running backend on port 18000
kill $(lsof -ti:18000) 2>/dev/null; sleep 2
SECRET_KEY=$(grep SECRET_KEY /home/autotrade/autotrade/backend/.env | cut -d= -f2)
cd /home/autotrade/autotrade/backend && \
  SECRET_KEY="$SECRET_KEY" ENV=development \
  nohup python3 -m uvicorn app.main:app --host 0.0.0.0 --port 18000 \
  > /home/autotrade/autotrade/logs/backend.log 2>&1 &
sleep 4
curl -s http://localhost:18000/api/health
```

Expected: `{"status":"ok"}`

- [ ] **Step 2: Run API smoke tests**

```bash
# Login as admin
curl -s -c /tmp/smoke_cookies.txt -X POST http://localhost:18000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin1"}' | python3 -m json.tool

# GET notification settings (should return empty defaults)
curl -s -b /tmp/smoke_cookies.txt http://localhost:18000/api/notifications/settings | python3 -m json.tool

# PUT bark_key
curl -s -b /tmp/smoke_cookies.txt -X PUT http://localhost:18000/api/notifications/settings \
  -H "Content-Type: application/json" \
  -d '{"bark_key":"testkey123","bark_enabled":true}' | python3 -m json.tool

# GET again to verify persistence
curl -s -b /tmp/smoke_cookies.txt http://localhost:18000/api/notifications/settings | python3 -m json.tool

# POST test (will fail with Bark API error since testkey123 is invalid — that's expected)
curl -s -b /tmp/smoke_cookies.txt -X POST http://localhost:18000/api/notifications/test | python3 -m json.tool

# Cleanup
rm -f /tmp/smoke_cookies.txt
```

Expected:
- Login: `{"user": {...}}`
- GET settings: `{"bark_key": null, "bark_enabled": false}`
- PUT settings: `{"bark_key": "testkey123", "bark_enabled": true}`
- GET again: `{"bark_key": "testkey123", "bark_enabled": true}`
- POST test: either success (if key valid) or `{"detail": "推送失败: ..."}` (400, expected for dummy key)

- [ ] **Step 3: Rebuild and restart frontend**

```bash
cd /home/autotrade/autotrade/frontend && npm run build 2>&1 | tail -5
kill $(lsof -ti:13000) 2>/dev/null; sleep 2
nohup npm exec next start -- -H 0.0.0.0 -p 13000 > /home/autotrade/autotrade/logs/frontend.log 2>&1 &
sleep 4
curl -s -o /dev/null -w "%{http_code}" http://localhost:13000/notifications
```

Expected: `200` (redirects to login if not authenticated, but 200 means the page exists)

- [ ] **Step 4: Final commit (if any remaining changes)**

```bash
cd /home/autotrade/autotrade && git status
```

If clean, no commit needed.

---

## Summary

After all tasks:

1. **Backend:** `UserSetting` model stores per-user `bark_key` / `bark_enabled`. `NotificationService` sends Bark in addition to Feishu (independently gated). `/api/notifications/settings` and `/api/notifications/test` endpoints.
2. **Frontend:** 「消息」tab in sidebar (Bell icon), config page at `/notifications` with Key input, enable toggle, Save + Test Push buttons.
3. **DB migration:** `user_settings` table auto-created by `Base.metadata.create_all` on next backend start.
