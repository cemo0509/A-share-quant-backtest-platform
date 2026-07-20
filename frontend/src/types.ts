/** 共享类型定义模块。
 *
 * 避免 StrategyItem 等接口在多个页面文件中重复定义。
 */

/** 策略基本信息（从后端 /api/strategy/list 返回） */
export interface StrategyItem {
  key: string
  name: string
  description: string
  category?: string
  type?: string
  params: StrategyParam[]
}

/** 策略参数定义 */
export interface StrategyParam {
  name: string
  label: string
  default: number
  min?: number
  max?: number
  type: string  // 'int' | 'float' | 'bool' | 'select'
  options?: string[]
}
