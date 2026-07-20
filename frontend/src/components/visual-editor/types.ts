// 可视化策略编辑器 —— 数据结构与工具

/** 逻辑关系（组合之间） */
export type LogicOperator = 'AND' | 'OR'

/** 单个条件（叶子节点） */
export interface ConditionLeaf {
  id: string
  type: 'condition'
  indicator: string // 指标 key
  line: string // 指标线 value
  params: Record<string, number> // 指标参数值
  timeframe: string // 分析周期 value
  operator: string // 逻辑关系 value
  targetType: 'value' | 'price' | 'indicator'
  targetValue?: number // targetType=value 时
  targetIndicator?: string // targetType=indicator 时
  targetLine?: string
  targetTimeframe?: string
  targetParam2?: number // between 时的上限
}

/** 组合（可嵌套） */
export interface ConditionGroup {
  id: string
  type: 'group'
  operator: LogicOperator // AND / OR
  items: ConditionNode[]
}

export type ConditionNode = ConditionLeaf | ConditionGroup

/** 全局设置（策略级，对标东财顶部栏；彻底改造后从各条件抽取到顶层） */
export interface VisualGlobal {
  timeframe: string // 分析周期 value（全局唯一）
  fuquan: string // 复权方式：qfq/hfq/none
  scope: string // 选股范围：all/hs300/...
  exclude_st: boolean // 剔除ST
  exclude_halt: boolean // 剔除停牌
  min_amount: number // 最小成交额（亿元）
}

/** 整条可视化规则 */
export interface VisualRule {
  operator: LogicOperator
  items: ConditionNode[]
  global?: VisualGlobal // 全局设置（可选，旧数据无此字段时取默认）
}

export function newId(): string {
  return 'n_' + Math.random().toString(36).slice(2, 9)
}

/** 创建一个默认条件（引用某个指标），按需填默认值 */
export function createLeaf(indicatorDef: any): ConditionLeaf {
  const params: Record<string, number> = {}
  for (const p of indicatorDef?.params || []) {
    params[p.name] = p.default
  }
  return {
    id: newId(),
    type: 'condition',
    indicator: indicatorDef?.key || '',
    line: indicatorDef?.lines?.[0]?.value || '',
    params,
    timeframe: 'daily',
    operator: indicatorDef?.operators?.[0] || 'greater',
    targetType: 'value',
    targetValue: 0,
  }
}

export function createGroup(operator: LogicOperator = 'AND'): ConditionGroup {
  return { id: newId(), type: 'group', operator, items: [] }
}

/** 按 id 递归更新某个节点（叶子或组），返回新树（不可变更新）。 */
export function updateNodeById(
  items: ConditionNode[],
  id: string,
  updater: (node: ConditionNode) => ConditionNode,
): ConditionNode[] {
  return items.map((node) => {
    if (node.id === id) return updater(node)
    if (node.type === 'group') {
      return { ...node, items: updateNodeById(node.items, id, updater) }
    }
    return node
  })
}

/** 收集树中所有叶子条件（带 id），用于参数面板聚合。 */
export function collectLeaves(items: ConditionNode[], acc: ConditionLeaf[] = []): ConditionLeaf[] {
  for (const node of items) {
    if (node.type === 'condition') acc.push(node)
    else if (node.type === 'group') collectLeaves(node.items, acc)
  }
  return acc
}

/** 深拷贝节点（避免直接改 state） */
export function cloneNode(node: ConditionNode): ConditionNode {
  return JSON.parse(JSON.stringify(node))
}

/** 把预置规则（来自后端 /presets）转换为带新 id 的本地规则树。
 *  深拷贝 + 递归重生成 id，避免与当前编辑区已有节点 id 冲突。 */
export function applyPreset(preset: VisualRule): VisualRule {
  const reId = (node: ConditionNode): ConditionNode => {
    if (node.type === 'group') {
      return {
        ...node,
        id: newId(),
        items: node.items.map(reId),
      }
    }
    return { ...node, id: newId() }
  }
  return {
    operator: preset.operator || 'AND',
    items: (preset.items || []).map(reId),
  }
}
