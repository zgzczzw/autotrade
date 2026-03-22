# 策略详情页触发历史 Tab 设计文档

**日期：** 2026-03-22
**状态：** 已批准

---

## 背景与目标

策略详情页（`/strategies/[id]`）的「触发历史」tab 目前是占位符。目标是在该 tab 内实现一个带分页的触发记录表格，展示该策略的所有触发历史。

---

## 技术方案

**方案 A（采用）：直接在策略详情页实现，不提取共享组件。**

全局触发日志页（`/triggers`）与策略详情页的列结构有差异（前者多一个「策略」列），复用收益低。直接在 `strategies/[id]/page.tsx` 内实现，自包含，不新建文件。

---

## 数据接口

复用现有后端接口，无需后端改动：

```
GET /api/triggers?strategy_id={id}&page={n}&page_size=20
```

响应结构（已有）：
```json
{
  "items": [...],
  "total": 42,
  "page": 1,
  "page_size": 20
}
```

---

## 表格列定义

| 列 | 字段 | 说明 |
|----|------|------|
| 时间 | `triggered_at` | `toLocaleString()` |
| 操作 | `action` | Badge：买入（绿）/ 卖出（红）/ 开空（橙）/ 平空（紫）/ 观望（灰） |
| 价格 | `price` | `formatPrice()`，无则显示 `-` |
| 数量 | `quantity` | 保留 4 位小数，无则显示 `-` |
| 盈亏 | `simulated_pnl` | 正值绿色 `+X`，负值红色 `X`，无则显示 `-` |
| 备注 | `signal_detail` | 完整文本，字体稍小，颜色 `text-slate-400` |

---

## 分页控件

- 布局：`上一页 ← | 第 X / Y 页 | → 下一页`，居中显示在表格下方
- 「上一页」在第 1 页时禁用；「下一页」在最后一页时禁用
- 显示总条数：`共 {total} 条`
- 使用现有 shadcn/ui `Button` 组件，`variant="outline"`，尺寸 `size="sm"`

---

## 状态与刷新

**加载状态**：tab 首次激活时显示「加载中...」。

**空状态**：无记录时显示 History 图标 + 「暂无触发记录」文本（与全局触发日志页保持一致）。

**自动刷新**：策略详情页现有 10 秒轮询（`loadStrategy`）。触发历史 tab 不单独轮询——只在以下两种情况重新加载数据：
1. 切换到触发历史 tab 时
2. 翻页时

原因：触发频率通常以小时计，10 秒轮询触发历史列表无实际意义，且会重置分页位置。

**翻页**：点击上一页/下一页时重新请求对应页，页码保存在组件 state。

---

## 前端实现细节

### 新增 state（在 `StrategyDetailPage` 内）

```typescript
// 触发历史
const [triggers, setTriggers] = useState<Trigger[]>([]);
const [triggersTotal, setTriggersTotal] = useState(0);
const [triggersPage, setTriggersPage] = useState(1);
const [triggersLoading, setTriggersLoading] = useState(false);
const [triggersLoaded, setTriggersLoaded] = useState(false);
```

### Trigger 接口（新增，与全局日志页一致）

```typescript
interface Trigger {
  id: number;
  strategy_id: number;
  triggered_at: string;
  signal_type: string;
  signal_detail?: string;
  action?: string;
  price?: number;
  quantity?: number;
  simulated_pnl?: number;
}
```

### 数据加载函数

```typescript
const loadTriggers = async (page = 1) => {
  setTriggersLoading(true);
  try {
    const response = await axios.get(
      `${API_BASE_URL}/api/triggers?strategy_id=${id}&page=${page}&page_size=20`
    );
    setTriggers(response.data.items || []);
    setTriggersTotal(response.data.total || 0);
    setTriggersPage(page);
  } catch (error) {
    console.error("Failed to load triggers:", error);
  } finally {
    setTriggersLoading(false);
    setTriggersLoaded(true);
  }
};
```

### Tab 激活时懒加载

在 `<Tabs>` 上使用 `onValueChange` 回调：

```typescript
<Tabs
  defaultValue="overview"
  onValueChange={(value) => {
    if (value === "triggers" && !triggersLoaded) {
      loadTriggers(1);
    }
  }}
>
```

`triggersLoaded` 标志位防止切换回 tab 时重复加载（保持当前分页位置）。

### getActionBadge 函数

复用与全局触发日志页相同的 badge 逻辑（局部函数，不共享）。

---

## 不在范围内

- 后端改动（现有接口已满足需求）
- 全局触发日志页改动
- 触发历史的日期范围筛选（可后续迭代）
- 提取共享 `TriggerLogTable` 组件（过早抽象）
- 触发历史 tab 的 10 秒自动刷新
