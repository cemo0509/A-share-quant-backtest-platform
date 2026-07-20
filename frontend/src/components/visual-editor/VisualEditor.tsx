import { useEffect, useRef, useState } from 'react'
import { Space, Button, Input, message, Drawer, Typography, Empty, theme, Select, Modal, Tooltip } from 'antd'
import { SaveOutlined, CodeOutlined, BulbOutlined, AppstoreOutlined } from '@ant-design/icons'
import GlobalSettingsBar from './GlobalSettingsBar'
import IndicatorTree from './IndicatorTree'
import ParameterPanel from './ParameterPanel'
import ConditionPreview from './ConditionPreview'
import { VisualRule, ConditionLeaf, ConditionNode, ConditionGroup, VisualGlobal, createGroup, createLeaf, newId, applyPreset, updateNodeById, collectLeaves } from './types'
import {
  getVisualIndicators, saveVisualRule, loadVisualRule,
  getVisualPresets,
} from '../../api'
import type { VisualIndicatorTree } from '../../api'

const { Text } = Typography

interface Props {
  ruleKey: string
  ruleName: string
  onSaved: () => void
  onKeyChange?: (key: string) => void
}

function defaultGlobal(tree: VisualIndicatorTree): VisualGlobal {
  const g = tree?.default_global || {}
  return {
    timeframe: g.timeframe || 'daily',
    fuquan: g.fuquan || 'qfq',
    scope: g.scope || 'all',
    exclude_st: g.exclude_st ?? true,
    exclude_halt: g.exclude_halt ?? true,
    min_amount: g.min_amount ?? 1,
  }
}

export default function VisualEditor({ ruleKey, ruleName, onSaved, onKeyChange }: Props) {
  const { token } = theme.useToken()
  const [tree, setTree] = useState<VisualIndicatorTree | null>(null)
  const [rule, setRule] = useState<VisualRule>(() => createGroup('AND'))
  const [name, setName] = useState(ruleName)
  const [desc, setDesc] = useState('')
  const [keyInput, setKeyInput] = useState(ruleKey)
  const [jsonOpen, setJsonOpen] = useState(false)
  const [saving, setSaving] = useState(false)
  const [loading, setLoading] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [presets, setPresets] = useState<{ presets: Record<string, any>; names: Record<string, string> } | null>(null)
  const [presetKey, setPresetKey] = useState<string | undefined>(undefined)
  const autoFilledRef = useRef<Set<string>>(new Set())

  useEffect(() => {
    getVisualIndicators()
      .then((res) => setTree(res.data.data || {}))
      .catch(() => message.error('指标库加载失败'))
  }, [])

  useEffect(() => {
    getVisualPresets()
      .then((res) => setPresets(res.data.data || {}))
      .catch(() => { setPresets({ presets: {}, names: {} }) })
  }, [])

  useEffect(() => {
    setKeyInput(ruleKey)
    if (!ruleKey) {
      setRule(createGroup('AND'))
      setName(ruleName)
      setDesc('')
      return
    }
    // 预置策略（如 cci_macd_selection）没有独立存储的可视化规则，
    // 直接走「智能推荐预设」自动填充推荐条件即可，不必去 load（否则必然 404）。
    // presets 未就绪时先等待（下方 effect 会重跑），避免预置策略控制台刷 404 红字。
    if (!presets) {
      setLoading(true)
      return
    }
    if (presets.presets[ruleKey]) {
      setLoading(true)
      setRule(createGroup('AND'))
      setName(ruleName || ruleKey)
      setDesc('')
      autoFillPreset(ruleKey)
      setLoading(false)
      return
    }
    setLoading(true)
    loadVisualRule(ruleKey)
      .then((res) => {
        const d = res.data.data || {}
        const loadedRule = d.rule || createGroup('AND')
        setName(d.name || ruleKey)
        setDesc(d.description || '')
        // 用函数式更新：保留 [tree] effect 可能已补上的 global，避免竞态覆盖（发现 #5）
        setRule((prev) => ({
          ...loadedRule,
          global: loadedRule.global || prev.global || (tree ? defaultGlobal(tree) : undefined),
        }))
        if ((loadedRule.items?.length || 0) === 0) autoFillPreset(ruleKey)
      })
      .catch(() => {
        setRule(createGroup('AND'))
        setName(ruleName || ruleKey)
        setDesc('')
        autoFillPreset(ruleKey)
      })
      .finally(() => setLoading(false))
  }, [ruleKey, presets])

  useEffect(() => {
    if (ruleKey && presets && (rule.items?.length || 0) === 0) autoFillPreset(ruleKey)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [presets])

  // 兜底：tree 就绪后，若当前规则仍缺 global（旧数据加载时 tree 未就绪），补默认 global
  useEffect(() => {
    if (tree && !rule.global) {
      setRule((prev) => (prev.global ? prev : { ...prev, global: defaultGlobal(tree) }))
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tree])

  const autoFillPreset = (key: string) => {
    if (!presets) return
    const preset = presets.presets[key]
    if (!preset) return
    if (autoFilledRef.current.has(key)) return
    const r = applyPreset(preset.rule)
    if (tree) r.global = defaultGlobal(tree)
    setRule(r)
    setName(presets.names[key] || key)
    setDesc(`智能推荐：${presets.names[key] || key}`)
    setPresetKey(key)
    autoFilledRef.current.add(key)
    message.success(`已自动载入「${presets.names[key] || key}」推荐条件`)
  }

  const emptyRule = (rule.items?.length || 0) === 0

  const handleSave = async () => {
    const finalKey = keyInput.trim() || ruleKey.trim()
    if (!finalKey) { message.warning('请先输入策略key（在上方输入框）'); return }
    if (emptyRule) { message.warning('请至少添加一个条件'); return }
    const miss = findBetweenMissing(rule as any)
    if (miss.length > 0) { message.warning(`「${miss[0]}」使用 between 区间，请同时填写下限和上限`); return }
    setSaving(true)
    try {
      await saveVisualRule({ key: finalKey, name: name || finalKey, description: desc, rule })
      message.success('可视化策略已保存')
      onKeyChange?.(finalKey)
      onSaved()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '保存失败')
    } finally {
      setSaving(false)
    }
  }

  const findBetweenMissing = (group: any): string[] => {
    const miss: string[] = []
    for (const node of group.items || []) {
      if (node.type === 'group') miss.push(...findBetweenMissing(node))
      else if (node.type === 'condition' && node.operator === 'between') {
        if (node.targetValue == null || node.targetParam2 == null) miss.push(node.indicator)
      }
    }
    return miss
  }

  // 点击左侧指标 → 添加一条默认条件到顶层（自然语言，来自后端 default_conditions）
  const onTreeSelect = (indKey: string) => {
    const leaf = makeLeaf(indKey)
    setRule((prev) => ({ ...prev, items: [...prev.items, leaf] }))
    setEditingId(leaf.id)
  }

  // 按指标 key 同步更新该指标下所有叶子的参数（按 id 递归，支持嵌套组）
  // 用函数式 setState，并基于 prev 中该指标已有 params 合并增量，
  // 避免快速连续改同一指标不同参数时基于过期快照丢失前一次修改（发现 #1 + 第四轮加固）
  const handleChangeParams = (indicatorKey: string, paramPatch: Record<string, number>) => {
    setRule((prev) => {
      const targetIds = collectLeaves(prev.items)
        .filter((lf) => lf.indicator === indicatorKey)
        .map((lf) => lf.id)
      let items: ConditionNode[] = prev.items
      for (const id of targetIds) {
        items = updateNodeById(items, id, (n) => {
          const leaf = n as ConditionLeaf
          return { ...leaf, params: { ...leaf.params, ...paramPatch } }
        })
      }
      return { ...prev, items }
    })
  }

  // 顶层添加条件（用第一个可用指标）
  // 用函数式 setState 避免快速双击时两次基于同一过期 items 导致第一条被覆盖（发现 #2）
  const addLeaf = (groupId?: string) => {
    const first = tree?.groups?.[0]?.indicators?.[0]
    if (!first) return
    const leaf = makeLeaf(first.key)
    setRule((prev) => {
      if (groupId) {
        return {
          ...prev,
          items: updateNodeById(prev.items, groupId, (n) => {
            const g = n as ConditionGroup
            return { ...g, items: [...g.items, leaf] }
          }),
        }
      }
      return { ...prev, items: [...prev.items, leaf] }
    })
    setEditingId(leaf.id)
  }
  // 生成一条默认条件（抽到函数，供 addLeaf 复用）
  const makeLeaf = (indKey: string): ConditionLeaf => {
    let def: any = null
    for (const g of tree?.groups || []) {
      def = g.indicators.find((i: any) => i.key === indKey)
      if (def) break
    }
    if (!def) return createLeaf({ key: indKey })
    const params: Record<string, number> = {}
    for (const p of def.params || []) params[p.name] = p.default
    const dc = tree?.default_conditions?.[indKey]
    // 用 tree 默认 global 的 timeframe，而非闭包中的 rule.global 快照，
    // 避免先改全局周期再点指标时新叶子用了旧周期（第四轮发现）
    const tf = (tree ? defaultGlobal(tree).timeframe : 'daily')
    return {
      id: newId(),
      type: 'condition',
      indicator: indKey,
      line: dc?.line ?? def.lines?.[0]?.value ?? '',
      params,
      timeframe: tf,
      operator: dc?.operator ?? def.operators?.[0] ?? 'greater',
      targetType: (dc?.targetType as ConditionLeaf['targetType']) ?? 'value',
      targetValue: dc?.targetValue ?? 0,
      targetParam2: dc?.targetParam2 ?? 0,
      targetIndicator: dc?.targetIndicator ?? undefined,
    }
  }
  const addSubGroup = (groupId?: string) => {
    const g = createGroup('OR')
    setRule((prev) => {
      if (groupId) {
        return {
          ...prev,
          items: updateNodeById(prev.items, groupId, (n) => {
            const grp = n as ConditionGroup
            return { ...grp, items: [...grp.items, g] }
          }),
        }
      }
      return { ...prev, items: [...prev.items, g] }
    })
  }

  // 全局设置变更：同步更新所有叶子的 timeframe，保持全局周期统一（发现 #9）
  const updateRuleGlobal = (g: VisualGlobal) => {
    setRule((prev) => {
      const syncTimeframe = (items: ConditionNode[]): ConditionNode[] =>
        items.map((n) =>
          n.type === 'condition'
            ? { ...n, timeframe: g.timeframe }
            : n.type === 'group'
              ? { ...n, items: syncTimeframe(n.items) }
              : n,
        )
      return { ...prev, global: g, items: syncTimeframe(prev.items) }
    })
  }
  const updateRule = (next: VisualRule) => setRule(next)

  const handlePresetChange = (key: string | undefined) => {
    setPresetKey(key)
    if (!key || !presets) return
    const preset = presets.presets[key]
    if (!preset) return
    const apply = () => {
      const r = applyPreset(preset.rule)
      if (tree) r.global = defaultGlobal(tree)
      setRule(r)
      setName(presets.names[key] || key)
      setDesc(`智能推荐：${presets.names[key] || key}`)
      autoFilledRef.current.add(key)
      message.success(`已载入「${presets.names[key] || key}」推荐条件`)
    }
    if ((rule.items?.length || 0) > 0) {
      Modal.confirm({ title: '覆盖当前条件？', content: `载入推荐条件将替换编辑区现有内容。`, okText: '覆盖', cancelText: '取消', onOk: apply })
    } else apply()
  }

  if (!tree) return <div style={{ padding: 24 }}><Empty description="加载中…" /></div>

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      {/* 顶部工具条 */}
      <div style={{ padding: '8px 12px', borderBottom: `1px solid ${token.colorBorderSecondary}`, background: token.colorBgContainer }}>
        <Space wrap>
          <span style={{ color: token.colorTextSecondary, fontSize: 12 }}>策略key</span>
          <Input size="small" style={{ width: 160 }} placeholder="如 my_rule（必填）" value={keyInput} onChange={(e) => setKeyInput(e.target.value)} />
          <span style={{ color: token.colorTextSecondary, fontSize: 12 }}>策略名称</span>
          <Input size="small" style={{ width: 180 }} placeholder="可视化策略名称" value={name} onChange={(e) => setName(e.target.value)} />
          {presets && Object.keys(presets.presets).length > 0 && (
            <Tooltip title="选择预置策略，自动预填推荐条件">
              <Select size="small" style={{ width: 170 }} placeholder="智能推荐…" value={presetKey} onChange={handlePresetChange}
                suffixIcon={<BulbOutlined />}
                options={Object.keys(presets.presets).map((k) => ({ value: k, label: presets.names[k] || k }))} />
            </Tooltip>
          )}
          <Button type="primary" size="small" icon={<SaveOutlined />} loading={saving} onClick={handleSave}>保存策略</Button>
          <Button size="small" icon={<CodeOutlined />} onClick={() => setJsonOpen(true)}>JSON 预览</Button>
          {loading && <Text type="secondary" style={{ fontSize: 12 }}>加载中…</Text>}
        </Space>
      </div>

      {/* 全局设置栏 */}
      <GlobalSettingsBar
        value={rule.global || defaultGlobal(tree)}
        timeframes={tree.timeframes}
        fuquanTypes={tree.fuquan_types || []}
        scopeTypes={tree.scope_types || []}
        onChange={updateRuleGlobal}
      />

      {/* 三栏主体：左指标树 / 中参数 / 右条件预览 */}
      <div style={{ display: 'flex', flex: 1, minHeight: 0 }}>
        {/* 左：指标树 */}
        <div style={{ width: 210, borderRight: `1px solid ${token.colorBorderSecondary}`, overflow: 'auto' }}>
          <IndicatorTree
            groups={tree.groups}
            recommendedIndicators={presetKey && presets?.presets[presetKey] ? presets.presets[presetKey].recommended_indicators : undefined}
            onSelect={onTreeSelect}
          />
        </div>

        {/* 中：参数面板 */}
        <div style={{ width: 260, borderRight: `1px solid ${token.colorBorderSecondary}`, overflow: 'auto' }}>
          <ParameterPanel groups={tree.groups} rule={rule} onChangeParams={handleChangeParams} />
        </div>

        {/* 右：条件预览 + 编辑 */}
        <div style={{ flex: 1, padding: 12, overflow: 'auto' }}>
          <Space style={{ marginBottom: 8 }} size={6}>
            <AppstoreOutlined style={{ color: token.colorPrimary }} />
            <Text strong>条件设置（自然语言）</Text>
          </Space>
          {emptyRule && <Empty description="从左侧点击指标，或点击下方「添加条件」开始构建" />}
          <ConditionPreview
            group={rule as any}
            groups={tree.groups}
            editingId={editingId}
            onChange={updateRule}
            onStartEdit={setEditingId}
            onStopEdit={() => setEditingId(null)}
            onAddLeaf={(groupId?: string) => addLeaf(groupId)}
            onAddSubGroup={(groupId?: string) => addSubGroup(groupId)}
            recommendedIndicators={presetKey && presets?.presets[presetKey] ? presets.presets[presetKey].recommended_indicators : undefined}
          />
        </div>
      </div>

      {/* JSON 预览抽屉 */}
      <Drawer title="规则 JSON 预览" open={jsonOpen} onClose={() => setJsonOpen(false)} width={420}>
        <pre style={{ fontSize: 12, background: token.colorBgElevated, padding: 12, borderRadius: 6, overflow: 'auto' }}>
          {JSON.stringify(rule, null, 2)}
        </pre>
      </Drawer>
    </div>
  )
}
