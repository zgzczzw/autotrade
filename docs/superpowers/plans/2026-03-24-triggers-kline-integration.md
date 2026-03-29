# 触发历史 + K线图联动 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在策略详情页的"触发历史"tab中，上方添加K线图并标记所有买卖点，下方保留触发历史表格，点击某条触发记录时K线图自动滚动并聚焦到对应K线。

**Architecture:** 复用现有 `KlineChartModule` 组件（已支持 markers、focusTimestamp、受控时间周期）。在策略详情页触发历史 tab 中集成：加载策略交易对的K线数据，将所有触发记录转换为 TradeMarker 叠加到图表上，点击表格行时更新 focusTimestamp 驱动图表滚动。需要加载全量触发记录（不分页）用于标记。

**Tech Stack:** Next.js, React, klinecharts, axios, existing KlineChartModule

---

### File Structure

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `frontend/src/app/strategies/[id]/page.tsx` | 集成K线图到触发历史tab，添加数据加载、markers转换、行点击联动逻辑 |

无需创建新文件——所有改动集中在策略详情页，复用已有的 `KlineChartModule`、`fetchMarketKlines` API。

---

### Task 1: 在触发历史 tab 集成 K 线图 + 买卖点标记 + 行点击联动

**Files:**
- Modify: `frontend/src/app/strategies/[id]/page.tsx`

- [ ] **Step 1: 添加 import 和新 state**

在文件顶部添加 KlineChartModule 和 fetchMarketKlines 的导入，以及新的 state 变量：

```tsx
import { KlineChartModule } from "@/components/kline-chart";
import { TradeMarker } from "@/components/kline-chart/types";
import { fetchMarketKlines } from "@/lib/api";
```

新增 state：
```tsx
const [klines, setKlines] = useState<any[]>([]);
const [klinesLoading, setKlinesLoading] = useState(false);
const [chartPeriod, setChartPeriod] = useState("1h");
const [focusTimestamp, setFocusTimestamp] = useState<number | undefined>();
const [allTriggers, setAllTriggers] = useState<Trigger[]>([]);
```

- [ ] **Step 2: 添加K线数据加载函数**

在 loadTriggers 函数附近添加 loadKlines：

```tsx
const loadKlines = async (sym: string, tf: string) => {
  setKlinesLoading(true);
  try {
    const data = await fetchMarketKlines(sym, tf, 500);
    setKlines(data as any[]);
  } catch (error) {
    console.error("Failed to load klines:", error);
  } finally {
    setKlinesLoading(false);
  }
};
```

- [ ] **Step 3: 添加全量触发记录加载函数**

K线上的标记需要全量触发记录（不止当前页），新增一个不分页的加载：

```tsx
const loadAllTriggers = async () => {
  try {
    const response = await axios.get(
      `${API_BASE_URL}/api/triggers?strategy_id=${id}&page=1&page_size=500`
    );
    setAllTriggers(response.data.items || []);
  } catch (error) {
    console.error("Failed to load all triggers:", error);
  }
};
```

- [ ] **Step 4: 修改 tab 切换逻辑，加载K线和全量触发**

在 `onValueChange` 回调中，当切换到 triggers tab 时同时加载K线数据和全量触发记录：

```tsx
if (value === "triggers" && !triggersLoaded) {
  loadTriggers(1);
  if (strategy) {
    loadKlines(strategy.symbol, chartPeriod);
    loadAllTriggers();
  }
}
```

- [ ] **Step 5: 添加 chartPeriod 变化时重新加载K线**

```tsx
const handleChartPeriodChange = (period: string) => {
  setChartPeriod(period);
  if (strategy) {
    loadKlines(strategy.symbol, period);
  }
};
```

- [ ] **Step 6: 将触发记录转换为 TradeMarker**

用 useMemo 将 allTriggers 转为 markers 数组：

```tsx
const tradeMarkers: TradeMarker[] = useMemo(() => {
  return allTriggers
    .filter((t) => t.action && t.action !== "观望" && t.price)
    .map((t) => ({
      timestamp: new Date(t.triggered_at).getTime(),
      price: t.price!,
      side: (t.action === "买入" ? "buy" : "sell") as "buy" | "sell",
      quantity: t.quantity,
      pnl: t.simulated_pnl,
    }));
}, [allTriggers]);
```

- [ ] **Step 7: 在触发历史 tab 中插入 K 线图**

在 `<TabsContent value="triggers">` 内、触发历史表格之前插入K线图区域：

```tsx
{/* K线图 */}
{strategy && (
  <div className="mb-4">
    <KlineChartModule
      data={klines}
      markers={tradeMarkers}
      indicators={{ ma: true, volume: true }}
      height={400}
      title={strategy.name}
      subtitle={`${strategy.symbol} · ${chartPeriod}`}
      activePeriod={chartPeriod}
      onPeriodChange={handleChartPeriodChange}
      focusTimestamp={focusTimestamp}
    />
  </div>
)}
```

- [ ] **Step 8: 表格行添加点击事件和高亮样式**

修改触发记录表格的 `<tr>` 添加点击事件，点击时设置 focusTimestamp：

```tsx
<tr
  key={trigger.id}
  className="border-b border-slate-800 last:border-0 cursor-pointer hover:bg-slate-800/50 transition-colors"
  onClick={() => {
    if (trigger.triggered_at) {
      setFocusTimestamp(new Date(trigger.triggered_at).getTime());
    }
  }}
>
```

- [ ] **Step 9: 添加 useMemo import**

确保顶部 import 中包含 useMemo：

```tsx
import { useEffect, useState, useMemo } from "react";
```

- [ ] **Step 10: 验证并构建**

Run: `cd /home/autotrade/autotrade/frontend && npx next build 2>&1 | tail -20`
Expected: 构建成功无错误

- [ ] **Step 11: Commit**

```bash
cd /home/autotrade/autotrade
git add frontend/src/app/strategies/\[id\]/page.tsx
git commit -m "feat: 策略详情触发历史tab集成K线图，支持买卖点标记和行点击联动"
```
