// 前端条件自然语言渲染 + 条件选项构建（与后端 condition_renderer.py 对齐）

import type { ConditionLeaf } from './types'

function paramStr(params: Record<string, number> | undefined): string {
  if (!params) return ''
  const labelMap: Record<string, string> = {
    fast: '快线', slow: '慢线', signal: '信号',
    n: 'N', m1: 'M1', m2: 'M2', std: 'std',
    period: '周期', dev: '标准差', smooth_k: 'K平滑', smooth_d: 'D平滑',
    short: '短期', mid: '中期', long: '长期', p: '周期', k: 'K',
  }
  const parts: string[] = []
  for (const [k, v] of Object.entries(params)) {
    if (v == null) continue
    parts.push(`${labelMap[k] || k}${v}`)
  }
  return parts.length ? `（${parts.join(' ')}）` : ''
}

/** 把单个条件渲染成自然语言（前端等价实现） */
export function renderCondition(leaf: ConditionLeaf): string {
  const { indicator, line, operator, params, targetValue, targetParam2, targetIndicator } = leaf
  const p = paramStr(params)
  const tInd = targetIndicator

  if (indicator === 'macd' || indicator === 'macd_cross') {
    if (line === 'gold' || (operator === 'equal' && targetValue === 1 && (line === 'gold' || line === 'dif_gold' || line === '' || line == null))) return `MACD 金叉（DIF 上穿 DEA）${p}`.trim()
    if (line === 'death' || line === 'dif_death' || (operator === 'equal' && targetValue === -1)) return `MACD 死叉（DIF 下穿 DEA）${p}`.trim()
    if (operator === 'greater') return `DIF 大于 ${targetValue}${p}`.trim()
    if (operator === 'less') return `DIF 小于 ${targetValue}${p}`.trim()
    if (operator === 'between') {
      const w = Math.max(Math.abs(targetValue || 0), Math.abs(targetParam2 || 0))
      return `DIF 在零轴附近（带宽 ${w}）${p}`.trim()
    }
    return `MACD 条件${p}`.trim()
  }
  if (indicator === 'ma' || indicator === 'ema') {
    const up = tInd ? `${indicator.toUpperCase()} 上穿 ${tInd.toUpperCase()}` : 'MA 上穿'
    const down = tInd ? `${indicator.toUpperCase()} 下穿 ${tInd.toUpperCase()}` : 'MA 下穿'
    if (operator === 'cross_up') return `${up}${p}`.trim()
    if (operator === 'cross_down') return `${down}${p}`.trim()
    if (operator === 'greater') return tInd ? `${indicator.toUpperCase()} 大于 ${tInd.toUpperCase()}${p}`.trim() : `${indicator.toUpperCase()} 大于 ${targetValue}${p}`.trim()
    if (operator === 'less') return `${indicator.toUpperCase()} 小于 ${targetValue}${p}`.trim()
    return `MA 条件${p}`.trim()
  }
  if (indicator === 'ma_arrangement') {
    if (line === 'bull') return `均线多头排列（MA5>MA10>MA20）${p}`.trim()
    if (line === 'bear') return `均线空头排列（MA5<MA10<MA20）${p}`.trim()
    return `均线排列${p}`.trim()
  }
  if (indicator === 'kdj' || indicator === 'kdj_bull') {
    const ll: Record<string, string> = { gold: 'K 上穿 D（金叉）', death: 'K 下穿 D（死叉）', k: 'K', d: 'D', j: 'J' }
    const label = ll[line] || line
    if (operator === 'equal' && targetValue === 1) return `KDJ 金叉（K 上穿 D）${p}`.trim()
    if (operator === 'equal' && targetValue === -1) return `KDJ 死叉（K 下穿 D）${p}`.trim()
    if (operator === 'greater') return `KDJ ${label} 大于 ${targetValue}${p}`.trim()
    if (operator === 'less') return `KDJ ${label} 小于 ${targetValue}${p}`.trim()
    return `KDJ 条件${p}`.trim()
  }
  if (indicator === 'rsi') {
    if (operator === 'between') return `RSI 介于 ${targetValue} ~ ${targetParam2}${p}`.trim()
    if (operator === 'cross_up') return `RSI 上穿 ${targetValue}${p}`.trim()
    if (operator === 'cross_down') return `RSI 下穿 ${targetValue}${p}`.trim()
    if (operator === 'greater') return `RSI 大于 ${targetValue}${p}`.trim()
    if (operator === 'less') return `RSI 小于 ${targetValue}${p}`.trim()
    return `RSI 条件${p}`.trim()
  }
  if (indicator === 'cci') {
    if (operator === 'between') return `CCI 介于 ${targetValue} ~ ${targetParam2}${p}`.trim()
    if (operator === 'greater') return `CCI 大于 ${targetValue}${p}`.trim()
    if (operator === 'less') return `CCI 小于 ${targetValue}${p}`.trim()
    if (operator === 'cross_up') return `CCI 上穿 ${targetValue}${p}`.trim()
    if (operator === 'cross_down') return `CCI 下穿 ${targetValue}${p}`.trim()
    return `CCI 条件${p}`.trim()
  }
  if (indicator === 'boll') {
    const t = { boll_upper: '上轨', boll_mid: '中轨', boll_lower: '下轨' }[tInd || line] || tInd || line
    if (operator === 'cross_up') return `价格 上穿 BOLL${t}${p}`.trim()
    if (operator === 'cross_down') return `价格 下穿 BOLL${t}${p}`.trim()
    if (operator === 'greater') return `价格 大于 BOLL${t}${p}`.trim()
    if (operator === 'less') return `价格 小于 BOLL${t}${p}`.trim()
    return `BOLL 条件${p}`.trim()
  }
  if (indicator === 'vol' || indicator === 'vol_ratio') {
    if (operator === 'greater') {
      if (targetValue && targetValue >= 1) return `成交量 放量（>${targetValue}倍均量）${p}`.trim()
      return `成交量 大于 ${targetValue} 日均量${p}`.trim()
    }
    if (operator === 'less') return `成交量 小于 ${targetValue} 日均量${p}`.trim()
    return `成交量 条件${p}`.trim()
  }
  if (indicator === 'amt') {
    if (operator === 'greater') return `成交额 大于 ${targetValue} 元`.trim()
    if (operator === 'less') return `成交额 小于 ${targetValue} 元`.trim()
    return '成交额 条件'
  }
  if (indicator === 'price') {
    if (operator === 'cross_up') return '价格 上穿'
    if (operator === 'cross_down') return '价格 下穿'
    if (operator === 'greater') return `收盘价 大于 ${targetValue}`
    if (operator === 'less') return `收盘价 小于 ${targetValue}`
    return '价格 条件'
  }
  return `${indicator}/${line} ${operator} ${targetValue ?? ''}`.trim()
}

/**
 * 为一个指标构建"自然语言条件选项"列表（对标方案 4.3 表）。
 * 每个选项是一个完整条件（line/operator/targetType/targetValue/targetParam2/targetIndicator），
 * 用户选择后直接套用，无需再理解"等于/常数/1"。
 */
export function buildConditionOptions(indicatorDef: any): any[] {
  if (!indicatorDef) return []
  const key = indicatorDef.key
  const opts: any[] = []

  const push = (label: string, patch: Partial<ConditionLeaf>) => {
    opts.push({ label, value: JSON.stringify(patch), patch })
  }

  if (key === 'macd' || key === 'macd_cross') {
    push('DIF 上穿 DEA（金叉）', { line: 'gold', operator: 'equal', targetType: 'value', targetValue: 1, targetParam2: undefined, targetIndicator: undefined })
    push('DIF 下穿 DEA（死叉）', { line: 'death', operator: 'equal', targetType: 'value', targetValue: -1, targetParam2: undefined, targetIndicator: undefined })
    push('DIF 大于 [N]', { line: 'dif', operator: 'greater', targetType: 'value', targetValue: 0, targetParam2: undefined, targetIndicator: undefined })
    push('DIF 小于 [N]', { line: 'dif', operator: 'less', targetType: 'value', targetValue: 0, targetParam2: undefined, targetIndicator: undefined })
    push('DIF 在零轴附近（带宽 N）', { line: 'dif', operator: 'between', targetType: 'value', targetValue: 0, targetParam2: 0, targetIndicator: undefined })
  } else if (key === 'ma' || key === 'ema') {
    push('MA[N] 上穿 MA[M]', { line: 'cross', operator: 'cross_up', targetType: 'indicator', targetIndicator: 'ma10' })
    push('MA[N] 下穿 MA[M]', { line: 'cross', operator: 'cross_down', targetType: 'indicator', targetIndicator: 'ma10' })
    push('MA[N] 大于 MA[M]', { line: 'ma', operator: 'greater', targetType: 'indicator', targetIndicator: 'ma10' })
    push('MA[N] 大于 [V]', { line: 'ma', operator: 'greater', targetType: 'value', targetValue: 0 })
  } else if (key === 'ma_arrangement') {
    push('均线多头排列（MA5>MA10>MA20）', { line: 'bull', operator: 'greater', targetType: 'value' })
    push('均线空头排列（MA5<MA10<MA20）', { line: 'bear', operator: 'less', targetType: 'value' })
  } else if (key === 'kdj' || key === 'kdj_bull') {
    push('K 上穿 D（金叉）', { line: 'gold', operator: 'equal', targetType: 'value', targetValue: 1 })
    push('K 下穿 D（死叉）', { line: 'death', operator: 'equal', targetType: 'value', targetValue: -1 })
    push('K 大于 [N]', { line: 'k', operator: 'greater', targetType: 'value', targetValue: 50 })
    push('D 大于 [N]', { line: 'd', operator: 'greater', targetType: 'value', targetValue: 50 })
    push('J 大于 [N]', { line: 'j', operator: 'greater', targetType: 'value', targetValue: 80 })
  } else if (key === 'rsi') {
    push('RSI 上穿 [N]', { line: 'rsi', operator: 'cross_up', targetType: 'value', targetValue: 30 })
    push('RSI 下穿 [N]', { line: 'rsi', operator: 'cross_down', targetType: 'value', targetValue: 70 })
    push('RSI 大于 [N]', { line: 'rsi', operator: 'greater', targetType: 'value', targetValue: 70 })
    push('RSI 小于 [N]', { line: 'rsi', operator: 'less', targetType: 'value', targetValue: 30 })
    push('RSI 介于 [下限]~[上限]', { line: 'rsi', operator: 'between', targetType: 'value', targetValue: 30, targetParam2: 70 })
  } else if (key === 'cci') {
    push('CCI 大于 [N]', { line: 'cci', operator: 'greater', targetType: 'value', targetValue: 100 })
    push('CCI 小于 [N]', { line: 'cci', operator: 'less', targetType: 'value', targetValue: -100 })
    push('CCI 上穿 [N]', { line: 'cci', operator: 'cross_up', targetType: 'value', targetValue: 0 })
    push('CCI 下穿 [N]', { line: 'cci', operator: 'cross_down', targetType: 'value', targetValue: 0 })
    push('CCI 介于 [下限]~[上限]', { line: 'cci', operator: 'between', targetType: 'value', targetValue: -100, targetParam2: 100 })
  } else if (key === 'boll') {
    push('价格 上穿 上轨', { line: 'price_upper', operator: 'cross_up', targetType: 'indicator', targetIndicator: 'boll_upper' })
    push('价格 下穿 下轨', { line: 'price_lower', operator: 'cross_down', targetType: 'indicator', targetIndicator: 'boll_lower' })
    push('价格 上穿 中轨', { line: 'price_mid', operator: 'cross_up', targetType: 'indicator', targetIndicator: 'boll_mid' })
  } else if (key === 'vol' || key === 'vol_ratio') {
    push('成交量 大于 [N] 日均量', { line: 'vol', operator: 'greater', targetType: 'value', targetValue: 5 })
    push('成交量 放量（>N倍均量）', { line: 'vol_ratio', operator: 'greater', targetType: 'value', targetValue: 2 })
  } else {
    // 兜底：使用指标自带 lines + operators 组合
    for (const l of indicatorDef.lines || []) {
      for (const op of indicatorDef.operators || ['greater']) {
        push(`${indicatorDef.name} ${l.label} ${op}`, { line: l.value, operator: op, targetType: 'value', targetValue: 0 })
      }
    }
  }
  return opts
}
