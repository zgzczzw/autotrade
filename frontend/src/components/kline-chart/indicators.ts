/**
 * K线图技术指标配置
 */

// MA指标配置
export const maIndicator = {
  name: 'MA',
  shortName: 'MA',
  calcParams: [5, 10, 20, 60],
  figures: [
    { key: 'ma5', title: 'MA5: ', type: 'line' as const },
    { key: 'ma10', title: 'MA10: ', type: 'line' as const },
    { key: 'ma20', title: 'MA20: ', type: 'line' as const },
    { key: 'ma60', title: 'MA60: ', type: 'line' as const },
  ],
  calc: (kLineDataList: any[], indicator: any) => {
    const params = indicator.calcParams || [5, 10, 20, 60];
    return kLineDataList.map((kLineData, i) => {
      const result: Record<string, number | undefined> = {};
      params.forEach((period: number) => {
        if (i >= period - 1) {
          let sum = 0;
          for (let j = 0; j < period; j++) {
            sum += kLineDataList[i - j].close;
          }
          result[`ma${period}`] = sum / period;
        } else {
          result[`ma${period}`] = undefined;
        }
      });
      return result;
    });
  },
};

// MACD指标配置
export const macdIndicator = {
  name: 'MACD',
  shortName: 'MACD',
  calcParams: [12, 26, 9],
  figures: [
    { key: 'dif', title: 'DIF: ', type: 'line' as const },
    { key: 'dea', title: 'DEA: ', type: 'line' as const },
    { key: 'macd', title: 'MACD: ', type: 'bar' as const },
  ],
  calc: (kLineDataList: any[], indicator: any) => {
    const params = indicator.calcParams || [12, 26, 9];
    const [fast, slow, signal] = params;
    const closes = kLineDataList.map((d: any) => d.close);
    
    const emaFast: number[] = [];
    const emaSlow: number[] = [];
    const dif: (number | undefined)[] = [];
    const dea: (number | undefined)[] = [];
    const macd: (number | undefined)[] = [];
    
    closes.forEach((close: number, i: number) => {
      if (i === 0) {
        emaFast.push(close);
        emaSlow.push(close);
      } else {
        const kFast = 2 / (fast + 1);
        const kSlow = 2 / (slow + 1);
        emaFast.push(close * kFast + emaFast[i - 1] * (1 - kFast));
        emaSlow.push(close * kSlow + emaSlow[i - 1] * (1 - kSlow));
      }
      dif.push(emaFast[i] - emaSlow[i]);
    });
    
    dif.forEach((d, i) => {
      if (i === 0) {
        dea.push(d);
      } else {
        const kSignal = 2 / (signal + 1);
        dea.push(d! * kSignal + dea[i - 1]! * (1 - kSignal));
      }
      macd.push((dif[i]! - dea[i]!) * 2);
    });
    
    return kLineDataList.map((_: any, i: number) => ({
      dif: dif[i],
      dea: dea[i],
      macd: macd[i],
    }));
  },
};

// KDJ指标配置
export const kdjIndicator = {
  name: 'KDJ',
  shortName: 'KDJ',
  calcParams: [9, 3, 3],
  figures: [
    { key: 'k', title: 'K: ', type: 'line' as const },
    { key: 'd', title: 'D: ', type: 'line' as const },
    { key: 'j', title: 'J: ', type: 'line' as const },
  ],
  calc: (kLineDataList: any[], indicator: any) => {
    const params = indicator.calcParams || [9, 3, 3];
    const [n, m1, m2] = params;
    const k: (number | undefined)[] = [];
    const d: (number | undefined)[] = [];
    const j: (number | undefined)[] = [];
    
    kLineDataList.forEach((data, i) => {
      if (i < n - 1) {
        k.push(undefined);
        d.push(undefined);
        j.push(undefined);
        return;
      }
      
      let low = data.low;
      let high = data.high;
      for (let idx = 0; idx < n; idx++) {
        low = Math.min(low, kLineDataList[i - idx].low);
        high = Math.max(high, kLineDataList[i - idx].high);
      }
      const rsv = high === low ? 50 : (data.close - low) / (high - low) * 100;
      
      if (i === n - 1) {
        k.push(50);
        d.push(50);
      } else {
        const prevK = k[i - 1] ?? 50;
        const prevD = d[i - 1] ?? 50;
        k.push(prevK * (m1 - 1) / m1 + rsv / m1);
        d.push(prevD * (m2 - 1) / m2 + k[i]! / m2);
      }
      j.push(3 * k[i]! - 2 * d[i]!);
    });
    
    return kLineDataList.map((_: any, i: number) => ({
      k: k[i],
      d: d[i],
      j: j[i],
    }));
  },
};

// RSI指标配置
export const rsiIndicator = {
  name: 'RSI',
  shortName: 'RSI',
  calcParams: [14],
  figures: [
    { key: 'rsi', title: 'RSI(14): ', type: 'line' as const },
  ],
  calc: (kLineDataList: any[], indicator: any) => {
    const params = indicator.calcParams || [14];
    const [period] = params;
    const rsi: (number | undefined)[] = [];
    let avgGain = 0;
    let avgLoss = 0;
    
    kLineDataList.forEach((data, i) => {
      if (i === 0) {
        rsi.push(undefined);
        return;
      }
      
      const change = data.close - kLineDataList[i - 1].close;
      const gain = change > 0 ? change : 0;
      const loss = change < 0 ? -change : 0;
      
      if (i < period) {
        avgGain += gain / period;
        avgLoss += loss / period;
        rsi.push(undefined);
      } else if (i === period) {
        avgGain = (avgGain * (period - 1) + gain) / period;
        avgLoss = (avgLoss * (period - 1) + loss) / period;
        const rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
        rsi.push(100 - 100 / (1 + rs));
      } else {
        avgGain = (avgGain * (period - 1) + gain) / period;
        avgLoss = (avgLoss * (period - 1) + loss) / period;
        const rs = avgLoss === 0 ? 100 : avgGain / avgLoss;
        rsi.push(100 - 100 / (1 + rs));
      }
    });
    
    return kLineDataList.map((_: any, i: number) => ({
      rsi: rsi[i],
    }));
  },
};

// BOLL指标配置
export const bollIndicator = {
  name: 'BOLL',
  shortName: 'BOLL',
  calcParams: [20, 2],
  figures: [
    { key: 'upper', title: 'UP: ', type: 'line' as const },
    { key: 'middle', title: 'MID: ', type: 'line' as const },
    { key: 'lower', title: 'LOW: ', type: 'line' as const },
  ],
  calc: (kLineDataList: any[], indicator: any) => {
    const params = indicator.calcParams || [20, 2];
    const [period, stdDev] = params;
    
    return kLineDataList.map((data, i) => {
      if (i < period - 1) {
        return { upper: undefined, middle: undefined, lower: undefined };
      }
      
      let sum = 0;
      for (let j = 0; j < period; j++) {
        sum += kLineDataList[i - j].close;
      }
      const middle = sum / period;
      
      let variance = 0;
      for (let j = 0; j < period; j++) {
        variance += Math.pow(kLineDataList[i - j].close - middle, 2);
      }
      const std = Math.sqrt(variance / period);
      
      return {
        upper: middle + stdDev * std,
        middle,
        lower: middle - stdDev * std,
      };
    });
  },
};

// 成交量指标
export const volumeIndicator = {
  name: 'VOL',
  shortName: 'VOL',
  figures: [
    { key: 'volume', title: 'V: ', type: 'bar' as const },
  ],
  calc: (kLineDataList: any[]) => {
    return kLineDataList.map((data: any) => ({
      volume: data.volume,
    }));
  },
};

// 获取启用的指标列表
export function getEnabledIndicators(config: {
  ma?: boolean | number[];
  macd?: boolean;
  kdj?: boolean;
  rsi?: boolean;
  boll?: boolean;
  volume?: boolean;
}) {
  const indicators: any[] = [];
  
  if (config.ma) {
    const periods = Array.isArray(config.ma) ? config.ma : [5, 10, 20, 60];
    indicators.push({
      ...maIndicator,
      calcParams: periods,
    });
  }
  
  if (config.boll !== false) {
    indicators.push(bollIndicator);
  }
  
  if (config.volume !== false) {
    indicators.push(volumeIndicator);
  }
  
  if (config.macd) {
    indicators.push(macdIndicator);
  }
  
  if (config.kdj) {
    indicators.push(kdjIndicator);
  }
  
  if (config.rsi) {
    indicators.push(rsiIndicator);
  }
  
  return indicators;
}
