import { useEffect, useState } from 'react'
import { Card, Typography, Input, Button, Select, Space, message, Layout, Splitter, Empty, Popconfirm, Radio, Alert, Tag, theme } from 'antd'
import { SaveOutlined, DeleteOutlined, CodeOutlined, AimOutlined } from '@ant-design/icons'
import { getStrategies, getCustomStrategyCode, saveCustomStrategy, deleteCustomStrategy } from '../services/api'
import { listVisualRules, deleteVisualRule } from '../api'
import Editor from '@monaco-editor/react'
import VisualEditor from '../components/visual-editor/VisualEditor'

const { Title, Paragraph, Text } = Typography
const { TextArea } = Input

// 策略模板（集中管理所有预置策略代码）
import { STRATEGY_TEMPLATES, PRESET_STRATEGY_CODES } from './strategyTemplates'

// 编辑模式
type EditMode = 'code' | 'visual'

export default function StrategyEditor() {
  const { token } = theme.useToken()
  const [strategies, setStrategies] = useState<{ key: string; name: string; type: string; category?: string }[]>([])
  const [selectedKey, setSelectedKey] = useState<string>('')
  const [code, setCode] = useState<string>('')
  const [saving, setSaving] = useState(false)
  const [loading, setLoading] = useState(false)
  const [editMode, setEditMode] = useState<EditMode>('code')

  // 加载策略列表（预置 + 自定义 + 可视化）
  const loadStrategies = () => {
    Promise.all([
      getStrategies().then((r: any) => (r.data.data || []) as any[]),
      listVisualRules().then((r) => r.data.data as any[]).catch(() => []),
    ])
      .then(([presets, visuals]) => {
        const merged = [...presets]
        // 把可视化规则并入自定义类别，标记 category=visual
        for (const v of visuals) {
          merged.push({ ...v, category: 'visual' })
        }
        setStrategies(merged)
        if (!selectedKey && merged.length > 0) {
          setSelectedKey(merged[0].key)
        }
      })
      .catch(() => message.warning('策略列表加载失败'))
  }

  useEffect(() => {
    loadStrategies()
  }, [])

  // 加载选中的策略代码 / 可视化规则
  useEffect(() => {
    if (!selectedKey) return
    
    const strategy = strategies.find((s) => s.key === selectedKey)
    if (!strategy) return
    
    // 可视化策略：切换到可视化模式（规则由 VisualEditor 自行加载）
    if (strategy.category === 'visual') {
      setEditMode('visual')
      setCode('')
      return
    }

    // 非可视化策略（预置/自定义 Python）：确保退出可视化模式，避免对不存在的 key 发起 load 请求（404）
    if (editMode === 'visual') {
      setEditMode('code')
    }

    if (strategy.type === 'custom') {
      // 加载自定义策略代码
      setLoading(true)
      getCustomStrategyCode(selectedKey)
        .then((res) => {
          setCode(res.data.data.code)
        })
        .catch(() => {
          message.error('加载策略代码失败')
          setCode('')
        })
        .finally(() => setLoading(false))
    } else {
      // 预置策略，显示代码（编程模式可见）
      const presetCode = getPresetStrategyCode(selectedKey)
      setCode(presetCode)
    }
  }, [selectedKey, strategies])

  // 获取预置策略的代码（用于展示）
  const getPresetStrategyCode = (key: string): string => {
    return PRESET_STRATEGY_CODES[key] || '# 预置策略代码不可见'
  }

  // 选股类（screening）预置策略：引导到实时选股池配置
  const selectedScreening = strategies.find((s) => s.key === selectedKey)?.category === 'screening'

  // 保存策略
  const handleSave = async () => {
    if (!selectedKey) {
      message.warning('请先输入策略key')
      return
    }
    
    // 检查是否为预置策略
    const strategy = strategies.find((s) => s.key === selectedKey)
    if (strategy && strategy.type !== 'custom') {
      message.error('不能覆盖预置策略，请使用新的key')
      return
    }
    
    setSaving(true)
    try {
      await saveCustomStrategy(selectedKey, code)
      message.success('策略保存成功')
      loadStrategies() // 刷新列表
    } catch (e: any) {
      const detail = e?.response?.data?.detail
      message.error(detail || '保存失败')
    } finally {
      setSaving(false)
    }
  }

  // 删除策略（自定义 Python / 可视化规则）
  const handleDelete = async () => {
    if (!selectedKey) return
    const strategy = strategies.find((s) => s.key === selectedKey)
    try {
      if (strategy?.category === 'visual') {
        await deleteVisualRule(selectedKey)
      } else {
        await deleteCustomStrategy(selectedKey)
      }
      message.success('策略删除成功')
      setSelectedKey('')
      setCode('')
      loadStrategies() // 刷新列表
    } catch (e: any) {
      const detail = e?.response?.data?.detail
      message.error(detail || '删除失败')
    }
  }

  // 创建新策略
  const handleNew = (templateKey: string) => {
    if (templateKey === 'visual') {
      setSelectedKey('')
      setCode('')
      setEditMode('visual')
      message.info('已新建「可视化策略」，请在右侧输入策略key并添加条件后保存')
      return
    }
    const template = STRATEGY_TEMPLATES[templateKey as keyof typeof STRATEGY_TEMPLATES]
    if (!template) return
    
    setSelectedKey('')
    setCode(template.code)
    setEditMode('code')
    message.info(`已创建 "${template.name}" 模板，请修改策略key后保存`)
  }

  // 自定义策略列表
  const customStrategies = strategies.filter((s) => s.type === 'custom')
  const presetStrategies = strategies.filter((s) => s.type === 'preset')

  return (
    <div>
      <Title level={3}>策略编辑器</Title>
      <Paragraph type="secondary">
        编写自定义Python策略代码，支持Backtrader框架。保存后可在回测页面选择使用。
        预置策略的代码在编程模式下可见。
      </Paragraph>

      <Layout style={{ marginTop: 16, height: 'calc(100vh - 250px)' }}>
        <Splitter>
          {/* 左侧：策略列表 */}
          <Splitter.Panel defaultSize={250} min={200} max={400}>
            <Card 
              title="策略列表" 
              size="small"
              extra={
                <Select
                  value=""
                  onChange={handleNew}
                  style={{ width: 120 }}
                  placeholder="新建策略"
                  options={[
                    { value: 'visual', label: '可视化策略' },
                    { value: 'empty', label: '空模板' },
                    { value: 'dual_ma', label: '双均线模板' },
                  ]}
                />
              }
              style={{ height: '100%', overflow: 'auto' }}
            >
              {presetStrategies.length > 0 && (
                <div style={{ marginBottom: 16 }}>
                  <Text strong>预置策略</Text>
                  {presetStrategies.map((s) => (
                    <div
                      key={s.key}
                      onClick={() => setSelectedKey(s.key)}
                      style={{
                        padding: '8px 12px',
                        cursor: 'pointer',
                        backgroundColor: selectedKey === s.key ? token.controlItemBgActive : 'transparent',
                        borderRadius: 4,
                        marginBottom: 4,
                      }}
                    >
                      {s.name}
                    </div>
                  ))}
                </div>
              )}

              {customStrategies.length > 0 && (
                <div>
                  <Text strong>自定义策略</Text>
                  {customStrategies.map((s) => (
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
                      <span>{s.name}</span>
                      {s.category === 'visual' && <Tag color="purple" style={{ marginRight: 0 }}>可视化</Tag>}
                    </div>
                  ))}
                </div>
              )}

              {customStrategies.length === 0 && presetStrategies.length === 0 && (
                <Empty description="暂无策略" />
              )}
            </Card>
          </Splitter.Panel>

          {/* 右侧：代码编辑器 / 可视化编辑器 */}
          <Splitter.Panel>
            {editMode === 'visual' ? (
              <Card
                title="可视化策略编辑器"
                style={{ height: '100%' }}
                bodyStyle={{ height: 'calc(100% - 56px)', padding: 0 }}
                extra={
                  <Radio.Group
                    value={editMode}
                    onChange={(e) => setEditMode(e.target.value)}
                    size="small"
                  >
                    <Radio.Button value="code"><CodeOutlined /> 编程模式</Radio.Button>
                    <Radio.Button value="visual"><AimOutlined /> 可视化模式</Radio.Button>
                  </Radio.Group>
                }
              >
                <VisualEditor
                  ruleKey={selectedKey}
                  ruleName={strategies.find((s) => s.key === selectedKey)?.name || ''}
                  onSaved={() => loadStrategies()}
                  onKeyChange={(k) => setSelectedKey(k)}
                />
              </Card>
            ) : (
              <Card
                title={
                  selectedKey
                    ? `编辑策略: ${selectedKey}`
                    : '新策略（请输入策略key并保存）'
                }
                extra={
                  <Space>
                    {/* 编辑模式切换 */}
                    <Radio.Group
                      value={editMode}
                      onChange={(e) => setEditMode(e.target.value)}
                      size="small"
                    >
                      <Radio.Button value="code"><CodeOutlined /> 编程模式</Radio.Button>
                      <Radio.Button value="visual"><AimOutlined /> 可视化模式</Radio.Button>
                    </Radio.Group>

                    <Input
                      placeholder="策略key（如 my_strategy）"
                      value={selectedKey}
                      onChange={(e) => setSelectedKey(e.target.value)}
                      style={{ width: 200 }}
                    />
                    <Button
                      type="primary"
                      icon={<SaveOutlined />}
                      loading={saving}
                      onClick={handleSave}
                    >
                      保存
                    </Button>
                    {selectedKey && strategies.find((s) => s.key === selectedKey)?.type === 'custom' && (
                      <Popconfirm title="确认删除该策略？" onConfirm={handleDelete}>
                        <Button danger icon={<DeleteOutlined />}>
                          删除
                        </Button>
                      </Popconfirm>
                    )}
                  </Space>
                }
                style={{ height: '100%' }}
                bodyStyle={{ height: 'calc(100% - 56px)', padding: 0 }}
              >
                {editMode === 'code' ? (
                  /* 编程模式：Monaco Editor */
                  <div style={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
                    {selectedScreening && (
                      <Alert
                        type="info"
                        showIcon
                        style={{ margin: 8 }}
                        message="这是「选股类」预置策略"
                        description="该类策略只用于实时选股池 / 盘中监控，不在回测中运行。实际参数（CCI阈值、MACD零线带宽、成交额、选股周期等）请在左侧菜单「实时选股池」页面通过可视化因子面板配置；下方为策略规范代码，仅供查看，不可修改。"
                      />
                    )}
                    <div style={{ flex: 1, minHeight: 0 }}>
                    <Editor
                      height="100%"
                      language="python"
                      theme="vs-dark"
                      value={code}
                      onChange={(val) => setCode(val || '')}
                      options={{
                        fontSize: 14,
                        fontFamily: 'Consolas, "Courier New", monospace',
                        minimap: { enabled: false },
                        scrollBeyondLastLine: false,
                        automaticLayout: true,
                        tabSize: 4,
                        wordWrap: 'on',
                        readOnly: loading || (selectedKey !== '' && strategies.find((s) => s.key === selectedKey)?.type !== 'custom'),
                      }}
                    />
                    </div>
                    </div>
                ) : (
                  <div style={{ height: 'calc(100% - 50px)', display: 'flex', justifyContent: 'center', alignItems: 'center' }}>
                    <Empty description="可视化拖拽编辑模式正在开发中..." />
                  </div>
                )}
              </Card>
            )}
          </Splitter.Panel>
        </Splitter>
      </Layout>

      <Card style={{ marginTop: 16 }} title="Backtrader策略编写指南">
        <Paragraph>
          <ul>
            <li>策略必须继承 <Text code>bt.Strategy</Text></li>
            <li>在 <Text code>__init__</Text> 中定义指标（如均线、MACD等）</li>
            <li>在 <Text code>next</Text> 中编写交易逻辑（使用 <Text code>self.buy()</Text> 和 <Text code>self.close()</Text>）</li>
            <li>使用 <Text code># Name:</Text> 和 <Text code># Description:</Text> 注释来定义策略名称和描述</li>
            <li>保存后，在"回测"页面可以选择该策略进行回测</li>
            <li><Text strong>编程模式</Text>：使用Monaco编辑器编写Python代码，预置策略的代码也可见</li>
            <li><Text strong>可视化模式</Text>：通过拖拽模块构建策略（正在开发）</li>
          </ul>
        </Paragraph>
      </Card>
    </div>
  )
}
