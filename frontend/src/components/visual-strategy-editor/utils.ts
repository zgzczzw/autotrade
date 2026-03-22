import {
  ConditionGroup,
  ConditionRule,
  StrategyConfig,
  makeEmptyConfig,
  getIndicatorDef,
} from "./types";

// ─── 序列化 ────────────────────────────────────────────────

export function serializeConfig(config: StrategyConfig): string {
  const obj: Record<string, unknown> = {
    buy_conditions: config.buy_conditions,
    sell_conditions: config.sell_conditions,
  };
  if (config.short_conditions && config.short_conditions.rules.length > 0) {
    obj.short_conditions = config.short_conditions;
  }
  if (config.cover_conditions && config.cover_conditions.rules.length > 0) {
    obj.cover_conditions = config.cover_conditions;
  }
  return JSON.stringify(obj);
}

// ─── 反序列化（兼容旧格式） ───────────────────────────────

function normalizeGroup(raw: any): ConditionGroup {
  // 旧格式：{ logic, rules: [...] } 无 type 字段
  const logic = raw.logic === "OR" ? "OR" : "AND";
  const rules = (raw.rules ?? []).map((r: any) => {
    if (r.type === "group" || (!r.type && r.logic)) {
      return normalizeGroup(r);
    }
    return normalizeRule(r);
  });
  return { type: "group", logic, rules };
}

function normalizeRule(raw: any): ConditionRule {
  return {
    type: "rule",
    indicator: raw.indicator,
    params: raw.params ?? {},
    operator: raw.operator,
    value: raw.value,
  };
}

export function deserializeConfig(json: string): StrategyConfig {
  try {
    const parsed = JSON.parse(json);
    const config: StrategyConfig = {
      buy_conditions: normalizeGroup(parsed.buy_conditions ?? { logic: "AND", rules: [] }),
      sell_conditions: normalizeGroup(parsed.sell_conditions ?? { logic: "AND", rules: [] }),
    };
    if (parsed.short_conditions?.rules?.length > 0) {
      config.short_conditions = normalizeGroup(parsed.short_conditions);
    }
    if (parsed.cover_conditions?.rules?.length > 0) {
      config.cover_conditions = normalizeGroup(parsed.cover_conditions);
    }
    return config;
  } catch {
    return makeEmptyConfig();
  }
}

// ─── 预览文本生成 ─────────────────────────────────────────

const LOGIC_LABEL: Record<string, string> = {
  AND: "且",
  OR: "或",
};

const OPERATOR_LABEL: Record<string, string> = {
  "<": "小于",
  ">": "大于",
  "<=": "小于等于",
  ">=": "大于等于",
  "==": "等于",
};

function describeRule(rule: ConditionRule): string {
  const def = getIndicatorDef(rule.indicator);

  // 参数描述
  const paramStr = def.paramDefs
    .map((p) => `${p.label}=${rule.params[p.key] ?? def.defaultParams[p.key]}`)
    .join(", ");
  const paramLabel = paramStr ? `(${paramStr})` : "";

  if (def.kind === "enum") {
    const enumLabel =
      def.enumValues?.find((e) => e.value === rule.value)?.label ?? String(rule.value);
    return `${def.label}${paramLabel} ${enumLabel}`;
  } else {
    const opLabel = OPERATOR_LABEL[rule.operator ?? ">"] ?? rule.operator;
    const unit = rule.indicator === "PRICE_CHANGE" ? "%" : "";
    const volumeExtra =
      rule.indicator === "VOLUME" ? " 倍均量" : "";
    return `${def.label}${paramLabel} ${opLabel} ${rule.value}${unit}${volumeExtra}`;
  }
}

function describeGroup(group: ConditionGroup, depth = 0): string {
  if (group.rules.length === 0) return "（无条件）";

  const connector = `\n${" ".repeat((depth + 1) * 2)}${LOGIC_LABEL[group.logic]} `;
  const indent = " ".repeat((depth + 1) * 2);

  const parts = group.rules.map((r) => {
    if (r.type === "group") {
      const inner = describeGroup(r, depth + 1);
      return `满足以下${r.logic === "AND" ? "全部" : "任一"}条件：\n${inner}`;
    }
    return describeRule(r);
  });

  return parts.map((p) => `${indent}· ${p}`).join("\n");
}

export function generatePreviewText(config: StrategyConfig): string {
  const buyLogic = config.buy_conditions.logic === "AND" ? "全部" : "任一";
  const sellLogic = config.sell_conditions.logic === "AND" ? "全部" : "任一";

  let text = `买入信号（满足${buyLogic}条件时买入）：\n${describeGroup(config.buy_conditions)}`;
  text += `\n\n卖出信号（满足${sellLogic}条件时卖出）：\n${describeGroup(config.sell_conditions)}`;

  if (config.short_conditions && config.short_conditions.rules.length > 0) {
    const shortLogic = config.short_conditions.logic === "AND" ? "全部" : "任一";
    text += `\n\n开空信号（满足${shortLogic}条件时开空）：\n${describeGroup(config.short_conditions)}`;
  }
  if (config.cover_conditions && config.cover_conditions.rules.length > 0) {
    const coverLogic = config.cover_conditions.logic === "AND" ? "全部" : "任一";
    text += `\n\n平空信号（满足${coverLogic}条件时平空）：\n${describeGroup(config.cover_conditions)}`;
  }

  return text;
}
