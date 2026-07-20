import { Tree, Tag, Space, Typography, theme } from 'antd'
import { BulbOutlined } from '@ant-design/icons'

interface Props {
  groups: any[]
  recommendedIndicators?: string[] // 智能推荐白名单，高亮显示
  onSelect: (indicatorKey: string) => void
}

const { Text } = Typography

export default function IndicatorTree({ groups, recommendedIndicators, onSelect }: Props) {
  const { token } = theme.useToken()
  const recSet = new Set(recommendedIndicators || [])

  const treeData = groups.map((g) => ({
    title: g.label,
    key: 'grp_' + g.key,
    selectable: false,
    children: g.indicators.map((i: any) => ({
      title: (
        <Space size={4}>
          <Tag
            color={recSet.has(i.key) ? 'blue' : 'default'}
            style={{ marginRight: 0, cursor: 'pointer' }}
          >
            {i.name}
            {recSet.has(i.key) && <BulbOutlined style={{ marginLeft: 4, fontSize: 10 }} />}
          </Tag>
        </Space>
      ),
      key: 'ind_' + i.key,
      isLeaf: true,
    })),
  }))

  const handleSelect = (keys: any[]) => {
    const k = keys[0]
    if (!k || !k.startsWith('ind_')) return
    onSelect(k.slice(4))
  }

  return (
    <div style={{ padding: 8 }}>
      <Text strong>系统公式</Text>
      <div style={{ marginTop: 8 }}>
        <Tree
          treeData={treeData}
          onSelect={handleSelect}
          defaultExpandAll
          blockNode
          showLine={{ showLeafIcon: false }}
        />
      </div>
      <div style={{ marginTop: 12, fontSize: 12, color: token.colorTextTertiary }}>
        点击指标 → 中间设置参数，右侧自动生成默认条件
      </div>
    </div>
  )
}
