# K线图模块设计方案

## 概述

设计一个功能完整的专业级K线图模块，参考Binance交易界面，提供丰富的技术指标和交互功能，供回测等模块调用显示。

## 设计目标

1. **功能完整性**: 提供与专业交易平台相当的K线显示能力
2. **模块化设计**: 独立封装，支持模态框显示，便于各模块复用
3. **指标丰富**: 支持MA、MACD、KDJ、RSI、BOLL等核心技术指标
4. **交互友好**: 支持缩放、平移、十字光标等基础交互

## 技术选型

### 核心库: KLineChart

- **选择理由**: 
  - 开源免费，功能完善
  - 原生支持多种技术指标
  - 体积小 (~100KB)，性能好
  - API友好，易于集成
- **官网**: https://klinecharts.com/

## 架构设计

### 整体布局

```
┌─────────────────────────────────────────────────────────────┐
│                    KLineChartModule                         │
│  ┌─────────────────────────────────────────────────────────┐│
│  │              图表容器 (KLineChart Core)                  ││
│  │  ┌─────────────────────────────────────────────────────┐││
│  │  │                                                     │││
│  │  │              主K线图区域                           │││
│  │  │   - K线数据渲染                                    │││
│  │  │   - MA指标线（5/10/20/60）                         │││
│  │  │   - BOLL布林带                                     │││
│  │  │   - 买卖信号标记                                   │││
│  │  │                                                     │││
│  │  └─────────────────────────────────────────────────────┘││
│  │  ┌──────────────┐  ┌──────────┐  ┌──────────┐        ││
│  │  │   MACD指标   │  │ KDJ指标  │  │ RSI指标  │        ││
│  │  │  (可切换)    │  │(可切换)  │  │(可切换)  │        ││
│  │  └──────────────┘  └──────────┘  └──────────┘        ││
│  │  ┌─────────────────────────────────────────────────────┐││
│  │  │              成交量区域                            │││
│  │  └─────────────────────────────────────────────────────┘││
│  └─────────────────────────────────────────────────────────┘│
│  ┌─────────────────────────────────────────────────────────┐│
│  │              工具栏 (Toolbar)                          ││
│  │  [时间: 1m 5m 15m 1h 4h 1d] [指标: MA MACD KDJ RSI]   ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

### 组件接口

```typescript
// K线数据格式
interface KlineData {
  timestamp: number;      // Unix毫秒时间戳
  open: number;           // 开盘价
  high: number;           // 最高价
  low: number;            // 最低价
  close: number;          // 收盘价
  volume: number;         // 成交量
}

// 交易标记
interface TradeMarker {
  timestamp: number;      // 时间戳
  price: number;          // 价格
  side: 'buy' | 'sell';   // 买入/卖出
  quantity?: number;      // 数量
  pnl?: number;           // 盈亏
}

// 组件Props
interface KlineChartProps {
  // 基础数据
  data: KlineData[];
  
  // 标记数据（买卖点）
  markers?: TradeMarker[];
  
  // 指标配置
  indicators?: {
    ma?: boolean | number[];    // MA周期，默认[5,10,20,60]
    macd?: boolean;             // MACD开关
    kdj?: boolean;              // KDJ开关
    rsi?: boolean;              // RSI开关
    boll?: boolean;             // BOLL开关
    volume?: boolean;           // 成交量开关，默认true
  };
  
  // 样式配置
  theme?: 'dark' | 'light';     // 主题，默认dark
  height?: number;              // 高度，默认600
}
```

## 功能特性

### 1. K线显示
- 标准蜡烛图显示
- 颜色：涨(红#ef4444)、跌(绿#22c55e)
- 支持缩放(滚轮)、平移(拖拽)
- 十字光标显示当前时间/价格

### 2. 技术指标

| 指标 | 类型 | 显示位置 | 可配置参数 |
|------|------|----------|-----------|
| MA | 主图叠加 | K线区域 | 周期: 5/10/20/60 |
| BOLL | 主图叠加 | K线区域 | 周期: 20, 标准差: 2 |
| MACD | 副图 | 独立区域 | 默认参数 |
| KDJ | 副图 | 独立区域 | 默认参数 |
| RSI | 副图 | 独立区域 | 周期: 14 |
| Volume | 底部 | K线下方 | - |

### 3. 买卖标记
- 买入: 蓝色上箭头 🔵
- 卖出: 橙色下箭头 🟠
- 显示在对应K线位置
- 悬停显示交易详情

### 4. 工具栏
- 时间周期切换: 1m/5m/15m/1h/4h/1d
- 指标开关: 一键显示/隐藏各指标
- 主题切换: 深色/浅色

## 使用场景

### 回测模块集成

```tsx
// 回测详情页
import { KlineChartModule } from '@/components/kline-chart-module';

// 点击"查看K线"按钮打开模态框
<Dialog open={showChart} onOpenChange={setShowChart}>
  <DialogContent className="max-w-6xl">
    <KlineChartModule 
      data={backtestKlines}
      markers={trades}
      indicators={{ 
        ma: [5, 10, 20, 60], 
        macd: true, 
        volume: true 
      }}
      height={600}
    />
  </DialogContent>
</Dialog>
```

## 样式规范

### 深色主题 (默认)
- 背景: #0f172a (slate-900)
- 网格线: #1e293b (slate-800)
- 文字: #94a3b8 (slate-400)
- 涨色: #22c55e (green-500)
- 跌色: #ef4444 (red-500)

### 指标颜色
- MA5: #f59e0b (amber)
- MA10: #3b82f6 (blue)
- MA20: #8b5cf6 (violet)
- MA60: #ec4899 (pink)
- 买入标记: #3b82f6 (blue)
- 卖出标记: #f59e0b (amber)

## 依赖

```json
{
  "dependencies": {
    "klinecharts": "^9.x"
  }
}
```

## 文件结构

```
frontend/src/components/kline-chart/
├── index.ts                    # 导出模块
├── kline-chart-module.tsx      # 主组件
├── indicators.ts               # 指标配置
├── styles.ts                   # 样式配置
└── types.ts                    # 类型定义
```

## 后续扩展

未来可考虑增加：
- 画图工具（趋势线、斐波那契回撤）
- 更多技术指标（CCI、WR、DMI）
- 多时间周期联动
- 自定义指标公式
