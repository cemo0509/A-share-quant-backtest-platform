import axios from 'axios'
import type { BacktestMetrics } from '../stores'

const api = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api',
  timeout: 120000,
})

// ===== 自动重试：后端未就绪时（连接被拒绝）自动重试，避免一启动就报 ERR_CONNECTION_REFUSED =====
api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const config = error.config || {}
    config.__retryCount = config.__retryCount || 0
    // 仅在“连接失败 / 无响应”时重试（排除真正的业务 4xx/5xx）
    const isConnError =
      error.code === 'ERR_CONNECTION_REFUSED' ||
      error.code === 'ECONNREFUSED' ||
      error.code === 'ECONNABORTED' ||
      !error.response
    if (isConnError && config.__retryCount < 30) {
      config.__retryCount++
      // 指数退避：2s, 4s, 6s ... 最多约 30 次覆盖后端启动窗口
      const delay = Math.min(2000 * config.__retryCount, 8000)
      await new Promise((resolve) => setTimeout(resolve, delay))
      return api.request(config)
    }
    return Promise.reject(error)
  }
)

// ===== 策略 =====
export const getStrategies = () => api.get('/strategy/list')

// 自定义策略API
export const getCustomStrategyCode = (key: string) => api.get(`/strategy/custom/${key}/code`)
export const saveCustomStrategy = (key: string, code: string) => api.post('/strategy/custom/save', { key, code })
export const deleteCustomStrategy = (key: string) => api.delete(`/strategy/custom/${key}`)

// ===== 数据 =====
export const fetchData = (data: { symbol: string; start_date: string; end_date: string; period?: string }) =>
  api.post('/data/fetch', data)
export const getCache = () => api.get('/data/cache')
export const clearCache = (symbol?: string) => api.delete('/data/cache', { params: { symbol } })
export const clearStaleCache = (maxAgeDays = 30) =>
  api.delete('/data/cache/stale', { params: { max_age_days: maxAgeDays } })
export const getRealtimeQuotes = (symbols: string[]) => api.post('/data/realtime', { symbols })
export const getDataSource = () => api.get('/data/source')
export const setDataSource = (source: string) => api.post('/data/source', { source })

// ===== 回测 =====
export interface BacktestReq {
  strategy: string
  symbol: string
  start_date: string
  end_date: string
  params?: Record<string, number | string>
  cash?: number
  commission?: number
  slippage?: number
  period?: string
  /** 复权方式：qfq 前复权 / hfq 后复权 / '' 不复权 */
  adjust?: string
  // ---- 仓位管理（接入 core.position_sizer）----
  /** allin 满仓 / fixed 固定比例 / atr 风险仓位 / volatility 目标波动率 */
  position_sizing?: string
  /** 基础仓位百分比（allin/fixed/volatility 用） */
  position_percent?: number
  /** 仓位上限 0-1 */
  max_position?: number
  /** atr 模式单笔风险比例 */
  risk_percent?: number
  /** atr 模式 ATR 乘数 */
  atr_multiplier?: number
  /** volatility 模式目标年化波动率 */
  target_volatility?: number
}

/** 仓位管理模式选项（与后端 BacktestRequest 校验白名单一致） */
export const POSITION_SIZING_OPTIONS = [
  { value: 'allin', label: '满仓（默认）', desc: '用可用资金的指定百分比建仓' },
  { value: 'fixed', label: '固定比例', desc: '每次按固定百分比资金建仓' },
  { value: 'atr', label: 'ATR 风险仓位', desc: '单笔亏损不超过资金的风险比例' },
  { value: 'volatility', label: '目标波动率', desc: '波动越大仓位越小，反向调节' },
]

export interface BacktestResult {
  total_return: number
  annual_return?: number
  sharpe_ratio: number
  max_drawdown: number
  win_rate: number
  total_trades: number
  final_value?: number
  equity_curve?: Array<{date: string, value: number}>
  trades?: Array<{
    date: string
    type: 'buy' | 'sell'
    price: number
    size: number
    cash: number
    value: number
  }>
}

export const runBacktest = (data: BacktestReq) => api.post('/backtest/run', data)

// 自定义代码回测
export interface BacktestCodeReq {
  code: string
  symbol: string
  start_date: string
  end_date: string
  cash?: number
  commission?: number
  slippage?: number
  period?: string
}

export const runBacktestCode = (data: BacktestCodeReq) => api.post('/backtest/run_code', data)

// ===== 交易 =====
export const placeOrder = (data: { symbol: string; action: string; quantity: number; price: number }) =>
  api.post('/trading/order', data)
export const getAccount = () => api.get('/trading/account')
export const getPositions = () => api.get('/trading/positions')
export const getOrders = () => api.get('/trading/orders')
export const resetAccount = (initial_cash: number = 1000000) => 
  api.post('/trading/reset', { initial_cash })

// ===== 选股池 (v3.0) =====
export interface StockScanReq {
  strategy_type: string
  strategy_params?: Record<string, any>
  stock_range?: string
  custom_stocks?: string[]
  scan_date?: string
  start_date?: string
  end_date?: string
  max_stocks?: number
  prepare_first?: boolean
  prepare_only?: boolean
}
export const scanStocks = (data: StockScanReq) => api.post('/stock-scan', data)

// ===== 数据缓存（独立入口，扫描前批量下载 K 线到本地） =====
export interface DataPrepareReq {
  stock_range?: string
  custom_stocks?: string[]
  start_date: string
  end_date: string
  period?: string
  max_stocks?: number
}
export const prepareData = (data: DataPrepareReq) => api.post('/stock-scan/prepare', data)

// ===== 盘中实时监控 (可组合因子选股) =====
export interface MonitorStartReq {
  interval?: number
  period?: string
  min_amount?: number
  max_stocks?: number
  combine?: string
  factors?: Record<string, { enabled: boolean; params: Record<string, any> }>
  cci_threshold?: number
  zero_line_band?: number
}
export const startMonitor = (data: MonitorStartReq) => api.post('/monitor/start', data)
export const stopMonitor = () => api.post('/monitor/stop')
export const getMonitorStatus = () => api.get('/monitor/status')
export const getMonitorPool = () => api.get('/monitor/pool')
export const getMonitorFactorDefs = () => api.get('/monitor/factor-defs')
export const refineMonitorPool = (data: {
  symbols?: string[]; min_cci?: number; min_price?: number; max_price?: number; sector?: string
}) => api.post('/monitor/refine', data)

// 自选池 (v3.0)
export const getWatchlist = () => api.get('/watchlist')
export const addToWatchlist = (data: { symbol: string; name?: string; added_price?: number; notes?: string }) =>
  api.post('/watchlist', data)
export const removeFromWatchlist = (symbol: string) => api.delete(`/watchlist/${symbol}`)

// 股票详情 (v3.0)
export const getKline = (params: { symbol: string; start_date?: string; end_date?: string; period?: string; limit?: number; adjust?: string }) =>
  api.get('/stocks/kline', { params })
export const getIntraday = (symbol: string) => api.get('/stocks/intraday', { params: { symbol } })
export const getIndicators = (params: { symbol: string; period?: string; limit?: number; start_date?: string; end_date?: string }) =>
  api.get('/stocks/indicators', { params })
export const getSignals = (params: { symbol: string; strategy: string; start_date?: string; end_date?: string }) =>
  api.get('/stocks/signals', { params })

// ===== 参数优化 =====
export interface OptimizeRequest {
  strategy: string
  symbol: string
  start_date: string
  end_date: string
  param_grid: Record<string, number[]>
  cash?: number
  commission?: number
  slippage?: number
  metric?: string
}

export interface OptimizeResultItem {
  params: Record<string, number>
  metric_value: number
  total_return: number
  annual_return: number
  sharpe_ratio: number
  max_drawdown: number
  win_rate: number
  total_trades: number
  // F-01：数据源标识，real=真实行情 / mock=模拟行情（真实行情获取失败时降级）。
  // 优化结果若有任一项为 mock，则该「最优参数」不构成决策依据。
  data_source?: 'real' | 'mock' | string
}

export const runOptimize = (request: OptimizeRequest) => api.post('/optimize', request)
export const getOptimizeMetrics = () => api.get('/optimize/metrics')

// ===== 导出 =====
export const exportResultJson = async (result: any): Promise<void> => {
  const response = await api.post('/optimize/export/json', { result }, { responseType: 'blob' })
  const blob = new Blob([response.data], { type: 'application/json' })
  const url = window.URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `backtest_result_${new Date().toISOString().slice(0, 19).replace(/[:-]/g, '')}.json`
  a.click()
  window.URL.revokeObjectURL(url)
}

export const exportTradesCsv = async (trades: any[]): Promise<void> => {
  const response = await api.post('/optimize/export/csv', { trades }, { responseType: 'blob' })
  const blob = new Blob([response.data], { type: 'text/csv;charset=utf-8-sig' })
  const url = window.URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = `backtest_trades_${new Date().toISOString().slice(0, 19).replace(/[:-]/g, '')}.csv`
  a.click()
  window.URL.revokeObjectURL(url)
}

// ===== 可视化策略编辑器 (v4.0) =====
export interface VisualIndicatorTree {
  timeframes: Array<{ value: string; label: string }>
  operators: Array<{ value: string; label: string }>
  target_types: Array<{ value: string; label: string }>
  fuquan_types: Array<{ value: string; label: string }>
  scope_types: Array<{ value: string; label: string }>
  default_global: {
    timeframe: string
    fuquan: string
    scope: string
    exclude_st: boolean
    exclude_halt: boolean
    min_amount: number
  }
  default_conditions: Record<string, {
    line: string
    operator: string
    targetType: string
    targetValue?: number | null
    targetParam2?: number | null
    targetIndicator?: string | null
    note?: string
  }>
  groups: Array<{
    key: string
    label: string
    indicators: Array<{
      key: string
      name: string
      note: string
      lines: Array<{ value: string; label: string }>
      params: Array<{ name: string; label: string; default: any; min?: number; max?: number; type?: string }>
      operators: string[]
      target_types: string[]
    }>
  }>
}

export const getVisualIndicators = () => api.get('/visual/indicators')
export const saveVisualRule = (data: { key: string; name: string; description?: string; rule: any }) =>
  api.post('/visual/save', data)
export const loadVisualRule = (key: string) => api.get(`/visual/load/${key}`)
export const listVisualRules = () => api.get('/visual/list')
export const deleteVisualRule = (key: string) => api.delete(`/visual/${key}`)
// 智能推荐：预置策略 → 可视化默认规则映射
export interface VisualPreset {
  rule: { operator: 'AND' | 'OR'; items: any[] }
  name: string
  recommended_indicators: string[]
}
export interface VisualPresetsResponse {
  presets: Record<string, VisualPreset>
  names: Record<string, string>
}
export const getVisualPresets = () => api.get<{ data: VisualPresetsResponse }>('/visual/presets')

// ===== 回测历史（P0-9 持久化） =====
export interface BacktestHistoryItem {
  id: string
  created_at: string
  strategy_key: string
  strategy_name: string
  symbol: string
  start_date: string
  end_date: string
  period: string
  adjust: string
  position_sizing: string
  cash: number
  commission: number
  slippage: number
  data_source: string
  params: Record<string, any>
  metrics: Partial<BacktestMetrics>
}

export const listBacktestHistory = (limit = 100, symbol = '') =>
  api.get('/backtest/history', { params: { limit, symbol } })
export const getBacktestHistory = (runId: string) => api.get(`/backtest/history/${runId}`)
export const deleteBacktestHistory = (runId: string) => api.delete(`/backtest/history/${runId}`)
export const clearBacktestHistory = () => api.delete('/backtest/history')

// codegen：可视化规则 → Backtrader 代码（让编辑器形成「画完就能跑」的闭环）
export interface VisualCodegenResponse {
  code: string
  lines: number
  valid: boolean
  error?: string | null
}
export const codegenVisualRule = (data: {
  rule: any; name?: string; description?: string; exit_mode?: string
}) => api.post('/visual/codegen', data)

// 直接运行可视化策略回测（生成代码 → 动态加载 → 回测）
export const runVisualBacktest = (data: {
  rule: any
  name?: string
  description?: string
  exit_mode?: string
  symbol: string
  start_date: string
  end_date: string
  params?: Record<string, any>
  cash?: number
  commission?: number
  slippage?: number
  period?: string
  adjust?: string
}) => api.post('/visual/run', data)

// ===== 策略比较 =====
export interface CompareRequest {
  strategies: string[]
  symbol: string
  start_date: string
  end_date: string
  cash?: number
  commission?: number
  slippage?: number
  period?: string
}

export const compareStrategies = (request: CompareRequest) => api.post('/backtest/compare', request)

export default api
