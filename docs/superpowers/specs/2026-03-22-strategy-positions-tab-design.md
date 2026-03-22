# 策略详情页持仓 Tab 设计文档

**日期：** 2026-03-22
**状态：** 已批准

---

## 背景与目标

策略详情页（`/strategies/[id]`）的「持仓」tab 目前是占位符。目标是实现完整的持仓信息展示：当前持仓（实时）+ 历史平仓记录（分页）。

---

## 技术方案

**方案 B（采用）：新增独立历史端点，保留现有开仓端点不变。**

现有 `GET /api/positions?strategy_id={id}` 只返回未平仓持仓，已被其他页面使用，不改动。历史平仓记录通过新端点独立提供，天然支持分页。

---

## 后端变更

### 新增端点

```
GET /api/positions/history?strategy_id={id}&page={n}&page_size=20
```

**文件：** `backend/app/routers/account.py`

**行为：**
- 过滤：`closed_at IS NOT NULL`，`user_id = current_user.id`
- 可选参数：`strategy_id`（不传则返回该用户所有历史）
- 排序：`closed_at DESC`
- 分页：`page`（从 1 开始）、`page_size`（默认 20）

**新增 Schema（`backend/app/schemas.py`）：**

```python
class PositionHistoryList(BaseModel):
    items: List[PositionResponse]
    total: int
    page: int
    page_size: int
```

item 复用现有 `PositionResponse`（已含 `closed_at`、`pnl` 等所有字段）。

---

## 前端变更

**文件：** `frontend/src/app/strategies/[id]/page.tsx`（仅此一个文件）

### 新增 State

```typescript
const [currentPosition, setCurrentPosition] = useState<Position | null>(null);
const [posHistory, setPosHistory] = useState<Position[]>([]);
const [posHistoryTotal, setPosHistoryTotal] = useState(0);
const [posHistoryPage, setPosHistoryPage] = useState(1);
const [positionsLoading, setPositionsLoading] = useState(false);
const [positionsLoaded, setPositionsLoaded] = useState(false);
```

### Position 接口

```typescript
interface Position {
  id: number;
  strategy_id: number;
  symbol: string;
  side: string;           // "long" | "short"
  entry_price: number;
  quantity: number;
  current_price?: number;
  pnl?: number;
  unrealized_pnl?: number;
  opened_at: string;
  closed_at?: string;
}
```

### 数据加载

Tab 首次激活时（`onValueChange` → `value === "positions" && !positionsLoaded`）并行请求：
1. `GET /api/positions?strategy_id={id}` → 当前持仓（取 items[0]，策略同时只有一个持仓）
2. `GET /api/positions/history?strategy_id={id}&page=1&page_size=20` → 历史记录

翻页时只重新请求历史端点，不重新请求当前持仓。

### Tab 布局

**当前持仓区块**

| 有持仓 | 无持仓 |
|--------|--------|
| 展示卡片：方向 badge（多仓绿 / 空仓橙）、开仓价、数量、浮动盈亏（正绿负红） | 小型空状态"当前无持仓" |

**历史持仓区块**

表格列定义：

| 列 | 字段 | 说明 |
|----|------|------|
| 开仓时间 | `opened_at` | `formatDateTime()` |
| 平仓时间 | `closed_at` | `formatDateTime()` |
| 方向 | `side` | Badge：多仓（绿）/ 空仓（橙） |
| 开仓价 | `entry_price` | `formatPrice()` |
| 平仓价 | `current_price` | `formatPrice()`，无则显示 `-` |
| 数量 | `quantity` | 保留 4 位小数 |
| 盈亏 | `pnl` | 正值绿色 `+X`，负值红色 `X`，无则显示 `-` |

分页控件：`上一页 ← | 第 X / Y 页，共 Z 条 | → 下一页`，同触发历史 tab 样式。

历史为空时显示空状态卡片（TrendingUp 图标 + "暂无平仓记录"）。

### 加载态

- Tab 首次激活前：不渲染任何内容（`positionsLoaded` 守卫，防止空状态闪现）
- 首次加载中：显示"加载中..."
- 翻页时：历史表格 + 分页控件保持可见（`opacity-60`），同触发历史 tab 处理方式

---

## 不在范围内

- 当前持仓的强制平仓操作（手动平仓按钮）
- 持仓的自动刷新轮询（手动翻页触发加载，当前持仓只在 tab 激活时加载一次）
- 跨策略的全局持仓页改动
- 持仓的日期范围筛选
