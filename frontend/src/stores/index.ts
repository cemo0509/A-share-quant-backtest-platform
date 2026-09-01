import { create } from 'zustand'

export interface BacktestMetrics {
  total_return: number
  annual_return: number
  max_drawdown: number
  /** 夏普比率（已年化）。数据不足时为 null，前端显示「—」 */
  sharpe_ratio: number | null
  win_rate: number
  profit_loss_ratio: number
  total_trades: number
  win_trades: number
  loss_trades: number
  // ---- 扩展风险指标（Q-08）：数据不足时为 null ----
  /** 年化波动率 % */
  volatility?: number | null
  /** 索提诺比率（只惩罚下行波动） */
  sortino_ratio?: number | null
  /** 卡玛比率（年化收益 / 最大回撤） */
  calmar_ratio?: number | null
  /** 最长回撤修复期（交易日） */
  max_drawdown_days?: number | null
  /** 年化交易次数（换手频率） */
  trades_per_year?: number | null
}

export interface TradeRecord {
  date: string
  action: string
  price: number
  size: number
  pnl?: number
}

/** 单条基准（买入持有 / 沪深300） */
export interface BenchmarkItem {
  name: string
  key: string
  total_return: number
  annual_return: number
  max_drawdown: number
  shares: number
  entry_price: number
  exit_price: number
  equity_curve?: Array<{ date: string; value: number }>
}

/** 基准对比结果（P0-10） */
export interface Benchmarks {
  /** 同一标的买入持有，数据不足时为 null */
  buy_hold: BenchmarkItem | null
  /** 沪深300 同期，网络不可用时为 null */
  hs300: BenchmarkItem | null
  /** 策略 − 买入持有（百分点） */
  excess_vs_buy_hold: number | null
  /** 策略 − 沪深300（百分点） */
  excess_vs_hs300: number | null
}

export interface EquityPoint {
  date: string
  value: number
}

export interface KLineBar {
  date: string
  open: number
  high: number
  low: number
  close: number
  volume: number
}

export interface BacktestResultData {
  metrics: BacktestMetrics
  equity_curve: EquityPoint[]
  trades: TradeRecord[]
  kline: KLineBar[]
  start_cash: number
  end_cash: number
  data_source?: 'real' | 'mock'
  /** 基准对比（P0-10）：买入持有 + 沪深300 + 超额收益 */
  benchmarks?: Benchmarks
  /** A 股规则防线计数（Q-07）：>0 说明策略试图违规交易被拦截 */
  constraints?: {
    t1_sell_blocked: number
    short_sell_blocked: number
  }
}

// 主题模式：'dark' | 'light' | 'system'（跟随系统）。持久化到 localStorage
export type ThemeMode = 'dark' | 'light' | 'system'

// 读取系统当前明暗（prefers-color-scheme），用于 mode==='system' 时决定实际渲染主题
export function getSystemDark(): boolean {
  if (typeof window === 'undefined' || !window.matchMedia) return true
  return window.matchMedia('(prefers-color-scheme: dark)').matches
}

// 根据 mode 解析出实际渲染用的明暗。'system' 时取系统设置
export function resolveDark(mode: ThemeMode): boolean {
  if (mode === 'system') return getSystemDark()
  return mode === 'dark'
}

interface AppState {
  result: BacktestResultData | null
  loading: boolean
  mode: ThemeMode
  setResult: (r: BacktestResultData | null) => void
  setLoading: (b: boolean) => void
  setMode: (m: ThemeMode) => void
}

const STORAGE_KEY = 'app-theme-mode'
const validModes: ThemeMode[] = ['dark', 'light', 'system']
const initialMode: ThemeMode =
  (typeof localStorage !== 'undefined'
    ? (localStorage.getItem(STORAGE_KEY) as ThemeMode)
    : null) || 'dark'
const safeInitialMode: ThemeMode = validModes.includes(initialMode) ? initialMode : 'dark'

export const useStore = create<AppState>((set) => ({
  result: null,
  loading: false,
  mode: safeInitialMode,
  setResult: (result) => set({ result }),
  setLoading: (loading) => set({ loading }),
  setMode: (m) => {
    try { localStorage.setItem(STORAGE_KEY, m) } catch { /* 忽略存储异常 */ }
    set({ mode: m })
  },
}))

// 监听系统主题变化：当 mode==='system' 时实时同步，并触发图表重建
if (typeof window !== 'undefined' && window.matchMedia) {
  const mql = window.matchMedia('(prefers-color-scheme: dark)')
  const onChange = () => {
    if (useStore.getState().mode === 'system') {
      // 触发一次无意义的 set 以通知订阅者（mode 值未变但解析结果变了）
      useStore.setState({ mode: 'system' })
    }
  }
  if (mql.addEventListener) mql.addEventListener('change', onChange)
  else if (mql.addListener) mql.addListener(onChange)
}
