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
  /** preset=预置 / custom=自定义(Python 或可视化) / variant=参数化变体 */
  type?: string
  params: StrategyParam[]
  /** 仅参数化变体有：它所基于的预置策略 key */
  base_key?: string
}

/** 策略参数定义 */
export interface StrategyParam {
  name: string
  label: string
  // 各类型默认值形态不同：int/float=数字、bool=布尔、select=字符串、list=数组
  default: any
  min?: number
  max?: number
  step?: number
  type: string  // 'int' | 'float' | 'bool' | 'select' | 'list'
  options?: string[]
}

/** 策略参数的可编辑值集合（键为参数名） */
export type ParamValues = Record<string, any>
