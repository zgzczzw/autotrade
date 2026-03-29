"""
快速回测脚本 — 直接调用回测引擎，不走 API
"""
import asyncio
import json
import sys
import os

# 添加 backend 到 path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime
from app.engine.backtester import BacktestEngine
from app.models import Strategy


async def run(code_path: str, timeframe: str, symbol: str,
              start_str: str, end_str: str,
              position_size: float = 10.0,
              position_size_type: str = "percent",
              initial_balance: float = 100000.0 * 10):
    """运行单次回测"""
    with open(code_path, "r") as f:
        code = f.read()

    # 构造模拟 Strategy 对象
    strategy = Strategy(
        id=99999,
        user_id=1,
        name=os.path.basename(code_path),
        type="code",
        code=code,
        symbol=symbol,
        timeframe=timeframe,
        position_size=position_size,
        position_size_type=position_size_type,
        status="running",
    )

    start_date = datetime.strptime(start_str, "%Y-%m-%d")
    end_date = datetime.strptime(end_str, "%Y-%m-%d")

    engine = BacktestEngine()
    result = await engine.run_backtest(strategy, symbol, start_date, end_date, initial_balance)

    trades = json.loads(result.trades) if isinstance(result.trades, str) else result.trades

    print(f"\n{'='*60}")
    print(f"策略: {code_path}")
    print(f"周期: {timeframe} | 品种: {symbol}")
    print(f"区间: {start_str} → {end_str}")
    print(f"{'='*60}")
    print(f"初始资金:   {initial_balance:,.2f}")
    print(f"最终资金:   {result.final_balance:,.2f}")
    print(f"总盈亏:     {result.total_pnl:,.2f} ({result.pnl_percent:+.2f}%)")
    print(f"最大回撤:   {result.max_drawdown:.2f}%")
    print(f"胜率:       {result.win_rate:.1f}%")
    print(f"总交易数:   {result.total_trades}")
    print(f"平均持仓:   {result.avg_hold_time}s (~{(result.avg_hold_time or 0)/3600:.1f}h)")
    print(f"{'='*60}")

    # 月度明细
    if trades:
        monthly = {}
        for t in trades:
            if t.get("pnl") is not None:
                month = t["time"][:7]
                monthly.setdefault(month, 0)
                monthly[month] += t["pnl"]
        if monthly:
            print("\n月度盈亏:")
            for m in sorted(monthly):
                pnl = monthly[m]
                bar = "+" * int(abs(pnl) / 100) if pnl > 0 else "-" * int(abs(pnl) / 100)
                print(f"  {m}: {pnl:>+10,.2f}  {bar}")

    return result


async def main():
    code_path = "/var/tmp/strategies/boll_breakout.py"
    symbol = "BTCUSDT"
    tf = "15m"
    size = 10.0
    size_type = "percent"

    periods = [
        ("过去1年", "2025-03-28", "2026-03-28"),
        ("过去半年", "2025-09-28", "2026-03-28"),
        ("过去3个月", "2025-12-28", "2026-03-28"),
    ]

    for label, start, end in periods:
        print(f"\n\n{'#'*60}")
        print(f"# {label}")
        print(f"{'#'*60}")
        try:
            await run(code_path, tf, symbol, start, end, size, size_type)
        except Exception as e:
            print(f"  回测失败: {e}")


if __name__ == "__main__":
    asyncio.run(main())
