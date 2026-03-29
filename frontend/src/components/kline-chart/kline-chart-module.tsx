"use client";

import { useEffect, useRef, useState, useMemo, useCallback } from "react";
import { init, dispose, Chart, IndicatorCreate, KLineData, registerOverlay } from "klinecharts";
import { KlineChartModuleProps, TradeMarker } from "./types";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { TrendingUp, TrendingDown, Maximize2, X } from "lucide-react";

// 注册自定义买卖点 overlay — 虚线 + 文字标签
// 锚点已经是 candle low(买) / high(卖)，绘制时只需向外延伸
let _overlayRegistered = false;
function ensureTradeMarkerOverlay() {
  if (_overlayRegistered) return;
  _overlayRegistered = true;

  registerOverlay({
    name: "tradeMarker",
    totalStep: 2,
    needDefaultPointFigure: false,
    createPointFigures: ({ overlay, coordinates }: any) => {
      const label: string = overlay.extendData ?? "";
      const isBuy = label === "B";
      const color: string = overlay.styles?.line?.color || (isBuy ? "#22c55e" : "#ef4444");
      const x = coordinates[0].x;
      const y = coordinates[0].y;
      // canvas y 轴向下增大：买入向下延伸(+)，卖出向上延伸(-)
      const d = isBuy ? 1 : -1;
      const lineStart = y + d * 4;
      const lineEnd = y + d * 40;
      const textY = lineEnd + d * 4;

      return [
        // 虚线
        {
          type: "line",
          attrs: { coordinates: [{ x, y: lineStart }, { x, y: lineEnd }] },
          styles: { style: "dashed", color, dashedValue: [4, 3], size: 1.5 },
          ignoreEvent: true,
        },
        // 小圆点（锚点位置）
        {
          type: "circle",
          attrs: { x, y: lineStart, r: 3 },
          styles: { style: "fill", color },
          ignoreEvent: true,
        },
        // B / S 文字
        {
          type: "text",
          attrs: {
            x,
            y: textY,
            text: label,
            align: "center",
            baseline: isBuy ? "top" : "bottom",
          },
          styles: { color: "#fff", backgroundColor: color, size: 11, paddingLeft: 4, paddingRight: 4, paddingTop: 2, paddingBottom: 2, borderRadius: 2 },
          ignoreEvent: true,
        },
      ];
    },
  } as any);
}

// 转换K线数据
function transformKlineData(data: any[]): KLineData[] {
  return data.map((item) => ({
    timestamp: typeof item.time === "string" ? new Date(item.time).getTime() : item.timestamp,
    open: Number(item.open),
    high: Number(item.high),
    low: Number(item.low),
    close: Number(item.close),
    volume: Number(item.volume),
  }));
}

// 时间周期（全局统一：1m / 15m / 1h / 4h / 1d）
const timePeriods = [
  { label: "1m",  value: "1m"  },
  { label: "15m", value: "15m" },
  { label: "1h",  value: "1h"  },
  { label: "4h",  value: "4h"  },
  { label: "1d",  value: "1d"  },
];

export function KlineChartModule({
  data,
  markers,
  indicators = { ma: true, volume: true },
  theme = "dark",
  height = 600,
  title = "K线图表",
  subtitle,
  focusTimestamp,
  activePeriod: controlledPeriod,
  onPeriodChange,
  hidePeriodSelector = false,
}: KlineChartModuleProps) {
  const chartRef = useRef<HTMLDivElement>(null);
  const chartInstance = useRef<Chart | null>(null);
  const [isFullscreen, setIsFullscreen] = useState(false);
  const [activeIndicators, setActiveIndicators] = useState({
    ma: !!indicators.ma,
    macd: !!indicators.macd,
    kdj: !!indicators.kdj,
    rsi: !!indicators.rsi,
    boll: indicators.boll !== false,
    volume: indicators.volume !== false,
  });
  const [internalPeriod, setInternalPeriod] = useState("1h");
  // 受控模式优先使用父组件传入的 activePeriod
  const activePeriod = controlledPeriod ?? internalPeriod;
  const handlePeriodClick = (value: string) => {
    if (onPeriodChange) {
      onPeriodChange(value);   // 受控：通知父组件，父组件拉取新数据
    } else {
      setInternalPeriod(value); // 非受控：仅更新内部视觉状态
    }
  };

  // 动态计算图表总高度：主图固定高度 + 各子图 100px
  const totalHeight = useMemo(() => {
    const subCount = (["macd", "kdj", "rsi", "volume"] as const).filter(
      (k) => activeIndicators[k]
    ).length;
    return height + subCount * 100;
  }, [height, activeIndicators]);

  // 根据价格量级自动计算精度：BTC(~70000)→0位, ETH(~2100)→1位, 小币→4位
  const pricePrecision = useMemo(() => {
    if (!data || data.length === 0) return 2;
    const sample = Number(data[data.length - 1]?.close ?? 0);
    if (sample === 0) return 2;
    if (sample >= 10000) return 0;
    if (sample >= 1000) return 1;
    if (sample >= 10) return 2;
    if (sample >= 1) return 3;
    return 4;
  }, [data]);

  // 转换数据
  const klineData = useMemo(() => transformKlineData(data), [data]);

  // 用 ref 持有最新数据，避免 useEffect 闭包捕获旧值
  const klineDataRef = useRef(klineData);
  klineDataRef.current = klineData;

  // 将 activePeriod 转换为 klinecharts 的 Period 格式
  const periodMap: Record<string, { type: string; span: number }> = {
    "1m":  { type: "minute", span: 1 },
    "15m": { type: "minute", span: 15 },
    "1h":  { type: "hour",   span: 1 },
    "4h":  { type: "hour",   span: 4 },
    "1d":  { type: "day",    span: 1 },
  };

  // 添加买卖点标记的辅助函数
  const applyMarkers = useCallback((chart: Chart, markersToApply: TradeMarker[]) => {
    // 清除旧的标记
    chart.removeOverlay({ groupId: "trade_markers" });

    if (!markersToApply || markersToApply.length === 0) return;

    // 构建有序时间戳数组和 timestamp→candle 索引
    const dataList = chart.getDataList();
    const candleMap = new Map<number, KLineData>();
    const timestamps: number[] = [];
    dataList.forEach((c) => {
      candleMap.set(c.timestamp, c);
      timestamps.push(c.timestamp);
    });

    // 二分查找最近的蜡烛时间戳
    const findNearestTimestamp = (target: number): number => {
      if (timestamps.length === 0) return target;
      let lo = 0, hi = timestamps.length - 1;
      while (lo < hi) {
        const mid = (lo + hi) >> 1;
        if (timestamps[mid] < target) lo = mid + 1;
        else hi = mid;
      }
      // lo 是第一个 >= target 的位置，比较 lo 和 lo-1 哪个更近
      if (lo === 0) return timestamps[0];
      const prev = timestamps[lo - 1];
      const curr = timestamps[lo];
      return (target - prev <= curr - target) ? prev : curr;
    };

    // 逐个创建 overlay
    markersToApply.forEach((marker) => {
      const isBuy = marker.side === "buy";
      const color = isBuy ? "#22c55e" : "#ef4444";
      // 对齐到最近的蜡烛时间戳
      const alignedTs = findNearestTimestamp(marker.timestamp);
      const candle = candleMap.get(alignedTs);
      // 买入锚定在 candle low，卖出锚定在 candle high，确保不与K线重叠
      const anchorPrice = candle
        ? (isBuy ? candle.low : candle.high)
        : marker.price;

      chart.createOverlay({
        name: "tradeMarker",
        groupId: "trade_markers",
        lock: true,
        visible: true,
        points: [{ timestamp: alignedTs, value: anchorPrice }],
        extendData: isBuy ? "B" : "S",
        styles: {
          line: { color },
        },
      } as any);
    });
  }, []);

  // 用 ref 持有最新 markers，供数据加载回调使用
  const markersRef = useRef(markers);
  markersRef.current = markers;

  // 初始化图表
  useEffect(() => {
    if (!chartRef.current) return;

    ensureTradeMarkerOverlay();

    if (chartInstance.current) {
      dispose(chartInstance.current);
      chartInstance.current = null;
    }

    const chart = init(chartRef.current, {
      styles: {
        grid: {
          show: false,
        },
        candle: {
          tooltip: {
            showRule: "follow_cross",
            title: { show: false },
            legend: {
              size: 10,
              marginLeft: 4,
              marginTop: 2,
              marginRight: 4,
              marginBottom: 2,
              template: [
                { title: "T", value: "{time}" },
                { title: "O", value: "{open}" },
                { title: "H", value: "{high}" },
                { title: "L", value: "{low}" },
                { title: "C", value: "{close}" },
              ],
            },
          },
        },
        indicator: {
          tooltip: {
            showRule: "follow_cross",
            title: {
              showName: false,
              showParams: false,
              size: 10,
              marginLeft: 4,
              marginTop: 2,
              marginRight: 4,
              marginBottom: 2,
            },
            legend: {
              size: 10,
              marginLeft: 4,
              marginTop: 2,
              marginRight: 4,
              marginBottom: 2,
            },
          },
        },
        yAxis: {
          tickText: {
            size: 10,
          },
        },
        xAxis: {
          tickText: {
            size: 10,
          },
        },
        crosshair: {
          horizontal: {
            text: { size: 10 },
          },
          vertical: {
            text: { size: 10 },
          },
        },
      },
    });

    if (chart) {
      chartInstance.current = chart;

      const period = periodMap[activePeriod] || { type: "hour", span: 1 };
      chart.setSymbol({ ticker: subtitle || "UNKNOWN", pricePrecision, volumePrecision: 2 });
      chart.setPeriod(period as any);
      chart.setDataLoader({
        getBars: (params) => {
          params.callback(klineDataRef.current, false);
          // 数据加载后立即添加标记
          requestAnimationFrame(() => {
            if (markersRef.current && markersRef.current.length > 0) {
              applyMarkers(chart, markersRef.current);
            }
          });
        },
      });

      applyIndicators(chart, activeIndicators);
    }

    return () => {
      if (chartInstance.current) {
        dispose(chartInstance.current);
        chartInstance.current = null;
      }
    };
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  // 数据更新时重新加载
  useEffect(() => {
    const chart = chartInstance.current;
    if (!chart) return;

    // 数据变化时更新精度
    chart.setSymbol({ ticker: subtitle || "UNKNOWN", pricePrecision, volumePrecision: 2 });

    const period = periodMap[activePeriod] || { type: "hour", span: 1 };
    chart.setPeriod(period as any);
    chart.setDataLoader({
      getBars: (params) => {
        params.callback(klineData, false);
        // 数据加载后添加标记
        requestAnimationFrame(() => {
          if (markersRef.current && markersRef.current.length > 0) {
            applyMarkers(chart, markersRef.current);
          }
        });
      },
    });
  }, [klineData, activePeriod]); // eslint-disable-line react-hooks/exhaustive-deps

  // 买卖点标记变化时重新添加（仅当 markers 引用变化时触发）
  useEffect(() => {
    const chart = chartInstance.current;
    if (!chart || !markers || markers.length === 0) return;

    // 使用 double-RAF 确保图表已完成渲染
    let cancelled = false;
    requestAnimationFrame(() => {
      if (cancelled) return;
      requestAnimationFrame(() => {
        if (cancelled) return;
        applyMarkers(chart, markers);
      });
    });

    return () => { cancelled = true; };
  }, [markers, applyMarkers]);

  // 聚焦到指定时间戳
  useEffect(() => {
    if (!focusTimestamp || !chartInstance.current) return;
    // 延迟确保数据已加载
    const timer = setTimeout(() => {
      try {
        (chartInstance.current as any)?.scrollToTimestamp?.(focusTimestamp);
      } catch {
        // scrollToTimestamp 不存在时忽略
      }
    }, 100);
    return () => clearTimeout(timer);
  }, [focusTimestamp]);

  // 容器高度变化后通知 klinecharts 重新布局，并固定主图高度
  useEffect(() => {
    const chart = chartInstance.current;
    if (!chart) return;
    // DOM 更新后 resize，再强制主图高度
    requestAnimationFrame(() => {
      chart.resize();
      requestAnimationFrame(() => {
        chart.setPaneOptions({ id: "candle_pane", height: height, minHeight: height });
      });
    });
  }, [totalHeight, height]);

  // 切换指标
  const toggleIndicator = useCallback((name: keyof typeof activeIndicators) => {
    setActiveIndicators((prev) => {
      const newConfig = { ...prev, [name]: !prev[name] };
      if (chartInstance.current) {
        applyIndicators(chartInstance.current, newConfig);
      }
      return newConfig;
    });
  }, []);

  return (
    <>
      <Card className="bg-slate-900 border-slate-800 overflow-hidden">
        <div className="flex flex-col h-full">
          {/* 工具栏 */}
          <div className="flex flex-wrap items-center gap-1 px-2 py-1.5 bg-slate-900 border-b border-slate-800">
            {/* 时间周期（可隐藏） */}
            {!hidePeriodSelector && (
              <>
                <div className="flex items-center gap-0.5">
                  {timePeriods.map((period) => (
                    <Button
                      key={period.value}
                      variant={activePeriod === period.value ? "default" : "ghost"}
                      size="sm"
                      onClick={() => handlePeriodClick(period.value)}
                      className={`h-6 px-1.5 text-[11px] ${
                        activePeriod === period.value
                          ? "bg-slate-700"
                          : "hover:bg-slate-800"
                      }`}
                    >
                      {period.label}
                    </Button>
                  ))}
                </div>
                <div className="w-px h-4 bg-slate-700 mx-1" />
              </>
            )}

            {/* 指标切换 */}
            <div className="flex items-center gap-0.5">
              {(["ma", "macd", "kdj", "rsi", "boll"] as const).map((name) => (
                <Button
                  key={name}
                  variant={activeIndicators[name] ? "default" : "outline"}
                  size="sm"
                  onClick={() => toggleIndicator(name)}
                  className={`h-6 px-1.5 text-[11px] ${
                    activeIndicators[name]
                      ? "bg-blue-600 hover:bg-blue-700"
                      : "bg-slate-800 border-slate-700 hover:bg-slate-700"
                  }`}
                >
                  {name.toUpperCase()}
                </Button>
              ))}
            </div>

            {/* 全屏按钮 */}
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setIsFullscreen(true)}
              className="h-6 px-1.5 ml-auto"
            >
              <Maximize2 className="w-3.5 h-3.5" />
            </Button>
          </div>

          {/* 标题 */}
          {(title || subtitle) && (
            <div className="px-2 py-1 bg-slate-900 border-b border-slate-800">
              <div className="flex items-center gap-1.5">
                {title && (
                  <h3 className="text-[11px] font-medium text-slate-200">{title}</h3>
                )}
                {subtitle && (
                  <Badge variant="outline" className="text-[10px] bg-slate-800 py-0">
                    {subtitle}
                  </Badge>
                )}
              </div>
            </div>
          )}

          {/* 图表容器 */}
          <div className="flex-1 relative">
            <div
              ref={chartRef}
              className="w-full"
              style={{ height: totalHeight }}
            />
          </div>

          {/* 图例 */}
          <div className="px-2 py-1 bg-slate-900 border-t border-slate-800 text-[10px] text-slate-400 flex items-center gap-2">
            <div className="flex items-center gap-0.5">
              <div className="w-2 h-2 bg-green-500 rounded-sm" />
              <span>涨</span>
            </div>
            <div className="flex items-center gap-0.5">
              <div className="w-2 h-2 bg-red-500 rounded-sm" />
              <span>跌</span>
            </div>
            <div className="flex items-center gap-0.5">
              <TrendingUp className="w-2.5 h-2.5 text-green-500" />
              <span>买</span>
            </div>
            <div className="flex items-center gap-0.5">
              <TrendingDown className="w-2.5 h-2.5 text-red-500" />
              <span>卖</span>
            </div>
            {activeIndicators.ma && (
              <div className="flex items-center gap-1.5 ml-auto">
                <span className="text-amber-500">MA5</span>
                <span className="text-blue-500">MA10</span>
                <span className="text-violet-500">MA20</span>
                <span className="text-pink-500">MA60</span>
              </div>
            )}
          </div>
        </div>
      </Card>

      <Dialog open={isFullscreen} onOpenChange={setIsFullscreen}>
        <DialogContent className="max-w-[95vw] w-[95vw] h-[95vh] p-0 bg-slate-900 border-slate-800">
          <DialogHeader className="p-4 border-b border-slate-800">
            <div className="flex items-center justify-between">
              <DialogTitle className="text-slate-200">
                {title || "K线图表"}
              </DialogTitle>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setIsFullscreen(false)}
              >
                <X className="w-4 h-4" />
              </Button>
            </div>
          </DialogHeader>
          <div className="flex-1 p-4">
            <KlineChartModule
              data={data}
              markers={markers}
              indicators={indicators}
              theme={theme}
              height={typeof window !== "undefined" ? window.innerHeight - 200 : 600}
              title={title}
              subtitle={subtitle}
            />
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}

// 子图指标固定高度
const SUB_PANE_HEIGHT = 100;

// 应用指标到图表
function applyIndicators(chart: Chart, config: Record<string, boolean>) {
  chart.removeIndicator();

  // MA / BOLL 叠加在主图，不新建子图
  if (config.ma) {
    chart.createIndicator(
      { name: "MA", calcParams: [5, 10, 20, 60] } as IndicatorCreate,
      true,
      { id: "candle_pane" }
    );
  }

  if (config.boll) {
    chart.createIndicator(
      { name: "BOLL", calcParams: [20, 2] } as IndicatorCreate,
      true,
      { id: "candle_pane" }
    );
  }

  // 子图指标：各自固定高度，主图高度不受影响
  if (config.macd) {
    chart.createIndicator(
      { name: "MACD", calcParams: [12, 26, 9] } as IndicatorCreate,
      false,
      { height: SUB_PANE_HEIGHT, minHeight: SUB_PANE_HEIGHT }
    );
  }

  if (config.kdj) {
    chart.createIndicator(
      { name: "KDJ", calcParams: [9, 3, 3] } as IndicatorCreate,
      false,
      { height: SUB_PANE_HEIGHT, minHeight: SUB_PANE_HEIGHT }
    );
  }

  if (config.rsi) {
    chart.createIndicator(
      { name: "RSI", calcParams: [14] } as IndicatorCreate,
      false,
      { height: SUB_PANE_HEIGHT, minHeight: SUB_PANE_HEIGHT }
    );
  }

  if (config.volume) {
    chart.createIndicator(
      { name: "VOL" } as IndicatorCreate,
      false,
      { height: SUB_PANE_HEIGHT, minHeight: SUB_PANE_HEIGHT }
    );
  }

  // 固定主图高度，不随子图增减变化（minHeight 保底）
  chart.setPaneOptions({ id: "candle_pane", minHeight: 300 });
}

// 导出便捷使用的模态框版本
export function KlineChartDialog({
  open,
  onOpenChange,
  ...props
}: KlineChartModuleProps & {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-6xl w-[90vw] h-[80vh] p-0 bg-slate-900 border-slate-800">
        <DialogHeader className="p-4 border-b border-slate-800">
          <DialogTitle className="text-slate-200">
            {props.title || "K线图表"}
          </DialogTitle>
        </DialogHeader>
        <div className="h-full">
          <KlineChartModule {...props} height={600} />
        </div>
      </DialogContent>
    </Dialog>
  );
}
