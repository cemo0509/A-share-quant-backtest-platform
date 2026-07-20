import { Card, Select, InputNumber, Button, Space, Typography, Tooltip, theme } from 'antd'
import { DeleteOutlined, CopyOutlined } from '@ant-design/icons'
import type { ConditionLeaf } from './types'
import { buildConditionOptions } from './conditionText'

interface Props {
  leaf: ConditionLeaf
  indicatorDef: any
  groups?: any[]
  onChange: (next: ConditionLeaf) => void
  onDelete: () => void
  onDuplicate: () => void
}

const { Text } = Typography

/** 动态生成"对照指标"下拉选项：遍历指标树，用每个指标的 lines 作为对照目标（发现 #6 去硬编码）。 */
function targetIndicatorOptions(groups?: any[]): { value: string; label: string }[] {
  const opts: { value: string; label: string }[] = []
  const seen = new Set<string>()
  const push = (value: string, label: string) => {
    if (seen.has(value)) return
    seen.add(value)
    opts.push({ value, label })
  }
  // 兼容旧数据中硬编码的几种
  push('ma5', 'MA5'); push('ma10', 'MA10'); push('ma20', 'MA20')
  push('boll_upper', 'BOLL 上轨'); push('boll_mid', 'BOLL 中轨'); push('boll_lower', 'BOLL 下轨')
  for (const g of groups || []) {
    for (const ind of g.indicators || []) {
      for (const ln of ind.lines || []) {
        const v = ln.value as string
        push(v, `${ind.name}·${ln.label || v}`)
      }
    }
  }
  return opts
}

export default function ConditionEditPanel({
  leaf, indicatorDef, groups, onChange, onDelete, onDuplicate,
}: Props) {
  const { token } = theme.useToken()
  if (!indicatorDef) {
    return <Card size="small" style={{ borderColor: token.colorError }}>未知指标: {leaf.indicator}</Card>
  }

  const update = (patch: Partial<ConditionLeaf>) => onChange({ ...leaf, ...patch })
  const condOptions = buildConditionOptions(indicatorDef)

  // 当前选中条件选项（根据 leaf 的 line/operator/targetValue 反查）
  const currentPatch = {
    line: leaf.line,
    operator: leaf.operator,
    targetType: leaf.targetType,
    targetValue: leaf.targetValue,
    targetParam2: leaf.targetParam2,
    targetIndicator: leaf.targetIndicator,
  }
  const currentValue = JSON.stringify(currentPatch)

  const handleCondChange = (val: string) => {
    const patch = JSON.parse(val)
    // 先清空所有目标相关字段，避免切换条件后残留旧的 targetIndicator/targetParam2 等脏字段
    onChange({
      ...leaf,
      line: patch.line,
      operator: patch.operator,
      targetType: patch.targetType ?? 'value',
      targetValue: patch.targetValue ?? undefined,
      targetParam2: patch.targetParam2 ?? undefined,
      targetIndicator: patch.targetIndicator ?? undefined,
      targetLine: undefined,
      targetTimeframe: undefined,
    })
  }

  // 是否需要在条件选项外再暴露自由 N 输入（大于/小于/零轴带宽/放量倍数等）
  const needTargetNumber =
    leaf.operator === 'greater' || leaf.operator === 'less' ||
    leaf.operator === 'between' || leaf.operator === 'cross_up' || leaf.operator === 'cross_down'

  return (
    <Card
      size="small"
      style={{ marginBottom: 8, background: token.colorBgElevated }}
      bodyStyle={{ padding: 12 }}
      extra={
        <Space size={4}>
          <Tooltip title="复制"><Button type="text" size="small" icon={<CopyOutlined />} onClick={onDuplicate} /></Tooltip>
          <Tooltip title="删除"><Button type="text" size="small" danger icon={<DeleteOutlined />} onClick={onDelete} /></Tooltip>
        </Space>
      }
    >
      <Space direction="vertical" style={{ width: '100%' }} size={8}>
        <Space wrap>
          <Text style={{ fontSize: 12, color: token.colorTextSecondary }}>指标</Text>
          <Text strong style={{ fontSize: 13 }}>{indicatorDef.name}</Text>
        </Space>

        <Space wrap>
          <Text style={{ fontSize: 12, color: token.colorTextSecondary }}>条件</Text>
          <Select
            size="small"
            style={{ width: 240 }}
            value={condOptions.some((o) => o.value === currentValue) ? currentValue : undefined}
            placeholder="选择条件…"
            options={condOptions}
            onChange={handleCondChange}
          />
        </Space>

        {needTargetNumber && leaf.targetType === 'value' && (
          <Space wrap>
            <Text style={{ fontSize: 12, color: token.colorTextSecondary }}>数值 N</Text>
            {leaf.operator === 'between' ? (
              <Space.Compact>
                <InputNumber size="small" style={{ width: 70 }} value={leaf.targetValue} placeholder="下限" onChange={(v) => update({ targetValue: v ?? undefined })} />
                <InputNumber size="small" style={{ width: 70 }} value={leaf.targetParam2} placeholder="上限" onChange={(v) => update({ targetParam2: v ?? undefined })} />
              </Space.Compact>
            ) : (
              <InputNumber size="small" style={{ width: 100 }} value={leaf.targetValue} onChange={(v) => update({ targetValue: v ?? 0 })} />
            )}
          </Space>
        )}

        {leaf.targetType === 'indicator' && (
          <Space wrap>
            <Text style={{ fontSize: 12, color: token.colorTextSecondary }}>对照指标</Text>
            <Select
              size="small"
              style={{ width: 150 }}
              value={leaf.targetIndicator}
              options={targetIndicatorOptions(groups)}
              onChange={(v) => update({ targetIndicator: v })}
            />
          </Space>
        )}
      </Space>
    </Card>
  )
}
