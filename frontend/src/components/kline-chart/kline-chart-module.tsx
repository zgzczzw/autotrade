"use client";

import { useEffect, useRef, useState, useMemo, useCallback } from "react";
import { init, dispose, Chart, IndicatorCreate, KLineData } from "klinecharts";
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

  // 转换数据
  const klineData = useMemo(() => transformKlineData(data), [data]);

  // 用 ref 持有最新数据，避免 useEffect 闭包捕获旧值
  const klineDataRef = useRef(klineData);
  klineDataRef.current = klineData;

  // 初始化图表
  useEffect(() => {
    if (!chartRef.current) return;

    if (chartInstance.current) {
      dispose(chartInstance.current);
      chartInstance.current = null;
    }

    const chart = init(chartRef.current, {
      styles: {
        grid: {
          show: false,
        },
      },
    });

    if (chart) {
      chartInstance.current = chart;

      chart.setSymbol({ ticker: subtitle || "UNKNOWN", pricePrecision: 2, volumePrecision: 4 });
      chart.setPeriod({ type: "hour", span: 1 });
      chart.setDataLoader({
        getBars: (params) => {
          params.callback(klineDataRef.current, false);
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
    if (!chartInstance.current) return;
    chartInstance.current.setDataLoader({
      getBars: (params) => {
        params.callback(klineData, false);
      },
    });
  }, [klineData]);

  // 买卖点标记
  useEffect(() => {
    const chart = chartInstance.current;
    if (!chart || !markers || markers.length === 0) return;

    // 等数据加载完毕后再添加标记
    const timer = setTimeout(() => {
      // 清除旧的标记
      chart.removeOverlay({ groupId: "trade_markers" });

      // 添加买卖点
      const overlays = markers.map((marker) => ({
        name: "simpleAnnotation",
        groupId: "trade_markers",
        lock: true,
        points: [{ timestamp: marker.timestamp, value: marker.price }],
        extendData: marker.side === "buy" ? "B" : "S",
        styles: {
          polygon: {
            color: marker.side === "buy" ? "#22c55e" : "#ef4444",
            borderColor: marker.side === "buy" ? "#22c55e" : "#ef4444",
          },
          text: {
            color: "#ffffff",
            backgroundColor: marker.side === "buy" ? "#22c55e" : "#ef4444",
          },
          line: {
            color: marker.side === "buy" ? "#22c55e" : "#ef4444",
          },
        },
      }));

      chart.createOverlay(overlays as any);
    }, 300);

    return () => clearTimeout(timer);
  }, [markers, klineData]);

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
          <div className="flex flex-wrap items-center gap-2 p-3 bg-slate-900 border-b border-slate-800">
            {/* 时间周期（可隐藏） */}
            {!hidePeriodSelector && (
              <>
                <div className="flex items-center gap-1">
                  {timePeriods.map((period) => (
                    <Button
                      key={period.value}
                      variant={activePeriod === period.value ? "default" : "ghost"}
                      size="sm"
                      onClick={() => handlePeriodClick(period.value)}
                      className={`h-7 px-2 text-xs ${
                        activePeriod === period.value
                          ? "bg-slate-700"
                          : "hover:bg-slate-800"
                      }`}
                    >
                      {period.label}
                    </Button>
                  ))}
                </div>
                <div className="w-px h-6 bg-slate-700 mx-2" />
              </>
            )}

            {/* 指标切换 */}
            <div className="flex items-center gap-1">
              {(["ma", "macd", "kdj", "rsi", "boll"] as const).map((name) => (
                <Button
                  key={name}
                  variant={activeIndicators[name] ? "default" : "outline"}
                  size="sm"
                  onClick={() => toggleIndicator(name)}
                  className={`h-7 px-2 text-xs ${
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
              className="h-7 px-2 ml-auto"
            >
              <Maximize2 className="w-4 h-4" />
            </Button>
          </div>

          {/* 标题 */}
          {(title || subtitle) && (
            <div className="px-4 py-2 bg-slate-900 border-b border-slate-800">
              <div className="flex items-center gap-2">
                {title && (
                  <h3 className="text-sm font-medium text-slate-200">{title}</h3>
                )}
                {subtitle && (
                  <Badge variant="outline" className="text-xs bg-slate-800">
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
          <div className="px-4 py-2 bg-slate-900 border-t border-slate-800 text-xs text-slate-400 flex items-center gap-4">
            <div className="flex items-center gap-1">
              <div className="w-3 h-3 bg-green-500 rounded-sm" />
              <span>上涨</span>
            </div>
            <div className="flex items-center gap-1">
              <div className="w-3 h-3 bg-red-500 rounded-sm" />
              <span>下跌</span>
            </div>
            <div className="flex items-center gap-1">
              <TrendingUp className="w-3 h-3 text-green-500" />
              <span>买入</span>
            </div>
            <div className="flex items-center gap-1">
              <TrendingDown className="w-3 h-3 text-red-500" />
              <span>卖出</span>
            </div>
            {activeIndicators.ma && (
              <div className="flex items-center gap-2 ml-auto">
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

  // 固定主图高度，不随子图增减变化
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
