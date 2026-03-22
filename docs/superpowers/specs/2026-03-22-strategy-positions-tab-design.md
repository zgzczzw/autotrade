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

> ⚠️ 此端点的 `response_model` 必须使用 `PositionHistoryList`，不得复用现有 `PositionList`。
> `PositionList` 只有 `items` 和 `total` 两个字段，缺少 `page` 和 `page_size`。

> ⚠️ 路由声明顺序：此路由 `@router.get("/positions/history")` 必须置于现有 `@router.get("/positions")` **之前**，否则 FastAPI 会将 `history` 解析为路径参数导致冲突。

> ⚠️ 导入：`PositionHistoryList` 需同时添加到 `account.py` 顶部的 `from app.schemas import ...` 导入行。

item 复用现有 `PositionResponse`（已含 `closed_at`、`pnl`、`current_price` 等所有字段）。

### 平仓价说明

`Position` 模型没有独立的 `closed_price` 字段。平仓时 simulator 会将平仓价写入 `current_price`（参见 `execute_sell`、`execute_cover`），因此 `current_price` 兼作历史平仓价的存储字段。历史列表展示时直接读取 `current_price`，无则显示 `-`。

部分平仓（`sell_size_pct < 100%`）不设置 `closed_at`，因此不会出现在历史列表中，这是预期行为。

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
  current_price?: number; // 开仓时为实时价；平仓后为平仓价
  pnl?: number;           // 已实现盈亏（平仓后有值）
  unrealized_pnl?: number; // 浮动盈亏（开仓时由后端计算）
  opened_at: string;
  closed_at?: string;
}
```

### loadPositions 函数契约

```typescript
const loadPositions = async (page = 1) => {
  setPositionsLoading(true);
  try {
    if (page === 1) {
      // 首次加载：并行请求当前持仓 + 历史第一页
      const [openRes, historyRes] = await Promise.all([
        axios.get(`${API_BASE_URL}/api/positions?strategy_id=${id}`),
        axios.get(`${API_BASE_URL}/api/positions/history?strategy_id=${id}&page=1&page_size=20`),
      ]);
      setCurrentPosition(openRes.data.items?.[0] ?? null);
      setPosHistory(historyRes.data.items || []);
      setPosHistoryTotal(historyRes.data.total || 0);
      setPosHistoryPage(1);
    } else {
      // 翻页：只重新请求历史，当前持仓不变
      const historyRes = await axios.get(
        `${API_BASE_URL}/api/positions/history?strategy_id=${id}&page=${page}&page_size=20`
      );
      setPosHistory(historyRes.data.items || []);
      setPosHistoryTotal(historyRes.data.total || 0);
      setPosHistoryPage(page);
    }
  } catch (error) {
    console.error("Failed to load positions:", error);
  } finally {
    setPositionsLoading(false);
    setPositionsLoaded(true); // 仅在 finally 中设为 true，翻页时不重置为 false
  }
};
```

> ⚠️ `setPositionsLoaded(true)` 只在 `finally` 中调用，永远不重置为 `false`。
> 这保证翻页时不会触发空状态闪现。

### onValueChange 扩展方式

在现有 `<Tabs onValueChange={...}>` 回调中**扩展** `"positions"` 分支，不替换现有 `"triggers"` 分支：

```typescript
onValueChange={(value) => {
  if (value === "triggers" && !triggersLoaded) {
    loadTriggers(1);
  }
  if (value === "positions" && !positionsLoaded) {
    loadPositions(1);
  }
}}
```

### Tab 布局

**当前持仓区块**

- 有持仓：展示卡片，字段：方向 badge（多仓绿 / 空仓橙）、开仓价、数量、**浮动盈亏（`unrealized_pnl`，正绿负红）**
  - 注意：当前持仓使用 `unrealized_pnl`（后端动态计算），不使用 `pnl`（平仓后才有值）
- 无持仓：小型空状态"当前无持仓"

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

- Tab 首次激活前：不渲染任何内容（`!positionsLoaded && !positionsLoading` 返回 `null`，防止空状态闪现）
- 首次加载中（`!positionsLoaded && positionsLoading`）：显示"加载中..."
- 翻页时（`positionsLoaded && positionsLoading`）：历史表格 + 分页控件保持可见（`opacity-60`），同触发历史 tab 处理方式

---

## 不在范围内

- 当前持仓的强制平仓操作（手动平仓按钮）
- 持仓的自动刷新轮询（手动翻页触发加载，当前持仓只在 tab 激活时加载一次）
- 跨策略的全局持仓页改动
- 持仓的日期范围筛选
