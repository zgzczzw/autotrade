/**
 * K线图模块
 * 
 * 功能完整的专业级K线图组件，支持多种技术指标和交互功能
 * 
 * Usage:
 * ```tsx
 * import { KlineChartModule } from '@/components/kline-chart';
 * 
 * <KlineChartModule
 *   data={klineData}
 *   markers={trades}
 *   indicators={{ ma: true, macd: true, volume: true }}
 *   height={600}
 * />
 * ```
 */

export { KlineChartModule, KlineChartDialog } from './kline-chart-module';
export type {
  KlineData,
  TradeMarker,
  IndicatorsConfig,
  KlineChartModuleProps,
  TimePeriod,
} from './types';
