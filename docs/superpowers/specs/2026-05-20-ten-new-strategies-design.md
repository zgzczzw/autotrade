# 十个全新策略设计 — 扩大策略池

## Overview

向 AutoTrade 策略池新增 10 个**风格互异**的策略，覆盖当前 16 个策略未涉及的流派：突破系（海龟/Squeeze）、ATR 趋势系（SuperTrend/ADX 通道）、日内回归（VWAP）、网格、多周期共振、形态平滑（Heikin Ashi）、摆动反转（StochRSI）、统计套利（Z-score）。

10 个策略均为 code 型，通过 `/var/tmp/strategies/` 文件同步机制注入，并在同步完成后由一次性脚本将 `status` 改为 `running`、注册到 APScheduler，实现"默认打开"。

## Motivation

### 当前策略表现摘要（基于 trigger_logs 模拟盈亏）

| sid | 名称 | 类型/周期 | 累计 PnL | 胜率 | 结论 |
|---|---|---|---|---|---|
| 3 | 布林带均值回归 ETH/1h | visual | **+8013** | 30W/14L (68%) | 均值回归在中等波动标的赚钱 |
| 13 | RSI 均值回归 BTC/1h | code | +57.76 | 17W/8L (68%) | 单指标反转也能稳定盈利 |
| 6 | RSI+MACD 双确认 BTC/1h | visual | +26.11 | 4W/1L (80%) | 多指标共振胜率最高 |
| 17 | 四维共振 BTC/4h | code | 回测 71% 胜率 | — | 多因子共振有效 |
| 2 | 双均线金叉死叉 | visual | -8.77 | 8W/19L (30%) | 单一交叉信号易被收割 |
| 5 | KDJ 摆动 ETH/1h | visual | -9.33 | 17W/24L (41%) | 信号过频，反复止损 |
| 7 | 布林带+量能 BTC/1h | visual | -28.79 | 3W/3L | 量能确认未带来优势 |
| 14 | 稳健混合 BTC/4h | code | -535 | 0W/1L | 实盘 vs 回测严重背离 |

### 设计立意

新策略不重复已经验证的"均值回归/多指标共振"模式（用户偏好"纯新思路探索"），转而探索：

- **突破系**：当前策略池只有"反向接刀"模式，缺少"顺势追突破"。海龟、Squeeze、SuperTrend 补齐。
- **波动率系**：现有策略对 ATR / 波动率收缩没有显式利用，Squeeze / ADX 通道引入。
- **多周期共振**：现有 4h 策略只看本周期，新增 1h+1d 双周期共振过滤假信号。
- **网格 / Z-score**：完全没有的统计/区间型，作为低相关性多样化补充。

## Requirements Summary

| Requirement | Decision |
|---|---|
| 策略数量 | 10 |
| 实现形式 | 全部 code 型（visual config 无法表达状态机/网格/MTF） |
| 注入方式 | `/var/tmp/strategies/*.py` → strategy_sync 自动 INSERT |
| 默认 status | `running`（由一次性脚本同步完成后 UPDATE 并触发 scheduler） |
| 用户归属 | admin (user_id=1) |
| 通知 | `notify_enabled=true` |
| 标的多样化 | BTC×5 / ETH×3 / SOL×2 |
| 周期多样化 | 15m×1 / 1h×4 / 4h×3 / 1d×2 |
| 风控基线 | 5% 硬止损 + ATR(14)×2.5 移动止损 + 平仓 3 根 K 线冷却 |
| 仓位 | percent 模式 10–15%（网格策略例外，每格 1% 总仓） |

## Data Model

无 schema 变更。所有新策略落地为 `strategies` 表新行：

- `type = "code"`
- `code = <文件内容>`
- `symbol = <主交易对>`（多 symbol 后续可通过 strategy_symbols 表扩展）
- `timeframe = <主周期>`
- `position_size`, `position_size_type`, `stop_loss`, `take_profit` 从文件头 `@meta` 自动解析
- `status = "running"`（由部署脚本设置）
- `user_id = 1`

## Architecture

### 文件 → DB → Scheduler 数据流

```
┌──────────────────────────────┐
│  /var/tmp/strategies/*.py    │  ← 策略源文件 (10 个新文件)
└──────────────┬───────────────┘
               │ 60s 扫描
               ▼
┌──────────────────────────────┐
│  services/strategy_sync.py   │  ← INSERT with status="stopped"
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│  strategies table (DB)       │
└──────────────┬───────────────┘
               │ 一次性部署脚本
               ▼  UPDATE status='running'
               │  + scheduler.add_strategy()
┌──────────────────────────────┐
│  engine/scheduler.py         │  ← 注册 APScheduler 任务
└──────────────────────────────┘
```

**为什么不绕过 sync 直接 INSERT：** sync 服务在循环中通过文件 mtime 反向覆盖 DB（`if mtime > db_updated: 更新 code/symbol/timeframe/...`）。如果先 INSERT 再补文件，文件 mtime 会比 DB updated_at 晚，导致每次 sync 都触发"更新"。**让文件成为 source-of-truth** 是更安全的路径。

### 部署脚本设计

`scripts/deploy_new_strategies.py`：

```python
"""
将 10 个新策略文件部署到 /var/tmp/strategies/，
等待 strategy_sync 入库后，将其 status 改为 running 并加入调度器。
"""
import asyncio, shutil, time
from pathlib import Path
from sqlalchemy import select, update
from app.database import async_session
from app.models import Strategy
from app.services.strategy_sync import sync_strategies
from app.engine.scheduler import scheduler_service

NEW_STRATEGY_NAMES = [
    "海龟突破策略", "SuperTrend 趋势策略", "VWAP 日内回归策略",
    "区间网格策略", "MTF 双周期共振策略", "Squeeze 波动率突破策略",
    "ADX 强趋势通道策略", "StochRSI 反转策略",
    "Heikin Ashi 趋势骑乘策略", "Z-score 均值回归策略",
]

async def main():
    # 1. 复制源文件
    src = Path("scripts/new_strategies")
    dst = Path("/var/tmp/strategies")
    for f in src.glob("*.py"):
        shutil.copy(f, dst / f.name)

    # 2. 触发同步（写入 DB，status="stopped"）
    await sync_strategies()

    # 3. 改 status=running + 注册到调度器
    async with async_session() as db:
        result = await db.execute(
            select(Strategy).where(Strategy.name.in_(NEW_STRATEGY_NAMES))
        )
        strategies = result.scalars().all()
        for s in strategies:
            s.status = "running"
        await db.commit()

        for s in strategies:
            await scheduler_service.add_strategy(s)
            print(f"✓ 启动 {s.name} (id={s.id})")

if __name__ == "__main__":
    asyncio.run(main())
```

**运行方式：** `./venv/bin/python3 scripts/deploy_new_strategies.py`

**幂等性：** 如果同名策略已存在，sync 走更新分支；status="running" 的策略不会被回退为 stopped。

### 公共代码模板

所有策略遵循统一骨架：

```python
# @name: <策略名>
# @symbol: <BTCUSDT|ETHUSDT|SOLUSDT>
# @timeframe: <15m|1h|4h|1d>
# @position_size: <10|15>
# @position_size_type: percent

class Strategy(BaseStrategy):
    def on_start(self):
        self.entry_price = None
        self.stop_price = None
        self.position_side = None
        self.highest_since_entry = None
        self.lowest_since_entry = None
        self.bars_since_exit = 99  # 冷却计数器

    def on_tick(self, data):
        klines = data["klines"]
        price  = data["price"]
        if len(klines) < <最小数据条数>:
            return "hold"

        # ① 计算策略特有指标
        ...
        # ② 计算 ATR（统一风控用）
        atr = self._atr(highs, lows, closes, 14)
        # ③ 持仓管理（统一风控）
        position = self.ctx.get_position()
        if position:
            return self._manage_position(position, price, atr, <反向退出条件>)
        # ④ 冷却
        self.bars_since_exit += 1
        if self.bars_since_exit < 3:
            return "hold"
        # ⑤ 入场判断（策略特有）
        ...

    # 共用辅助方法：_atr / _manage_position / _enter / _exit / _clear_state
```

`_manage_position`、`_atr`、`_enter`、`_exit`、`_clear_state` 在 10 个策略文件里各自实现（避免引入跨文件依赖；sync 目录只接受单文件策略）。

**每个策略 `on_tick` 入口最小 K 线数：**

| 策略 | 最小 K 线数 | 决定因素 |
|---|---|---|
| 1 海龟 | 25 | Donchian 20 + ATR(14) |
| 2 SuperTrend | 30 | ATR(10) + 上下轨 ratchet 需要历史 |
| 3 VWAP 日内回归 | 当日 5 根 | UTC 重置；当日数据不足按 hold |
| 4 区间网格 | 60 | EMA(50) 锚点 |
| 5 MTF 共振 | 1h 40 + daily 50 | MACD(26+9) + 日 EMA50 |
| 6 Squeeze | 30 | BB(20) + KC(20) + 5 根挤压窗口 |
| 7 ADX 通道 | 40 | ADX(14) 需要平滑期 + KC(20) |
| 8 StochRSI | 40 | RSI(14) + Stoch 窗口(14) + SMA(3) |
| 9 Heikin Ashi | 5 | 仅需 3 根 HA + 上一根 ha_open/close |
| 10 Z-score | 25 | window=20 + 一个 ATR(14) |

## Strategies Detail

### 策略 1：海龟突破策略

- **文件**：`turtle_breakout.py`
- **标的/周期**：BTCUSDT / 1d
- **思路**：经典 Donchian 通道，20 日新高入场，10 日新低出场（多空对称）
- **入场**：`price > max(high[-21:-1])` → 买；`price < min(low[-21:-1])` → 卖
- **出场**：反向 10 日通道触发 + 5% 硬止损 + ATR×2 移动止损
- **风控**：`position_size=15%`，`bars_cooldown=3`
- **预期场景**：长周期单边趋势（牛市启动、熊市破位）

### 策略 2：SuperTrend 趋势策略

- **文件**：`supertrend.py`
- **标的/周期**：BTCUSDT / 4h
- **思路**：基于 ATR 的抛物追踪线（上下轨随价格 ratchet），价格穿越翻转方向
- **公式**：
  ```
  basic_upper = (high+low)/2 + 3 × ATR(10)
  basic_lower = (high+low)/2 - 3 × ATR(10)
  final 上轨/下轨 取上一根 ratchet 值（只能更紧）
  trend = 1 if close > final_upper(prev) else -1 if close < final_lower(prev) else trend_prev
  ```
- **入场**：trend 由 -1 → +1 买；+1 → -1 卖
- **出场**：trend 反向翻转 + 统一风控
- **风控**：`position_size=15%`
- **预期场景**：中周期顺势跟随，主流 4h 趋势

### 策略 3：VWAP 日内回归策略

- **文件**：`vwap_reversion.py`
- **标的/周期**：ETHUSDT / 15m
- **思路**：每日 UTC 0 点重置 VWAP，价格偏离 VWAP 超过 1.5×stdev 时反向开仓，回归 VWAP 平仓
- **VWAP 计算**：
  ```
  cum_pv = Σ (typical_price × volume) (当日)
  cum_v  = Σ volume
  vwap   = cum_pv / cum_v
  stdev  = sqrt( Σ((typical - vwap)² × v) / cum_v )
  ```
- **入场**：`price > vwap + 1.5σ` → 卖；`price < vwap - 1.5σ` → 买
- **出场**：价格回归 |price - vwap| < 0.3σ + 统一风控
- **风控**：`position_size=10%`，因 15m 高频降低仓位
- **预期场景**：日内震荡市，ETH 流动性好且日内波动充分

### 策略 4：区间网格策略

- **文件**：`grid_range.py`
- **标的/周期**：ETHUSDT / 1h
- **思路**：在 [center×0.95, center×1.05] 区间内划 10 格，价格落入新格买入对应仓位，涨/跌至上/下一格止盈
- **center 计算**：启动时取 EMA(50) 作为锚点；每 24 小时滑动重置
- **入场**：`price` 落入空格 → 买入（每格固定 1% 总仓）
- **出场**：当前持仓的格子价 ±1% → 卖出该格
- **风控**：硬止损：价格超出区间 5% → 全部平仓 + 停止 24 小时
- **预期场景**：横盘震荡市，ETH 的中期区间

### 策略 5：MTF 双周期共振策略

- **文件**：`mtf_resonance.py`
- **标的/周期**：BTCUSDT / 1h（同时读 daily_klines）
- **思路**：1h 入场信号（MACD 金叉）必须叠加 1d 趋势同向（EMA50 斜率向上）
- **入场**：`1h MACD 金叉 ∧ daily_close > daily_ema50 ∧ daily_ema50 斜率>0` → 买
- **出场**：1h MACD 死叉 ∨ 1d 趋势反转 + 统一风控
- **风控**：`position_size=15%`
- **预期场景**：用日线趋势过滤 1h 假突破，提高胜率

### 策略 6：Squeeze 波动率突破策略

- **文件**：`squeeze_breakout.py`
- **标的/周期**：SOLUSDT / 1h
- **思路**：布林带被 Keltner 通道完全包裹（"挤压"）≥5 根 K 线后，向突破方向开仓
- **挤压条件**：`BB.upper < KC.upper ∧ BB.lower > KC.lower`
- **入场**：挤压结束（不再满足）且 `price > BB.upper` → 买；`price < BB.lower` → 卖
- **出场**：ATR×2 移动止损 + 5% 硬止损
- **风控**：`position_size=10%`（SOL 波动大）
- **预期场景**：SOL 高波动后的方向选择

### 策略 7：ADX 强趋势通道策略

- **文件**：`adx_keltner.py`
- **标的/周期**：BTCUSDT / 4h
- **思路**：ADX(14) > 25 时跟随 Keltner 通道方向开仓，ADX 衰减或反向穿轨退出
- **ADX**：经典 Wilder 算法（+DI/-DI/ADX）
- **入场**：`ADX>25 ∧ +DI>-DI ∧ price > KC.middle` → 买；对称做空
- **出场**：`ADX<20` ∨ `price` 穿对侧 Keltner 轨 + 统一风控
- **风控**：`position_size=12%`
- **预期场景**：明确单边趋势期（牛/熊），避开横盘

### 策略 8：StochRSI 反转策略

- **文件**：`stoch_rsi_reversal.py`
- **标的/周期**：ETHUSDT / 1h
- **思路**：StochRSI 极值区（<20 / >80）+ K 线钩头反转
- **StochRSI 计算**：`stoch_rsi = (RSI - min(RSI,N)) / (max(RSI,N) - min(RSI,N))`，再 SMA(3) 得 K 线
- **入场**：`K<20 ∧ K[t-1] < K[t]` → 买；`K>80 ∧ K[t-1] > K[t]` → 卖
- **出场**：`K` 回归至 [40, 60] + 统一风控
- **风控**：`position_size=10%`
- **预期场景**：震荡市的高胜率短线反转

### 策略 9：Heikin Ashi 趋势骑乘策略

- **文件**：`heikin_ashi_trend.py`
- **标的/周期**：SOLUSDT / 4h
- **思路**：Heikin Ashi 蜡烛平滑后，连续 3 根同色实体且无对侧影线 → 趋势成立，跟随
- **HA 公式**：
  ```
  ha_close = (open + high + low + close) / 4
  ha_open  = (prev_ha_open + prev_ha_close) / 2
  ha_high  = max(high, ha_open, ha_close)
  ha_low   = min(low,  ha_open, ha_close)
  ```
- **入场**：`HA[t-2..t] 三根阳线 ∧ HA[t-2..t] 无下影线（low >= min(open, close) − tol，tol = 0.05% × price）` → 买；对称做空（HA 三根阴线 ∧ 无上影线）
- **出场**：出现反色 HA 蜡烛或带长对侧影线 + 统一风控
- **风控**：`position_size=10%`
- **预期场景**：SOL 趋势平滑捕捉，过滤插针

### 策略 10：Z-score 均值回归策略

- **文件**：`zscore_reversion.py`
- **标的/周期**：BTCUSDT / 1h
- **思路**：价格相对滑动均值的 z-score 极端时反向开仓
- **z-score**：`z = (price - mean(close, 20)) / stdev(close, 20)`
- **入场**：`z < -2.0` → 买；`z > +2.0` → 卖
- **出场**：`|z| < 0.5` → 平仓 + 统一风控（硬止损 5%）
- **风控**：`position_size=10%`
- **预期场景**：1h BTC 短期偏离修复（与 sid=3 的布林带回归互为补充，但用纯统计参数）

## Data Constraints

executor 注入到 `on_tick(data)` 的字段：
- `data["symbol"]`、`data["timeframe"]`、`data["price"]`
- `data["klines"]`（当前周期 K 线列表）
- `data["daily_klines"]`（日线，当本周期不是 1d 时由 market_data_service 拉取）
- `data["fear_greed"]`（恐惧贪婪指数）

**没有提供：**
- 跨标的实时数据（→ 跨标的统计套利无法实现，#10 改为单标的 z-score）
- 第三周期数据（→ #5 由"三周期共振"降级为"1h+1d 双周期共振"）

## Error Handling

| 场景 | 处理 |
|---|---|
| K 线不足（< 最小条数） | 返回 `"hold"`，不入场 |
| `ATR == 0` 或 `None` | 用 `price * 0.02` 作为 fallback |
| `daily_klines` 为空（#5） | 跳过日线过滤层，仅本周期信号入场（更保守可改为 `hold`） |
| 计算溢出 / 异常 | executor 已有 try/except，捕获后下次 tick 重试 |
| 同步过程中策略名冲突 | sync 服务按 name+user_id 唯一去重，重复文件覆盖旧代码 |
| 部署脚本中途失败 | 重新运行即可（INSERT 已存在 → 走更新分支；status 已为 running → 重复 UPDATE 无害） |

## Testing Strategy

1. **静态语法检查**：所有 10 个文件本地 `python3 -m py_compile` 通过
2. **单文件冒烟测试**：在 `tests/` 下加 `test_new_strategies_smoke.py`，对每个策略构造 200 根 mock K 线，调用 `on_tick` 不抛异常
3. **回测对照**：部署后，通过 `POST /api/backtests/multi` 接口为每个策略跑近 90 日 BTC/ETH/SOL 回测，记录基线 pnl_percent / win_rate / max_drawdown
4. **手动验收**：前端打开 `/strategies` 页面，确认 10 个新策略全部 `running`，trigger_logs 在第一个完整 K 线周期内有信号产生

## Rollout

1. 将 10 个策略文件提交到 `scripts/new_strategies/` 目录（git tracked）
2. 部署脚本 `scripts/deploy_new_strategies.py` 也提交到 git
3. 运行 `./venv/bin/python3 scripts/deploy_new_strategies.py`
4. 在前端验证策略全部 running
5. 24 小时后查看 trigger_logs，确认每个策略至少有 1 次信号产生（否则参数过严，需要回炉调整）

## Rollback

```bash
# 紧急停止所有 10 个新策略
./venv/bin/python3 -c "
import asyncio
from sqlalchemy import update
from app.database import async_session
from app.models import Strategy
NAMES = [
    '海龟突破策略', 'SuperTrend 趋势策略', 'VWAP 日内回归策略',
    '区间网格策略', 'MTF 双周期共振策略', 'Squeeze 波动率突破策略',
    'ADX 强趋势通道策略', 'StochRSI 反转策略',
    'Heikin Ashi 趋势骑乘策略', 'Z-score 均值回归策略',
]
async def stop():
    async with async_session() as db:
        await db.execute(update(Strategy).where(Strategy.name.in_(NAMES)).values(status='stopped'))
        await db.commit()
asyncio.run(stop())
"

# 永久删除：从 sync 目录移除文件 + DELETE FROM strategies
```

## Open Questions

- [ ] 网格策略的 center 锚点：用 EMA(50) 还是部署时刻的现价？现选 EMA(50) 是因为更稳健，但用户可能希望"立刻按现价启动"。
- [ ] StochRSI 反转策略是否需要叠加一个日线趋势过滤器（避免在大趋势中反复抄底/摸顶）？目前未叠加，保持纯反转。
- [ ] Z-score 策略与既有 sid=3 布林带均值回归 ETH/1h 高度相关，但标的不同（BTC vs ETH）+ 参数不同（z-score 用纯 stdev 而非 BB）。如果担心策略池冗余，可替换为别的（如 PSAR、Aroon）。

## Success Criteria

- [ ] 10 个 .py 文件落地于 `/var/tmp/strategies/`
- [ ] 数据库 strategies 表新增 10 行，`status='running'`，`user_id=1`
- [ ] APScheduler 注册 10 个新任务（`scheduler_service.scheduler.get_jobs()` 显示）
- [ ] 部署后 24 小时内，每个策略 trigger_logs 至少 1 条
- [ ] 10 个策略冒烟测试 + 回测全部通过，无 executor 异常
