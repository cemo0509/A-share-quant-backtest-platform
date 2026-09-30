import { Col, InputNumber, Row, Select, Space, Switch, Typography } from 'antd'
import type { StrategyParam, ParamValues } from '../types'

const { Text } = Typography

interface Props {
  params: StrategyParam[]
  values: ParamValues
  onChange: (next: ParamValues) => void
  /** 每个参数占用的栅格宽度（24 栅格），默认 6 即一行 4 个 */
  span?: number
}

/** 用参数定义里的 default 初始化一份可编辑值。
 *
 * 数组必须拷贝：直接引用会让用户的编辑改到策略定义本身，
 * 切换策略再切回来时会看到被污染的值。
 */
export function initParamValues(params: StrategyParam[]): ParamValues {
  const v: ParamValues = {}
  for (const p of params || []) {
    v[p.name] = Array.isArray(p.default) ? [...p.default] : p.default
  }
  return v
}

function formatDefault(d: any): string {
  if (Array.isArray(d)) return `[${d.join(', ')}]`
  if (typeof d === 'boolean') return d ? '开' : '关'
  return String(d)
}

export default function StrategyParamsForm({ params, values, onChange, span = 6 }: Props) {
  const setVal = (name: string, v: any) => onChange({ ...values, [name]: v })

  const renderList = (p: StrategyParam) => {
    const arr: number[] = Array.isArray(values[p.name]) ? values[p.name] : []
    const sum = arr.reduce((a, b) => a + (Number(b) || 0), 0)
    return (
      <Space direction="vertical" size={4} style={{ width: '100%' }}>
        <Space size={6} wrap>
          {arr.map((n, i) => (
            <InputNumber
              key={i}
              size="small"
              style={{ width: 78 }}
              // 因子权重按「第 i 个因子」标注，避免用户不知道哪个框对应哪个因子
              addonBefore={`#${i + 1}`}
              value={n}
              min={0}
              max={1}
              step={0.05}
              onChange={(v) => {
                const next = [...arr]
                next[i] = v ?? 0
                setVal(p.name, next)
              }}
            />
          ))}
        </Space>
        <Text type="secondary" style={{ fontSize: 12 }}>
          共 {arr.length} 项，当前合计 {sum.toFixed(2)}（建议合计为 1）
        </Text>
      </Space>
    )
  }

  const renderInput = (p: StrategyParam) => {
    const val = values[p.name]

    if (p.type === 'bool') {
      return <Switch checked={!!val} onChange={(c) => setVal(p.name, c)} />
    }

    if (p.type === 'select') {
      return (
        <Select
          style={{ width: '100%' }}
          value={val}
          onChange={(v) => setVal(p.name, v)}
          options={(p.options || []).map((o) => ({ value: o, label: o }))}
        />
      )
    }

    if (p.type === 'list') {
      return renderList(p)
    }

    // int / float 及未声明类型的兜底：数字输入，带 min/max 约束
    return (
      <InputNumber
        style={{ width: '100%' }}
        value={typeof val === 'number' ? val : undefined}
        min={p.min}
        max={p.max}
        step={p.step ?? (p.type === 'float' ? 0.1 : 1)}
        onChange={(v) => setVal(p.name, v)}
      />
    )
  }

  if (!params || params.length === 0) {
    return <Text type="secondary">该策略没有可配置参数</Text>
  }

  return (
    <Row gutter={[16, 8]}>
      {params.map((p) => (
        <Col span={span} key={p.name}>
          <div style={{ marginBottom: 4, fontSize: 13 }}>
            {p.label}
            <Text type="secondary" style={{ fontSize: 12, marginLeft: 6 }}>
              （默认：{formatDefault(p.default)}）
            </Text>
          </div>
          {renderInput(p)}
        </Col>
      ))}
    </Row>
  )
}
