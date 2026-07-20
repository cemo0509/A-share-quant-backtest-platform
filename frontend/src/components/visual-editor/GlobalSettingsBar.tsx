import { Space, Select, Checkbox, InputNumber, Typography, theme } from 'antd'
import type { VisualGlobal } from './types'

interface Props {
  value: VisualGlobal
  timeframes: any[]
  fuquanTypes: any[]
  scopeTypes: any[]
  onChange: (next: VisualGlobal) => void
}

const { Text } = Typography

export default function GlobalSettingsBar({
  value, timeframes, fuquanTypes, scopeTypes, onChange,
}: Props) {
  const { token } = theme.useToken()
  const update = (patch: Partial<VisualGlobal>) => onChange({ ...value, ...patch })

  return (
    <div
      style={{
        padding: '8px 12px',
        borderBottom: `1px solid ${token.colorBorderSecondary}`,
        background: token.colorBgContainer,
      }}
    >
      <Space wrap size={[12, 8]}>
        <span style={{ color: token.colorTextSecondary, fontSize: 12 }}>分析周期</span>
        <Select
          size="small"
          style={{ width: 96 }}
          value={value.timeframe}
          options={timeframes}
          onChange={(v) => update({ timeframe: v })}
        />
        <span style={{ color: token.colorTextSecondary, fontSize: 12 }}>复权方式</span>
        <Select
          size="small"
          style={{ width: 96 }}
          value={value.fuquan}
          options={fuquanTypes}
          onChange={(v) => update({ fuquan: v })}
        />
        <span style={{ color: token.colorTextSecondary, fontSize: 12 }}>选股范围</span>
        <Select
          size="small"
          style={{ width: 110 }}
          value={value.scope}
          options={scopeTypes}
          onChange={(v) => update({ scope: v })}
        />
        <Checkbox
          checked={value.exclude_st}
          onChange={(e) => update({ exclude_st: e.target.checked })}
        >
          <Text style={{ fontSize: 12 }}>剔除ST</Text>
        </Checkbox>
        <Checkbox
          checked={value.exclude_halt}
          onChange={(e) => update({ exclude_halt: e.target.checked })}
        >
          <Text style={{ fontSize: 12 }}>剔除停牌</Text>
        </Checkbox>
        <span style={{ color: token.colorTextSecondary, fontSize: 12 }}>最小成交额</span>
        <InputNumber
          size="small"
          style={{ width: 70 }}
          min={0}
          value={value.min_amount}
          onChange={(v) => update({ min_amount: v ?? 0 })}
        />
        <Text style={{ fontSize: 12, color: token.colorTextTertiary }}>亿元</Text>
      </Space>
    </div>
  )
}
