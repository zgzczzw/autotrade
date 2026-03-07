"use client";

import { Button } from "@/components/ui/button";
import { Plus, Layers, Trash2 } from "lucide-react";
import { ConditionGroup, ConditionRule, makeEmptyRule, makeEmptyGroup } from "./types";
import { ConditionRuleRow } from "./condition-rule";

const MAX_DEPTH = 3;

interface ConditionGroupProps {
  group: ConditionGroup;
  onChange: (group: ConditionGroup) => void;
  onDelete?: () => void;  // 顶层无删除
  depth?: number;
  label?: string;         // 顶层标题，如"买入条件"
}

export function ConditionGroupEditor({
  group,
  onChange,
  onDelete,
  depth = 0,
  label,
}: ConditionGroupProps) {
  function updateRule(index: number, updated: ConditionRule | ConditionGroup) {
    const rules = [...group.rules];
    rules[index] = updated;
    onChange({ ...group, rules });
  }

  function deleteRule(index: number) {
    const rules = group.rules.filter((_, i) => i !== index);
    onChange({ ...group, rules });
  }

  function addRule() {
    onChange({ ...group, rules: [...group.rules, makeEmptyRule()] });
  }

  function addGroup() {
    onChange({ ...group, rules: [...group.rules, makeEmptyGroup()] });
  }

  function toggleLogic() {
    onChange({ ...group, logic: group.logic === "AND" ? "OR" : "AND" });
  }

  const canNest = depth < MAX_DEPTH - 1;
  const isTopLevel = depth === 0;

  return (
    <div
      className={`rounded-lg border ${
        isTopLevel
          ? "border-slate-700 bg-slate-900"
          : "border-slate-700 bg-slate-800/50"
      } p-3 space-y-2`}
    >
      {/* 标题行 */}
      <div className="flex items-center gap-2">
        {label && (
          <span className="text-sm font-medium text-slate-300 mr-1">{label}</span>
        )}

        {/* AND/OR 切换 */}
        <button
          onClick={toggleLogic}
          className="px-2 py-0.5 rounded text-xs font-semibold border border-slate-600 hover:border-blue-500 transition-colors"
          style={{
            backgroundColor: group.logic === "AND" ? "#1e3a5f" : "#3b1f5e",
            color: group.logic === "AND" ? "#60a5fa" : "#c084fc",
          }}
        >
          {group.logic === "AND" ? "全部满足 AND" : "任一满足 OR"}
        </button>

        <span className="text-xs text-slate-500 ml-1">时触发</span>

        {/* 删除整组（非顶层） */}
        {onDelete && (
          <Button
            variant="ghost"
            size="icon"
            onClick={onDelete}
            className="h-6 w-6 ml-auto text-slate-500 hover:text-red-400"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </Button>
        )}
      </div>

      {/* 条件列表 */}
      <div className="space-y-2 pl-3 border-l-2 border-slate-700">
        {group.rules.map((rule, i) =>
          rule.type === "rule" ? (
            <ConditionRuleRow
              key={i}
              rule={rule}
              onChange={(updated) => updateRule(i, updated)}
              onDelete={() => deleteRule(i)}
            />
          ) : (
            <ConditionGroupEditor
              key={i}
              group={rule}
              onChange={(updated) => updateRule(i, updated)}
              onDelete={() => deleteRule(i)}
              depth={depth + 1}
            />
          )
        )}
      </div>

      {/* 操作按钮 */}
      <div className="flex items-center gap-2 pl-3">
        <Button
          variant="ghost"
          size="sm"
          onClick={addRule}
          className="h-7 px-2 text-xs text-slate-400 hover:text-slate-200"
        >
          <Plus className="w-3 h-3 mr-1" />
          添加条件
        </Button>

        {canNest && (
          <Button
            variant="ghost"
            size="sm"
            onClick={addGroup}
            className="h-7 px-2 text-xs text-slate-400 hover:text-slate-200"
          >
            <Layers className="w-3 h-3 mr-1" />
            添加条件组
          </Button>
        )}
      </div>
    </div>
  );
}
