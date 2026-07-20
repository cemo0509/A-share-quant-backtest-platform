import { InputNumber, Typography, Empty, Collapse, theme } from 'antd'
import type { ConditionNode, ConditionLeaf } from './types'
import { collectLeaves } from './types'

interface Props {
  groups: any[]
  rule: { items: ConditionNode[] }
  /** 按指标参数更新：传入指标 key 与新参数，父级负责同步该指标下所有叶子（按 id 递归）。 */
  onChangeParams: (indicatorKey: string, params: Record<string, number>) => void
}

const { Text } = Typography

/** 按 indicator 聚合（去重），用于参数面板分组显示 */
function groupByIndicator(leaves: ConditionLeaf[]) {
  const map = new Map<string, ConditionLeaf[]>()
  for (const leaf of leaves) {
    const k = leaf.indicator
    if (!map.has(k)) map.set(k, [])
    map.get(k)!.push(leaf)
  }
  return map
}

export default function ParameterPanel({ groups, rule, onChangeParams }: Props) {
  const { token } = theme.useToken()
  const allIndicators = groups.flatMap((g: any) => g.indicators)
  const leaves = collectLeaves(rule.items || [])
  const byIndicator = groupByIndicator(leaves)

  if (byIndicator.size === 0) {
    return (
      <div style={{ padding: 12 }}>
        <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="尚未选择指标" />
      </div>
    )
  }

  const items = Array.from(byIndicator.entries()).map(([indKey, groupLeaves]) => {
    const def = allIndicators.find((i: any) => i.key === indKey)
    const first = groupLeaves[0]
    const params = def?.params || []
    const paramBody = params.length > 0 ? (
      <div style={{ padding: '8px 4px' }}>
        {params.map((p: any) => (
          <span key={p.name} style={{ marginRight: 12, display: 'inline-block', marginBottom: 6 }}>
            <Text style={{ fontSize: 12, marginRight: 4 }}>{p.label}</Text>
            <InputNumber
              size="small"
              style={{ width: 70 }}
              value={first.params?.[p.name]}
              min={p.min}
              max={p.max}
              onChange={(v) => {
                // 只传增量 patch，父级基于 prev 合并，避免快速连改丢参（第四轮加固）
                onChangeParams(indKey, { [p.name]: v ?? p.default })
              }}
            />
          </span>
        ))}
      </div>
    ) : (
      <div style={{ padding: '8px 4px', fontSize: 12, color: token.colorTextTertiary }}>该指标无参数</div>
    )

    return {
      key: indKey,
      label: def?.name || indKey,
      children: paramBody,
    }
  })

  return (
    <div style={{ padding: 12 }}>
      <Text strong>参数设置</Text>
      <div style={{ marginTop: 8 }}>
        <Collapse
          size="small"
          defaultActiveKey={Array.from(byIndicator.keys())}
          items={items}
          style={{ background: token.colorBgContainer }}
        />
      </div>
    </div>
  )
}
