"use client";

import { StrategyConfig } from "./types";
import { generatePreviewText } from "./utils";

interface StrategyPreviewProps {
  config: StrategyConfig;
  stopLoss?: number | null;
  takeProfit?: number | null;
}

export function StrategyPreview({ config, stopLoss, takeProfit }: StrategyPreviewProps) {
  const text = generatePreviewText(config);
  const lines = text.split("\n");

  return (
    <div className="rounded-lg border border-blue-800/50 bg-blue-950/30 p-4 space-y-2">
      <p className="text-xs font-semibold text-blue-400 uppercase tracking-wide">策略预览</p>
      <div className="text-sm text-slate-300 space-y-0.5">
        {lines.map((line, i) => (
          <p
            key={i}
            className={
              line.startsWith("买入") || line.startsWith("卖出")
                ? "font-medium text-slate-200 mt-2 first:mt-0"
                : line.trim().startsWith("·")
                ? "pl-4 text-slate-400"
                : "pl-8 text-slate-500 text-xs"
            }
          >
            {line || "\u00A0"}
          </p>
        ))}
      </div>

      {(stopLoss || takeProfit) && (
        <div className="flex gap-4 pt-2 border-t border-slate-700 text-xs">
          {stopLoss && (
            <span className="text-red-400">止损：-{stopLoss}%</span>
          )}
          {takeProfit && (
            <span className="text-green-400">止盈：+{takeProfit}%</span>
          )}
        </div>
      )}
    </div>
  );
}
