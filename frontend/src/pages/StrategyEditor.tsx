import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Alert, Button, Card, DatePicker, Empty, Input, InputNumber, Layout, Modal,
  Popconfirm, Space, Splitter, Tag, Typography, message, theme,
} from 'antd'
import { DeleteOutlined, SaveOutlined, ThunderboltOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import {
  getStrategies, listVisualRules, deleteVisualRule, deleteCustomStrategy,
  deleteVariant, runBacktest, saveVariant,
} from '../api'
import { useStore } from '../stores'
import StrategyParamsForm, { initParamValues } from '../components/StrategyParamsForm'
import type { StrategyItem, ParamValues } from '../types'

const { Title, Paragraph, Text } = Typography
const { RangePicker } = DatePicker

const KEY_RE = /^[A-Za-z][A-Za-z0-9_-]{0,63}$/

/** 页面 A：策略编辑器 —— 只做「选中策略 → 调它的参数」。
 *
 * 「从零造策略」不在这里：可视化编辑器已迁到独立的「自定义策略」页。
 * 因此本页不再包含指标库 / 条件积木 / 环境设置，也不再有代码编辑器。
 */
export default function StrategyEditor() {
  const { token } = theme.useToken()
  const navigate = useNavigate()
  const { setResult } = useStore()

  const [strategies, setStrategies] = useState<StrategyItem[]>([])
  const [selectedKey, setSelectedKey] = useState<string>('')
  const [paramValues, setParamValues] = useState<ParamValues>({})

  // 回测所需的必要输入（股票代码 / 区间 / 初始资金）
  const [symbol, setSymbol] = useState('000001')
  const [range, setRange] = useState<[dayjs.Dayjs, dayjs.Dayjs]>(
    [dayjs('2024-01-01'), dayjs('2025-06-30')],
  )
  const [cash, setCash] = useState(1000000)

  const [running, setRunning] = useState(false)
  const [saving, setSaving] = useState(false)
  const [saveOpen, setSaveOpen] = useState(false)
  const [newKey, setNewKey] = useState('')
  const [newName, setNewName] = useState('')

  const loadStrategies = () => {
    Promise.all([
      getStrategies().then((r: any) => (r.data.data || []) as StrategyItem[]),
      listVisualRules().then((r: any) => r.data.data as any[]).catch(() => []),
    ])
      .then(([presets, visuals]) => {
        const merged: StrategyItem[] = [...presets]
        for (const v of visuals) merged.push({ ...v, category: 'visual' })
        setStrategies(merged)
        if (!selectedKey && merged.length > 0) setSelectedKey(merged[0].key)
      })
      .catch(() => message.warning('策略列表加载失败'))
  }

  useEffect(() => {
    loadStrategies()
  }, [])

  const current = strategies.find((s) => s.key === selectedKey)

  // 切换策略时立刻用「该策略自己的参数定义」重置表单。
  // 参数是单一 selectedKey 驱动，切换不留上一个策略的残留值。
  useEffect(() => {
    if (!current) {
      setParamValues({})
      return
    }
    setParamValues(initParamValues(current.params || []))
  }, [selectedKey, strategies])

  const presetStrategies = strategies.filter((s) => s.type === 'preset')
  const variantStrategies = strategies.filter((s) => s.type === 'variant')
  const customStrategies = strategies.filter((s) => s.type === 'custom')

  const isScreening = current?.category === 'screening'

  const handleRunBacktest = async () => {
    if (!current) return
    if (!range || range.length !== 2) {
      message.warning('请选择回测区间')
      return
    }
    setRunning(true)
    try {
      const res = await runBacktest({
        strategy: current.key,
        symbol,
        start_date: range[0].format('YYYYMMDD'),
        end_date: range[1].format('YYYYMMDD'),
        params: paramValues,
        cash,
      })
      const data = res.data?.data
      if (!data) {
        message.error('回测未返回结果')
        return
      }
      setResult(data)
      message.success('回测完成')
      navigate('/results')
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '回测失败')
    } finally {
      setRunning(false)
    }
  }

  const openSaveAs = () => {
    if (!current) return
    setNewKey('')
    setNewName(`${current.name} 副本`)
    setSaveOpen(true)
  }

  const handleSaveAs = async () => {
    if (!current) return
    const key = newKey.trim()
    if (!key) {
      message.warning('请输入新策略 key')
      return
    }
    if (!KEY_RE.test(key)) {
      message.warning('key 只能包含字母、数字、下划线和连字符，且以字母开头')
      return
    }
    // 变体基于「它自己的基础策略」，避免变体套变体
    const baseKey = current.type === 'variant' ? (current.base_key || current.key) : current.key
    setSaving(true)
    try {
      await saveVariant({
        key,
        name: newName.trim() || key,
        base_key: baseKey,
        params: paramValues,
        description: `基于「${current.name}」的参数变体`,
      })
      message.success(`已另存为新策略「${key}」，原策略保持不变`)
      setSaveOpen(false)
      await loadStrategies()
      setSelectedKey(key)
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '保存失败')
    } finally {
      setSaving(false)
    }
  }

  const handleDelete = async () => {
    if (!current) return
    try {
      if (current.type === 'variant') {
        await deleteVariant(current.key)
      } else if (current.category === 'visual') {
        await deleteVisualRule(current.key)
      } else {
        await deleteCustomStrategy(current.key)
      }
      message.success('策略已删除')
      setSelectedKey('')
      loadStrategies()
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '删除失败')
    }
  }

  const renderItem = (s: StrategyItem) => (
    <div
      key={s.key}
      onClick={() => setSelectedKey(s.key)}
      style={{
        padding: '8px 12px',
        cursor: 'pointer',
        backgroundColor: selectedKey === s.key ? token.controlItemBgActive : 'transparent',
        borderRadius: 4,
        marginBottom: 4,
        display: 'flex',
        justifyContent: 'space-between',
        alignItems: 'center',
      }}
    >
      <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{s.name}</span>
      {s.type === 'variant' && <Tag color="blue" style={{ marginRight: 0 }}>参数变体</Tag>}
      {s.category === 'visual' && <Tag color="purple" style={{ marginRight: 0 }}>可视化</Tag>}
    </div>
  )

  return (
    <div>
      <Title level={3}>策略编辑器</Title>
      <Paragraph type="secondary">
        选中一个策略，调整它自己的参数后可直接回测，或「另存为新策略」把当前参数固化成一条新策略（原策略不会被修改）。
        要从零组合条件创建新策略，请使用「自定义策略」页。
      </Paragraph>

      <Layout style={{ marginTop: 16, height: 'calc(100vh - 250px)' }}>
        <Splitter>
          <Splitter.Panel defaultSize={250} min={200} max={400}>
            <Card
              title="策略列表"
              size="small"
              style={{ height: '100%', overflow: 'auto' }}
            >
              {presetStrategies.length > 0 && (
                <div style={{ marginBottom: 16 }}>
                  <Text strong>预置策略</Text>
                  {presetStrategies.map(renderItem)}
                </div>
              )}
              {variantStrategies.length > 0 && (
                <div style={{ marginBottom: 16 }}>
                  <Text strong>参数变体</Text>
                  {variantStrategies.map(renderItem)}
                </div>
              )}
              {customStrategies.length > 0 && (
                <div>
                  <Text strong>自定义策略</Text>
                  {customStrategies.map(renderItem)}
                </div>
              )}
              {strategies.length === 0 && <Empty description="暂无策略" />}
            </Card>
          </Splitter.Panel>

          <Splitter.Panel>
            <Card
              title={current ? `${current.name} 的参数` : '未选择策略'}
              style={{ height: '100%', overflow: 'auto' }}
              extra={
                current && (
                  <Space>
                    <Button icon={<SaveOutlined />} onClick={openSaveAs}>另存为新策略</Button>
                    {(current.type === 'variant' || current.type === 'custom') && (
                      <Popconfirm title="确认删除该策略？" onConfirm={handleDelete}>
                        <Button danger icon={<DeleteOutlined />}>删除</Button>
                      </Popconfirm>
                    )}
                  </Space>
                )
              }
            >
              {!current ? (
                <Empty description="请在左侧选择一个策略" />
              ) : (
                <>
                  {current.description && (
                    <Paragraph type="secondary" style={{ marginBottom: 12 }}>
                      {current.description}
                    </Paragraph>
                  )}
                  {current.type === 'variant' && current.base_key && (
                    <Alert
                      type="info"
                      showIcon
                      style={{ marginBottom: 12 }}
                      message={`参数变体：基于预置策略「${current.base_key}」，已固化下方参数`}
                    />
                  )}
                  {isScreening && (
                    <Alert
                      type="warning"
                      showIcon
                      style={{ marginBottom: 12 }}
                      message="这是「选股类」策略"
                      description="选股类策略用于实时选股池 / 盘中监控，通常不在回测中运行。如需查看效果请到「实时选股池」页。"
                    />
                  )}

                  <StrategyParamsForm
                    params={current.params || []}
                    values={paramValues}
                    onChange={setParamValues}
                  />

                  <Card size="small" title="回测" style={{ marginTop: 16 }}>
                    <Space wrap size={12}>
                      <span>
                        <Text style={{ marginRight: 6 }}>股票代码</Text>
                        <Input
                          style={{ width: 130 }}
                          value={symbol}
                          onChange={(e) => setSymbol(e.target.value)}
                          placeholder="如 000001"
                        />
                      </span>
                      <span>
                        <Text style={{ marginRight: 6 }}>回测区间</Text>
                        <RangePicker
                          value={range}
                          onChange={(v) => {
                            if (v && v[0] && v[1]) setRange([v[0], v[1]])
                          }}
                        />
                      </span>
                      <span>
                        <Text style={{ marginRight: 6 }}>初始资金</Text>
                        <InputNumber
                          style={{ width: 150 }}
                          min={10000}
                          step={100000}
                          value={cash}
                          onChange={(v) => setCash(v || 1000000)}
                        />
                      </span>
                      <Button
                        type="primary"
                        icon={<ThunderboltOutlined />}
                        loading={running}
                        onClick={handleRunBacktest}
                      >
                        立即回测
                      </Button>
                    </Space>
                  </Card>
                </>
              )}
            </Card>
          </Splitter.Panel>
        </Splitter>
      </Layout>

      <Modal
        title="另存为新策略"
        open={saveOpen}
        onCancel={() => setSaveOpen(false)}
        onOk={handleSaveAs}
        confirmLoading={saving}
        okText="保存"
        cancelText="取消"
      >
        <Space direction="vertical" size={12} style={{ width: '100%' }}>
          <Alert
            type="info"
            showIcon
            message="原策略保持不变"
            description="当前参数会固化成一条新策略记录，出现在列表的「参数变体」分组中，之后可继续调参和回测。"
          />
          <div>
            <div style={{ marginBottom: 4 }}>策略 key（字母开头，可含数字/下划线/连字符）</div>
            <Input
              value={newKey}
              onChange={(e) => setNewKey(e.target.value)}
              placeholder="如 my_dual_ma_8_30"
            />
          </div>
          <div>
            <div style={{ marginBottom: 4 }}>策略名称</div>
            <Input
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              placeholder="显示用的名称"
            />
          </div>
        </Space>
      </Modal>
    </div>
  )
}
