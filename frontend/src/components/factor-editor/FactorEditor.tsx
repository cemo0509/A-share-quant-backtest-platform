import { useMemo, useState } from 'react'
import {
  Space, Button, Card, Tag, Typography, Empty, theme, Modal, Tooltip,
} from 'antd'
import {
  PlusOutlined, DeleteOutlined, EditOutlined, CopyOutlined, BulbOutlined, AimOutlined,
} from '@ant-design/icons'
import ConditionEditPanel from '../visual-editor/ConditionEditPanel'
import { renderCondition, buildConditionOptions } from '../visual-editor/conditionText'
import type { VisualIndicatorTree } from '../../api'
import {
  VisualRule, ConditionLeaf, VisualGlobal, createLeaf, newId,
} from '../visual-editor/types'

const { Text } = Typography

export interface FactorEditorPreset {
  key: string
  name: string
}

interface Props {
  /** 当前条件（扁平 AND：items 里全部是叶子） */
  rule: VisualRule
  /** 指标库（分类 + 指标） */
  tree: VisualIndicatorTree
  /** 条件变化回调 */
  onChange: (rule: VisualRule) => void
  /** 全局设置变化（同步 timeframe 到每个叶子） */
  onGlobalChange?: (g: VisualGlobal) => void
  /** 可选：我的方案（点击加载一组预置条件） */
  presets?: FactorEditorPreset[]
  onLoadPreset?: (key: string) => void
  /** 是否在下方展示指标库（默认 true） */
  showIndicatorLibrary?: boolean
}

function findIndicatorDef(tree: VisualIndicatorTree | null, key: string): any {
  for (const g of tree?.groups || []) {
    const def = (g.indicators || []).find((i: any) => i.key === key)
    if (def) return def
  }
  return null
}

/**
 * 同花顺式「因子标签块」编辑器（选股器 / 策略编辑器共用）。
 *
 * 只支持扁平 AND：items 里全部是叶子条件，没有嵌套组、没有 OR。
 * 顶部横排条件块（点击编辑、点 × 删除），下方左侧因子分类 + 右侧指标库，
 * 点指标弹出「选条件类型」确认后追加一个标签块。
 */
export default function FactorEditor({
  rule,
  tree,
  onChange,
  presets,
  onLoadPreset,
  showIndicatorLibrary = true,
}: Props) {
  const { token } = theme.useToken()
  const [activeGroupKey, setActiveGroupKey] = useState<string>('')
  const [pickerIndicator, setPickerIndicator] = useState<any | null>(null)
  const [editingLeaf, setEditingLeaf] = useState<ConditionLeaf | null>(null)

  const leaves = useMemo(
    () => (rule.items || []).filter((n): n is ConditionLeaf => n.type === 'condition'),
    [rule.items],
  )

  const groups = tree?.groups || []
  const activeGroup =
    groups.find((g) => g.key === activeGroupKey) || groups[0]

  // ---------- 条件操作 ----------
  const setLeaves = (next: ConditionLeaf[]) =>
    onChange({ ...rule, items: next })

  const removeLeaf = (id: string) =>
    setLeaves(leaves.filter((l) => l.id !== id))

  const updateLeaf = (next: ConditionLeaf) => {
    setLeaves(leaves.map((l) => (l.id === next.id ? next : l)))
    setEditingLeaf(null)
  }

  const duplicateLeaf = (leaf: ConditionLeaf) => {
    const copy = { ...JSON.parse(JSON.stringify(leaf)), id: newId() }
    const idx = leaves.findIndex((l) => l.id === leaf.id)
    const next = leaves.slice()
    next.splice(idx + 1, 0, copy)
    setLeaves(next)
  }

  // 点指标 → 打开「选条件类型」弹窗
  const openPicker = (ind: any) => setPickerIndicator(ind)

  // 在指标选择弹窗里选定一种条件类型 → 追加一个标签块
  const confirmPick = (patch: Partial<ConditionLeaf>) => {
    if (!pickerIndicator) return
    const def = findIndicatorDef(tree, pickerIndicator.key)
    const leaf = createLeaf(def)
    const merged: ConditionLeaf = {
      ...leaf,
      ...patch,
      targetLine: patch.targetLine ?? undefined,
      targetTimeframe: patch.targetTimeframe ?? undefined,
    }
    setLeaves([...leaves, merged])
    setPickerIndicator(null)
    // 刚加的条件直接进入编辑态，便于立刻改数值
    setEditingLeaf(merged)
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0 }}>
      {/* ============ 顶部：条件标签块（同花顺核心） ============ */}
      <div
        style={{
          padding: '10px 12px',
          background: token.colorBgContainer,
          borderBottom: `1px solid ${token.colorBorderSecondary}`,
        }}
      >
        <Space size={6} style={{ marginBottom: 6 }}>
          <AimOutlined style={{ color: token.colorPrimary }} />
          <Text strong>当前条件</Text>
          <Text type="secondary" style={{ fontSize: 12 }}>
            {leaves.length > 0 ? `需同时满足以下 ${leaves.length} 项` : '点击下方指标库添加条件'}
          </Text>
        </Space>

        {leaves.length === 0 ? (
          <Empty
            image={Empty.PRESENTED_IMAGE_SIMPLE}
            imageStyle={{ height: 48 }}
            description="还没有条件，从下方指标库点一个指标开始"
            style={{ margin: '8px 0' }}
          />
        ) : (
          <Space wrap size={[8, 8]}>
            {leaves.map((leaf) => (
              <div
                key={leaf.id}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 6,
                  padding: '5px 10px',
                  background: token.colorPrimaryBg,
                  border: `1px solid ${token.colorPrimaryBorder}`,
                  borderRadius: 6,
                }}
              >
                <span style={{ fontSize: 13, whiteSpace: 'nowrap' }}>
                  {renderCondition(leaf)}
                </span>
                <Tooltip title="编辑">
                  <EditOutlined
                    style={{ fontSize: 12, color: token.colorPrimary, cursor: 'pointer' }}
                    onClick={() => setEditingLeaf(leaf)}
                  />
                </Tooltip>
                <Tooltip title="复制">
                  <CopyOutlined
                    style={{ fontSize: 12, color: token.colorTextSecondary, cursor: 'pointer' }}
                    onClick={() => duplicateLeaf(leaf)}
                  />
                </Tooltip>
                <Tooltip title="删除">
                  <DeleteOutlined
                    style={{ fontSize: 12, color: token.colorError, cursor: 'pointer' }}
                    onClick={() => removeLeaf(leaf.id)}
                  />
                </Tooltip>
              </div>
            ))}
            <Button
              type="dashed"
              size="small"
              icon={<PlusOutlined />}
              onClick={() => {
                if (activeGroup?.indicators?.[0]) openPicker(activeGroup.indicators[0])
              }}
            >
              添加
            </Button>
          </Space>
        )}
      </div>

      {/* ============ 下方：左因子分类 + 右指标库 ============ */}
      {showIndicatorLibrary && (
        <div style={{ display: 'flex', flex: 1, minHeight: 0 }}>
          {/* 左：因子分类 */}
          <div
            style={{
              width: 150,
              borderRight: `1px solid ${token.colorBorderSecondary}`,
              overflow: 'auto',
              background: token.colorBgLayout,
            }}
          >
            {groups.map((g) => (
              <div
                key={g.key}
                onClick={() => setActiveGroupKey(g.key)}
                style={{
                  padding: '9px 12px',
                  cursor: 'pointer',
                  fontSize: 13,
                  background: g.key === (activeGroup?.key) ? token.colorBgContainer : 'transparent',
                  borderLeft: g.key === (activeGroup?.key)
                    ? `2px solid ${token.colorPrimary}`
                    : '2px solid transparent',
                  color: g.key === (activeGroup?.key) ? token.colorPrimary : token.colorText,
                  fontWeight: g.key === (activeGroup?.key) ? 600 : 400,
                }}
              >
                {g.label}
              </div>
            ))}
          </div>

          {/* 右：指标库（当前分类下） */}
          <div style={{ flex: 1, padding: 12, overflow: 'auto' }}>
            <Space size={6} style={{ marginBottom: 8 }}>
              <Text strong>{activeGroup?.label || '指标'}</Text>
              <Text type="secondary" style={{ fontSize: 12 }}>
                点指标 → 选择条件类型即可加入
              </Text>
            </Space>
            <Space wrap size={[8, 8]}>
              {(activeGroup?.indicators || []).map((ind: any) => (
                <Card
                  key={ind.key}
                  size="small"
                  hoverable
                  onClick={() => openPicker(ind)}
                  style={{ width: 108 }}
                  bodyStyle={{ padding: '8px 10px', textAlign: 'center' }}
                >
                  <div style={{ fontSize: 13, fontWeight: 500 }}>{ind.name}</div>
                  {ind.key && (
                    <div style={{ fontSize: 11, color: token.colorTextTertiary }}>{ind.key}</div>
                  )}
                </Card>
              ))}
            </Space>
          </div>
        </div>
      )}

      {/* ============ 我的方案（可选） ============ */}
      {presets && presets.length > 0 && (
        <div
          style={{
            padding: '8px 12px',
            borderTop: `1px solid ${token.colorBorderSecondary}`,
            background: token.colorBgContainer,
          }}
        >
          <Space wrap size={[6, 6]}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              <BulbOutlined /> 我的方案：
            </Text>
            {presets.map((p) => (
              <Tag
                key={p.key}
                color="blue"
                style={{ cursor: 'pointer', marginRight: 0 }}
                onClick={() => onLoadPreset?.(p.key)}
              >
                {p.name}
              </Tag>
            ))}
          </Space>
        </div>
      )}

      {/* ============ 弹窗：选条件类型 ============ */}
      <Modal
        title={pickerIndicator ? `添加「${pickerIndicator.name}」条件` : ''}
        open={!!pickerIndicator}
        onCancel={() => setPickerIndicator(null)}
        footer={null}
        width={440}
      >
        <Space direction="vertical" style={{ width: '100%' }} size={6}>
          {(pickerIndicator ? buildConditionOptions(pickerIndicator) : []).map((opt: any) => (
            <Button
              key={opt.value}
              block
              style={{ textAlign: 'left', height: 'auto', padding: '8px 12px' }}
              onClick={() => confirmPick(opt.patch)}
            >
              {opt.label}
            </Button>
          ))}
        </Space>
      </Modal>

      {/* ============ 弹窗：编辑条件 ============ */}
      <Modal
        title="编辑条件"
        open={!!editingLeaf}
        onCancel={() => setEditingLeaf(null)}
        footer={null}
        width={560}
        destroyOnClose
      >
        {editingLeaf && (
          <ConditionEditPanel
            leaf={editingLeaf}
            indicatorDef={findIndicatorDef(tree, editingLeaf.indicator)}
            groups={tree?.groups}
            onChange={updateLeaf}
            onDelete={() => {
              removeLeaf(editingLeaf.id)
              setEditingLeaf(null)
            }}
            onDuplicate={() => {
              duplicateLeaf(editingLeaf)
              setEditingLeaf(null)
            }}
          />
        )}
      </Modal>
    </div>
  )
}
