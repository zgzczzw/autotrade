# TriggerLog 操作中文化 + position_effect 设计

## 目标

将 TriggerLog 的 `action` 和 `signal_type` 从英文 4 值（buy/sell/short/cover）改为中文 2 值（买入/卖出），新增 `position_effect` 字段区分开仓/平仓。

## 值映射表

| 原 action | 原 signal_type | 新 action | 新 signal_type | position_effect |
|-----------|---------------|-----------|---------------|-----------------|
| `buy`     | `buy`         | `买入`    | `买入`        | `开仓`          |
| `sell`    | `sell`        | `卖出`    | `卖出`        | `平仓`          |
| `short`   | `short`       | `卖出`    | `卖出`        | `开仓`          |
| `cover`   | `cover`       | `买入`    | `买入`        | `平仓`          |
| `hold`    | 保持原方向     | `观望`    | 原信号中文化   | `NULL`          |
| —         | `error`       | `观望`    | `错误`        | `NULL`          |

**hold 的 signal_type 规则：** hold 意味着"想做某操作但条件不满足"，signal_type 跟随原始意图。例如余额不足无法买入时：`signal_type="买入"`, `action="观望"`。

## 涉及文件

### 1. models.py — TriggerLog 模型

新增字段：

```python
position_effect = Column(String, nullable=True)  # 开仓 / 平仓 / NULL
```

### 2. schemas.py — TriggerLogResponse

新增字段：

```python
position_effect: Optional[str] = None
```

### 3. simulator.py — 四个 execute 方法

**execute_buy：**
- `signal_type="buy"` → `"买入"`
- `action="buy"` → `"买入"`，`action="hold"` → `"观望"`
- 新增 `position_effect="开仓"`（成功时），hold 时不设

**execute_sell：**
- `signal_type="sell"` → `"卖出"`
- `action="sell"` → `"卖出"`，`action="hold"` → `"观望"`
- 新增 `position_effect="平仓"`（成功时），hold 时不设

**execute_short：**
- `signal_type="short"` → `"卖出"`
- `action="short"` → `"卖出"`，`action="hold"` → `"观望"`
- 新增 `position_effect="开仓"`（成功时），hold 时不设

**execute_cover：**
- `signal_type="cover"` → `"买入"`
- `action="cover"` → `"买入"`，`action="hold"` → `"观望"`
- 新增 `position_effect="平仓"`（成功时），hold 时不设

### 4. executor.py — 错误处理

```python
signal_type="error" → "错误"
action="hold" → "观望"
```

### 5. feishu.py — 通知服务

**飞书卡片（build_trade_card）：**
- action_labels 改为：`{"买入": "买入", "卖出": "卖出", "观望": "观望"}`
- 实际上 action 已经是中文了，可以直接用 `action` 值作显示文本
- action_colors 改为：`{"买入": "green", "卖出": "red"}`
- 可在通知文案中加入 position_effect 信息

**Bark 通知（send_strategy_notification）：**
- action_map 同理，action 已是中文，直接使用

### 6. 前端三个文件

**triggers/page.tsx、strategies/[id]/page.tsx 的 getActionBadge：**

```typescript
const getActionBadge = (action?: string) => {
  switch (action) {
    case "买入":
      return <Badge className="bg-green-600">买入</Badge>;
    case "卖出":
      return <Badge className="bg-red-600">卖出</Badge>;
    default:
      return <Badge variant="secondary">观望</Badge>;
  }
};
```

**page.tsx（Dashboard）：**

```typescript
trigger.action === "买入"
  ? "bg-green-900 text-green-300"
  : trigger.action === "卖出"
  ? "bg-red-900 text-red-300"
  : "bg-slate-700 text-slate-300"
```

显示文本从 `trigger.action?.toUpperCase() || "HOLD"` 改为 `trigger.action || "观望"`。

### 7. check_stop_loss_take_profit

该方法在触发止盈止损后修改 `trigger.signal_detail` 加 `[止损]`/`[止盈]` 前缀，不涉及 action/signal_type 修改，无需改动。

### 8. 测试文件

- `test_simulator_short.py` — 断言 action/signal_type 改为中文值，增加 position_effect 断言
- `test_executor_short.py` — mock 返回值和断言改为中文值
- `test_backtester_short.py` — 不涉及 TriggerLog，无需改动

### 9. Alembic 迁移

新增 `position_effect` 列（nullable，无默认值）。

### 10. backtester.py

backtester 内部 trade 记录的 `side` 字段（buy/sell/short/cover）保持英文不变，不在本次改动范围内。

## 不在范围内

- backtester 内部统计（side 字段保持英文）
- Position 模型的 side 字段（保持 long/short 英文）
- 已有数据库记录的历史数据迁移（新记录用新值，旧记录保持原值）
