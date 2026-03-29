# 策略详情页触发历史 Tab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在策略详情页的「触发历史」tab 中实现带分页的触发记录表格，替换现有占位符。

**Architecture:** 纯前端改动，只修改 `strategies/[id]/page.tsx` 一个文件。复用现有后端接口 `GET /api/triggers?strategy_id={id}&page={n}&page_size=20`，tab 激活时懒加载，翻页时重新请求。

**Tech Stack:** Next.js / TypeScript / shadcn/ui (Badge, Button, Card) / axios

---

## 文件变更一览

| 文件 | 变更类型 | 说明 |
|------|---------|------|
| `frontend/src/app/strategies/[id]/page.tsx` | 修改 | 添加 Trigger 接口、state、loadTriggers、getActionBadge、触发历史 tab 内容 |

---

## Task 1: 实现触发历史 Tab

**Files:**
- Modify: `frontend/src/app/strategies/[id]/page.tsx`

背景：该文件已有 Strategy 接口、axios、shadcn/ui 组件的引用，以及一个 `<Tabs>` 结构，触发历史 tab 目前是占位符。`formatPrice` 从 `@/lib/utils` 导入（全局触发日志页已有示例）。

- [ ] **Step 1: 读取当前文件，确认导入和结构**

读取 `frontend/src/app/strategies/[id]/page.tsx` 确认：
- 顶部 import 中已有 `Badge` (shadcn/ui)、`Button`、`axios`、`History`（lucide-react）
- 如果没有 `History` 和 `formatPrice`，需要在下一步添加

- [ ] **Step 2: 更新 import，添加缺失的依赖**

在文件顶部 import 区域，确保以下内容存在：

```typescript
import { formatPrice, formatSymbol } from "@/lib/utils";
import { ArrowLeft, ChevronLeft, ChevronRight, History, Pencil, Play, Square } from "lucide-react";
```

如果 `ChevronLeft`、`ChevronRight`、`History` 已有其他引入方式，保持原样；如果 `formatPrice` 还没导入，加上它。

- [ ] **Step 3: 在 Strategy 接口之后添加 Trigger 接口**

在 `interface Strategy { ... }` 定义之后添加：

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

- [ ] **Step 4: 在组件 state 中添加触发历史相关 state**

在 `StrategyDetailPage` 函数内，现有的 `const [loading, setLoading] = useState(true);` 之后添加：

```typescript
const [triggers, setTriggers] = useState<Trigger[]>([]);
const [triggersTotal, setTriggersTotal] = useState(0);
const [triggersPage, setTriggersPage] = useState(1);
const [triggersLoading, setTriggersLoading] = useState(false);
const [triggersLoaded, setTriggersLoaded] = useState(false);
```

- [ ] **Step 5: 添加 loadTriggers 函数**

在现有 `loadStrategy` 函数之后添加：

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

- [ ] **Step 6: 添加 getActionBadge 函数**

在 `getStatusBadge` 函数之后添加：

```typescript
const getActionBadge = (action?: string) => {
  switch (action) {
    case "buy":
      return <Badge className="bg-green-600">买入</Badge>;
    case "sell":
      return <Badge className="bg-red-600">卖出</Badge>;
    case "short":
      return <Badge className="bg-orange-600">开空</Badge>;
    case "cover":
      return <Badge className="bg-purple-600">平空</Badge>;
    default:
      return <Badge variant="secondary">观望</Badge>;
  }
};
```

- [ ] **Step 7: 在 `<Tabs>` 上添加 onValueChange 回调**

找到现有的：

```tsx
<Tabs defaultValue="overview" className="space-y-6">
```

改为：

```tsx
<Tabs
  defaultValue="overview"
  className="space-y-6"
  onValueChange={(value) => {
    if (value === "triggers" && !triggersLoaded) {
      loadTriggers(1);
    }
  }}
>
```

- [ ] **Step 8: 替换触发历史 TabsContent**

找到现有的占位符：

```tsx
<TabsContent value="triggers">
  <Card className="bg-slate-900 border-slate-800">
    <CardContent className="py-12 text-center">
      <p className="text-slate-400">触发历史功能将在后续版本中支持</p>
    </CardContent>
  </Card>
</TabsContent>
```

替换为完整实现：

```tsx
<TabsContent value="triggers">
  {triggersLoading ? (
    <div className="text-center py-12 text-slate-400">加载中...</div>
  ) : triggers.length === 0 ? (
    <Card className="bg-slate-900 border-slate-800">
      <CardContent className="py-12 text-center">
        <History className="w-12 h-12 text-slate-600 mx-auto mb-4" />
        <p className="text-slate-400">暂无触发记录</p>
        <p className="text-sm text-slate-500 mt-2">
          启动策略后将在此显示触发记录
        </p>
      </CardContent>
    </Card>
  ) : (
    <div className="space-y-4">
      <Card className="bg-slate-900 border-slate-800">
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead>
                <tr className="border-b border-slate-800">
                  <th className="text-left p-4 text-slate-400 font-medium">时间</th>
                  <th className="text-left p-4 text-slate-400 font-medium">操作</th>
                  <th className="text-left p-4 text-slate-400 font-medium">价格</th>
                  <th className="text-left p-4 text-slate-400 font-medium">数量</th>
                  <th className="text-right p-4 text-slate-400 font-medium">盈亏</th>
                  <th className="text-left p-4 text-slate-400 font-medium">备注</th>
                </tr>
              </thead>
              <tbody>
                {triggers.map((trigger) => (
                  <tr key={trigger.id} className="border-b border-slate-800 last:border-0">
                    <td className="p-4 whitespace-nowrap">
                      {new Date(trigger.triggered_at).toLocaleString()}
                    </td>
                    <td className="p-4">{getActionBadge(trigger.action)}</td>
                    <td className="p-4">
                      {trigger.price ? formatPrice(trigger.price) : "-"}
                    </td>
                    <td className="p-4">
                      {trigger.quantity != null
                        ? trigger.quantity.toFixed(4)
                        : "-"}
                    </td>
                    <td className="p-4 text-right">
                      {trigger.simulated_pnl != null ? (
                        <span
                          className={
                            trigger.simulated_pnl >= 0
                              ? "text-green-400"
                              : "text-red-400"
                          }
                        >
                          {trigger.simulated_pnl >= 0 ? "+" : ""}
                          {formatPrice(trigger.simulated_pnl)}
                        </span>
                      ) : (
                        "-"
                      )}
                    </td>
                    <td className="p-4 text-sm text-slate-400 max-w-xs truncate">
                      {trigger.signal_detail || "-"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>

      {/* 分页控件 */}
      <div className="flex items-center justify-center gap-4 text-sm text-slate-400">
        <Button
          variant="outline"
          size="sm"
          onClick={() => loadTriggers(triggersPage - 1)}
          disabled={triggersPage <= 1}
        >
          <ChevronLeft className="w-4 h-4 mr-1" />
          上一页
        </Button>
        <span>
          第 {triggersPage} / {Math.ceil(triggersTotal / 20)} 页，共 {triggersTotal} 条
        </span>
        <Button
          variant="outline"
          size="sm"
          onClick={() => loadTriggers(triggersPage + 1)}
          disabled={triggersPage >= Math.ceil(triggersTotal / 20)}
        >
          下一页
          <ChevronRight className="w-4 h-4 ml-1" />
        </Button>
      </div>
    </div>
  )}
</TabsContent>
```

- [ ] **Step 9: 本地 TypeScript 编译检查**

```bash
cd /home/autotrade/autotrade/frontend
npx tsc --noEmit 2>&1 | head -30
```

预期：无输出（无 TypeScript 错误）。如有错误，根据报错修复后再继续。

- [ ] **Step 10: 提交**

```bash
cd /home/autotrade/autotrade
git add frontend/src/app/strategies/[id]/page.tsx
git commit -m "feat: implement trigger history tab with pagination"
```

---

## Task 2: 重新编译并重启前端

**Files:** 无代码变更，构建和部署操作

- [ ] **Step 1: 构建前端**

```bash
cd /home/autotrade/autotrade/frontend && npm run build 2>&1 | tail -20
```

预期：`✓ Compiled successfully`。如有构建错误，根据报错修复。

- [ ] **Step 2: 重启前端服务**

```bash
kill -9 $(lsof -ti:13000) 2>/dev/null
sleep 2
nohup npm exec next start -- -H 0.0.0.0 -p 13000 > /home/autotrade/autotrade/logs/frontend.log 2>&1 &
sleep 4
tail -3 /home/autotrade/autotrade/logs/frontend.log
```

预期：末行显示 `✓ Ready in Xms`。

- [ ] **Step 3: 冒烟测试**

```bash
curl -s -o /dev/null -w "%{http_code}" http://localhost:13000/strategies/1
```

预期：`200` 或 `307`（重定向到登录页均正常）。

- [ ] **Step 4: 提交构建产物无需提交（Next.js 构建输出不进 git）**

无需额外提交，Task 1 的 commit 已包含所有代码变更。
