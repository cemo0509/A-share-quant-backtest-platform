import { Segmented, Button, Space, Typography, Empty, Card, theme } from 'antd'
import { PlusOutlined, PartitionOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons'
import type { ConditionNode, ConditionGroup as GroupType, ConditionLeaf } from './types'
import { renderCondition } from './conditionText'
import ConditionEditPanel from './ConditionEditPanel'

interface Props {
  group: GroupType
  groups: any[]
  editingId: string | null
  onChange: (next: GroupType) => void
  onStartEdit: (id: string) => void
  onStopEdit: () => void
  onAddLeaf: (groupId?: string) => void
  onAddSubGroup: (groupId?: string) => void
  recommendedIndicators?: string[]
}

const { Text } = Typography

function findIndicator(groups: any[], key: string): any {
  for (const g of groups) {
    const def = g.indicators.find((i: any) => i.key === key)
    if (def) return def
  }
  return null
}

export default function ConditionPreview({
  group, groups, editingId, onChange, onStartEdit, onStopEdit,
  onAddLeaf, onAddSubGroup, recommendedIndicators,
}: Props) {
  const { token } = theme.useToken()
  const setItems = (items: ConditionNode[]) => onChange({ ...group, items })

  const updateNode = (idx: number, next: ConditionNode) => {
    const items = group.items.slice()
    items[idx] = next
    setItems(items)
  }
  const removeNode = (idx: number) => setItems(group.items.filter((_, i) => i !== idx))
  const duplicateNode = (idx: number) => {
    const node = group.items[idx]
    const clone = JSON.parse(JSON.stringify(node))
    clone.id = 'n_' + Math.random().toString(36).slice(2, 9)
    const items = group.items.slice()
    items.splice(idx + 1, 0, clone)
    setItems(items)
  }

  const renderItem = (node: ConditionNode, idx: number, showOp: boolean) => {
    const opTag = showOp ? (
      <Text type="secondary" style={{ fontSize: 12, marginRight: 6 }}>
        {idx === 0 ? '' : group.operator === 'AND' ? '且' : '或'}
      </Text>
    ) : null

    if (node.type === 'group') {
      return (
        <div key={node.id} style={{ marginLeft: 16, borderLeft: `2px solid ${token.colorBorderSecondary}`, paddingLeft: 8, marginTop: 6 }}>
          <Space wrap style={{ marginBottom: 4 }}>
            <PartitionOutlined />
            <Segmented
              size="small"
              value={node.operator}
              options={[{ label: '并且 (AND)', value: 'AND' }, { label: '或者 (OR)', value: 'OR' }]}
              onChange={(v) => updateNode(idx, { ...node, operator: v as any })}
            />
            <Button type="text" size="small" danger icon={<DeleteOutlined />} onClick={() => removeNode(idx)}>删除组合</Button>
          </Space>
          <ConditionPreview
            group={node}
            groups={groups}
            editingId={editingId}
            onChange={(next) => updateNode(idx, next)}
            onStartEdit={onStartEdit}
            onStopEdit={onStopEdit}
            onAddLeaf={(gid?: string) => onAddLeaf(gid ?? node.id)}
            onAddSubGroup={(gid?: string) => onAddSubGroup(gid ?? node.id)}
            recommendedIndicators={recommendedIndicators}
          />
        </div>
      )
    }

    // 叶子
    const leaf = node as ConditionLeaf
    const def = findIndicator(groups, leaf.indicator)
    const isEditing = editingId === leaf.id

    return (
      <div key={leaf.id} style={{ display: 'flex', alignItems: 'flex-start', marginTop: 6 }}>
        {opTag}
        <div style={{ flex: 1 }}>
          {isEditing ? (
            <ConditionEditPanel
              leaf={leaf}
              indicatorDef={def}
              groups={groups}
              onChange={(next) => updateNode(idx, next)}
              onDelete={() => removeNode(idx)}
              onDuplicate={() => duplicateNode(idx)}
            />
          ) : (
            <Card size="small" style={{ background: token.colorBgElevated }} bodyStyle={{ padding: '8px 12px' }}>
              <Space wrap style={{ width: '100%', justifyContent: 'space-between' }}>
                <Text>• {renderCondition(leaf)}</Text>
                <Space size={4}>
                  <Button type="link" size="small" icon={<EditOutlined />} onClick={() => onStartEdit(leaf.id)}>编辑</Button>
                  <Button type="link" size="small" danger icon={<DeleteOutlined />} onClick={() => removeNode(idx)}>删除</Button>
                </Space>
              </Space>
            </Card>
          )}
        </div>
      </div>
    )
  }

  return (
    <div>
      <Space wrap style={{ marginBottom: 8 }}>
        <Text strong>条件组合</Text>
        <Segmented
          size="small"
          value={group.operator}
          options={[{ label: '并且 (AND)', value: 'AND' }, { label: '或者 (OR)', value: 'OR' }]}
          onChange={(v) => onChange({ ...group, operator: v as any })}
        />
      </Space>

      {group.items.length === 0 && <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="暂无条件，点击下方添加" />}

      {group.items.map((node, idx) => renderItem(node, idx, true))}

      <Space style={{ marginTop: 8 }}>
        <Button type="dashed" size="small" icon={<PlusOutlined />} onClick={() => onAddLeaf(group.id)}>添加条件</Button>
        <Button type="dashed" size="small" icon={<PartitionOutlined />} onClick={() => onAddSubGroup(group.id)}>添加子组合（或）</Button>
      </Space>
    </div>
  )
}
