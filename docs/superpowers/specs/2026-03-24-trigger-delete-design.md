# 触发日志删除功能设计

## 目标

为触发日志页面添加单条删除和批量删除能力。

## 后端

### models.py

TriggerLog 的 `notification_logs` 关系加级联删除：

```python
notification_logs = relationship("NotificationLog", back_populates="trigger_log", cascade="all, delete-orphan")
```

### triggers.py — 新增 2 个 API

**DELETE /api/triggers/{trigger_id}** — 删除单条

- 通过 join Strategy 校验 trigger 归属当前用户
- 找不到或不属于当前用户返回 404
- 成功返回 `{"message": "ok"}`

**DELETE /api/triggers** — 批量删除

- Request body: `{"ids": [1, 2, 3]}`
- 校验所有 id 归属当前用户，只删属于当前用户的
- 返回 `{"deleted": 实际删除数量}`

### schemas.py

新增：

```python
class TriggerDeleteRequest(BaseModel):
    ids: List[int]
```

## 前端

### triggers/page.tsx

- Trigger 接口无变化
- 表头新增全选复选框列 + "批量删除"按钮（仅选中时显示）
- 每行新增复选框 + 单条删除按钮（垃圾桶图标）
- 删除后直接刷新列表，不弹确认框
- 批量删除按钮显示选中数量，如"删除 (3)"

## 不在范围内

- 确认对话框（用户明确不需要）
- 其他页面的删除功能（如策略详情页的触发记录）
