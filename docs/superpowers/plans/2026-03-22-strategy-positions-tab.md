# Strategy Positions Tab Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement the positions tab in the strategy detail page, showing current open position + paginated closed position history.

**Architecture:** Add a new `GET /api/positions/history` endpoint (with pagination) and a new `PositionHistoryList` schema in the backend; update the single frontend file `strategies/[id]/page.tsx` to lazy-load and render both sections on tab activation.

**Tech Stack:** FastAPI + SQLAlchemy async (backend), Next.js App Router + TypeScript + shadcn/ui + Tailwind CSS (frontend)

---

### Task 1: Backend — PositionHistoryList schema + history endpoint

**Files:**
- Modify: `backend/app/schemas.py` (after line 132, before `# === 账户相关 ===`)
- Modify: `backend/app/routers/account.py` (insert route before existing `@router.get("/positions")`)

- [ ] **Step 1: Add `PositionHistoryList` schema to `schemas.py`**

  In `backend/app/schemas.py`, after the `PositionList` class (around line 132) and before the `# === 账户相关 ===` comment, insert:

  ```python
  class PositionHistoryList(BaseModel):
      """历史持仓列表响应（含分页信息）"""
      items: List[PositionResponse]
      total: int
      page: int
      page_size: int
  ```

- [ ] **Step 2: Add `PositionHistoryList` to the import in `account.py`**

  In `backend/app/routers/account.py`, find the schemas import line:
  ```python
  from app.schemas import AccountResponse, MessageResponse, PositionList, PositionResponse
  ```
  Change it to:
  ```python
  from app.schemas import AccountResponse, MessageResponse, PositionHistoryList, PositionList, PositionResponse
  ```

- [ ] **Step 3: Add the `/positions/history` route BEFORE `/positions` in `account.py`**

  Insert the following block immediately before the existing `@router.get("/positions", response_model=PositionList)` route (before line 98):

  ```python
  @router.get("/positions/history", response_model=PositionHistoryList)
  async def list_position_history(
      strategy_id: Optional[int] = Query(None, description="筛选特定策略"),
      page: int = Query(1, ge=1, description="页码（从 1 开始）"),
      page_size: int = Query(20, ge=1, le=100, description="每页条数"),
      db: AsyncSession = Depends(get_db),
      current_user: User = Depends(get_current_user),
  ):
      """获取当前用户的历史平仓记录（已平仓持仓，分页）"""
      base_query = select(Position).where(
          Position.user_id == current_user.id,
          Position.closed_at.isnot(None),
      )

      if strategy_id:
          base_query = base_query.where(Position.strategy_id == strategy_id)

      # 总数
      count_result = await db.execute(
          select(func.count()).select_from(base_query.subquery())
      )
      total = count_result.scalar_one()

      # 分页查询
      query = base_query.order_by(Position.closed_at.desc())
      query = query.offset((page - 1) * page_size).limit(page_size)

      result = await db.execute(query)
      items = result.scalars().all()

      return PositionHistoryList(
          items=[PositionResponse.model_validate(item) for item in items],
          total=total,
          page=page,
          page_size=page_size,
      )
  ```

- [ ] **Step 4: Add `func` to the SQLAlchemy imports in `account.py`**

  The route uses `func.count()`. Find the existing line:
  ```python
  from sqlalchemy import text
  ```
  Change to (merge `func` into the same import):
  ```python
  from sqlalchemy import func, text
  ```

- [ ] **Step 5: Manually verify the endpoint logic**

  Read `backend/app/routers/account.py` and confirm:
  - `/positions/history` route appears **before** `/positions` route
  - `PositionHistoryList` is in the import line
  - `func` is imported from `sqlalchemy`
  - `closed_at.isnot(None)` filter is correct
  - pagination offset/limit formula: `(page - 1) * page_size`

- [ ] **Step 6: Commit backend changes**

  ```bash
  cd /home/autotrade/autotrade
  git add backend/app/schemas.py backend/app/routers/account.py
  git commit -m "feat: add /api/positions/history endpoint with pagination

  Generated with [Claude Code](https://claude.ai/code)
  via [Happy](https://happy.engineering)

  Co-Authored-By: Claude <noreply@anthropic.com>
  Co-Authored-By: Happy <yesreply@happy.engineering>"
  ```

---

### Task 2: Frontend — Positions tab UI

**Files:**
- Modify: `frontend/src/app/strategies/[id]/page.tsx`

- [ ] **Step 1: Add `TrendingUp` to the lucide-react import**

  Find the existing lucide import line:
  ```typescript
  import { ArrowLeft, ChevronLeft, ChevronRight, History, Pencil, Play, Square } from "lucide-react";
  ```
  Change to:
  ```typescript
  import { ArrowLeft, ChevronLeft, ChevronRight, History, Pencil, Play, Square, TrendingUp } from "lucide-react";
  ```

- [ ] **Step 2: Add the `Position` interface after the `Trigger` interface**

  After the closing `}` of the `Trigger` interface (around line 52), insert:

  ```typescript
  interface Position {
    id: number;
    strategy_id: number;
    symbol: string;
    side: string;
    entry_price: number;
    quantity: number;
    current_price?: number;
    pnl?: number;
    unrealized_pnl?: number;
    opened_at: string;
    closed_at?: string;
  }
  ```

- [ ] **Step 3: Add position state variables after the triggersLoaded state**

  After `const [triggersLoaded, setTriggersLoaded] = useState(false);` (line 63), insert:

  ```typescript
  const [currentPosition, setCurrentPosition] = useState<Position | null>(null);
  const [posHistory, setPosHistory] = useState<Position[]>([]);
  const [posHistoryTotal, setPosHistoryTotal] = useState(0);
  const [posHistoryPage, setPosHistoryPage] = useState(1);
  const [positionsLoading, setPositionsLoading] = useState(false);
  const [positionsLoaded, setPositionsLoaded] = useState(false);
  ```

- [ ] **Step 4: Add the `loadPositions` function after `loadTriggers`**

  After the closing `};` of `loadTriggers` (around line 97), insert:

  ```typescript
  const loadPositions = async (page = 1) => {
    setPositionsLoading(true);
    try {
      if (page === 1) {
        const [openRes, historyRes] = await Promise.all([
          axios.get(`${API_BASE_URL}/api/positions?strategy_id=${id}`),
          axios.get(`${API_BASE_URL}/api/positions/history?strategy_id=${id}&page=1&page_size=20`),
        ]);
        setCurrentPosition(openRes.data.items?.[0] ?? null);
        setPosHistory(historyRes.data.items || []);
        setPosHistoryTotal(historyRes.data.total || 0);
        setPosHistoryPage(1);
      } else {
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
      setPositionsLoaded(true);
    }
  };
  ```

- [ ] **Step 5: Extend the `onValueChange` handler to include the `"positions"` branch**

  Find the existing `onValueChange` on the `<Tabs>` component:
  ```typescript
  onValueChange={(value) => {
    if (value === "triggers" && !triggersLoaded) {
      loadTriggers(1);
    }
  }}
  ```
  Change to:
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

- [ ] **Step 6: Replace the placeholder positions TabsContent with the full implementation**

  Find and replace the entire `<TabsContent value="positions">` block:

  **Old:**
  ```tsx
  <TabsContent value="positions">
    <Card className="bg-slate-900 border-slate-800">
      <CardContent className="py-12 text-center">
        <p className="text-slate-400">持仓信息功能将在后续版本中支持</p>
      </CardContent>
    </Card>
  </TabsContent>
  ```

  **New:**
  ```tsx
  <TabsContent value="positions">
    {!positionsLoaded ? (
      positionsLoading ? (
        <div className="text-center py-12 text-slate-400">加载中...</div>
      ) : null
    ) : (
      <div className="space-y-6">
        {/* 当前持仓 */}
        <div>
          <h3 className="text-sm font-medium text-slate-400 mb-3">当前持仓</h3>
          {currentPosition ? (
            <Card className="bg-slate-900 border-slate-800">
              <CardContent className="p-4">
                <div className="flex flex-wrap gap-4 items-center">
                  <Badge className={currentPosition.side === "long" ? "bg-green-600" : "bg-orange-600"}>
                    {currentPosition.side === "long" ? "多仓" : "空仓"}
                  </Badge>
                  <div className="flex gap-6 text-sm">
                    <div>
                      <span className="text-slate-400 mr-2">开仓价</span>
                      <span>{formatPrice(currentPosition.entry_price)}</span>
                    </div>
                    <div>
                      <span className="text-slate-400 mr-2">数量</span>
                      <span>{currentPosition.quantity.toFixed(4)}</span>
                    </div>
                    {currentPosition.unrealized_pnl != null && (
                      <div>
                        <span className="text-slate-400 mr-2">浮动盈亏</span>
                        <span className={currentPosition.unrealized_pnl >= 0 ? "text-green-400" : "text-red-400"}>
                          {currentPosition.unrealized_pnl >= 0 ? "+" : ""}
                          {formatPrice(currentPosition.unrealized_pnl)}
                        </span>
                      </div>
                    )}
                  </div>
                </div>
              </CardContent>
            </Card>
          ) : (
            <p className="text-sm text-slate-500">当前无持仓</p>
          )}
        </div>

        {/* 历史平仓记录 */}
        <div>
          <h3 className="text-sm font-medium text-slate-400 mb-3">历史平仓记录</h3>
          {posHistory.length === 0 ? (
            <Card className="bg-slate-900 border-slate-800">
              <CardContent className="py-12 text-center">
                <TrendingUp className="w-12 h-12 text-slate-600 mx-auto mb-4" />
                <p className="text-slate-400">暂无平仓记录</p>
              </CardContent>
            </Card>
          ) : (
            <div className="space-y-4">
              <Card className={`bg-slate-900 border-slate-800 transition-opacity ${positionsLoading ? "opacity-60" : ""}`}>
                <CardContent className="p-0">
                  <div className="overflow-x-auto">
                    <table className="w-full">
                      <thead>
                        <tr className="border-b border-slate-800">
                          <th className="text-left p-4 text-slate-400 font-medium">开仓时间</th>
                          <th className="text-left p-4 text-slate-400 font-medium">平仓时间</th>
                          <th className="text-left p-4 text-slate-400 font-medium">方向</th>
                          <th className="text-left p-4 text-slate-400 font-medium">开仓价</th>
                          <th className="text-left p-4 text-slate-400 font-medium">平仓价</th>
                          <th className="text-left p-4 text-slate-400 font-medium">数量</th>
                          <th className="text-right p-4 text-slate-400 font-medium">盈亏</th>
                        </tr>
                      </thead>
                      <tbody>
                        {posHistory.map((pos) => (
                          <tr key={pos.id} className="border-b border-slate-800 last:border-0">
                            <td className="p-4 whitespace-nowrap">{formatDateTime(pos.opened_at)}</td>
                            <td className="p-4 whitespace-nowrap">{pos.closed_at ? formatDateTime(pos.closed_at) : "-"}</td>
                            <td className="p-4">
                              <Badge className={pos.side === "long" ? "bg-green-600" : "bg-orange-600"}>
                                {pos.side === "long" ? "多仓" : "空仓"}
                              </Badge>
                            </td>
                            <td className="p-4">{formatPrice(pos.entry_price)}</td>
                            <td className="p-4">{pos.current_price ? formatPrice(pos.current_price) : "-"}</td>
                            <td className="p-4">{pos.quantity.toFixed(4)}</td>
                            <td className="p-4 text-right">
                              {pos.pnl != null ? (
                                <span className={pos.pnl >= 0 ? "text-green-400" : "text-red-400"}>
                                  {pos.pnl >= 0 ? "+" : ""}{formatPrice(pos.pnl)}
                                </span>
                              ) : "-"}
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
                  onClick={() => loadPositions(posHistoryPage - 1)}
                  disabled={posHistoryPage <= 1}
                >
                  <ChevronLeft className="w-4 h-4 mr-1" />
                  上一页
                </Button>
                <span>
                  第 {posHistoryPage} / {Math.ceil(posHistoryTotal / 20)} 页，共 {posHistoryTotal} 条
                </span>
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => loadPositions(posHistoryPage + 1)}
                  disabled={posHistoryPage >= Math.ceil(posHistoryTotal / 20)}
                >
                  下一页
                  <ChevronRight className="w-4 h-4 ml-1" />
                </Button>
              </div>
            </div>
          )}
        </div>
      </div>
    )}
  </TabsContent>
  ```

- [ ] **Step 7: Commit frontend changes**

  ```bash
  cd /home/autotrade/autotrade
  git add frontend/src/app/strategies/[id]/page.tsx
  git commit -m "feat: implement positions tab with current position + paginated history

  Generated with [Claude Code](https://claude.ai/code)
  via [Happy](https://happy.engineering)

  Co-Authored-By: Claude <noreply@anthropic.com>
  Co-Authored-By: Happy <yesreply@happy.engineering>"
  ```

---

### Task 3: Build, restart, and smoke test

**Files:** None (operational)

- [ ] **Step 1: Restart backend**

  ```bash
  cd /home/autotrade/autotrade
  pkill -f "uvicorn" || true
  sleep 1
  nohup uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload > logs/backend.log 2>&1 &
  sleep 2
  ```

- [ ] **Step 2: Verify the new endpoint is registered**

  ```bash
  curl -s http://localhost:8000/openapi.json | python3 -c "
  import json, sys
  spec = json.load(sys.stdin)
  paths = spec.get('paths', {})
  print('/api/positions/history' in paths or any('history' in p for p in paths))
  print([p for p in paths if 'position' in p])
  "
  ```
  Expected: `True` and a list containing both `/api/positions` and `/api/positions/history`.

- [ ] **Step 3: Build the frontend**

  ```bash
  cd /home/autotrade/autotrade/frontend
  npm run build 2>&1 | tail -20
  ```
  Expected: exit 0, no TypeScript errors.

- [ ] **Step 4: Restart frontend**

  ```bash
  pkill -f "next" || true
  sleep 1
  cd /home/autotrade/autotrade/frontend
  nohup npm run start > ../logs/frontend.log 2>&1 &
  sleep 3
  ```

- [ ] **Step 5: Smoke test the history endpoint**

  Get a valid token first (replace `<TOKEN>` with an actual JWT from the running session), then:
  ```bash
  curl -s "http://localhost:8000/api/positions/history?strategy_id=1&page=1&page_size=20" \
    -H "Authorization: Bearer <TOKEN>" | python3 -m json.tool
  ```
  Expected: JSON with `items`, `total`, `page`, `page_size` fields (items may be empty array if no closed positions).

- [ ] **Step 6: Commit smoke test results (if any follow-up fixes were made)**

  Only if fixes were needed during smoke testing:
  ```bash
  git add -A
  git commit -m "fix: positions tab smoke test corrections

  Generated with [Claude Code](https://claude.ai/code)
  via [Happy](https://happy.engineering)

  Co-Authored-By: Claude <noreply@anthropic.com>
  Co-Authored-By: Happy <yesreply@happy.engineering>"
  ```
