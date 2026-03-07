"use client";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { X } from "lucide-react";
import {
  ConditionRule,
  INDICATOR_DEFS,
  IndicatorKey,
  Operator,
  getIndicatorDef,
  makeEmptyRule,
} from "./types";

interface ConditionRuleProps {
  rule: ConditionRule;
  onChange: (rule: ConditionRule) => void;
  onDelete: () => void;
}

export function ConditionRuleRow({ rule, onChange, onDelete }: ConditionRuleProps) {
  const def = getIndicatorDef(rule.indicator);

  function handleIndicatorChange(key: IndicatorKey) {
    const newDef = getIndicatorDef(key);
    const fresh = makeEmptyRule();
    onChange({ ...fresh, indicator: key, params: { ...newDef.defaultParams } });
  }

  function handleParamChange(paramKey: string, val: string) {
    const num = parseFloat(val);
    onChange({ ...rule, params: { ...rule.params, [paramKey]: isNaN(num) ? 0 : num } });
  }

  return (
    <div className="flex items-center gap-2 flex-wrap">
      {/* 指标选择 */}
      <Select value={rule.indicator} onValueChange={(v) => handleIndicatorChange(v as IndicatorKey)}>
        <SelectTrigger className="h-8 w-36 bg-slate-800 border-slate-700 text-sm">
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {INDICATOR_DEFS.map((d) => (
            <SelectItem key={d.key} value={d.key}>{d.label}</SelectItem>
          ))}
        </SelectContent>
      </Select>

      {/* 参数输入 */}
      {def.paramDefs.map((p) => (
        <div key={p.key} className="flex items-center gap-1">
          <span className="text-xs text-slate-400">{p.label}</span>
          <Input
            type="number"
            value={rule.params[p.key] ?? def.defaultParams[p.key]}
            onChange={(e) => handleParamChange(p.key, e.target.value)}
            min={p.min}
            max={p.max}
            className="h-8 w-16 bg-slate-800 border-slate-700 text-sm"
          />
        </div>
      ))}

      {/* 运算符（数值类）或 枚举值（枚举类） */}
      {def.kind === "numeric" ? (
        <>
          <Select
            value={rule.operator ?? ">"}
            onValueChange={(v) => onChange({ ...rule, operator: v as Operator })}
          >
            <SelectTrigger className="h-8 w-16 bg-slate-800 border-slate-700 text-sm">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {def.operators!.map((op) => (
                <SelectItem key={op} value={op}>{op}</SelectItem>
              ))}
            </SelectContent>
          </Select>
          <Input
            type="number"
            value={rule.value as number}
            onChange={(e) => onChange({ ...rule, value: parseFloat(e.target.value) ?? 0 })}
            className="h-8 w-20 bg-slate-800 border-slate-700 text-sm"
          />
        </>
      ) : (
        <Select
          value={rule.value as string}
          onValueChange={(v) => v && onChange({ ...rule, value: v })}
        >
          <SelectTrigger className="h-8 w-44 bg-slate-800 border-slate-700 text-sm">
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {def.enumValues!.map((ev) => (
              <SelectItem key={ev.value} value={ev.value}>{ev.label}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      )}

      {/* 删除 */}
      <Button
        variant="ghost"
        size="icon"
        onClick={onDelete}
        className="h-8 w-8 text-slate-500 hover:text-red-400 shrink-0"
      >
        <X className="w-4 h-4" />
      </Button>
    </div>
  );
}
