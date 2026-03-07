"use client";

import { useMemo } from "react";

interface KlineData {
  time: string;
  open: number;
  high: number;
  low: number;
  close: number;
  volume: number;
}

interface Trade {
  time: string;
  side: "buy" | "sell";
  price: number;
  quantity: number;
  pnl?: number;
}

interface BacktestKlineChartProps {
  klinesJson: string;
  tradesJson: string;
  height?: number;
}

export function BacktestKlineChart({
  klinesJson,
  tradesJson,
  height = 400,
}: BacktestKlineChartProps) {
  const { klines, trades, stats } = useMemo(() => {
    try {
      const parsedKlines: KlineData[] = JSON.parse(klinesJson || "[]");
      const parsedTrades: Trade[] = JSON.parse(tradesJson || "[]");

      // 采样，最多显示200根K线
      let displayKlines = parsedKlines;
      if (parsedKlines.length > 200) {
        const step = Math.ceil(parsedKlines.length / 200);
        displayKlines = parsedKlines.filter((_, i) => i % step === 0);
      }

      // 计算价格范围
      const prices = displayKlines.flatMap((k) => [k.high, k.low]);
      const minPrice = Math.min(...prices);
      const maxPrice = Math.max(...prices);
      const priceRange = maxPrice - minPrice || 1;

      // 计算成交量范围
      const maxVolume = Math.max(...displayKlines.map((k) => k.volume), 1);

      return {
        klines: displayKlines,
        trades: parsedTrades,
        stats: { minPrice, maxPrice, priceRange, maxVolume },
      };
    } catch {
      return { klines: [], trades: [], stats: { minPrice: 0, maxPrice: 0, priceRange: 1, maxVolume: 1 } };
    }
  }, [klinesJson, tradesJson]);

  if (klines.length === 0) {
    return (
      <div
        className="flex items-center justify-center bg-slate-800 rounded-lg"
        style={{ height }}
      >
        <p className="text-slate-400">暂无K线数据</p>
      </div>
    );
  }

  const margin = { top: 20, right: 60, bottom: 80, left: 10 };
  const volumeHeight = 60;
  const chartHeight = height - margin.top - margin.bottom - volumeHeight;
  const width = klines.length * 8 + margin.left + margin.right;
  const candleWidth = 6;
  const candleGap = 2;

  // 坐标转换函数
  const priceToY = (price: number) => {
    return (
      margin.top +
      chartHeight -
      ((price - stats.minPrice) / stats.priceRange) * chartHeight
    );
  };

  const volumeToY = (volume: number) => {
    return (
      margin.top + chartHeight + volumeHeight - (volume / stats.maxVolume) * volumeHeight
    );
  };

  const indexToX = (index: number) => {
    return margin.left + index * (candleWidth + candleGap) + candleWidth / 2;
  };

  // 查找交易点对应的K线索引
  const findTradeIndex = (tradeTime: string) => {
    const tradeDate = new Date(tradeTime).getTime();
    return klines.findIndex((k) => {
      const klineDate = new Date(k.time).getTime();
      return Math.abs(klineDate - tradeDate) < 3600000; // 1小时内
    });
  };

  // 生成价格刻度
  const priceTicks = 5;
  const priceLabels = Array.from({ length: priceTicks }, (_, i) => {
    const price = stats.minPrice + (stats.priceRange * i) / (priceTicks - 1);
    return {
      price,
      y: priceToY(price),
      label: price.toFixed(2),
    };
  });

  return (
    <div className="overflow-x-auto">
      <svg
        width={Math.max(width, 800)}
        height={height}
        className="bg-slate-900"
      >
        {/* 网格线 */}
        {priceLabels.map((tick, i) => (
          <g key={i}>
            <line
              x1={margin.left}
              y1={tick.y}
              x2={width - margin.right}
              y2={tick.y}
              stroke="#334155"
              strokeWidth={0.5}
              strokeDasharray="2,2"
            />
            <text
              x={width - margin.right + 5}
              y={tick.y + 4}
              fill="#94a3b8"
              fontSize={10}
            >
              {tick.label}
            </text>
          </g>
        ))}

        {/* 成交量区域背景 */}
        <rect
          x={margin.left}
          y={margin.top + chartHeight}
          width={width - margin.left - margin.right}
          height={volumeHeight}
          fill="#1e293b"
          opacity={0.3}
        />

        {/* 分隔线 */}
        <line
          x1={margin.left}
          y1={margin.top + chartHeight}
          x2={width - margin.right}
          y2={margin.top + chartHeight}
          stroke="#475569"
          strokeWidth={1}
        />

        {/* K线 */}
        {klines.map((kline, i) => {
          const x = indexToX(i);
          const yOpen = priceToY(kline.open);
          const yClose = priceToY(kline.close);
          const yHigh = priceToY(kline.high);
          const yLow = priceToY(kline.low);
          const isUp = kline.close >= kline.open;
          const color = isUp ? "#22c55e" : "#ef4444"; // 绿色涨，红色跌

          return (
            <g key={i}>
              {/* 影线 */}
              <line
                x1={x}
                y1={yHigh}
                x2={x}
                y2={yLow}
                stroke={color}
                strokeWidth={1}
              />
              {/* 实体 */}
              <rect
                x={x - candleWidth / 2}
                y={Math.min(yOpen, yClose)}
                width={candleWidth}
                height={Math.max(Math.abs(yClose - yOpen), 1)}
                fill={color}
              />
              {/* 成交量 */}
              <rect
                x={x - candleWidth / 2}
                y={volumeToY(kline.volume)}
                width={candleWidth}
                height={
                  margin.top + chartHeight + volumeHeight - volumeToY(kline.volume)
                }
                fill={color}
                opacity={0.5}
              />
            </g>
          );
        })}

        {/* 交易标记点 */}
        {trades.map((trade, i) => {
          const index = findTradeIndex(trade.time);
          if (index === -1) return null;

          const x = indexToX(index);
          const y = priceToY(trade.price);
          const isBuy = trade.side === "buy";
          const color = isBuy ? "#3b82f6" : "#f59e0b"; // 蓝色买，橙色卖

          return (
            <g key={i}>
              {/* 标记圆圈 */}
              <circle cx={x} cy={y} r={6} fill={color} stroke="white" strokeWidth={1} />
              {/* 箭头 */}
              {isBuy ? (
                <polygon
                  points={`${x},${y - 3} ${x - 3},${y + 2} ${x + 3},${y + 2}`}
                  fill="white"
                />
              ) : (
                <polygon
                  points={`${x},${y + 3} ${x - 3},${y - 2} ${x + 3},${y - 2}`}
                  fill="white"
                />
              )}
            </g>
          );
        })}

        {/* 图例 */}
        <g transform={`translate(${margin.left + 10}, ${height - 25})`}>
          <rect x={0} y={-8} width={12} height={12} fill="#22c55e" />
          <text x={16} y={2} fill="#94a3b8" fontSize={11}>
            上涨
          </text>

          <rect x={60} y={-8} width={12} height={12} fill="#ef4444" />
          <text x={76} y={2} fill="#94a3b8" fontSize={11}>
            下跌
          </text>

          <circle cx={130} cy={-2} r={5} fill="#3b82f6" stroke="white" strokeWidth={1} />
          <text x={140} y={2} fill="#94a3b8" fontSize={11}>
            买入
          </text>

          <circle cx={190} cy={-2} r={5} fill="#f59e0b" stroke="white" strokeWidth={1} />
          <text x={200} y={2} fill="#94a3b8" fontSize={11}>
            卖出
          </text>
        </g>

        {/* X轴时间标签（显示开始、中间、结束） */}
        {klines.length > 0 && (
          <>
            <text
              x={margin.left}
              y={height - 50}
              fill="#94a3b8"
              fontSize={10}
              textAnchor="start"
            >
              {new Date(klines[0].time).toLocaleDateString()}
            </text>
            <text
              x={width / 2}
              y={height - 50}
              fill="#94a3b8"
              fontSize={10}
              textAnchor="middle"
            >
              {new Date(klines[Math.floor(klines.length / 2)].time).toLocaleDateString()}
            </text>
            <text
              x={width - margin.right}
              y={height - 50}
              fill="#94a3b8"
              fontSize={10}
              textAnchor="end"
            >
              {new Date(klines[klines.length - 1].time).toLocaleDateString()}
            </text>
          </>
        )}
      </svg>
    </div>
  );
}
