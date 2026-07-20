// 向后兼容：从统一 API 模块重新导出所有接口
// 新代码请直接从 '../api' 导入
export {
  getStrategies,
  getCustomStrategyCode,
  saveCustomStrategy,
  deleteCustomStrategy,
  runBacktest,
  runBacktestCode,
  getRealtimeQuotes,
  runOptimize,
  getOptimizeMetrics,
  exportResultJson,
  exportTradesCsv,
  compareStrategies,
} from '../api'

export type {
  BacktestResult,
  OptimizeResultItem,
  OptimizeRequest,
  CompareRequest,
  BacktestReq,
  BacktestCodeReq,
  StockScanReq,
} from '../api'

export { default } from '../api'
