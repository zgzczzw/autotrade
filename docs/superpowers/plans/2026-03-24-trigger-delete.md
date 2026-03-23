# 触发日志删除功能 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add single and batch delete capability for trigger logs, with cascade delete of notification_logs.

**Architecture:** Add cascade to TriggerLog→NotificationLog relationship, add 2 DELETE API endpoints following existing patterns (backtests.py), update frontend triggers page with checkboxes and delete buttons.

**Tech Stack:** FastAPI, SQLAlchemy async, React/TypeScript, axios

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `backend/app/models.py:97` | Modify | Add cascade to notification_logs relationship |
| `backend/app/schemas.py` | Modify | Add TriggerDeleteRequest schema |
| `backend/app/routers/triggers.py` | Modify | Add DELETE endpoints |
| `frontend/src/app/triggers/page.tsx` | Modify | Add checkboxes, delete buttons |

---

### Task 1: Model cascade + Schema

**Files:**
- Modify: `backend/app/models.py:97`
- Modify: `backend/app/schemas.py`

- [ ] **Step 1: Add cascade to notification_logs relationship**

In `backend/app/models.py`, line 97, change:

```python
# Before:
notification_logs = relationship("NotificationLog", back_populates="trigger_log")
# After:
notification_logs = relationship("NotificationLog", back_populates="trigger_log", cascade="all, delete-orphan")
```

- [ ] **Step 2: Add TriggerDeleteRequest schema**

In `backend/app/schemas.py`, add near the TriggerLog section (after `TriggerLogList` class):

```python
class TriggerDeleteRequest(BaseModel):
    ids: List[int]
```

- [ ] **Step 3: Verify import**

Run: `cd /home/autotrade/autotrade/backend && python3 -c "from app.schemas import TriggerDeleteRequest; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add backend/app/models.py backend/app/schemas.py
git commit -m "feat: add cascade delete for notification_logs and TriggerDeleteRequest schema"
```

---

### Task 2: DELETE API endpoints

**Files:**
- Modify: `backend/app/routers/triggers.py`

Follow the existing pattern in `backend/app/routers/backtests.py:179-201` for DELETE endpoints.

- [ ] **Step 1: Add single delete endpoint**

Add to `backend/app/routers/triggers.py`. Need to import `HTTPException`, `status` from fastapi, and `MessageResponse`, `TriggerDeleteRequest` from schemas.

```python
from fastapi import APIRouter, Depends, HTTPException, Query, status
from app.schemas import MessageResponse, TriggerDeleteRequest, TriggerLogList, TriggerLogResponse


@router.delete("/triggers/{trigger_id}", response_model=MessageResponse)
async def delete_trigger(
    trigger_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """删除单条触发日志"""
    result = await db.execute(
        select(TriggerLog)
        .join(Strategy, TriggerLog.strategy_id == Strategy.id)
        .where(TriggerLog.id == trigger_id, Strategy.user_id == current_user.id)
    )
    trigger = result.scalar_one_or_none()

    if not trigger:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="触发记录不存在",
        )

    await db.delete(trigger)
    await db.commit()
    return MessageResponse(message="触发记录已删除")
```

- [ ] **Step 2: Add batch delete endpoint**

```python
@router.delete("/triggers", response_model=dict)
async def batch_delete_triggers(
    request: TriggerDeleteRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """批量删除触发日志"""
    result = await db.execute(
        select(TriggerLog)
        .join(Strategy, TriggerLog.strategy_id == Strategy.id)
        .where(TriggerLog.id.in_(request.ids), Strategy.user_id == current_user.id)
    )
    triggers = result.scalars().all()

    for trigger in triggers:
        await db.delete(trigger)
    await db.commit()

    return {"deleted": len(triggers)}
```

- [ ] **Step 3: Verify server starts**

Run: `cd /home/autotrade/autotrade/backend && python3 -c "from app.routers.triggers import router; print([r.path for r in router.routes])"`
Expected: output includes `/triggers/{trigger_id}` and `/triggers`

- [ ] **Step 4: Commit**

```bash
git add backend/app/routers/triggers.py
git commit -m "feat: add single and batch delete API endpoints for trigger logs"
```

---

### Task 3: Frontend — checkboxes and delete buttons

**Files:**
- Modify: `frontend/src/app/triggers/page.tsx`

- [ ] **Step 1: Add state and handlers**

Add to the component, after the existing state declarations:

```typescript
const [selectedIds, setSelectedIds] = useState<Set<number>>(new Set());

const toggleSelect = (id: number) => {
  setSelectedIds((prev) => {
    const next = new Set(prev);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    return next;
  });
};

const toggleSelectAll = () => {
  if (selectedIds.size === triggers.length) {
    setSelectedIds(new Set());
  } else {
    setSelectedIds(new Set(triggers.map((t) => t.id)));
  }
};

const deleteTrigger = async (id: number) => {
  try {
    await axios.delete(`${API_BASE_URL}/api/triggers/${id}`);
    setSelectedIds((prev) => {
      const next = new Set(prev);
      next.delete(id);
      return next;
    });
    loadTriggers();
  } catch (error) {
    console.error("Failed to delete trigger:", error);
  }
};

const batchDelete = async () => {
  if (selectedIds.size === 0) return;
  try {
    await axios.delete(`${API_BASE_URL}/api/triggers`, {
      data: { ids: Array.from(selectedIds) },
    });
    setSelectedIds(new Set());
    loadTriggers();
  } catch (error) {
    console.error("Failed to batch delete triggers:", error);
  }
};
```

- [ ] **Step 2: Add Trash2 icon import**

Update the import line:

```typescript
import { History, Trash2 } from "lucide-react";
```

- [ ] **Step 3: Add batch delete button above table**

Add between the `<h1>` and the empty/table section. Add a `Button` import from `@/components/ui/button`:

```typescript
import { Button } from "@/components/ui/button";
```

```tsx
<div className="flex items-center justify-between mb-6 md:mb-8">
  <h1 className="text-2xl md:text-3xl font-bold">触发日志</h1>
  {selectedIds.size > 0 && (
    <Button
      variant="destructive"
      size="sm"
      onClick={batchDelete}
    >
      <Trash2 className="w-4 h-4 mr-1" />
      删除 ({selectedIds.size})
    </Button>
  )}
</div>
```

Remove the existing standalone `<h1>` tag.

- [ ] **Step 4: Add checkbox column to table**

Add checkbox header as the first `<th>`:

```tsx
<th className="p-4 w-12">
  <input
    type="checkbox"
    checked={triggers.length > 0 && selectedIds.size === triggers.length}
    onChange={toggleSelectAll}
    className="rounded border-slate-600"
  />
</th>
```

Add checkbox cell as the first `<td>` in each row:

```tsx
<td className="p-4">
  <input
    type="checkbox"
    checked={selectedIds.has(trigger.id)}
    onChange={() => toggleSelect(trigger.id)}
    className="rounded border-slate-600"
  />
</td>
```

- [ ] **Step 5: Add delete button column to table**

Add a header for the actions column as the last `<th>`:

```tsx
<th className="p-4 w-12"></th>
```

Add delete button as the last `<td>` in each row:

```tsx
<td className="p-4">
  <button
    onClick={() => deleteTrigger(trigger.id)}
    className="text-slate-500 hover:text-red-400 transition-colors"
  >
    <Trash2 className="w-4 h-4" />
  </button>
</td>
```

- [ ] **Step 6: Verify frontend builds**

Run: `cd /home/autotrade/autotrade/frontend && npx next build 2>&1 | tail -10`
Expected: build succeeds

- [ ] **Step 7: Commit**

```bash
git add frontend/src/app/triggers/page.tsx
git commit -m "feat: add trigger log delete and batch delete UI"
```
