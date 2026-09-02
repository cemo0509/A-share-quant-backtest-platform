import { useEffect, useState, useMemo } from 'react'
import { Card, Form, Input, InputNumber, Button, Select, DatePicker, Space, message, Spin, Table, Tag, Typography, Alert, Row, Col, Tabs } from 'antd'
import dayjs from 'dayjs'
import { getStrategies, runOptimize, getOptimizeMetrics, type OptimizeResultItem } from '../services/api'
import { useNavigate } from 'react-router-dom'
import type { StrategyItem } from '../types'

const { RangePicker } = DatePicker
const { Title, Text } = Typography

const { TextArea } = Input

// 参数敏感性热力图（P0-8 第二步）：以两个参数做轴，颜色深浅表示指标强弱
function HeatmapView({ heatmap, heatX, heatY, heatMetric, bestParams }: {
  heatmap: { xVals: number[]; yVals: number[]; cellMap: Map<string, OptimizeResultItem>; min: number; max: number; metricOf: (r: OptimizeResultItem) => number }
  heatX: string
  heatY: string
  heatMetric: string
  bestParams: Record<string, number> | null
}) {
  const { xVals, yVals, cellMap, min, max, metricOf } = heatmap
  const cellHead = { padding: '4px 8px', fontSize: 12, color: '#666', fontWeight: 500, background: '#fafafa' }
  const color = (v: number) => {
    if (!isFinite(v) || max === min) return 'hsl(140, 60%, 45%)'
    const t = (v - min) / (max - min)
    // 低(蓝 220°) → 高(红 0°)
    return `hsl(${Math.round((1 - t) * 220)}, 72%, 48%)`
  }
  return (
    <div style={{ overflowX: 'auto' }}>
      <table style={{ borderCollapse: 'collapse' }}>
        <thead>
          <tr>
            <th style={cellHead}></th>
            {xVals.map((x) => (
              <th key={`x${x}`} style={cellHead}>{x}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {yVals.map((y) => (
            <tr key={`y${y}`}>
              <th style={cellHead}>{y}</th>
              {xVals.map((x) => {
                const r = cellMap.get(`${x}|${y}`)
                if (!r) return <td key={`c${x}`} style={{ background: '#f0f0f0', width: 64, height: 40 }} />
                const v = metricOf(r)
                const isBest = !!bestParams && r.params[heatX] === bestParams[heatX] && r.params[heatY] === bestParams[heatY]
                return (
                  <td key={`c${x}`}
                    title={`${heatX}=${x}, ${heatY}=${y}\n${heatMetric}: ${v.toFixed(2)}`}
                    style={{
                      width: 64, height: 40, textAlign: 'center', fontSize: 11,
                      background: color(v),
                      border: isBest ? '2px solid gold' : '1px solid #fff',
                      color: '#fff', fontWeight: isBest ? 700 : 400,
                    }}>
                    {v.toFixed(2)}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function Optimize() {
  const [strategies, setStrategies] = useState<StrategyItem[]>([])
  const [selectedKey, setSelectedKey] = useState<string>('')
  const [paramGridText, setParamGridText] = useState<string>('')
  const [results, setResults] = useState<OptimizeResultItem[]>([])
  const [bestParams, setBestParams] = useState<Record<string, number> | null>(null)
  // 样本外验证结果（P0-8）
  const [validation, setValidation] = useState<any>(null)
  const [loading, setLoading] = useState(false)
  const [metricOptions, setMetricOptions] = useState<{ key: string; name: string }[]>([])
  const [form] = Form.useForm()
  const navigate = useNavigate()

  // 参数敏感性热力图（P0-8 第二步）：用两个参数做轴，颜色表示指标强弱
  const [heatX, setHeatX] = useState<string>('')
  const [heatY, setHeatY] = useState<string>('')
  const [heatMetric, setHeatMetric] = useState<string>('sharpe_ratio')

  const paramNames = results.length ? Object.keys(results[0].params) : []
  useEffect(() => {
    if (paramNames.length >= 2 && !heatX) setHeatX(paramNames[0])
    if (paramNames.length >= 2 && !heatY) setHeatY(paramNames[1])
  }, [paramNames, heatX, heatY])

  const heatmap = useMemo(() => {
    if (!heatX || !heatY || !results.length) return null
    const otherParams = paramNames.filter((p) => p !== heatX && p !== heatY)
    const fixed = (bestParams || results[0].params) as Record<string, number>
    const slice = results.filter((r) =>
      otherParams.every((p) => r.params[p] === fixed[p])
    )
    if (!slice.length) return null
    const xVals = Array.from(new Set(slice.map((r) => r.params[heatX]))).sort((a, b) => a - b)
    const yVals = Array.from(new Set(slice.map((r) => r.params[heatY]))).sort((a, b) => a - b)
    const cellMap = new Map<string, OptimizeResultItem>()
    slice.forEach((r) => cellMap.set(`${r.params[heatX]}|${r.params[heatY]}`, r))
    const metricOf = (r: OptimizeResultItem): number => {
      if (heatMetric === 'total_return') return r.total_return
      if (heatMetric === 'annual_return') return r.annual_return
      if (heatMetric === 'sharpe_ratio') return r.sharpe_ratio
      if (heatMetric === 'max_drawdown') return r.max_drawdown
      if (heatMetric === 'win_rate') return r.win_rate
      return r.metric_value
    }
    const vals = slice.map(metricOf)
    const min = Math.min(...vals)
    const max = Math.max(...vals)
    return { xVals, yVals, cellMap, min, max, metricOf }
  }, [heatX, heatY, heatMetric, results, bestParams, paramNames])

  useEffect(() => {
    getStrategies()
      .then((res) => {
        const list = res.data.data || []
        setStrategies(list)
        if (list.length) setSelectedKey(list[0].key)
      })
      .catch(() => message.warning('策略列表加载失败'))

    getOptimizeMetrics()
      .then((res) => setMetricOptions(res.data.data || []))
      .catch(() => setMetricOptions([
        { key: 'sharpe_ratio', name: '夏普比率' },
        { key: 'total_return', name: '总收益率' },
        { key: 'max_drawdown', name: '最大回撤' },
      ]))
  }, [])

  const currentStrategy = strategies.find((s) => s.key === selectedKey)

  // 生成参数网格的占位符
  const getParamGridPlaceholder = () => {
    if (!currentStrategy) return ''
    return currentStrategy.params
      .map((p) => `"${p.name}": [${p.min ?? 0}, ${Math.round(((p.min ?? 0) + (p.max ?? 100)) / 2)}, ${p.max ?? 100}]`)
      .join('\n')
  }

  // F-04：参数网格可视化编辑（此前只能手写 JSON，容易格式错误）。
  // 为每个策略参数提供「最小值 / 最大值 / 取值个数」，自动生成等间隔组合；
  // 同时保留 JSON 模式供高级用法（如非等间隔、手工指定取值）。
  const [gridMode, setGridMode] = useState<'visual' | 'json'>('visual')
  const [visualGrid, setVisualGrid] = useState<Record<string, { min: number; max: number; count: number }>>({})

  // 切换策略时，按该策略参数的默认区间初始化可视化网格
  useEffect(() => {
    if (!currentStrategy) return
    const init: Record<string, { min: number; max: number; count: number }> = {}
    currentStrategy.params.forEach((p) => {
      init[p.name] = { min: p.min ?? 0, max: p.max ?? 100, count: 3 }
    })
    setVisualGrid(init)
  }, [currentStrategy])

  // 按「最小值 / 最大值 / 个数」生成等间隔取值；整数型参数自动取整
  const buildGridFromVisual = (): Record<string, number[]> => {
    const grid: Record<string, number[]> = {}
    Object.entries(visualGrid).forEach(([name, cfg]) => {
      const n = Math.max(1, Math.floor(cfg.count || 1))
      if (n === 1) {
        grid[name] = [cfg.min]
        return
      }
      const step = (cfg.max - cfg.min) / (n - 1)
      const p = currentStrategy?.params.find((x) => x.name === name)
      const isFloat = p?.type === 'float'
      grid[name] = Array.from({ length: n }, (_, i) => {
        const v = cfg.min + step * i
        return isFloat ? Number(v.toFixed(4)) : Math.round(v)
      })
    })
    return grid
  }

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()

      let paramGrid: Record<string, number[]>
      if (gridMode === 'visual') {
        paramGrid = buildGridFromVisual()
        if (!Object.keys(paramGrid).length) {
          message.error('请至少配置一个参数的取值范围')
          return
        }
      } else {
        if (!paramGridText.trim()) {
          message.error('请输入参数网格')
          return
        }
        try {
          paramGrid = JSON.parse(paramGridText)
        } catch {
          message.error('参数网格 JSON 格式错误')
          return
        }
      }

      const totalCombos = Object.values(paramGrid).reduce((acc, vals) => acc * vals.length, 1)
      if (totalCombos > 100) {
        if (!window.confirm(`参数组合共 ${totalCombos} 组，可能需要较长时间，确认继续？`)) {
          return
        }
      }

      setLoading(true)
      setResults([])
      setBestParams(null)

      const req = {
        strategy: selectedKey,
        symbol: values.symbol,
        start_date: values.range[0].format('YYYYMMDD'),
        end_date: values.range[1].format('YYYYMMDD'),
        param_grid: paramGrid,
        cash: values.cash,
        commission: values.commission,
        slippage: values.slippage,
        metric: values.metric,
      }

      const res = await runOptimize(req)
      const responseData = res.data
      // responseData 结构: { status, data: OptimizeResultItem[], best_params, best_metric_value }
      const resultsList = responseData.data || []
      setResults(resultsList)
      setBestParams(responseData.best_params || null)
      // 样本外验证结果（P0-8 过拟合防护）
      setValidation(responseData.validation || null)

      if (resultsList.length) {
        message.success(`优化完成，共 ${resultsList.length} 组参数`)
      } else {
        message.warning('没有产生有效结果')
      }
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '优化失败')
    } finally {
      setLoading(false)
    }
  }

  const columns = [
    { title: '排名', key: 'rank', width: 60, render: (_: any, __: any, idx: number) => idx + 1 },
    {
      title: '参数组合',
      key: 'params',
      render: (_: any, rec: OptimizeResultItem) => (
        <span>{Object.entries(rec.params).map(([k, v]) => `${k}=${v}`).join(', ')}</span>
      ),
    },
    { title: '目标值', dataIndex: 'metric_value', key: 'metric_value', render: (v: number) => v.toFixed(4) },
    { title: '总收益%', dataIndex: 'total_return', key: 'total_return', render: (v: number) => `${v.toFixed(2)}%` },
    { title: '年化%', dataIndex: 'annual_return', key: 'annual_return', render: (v: number) => `${v.toFixed(2)}%` },
    { title: '夏普', dataIndex: 'sharpe_ratio', key: 'sharpe_ratio', render: (v: number) => v.toFixed(2) },
    { title: '最大回撤%', dataIndex: 'max_drawdown', key: 'max_drawdown', render: (v: number) => `${Math.abs(v).toFixed(2)}%` },
    { title: '胜率%', dataIndex: 'win_rate', key: 'win_rate', render: (v: number) => `${v.toFixed(1)}%` },
    { title: '交易数', dataIndex: 'total_trades', key: 'total_trades' },
    // F-01：每组参数标注 mock / 真实行情，mock 行的指标不可信
    {
      title: '数据源',
      key: 'data_source',
      width: 110,
      render: (_: any, rec: OptimizeResultItem) => {
        const src = rec.data_source || 'unknown'
        if (src === 'real') return <Tag color="green">真实行情</Tag>
        if (src === 'mock') return <Tag color="orange">模拟数据</Tag>
        return <Tag>{src}</Tag>
      },
    },
  ]

  return (
    <Spin spinning={loading}>
      <Title level={3}>参数优化扫描</Title>
      <Alert
        type="info"
        showIcon
        message="功能说明"
        description="设置参数网格（JSON格式），系统将遍历所有参数组合并运行回测，按优化目标排序找出最优参数。"
        style={{ marginBottom: 16 }}
      />

      <Card title="优化配置">
        <Form form={form} layout="vertical" initialValues={{
          symbol: '000001',
          range: [dayjs('2023-01-01'), dayjs('2024-12-31')],
          cash: 1000000,
          commission: 0.0003,
          slippage: 0.001,
          metric: 'sharpe_ratio',
        }}>
          <Row gutter={16}>
            <Col span={6}>
              <Form.Item label="股票代码" name="symbol" rules={[{ required: true }]}>
                <Input placeholder="如 000001" />
              </Form.Item>
            </Col>
            <Col span={8}>
              <Form.Item label="回测区间" name="range" rules={[{ required: true }]}>
                <RangePicker style={{ width: '100%' }} />
              </Form.Item>
            </Col>
            <Col span={4}>
              <Form.Item label="初始资金" name="cash">
                <InputNumber style={{ width: '100%' }} min={10000} step={100000} />
              </Form.Item>
            </Col>
            <Col span={3}>
              <Form.Item label="佣金率" name="commission">
                <InputNumber style={{ width: '100%' }} step={0.0001} min={0} />
              </Form.Item>
            </Col>
            <Col span={3}>
              <Form.Item label="滑点" name="slippage">
                <InputNumber style={{ width: '100%' }} step={0.001} min={0} />
              </Form.Item>
            </Col>
          </Row>

          <Form.Item label="选择策略">
            <Select
              value={selectedKey}
              onChange={setSelectedKey}
              options={strategies.map((s) => ({ value: s.key, label: `${s.name} — ${s.description}` }))}
            />
          </Form.Item>

          <Form.Item label="优化目标" name="metric">
            <Select
              options={metricOptions.map((m) => ({ value: m.key, label: m.name }))}
            />
          </Form.Item>

          <Form.Item label="参数网格">
            <Tabs
              activeKey={gridMode}
              onChange={(k) => setGridMode(k as 'visual' | 'json')}
              items={[
                {
                  key: 'visual',
                  label: '可视化',
                  children: currentStrategy && currentStrategy.params.length > 0 ? (
                    <div>
                      {currentStrategy.params.map((p) => {
                        const cfg = visualGrid[p.name] || { min: p.min ?? 0, max: p.max ?? 100, count: 3 }
                        const setCfg = (patch: Partial<typeof cfg>) =>
                          setVisualGrid({ ...visualGrid, [p.name]: { ...cfg, ...patch } })
                        return (
                          <Row key={p.name} gutter={8} style={{ marginBottom: 8, alignItems: 'center' }}>
                            <Col span={6}><Text>{p.label || p.name}</Text></Col>
                            <Col span={5}>
                              <InputNumber style={{ width: '100%' }} value={cfg.min}
                                onChange={(v) => setCfg({ min: v as number })} />
                            </Col>
                            <Col span={5}>
                              <InputNumber style={{ width: '100%' }} value={cfg.max}
                                onChange={(v) => setCfg({ max: v as number })} />
                            </Col>
                            <Col span={5}>
                              <InputNumber style={{ width: '100%' }} value={cfg.count} min={1} max={20}
                                precision={0} onChange={(v) => setCfg({ count: v as number })} />
                            </Col>
                            <Col span={3}>
                              <Text type="secondary" style={{ fontSize: 12 }}>
                                {Math.max(1, Math.floor(cfg.count || 1))} 个取值
                              </Text>
                            </Col>
                          </Row>
                        )
                      })}
                      <Text type="secondary" style={{ fontSize: 12 }}>
                        填「最小值 / 最大值 / 取值个数」即可自动生成等间隔组合；切换策略会自动填入该策略的默认区间。
                      </Text>
                    </div>
                  ) : (
                    <Text type="secondary">请先在上方选择策略</Text>
                  ),
                },
                {
                  key: 'json',
                  label: 'JSON',
                  children: (
                    <div>
                      <TextArea
                        value={paramGridText}
                        onChange={(e) => setParamGridText(e.target.value)}
                        placeholder={getParamGridPlaceholder()}
                        autoSize={{ minRows: 3, maxRows: 6 }}
                      />
                      {currentStrategy && (
                        <Text type="secondary" style={{ fontSize: 12 }}>
                          示例（{currentStrategy.name}）：每行一个参数，值为数组
                        </Text>
                      )}
                    </div>
                  ),
                },
              ]}
            />
          </Form.Item>

          <Space>
            <Button type="primary" onClick={handleSubmit} loading={loading}>
              开始优化
            </Button>
          </Space>
        </Form>
      </Card>

      {/* F-01 决策风险防护：任一组参数为 mock，则该「最优参数」不构成决策依据，
          用户看到的是基于随机行情拟合的噪声，不是真实市场规律 */}
      {results.some((r) => r.data_source === 'mock') && (
        <Alert
          type="error"
          showIcon
          style={{ marginTop: 16 }}
          message="本次参数优化包含模拟数据，最优参数不可信"
          description="部分参数组合是在真实行情获取失败后用随机生成的模拟 K 线跑出来的，对应的收益/夏普等指标不反映任何真实市场规律。请检查网络后重跑，或只采纳数据源列为「真实行情」的那些参数组合。"
        />
      )}

      {bestParams && (
        <Card title="最优参数" style={{ marginTop: 16 }} size="small">
          <Space>
            {Object.entries(bestParams).map(([k, v]) => (
              <Tag color="green" key={k}>{k} = {v}</Tag>
            ))}
          </Space>
        </Card>
      )}

      {/* 样本外验证（P0-8 过拟合防护）：
          网格搜索总能找到一组历史最优，但那大概率是过拟合。
          这里把样本内/样本外表现并列，衰减严重时高亮告警。 */}
      {validation && (
        <Card title="样本外验证（过拟合检测）" style={{ marginTop: 16 }} size="small">
          {!validation.enabled ? (
            <Alert
              type="info"
              showIcon
              message="未执行样本外验证"
              description={validation.reason || '数据量不足或切分失败'}
            />
          ) : (
            <>
              <Alert
                type={
                  validation.warning_level === 'danger' ? 'error'
                    : validation.warning_level === 'warn' ? 'warning' : 'success'
                }
                showIcon
                style={{ marginBottom: 12 }}
                message={
                  validation.overfit_warning
                    ? `检测到过拟合风险（${validation.warning_level === 'danger' ? '严重' : '警告'}）`
                    : '未检测到明显过拟合'
                }
                description={validation.warning_message}
              />
              <Row gutter={16}>
                <Col span={8}>
                  <Card size="small" title="样本内（用于调参）">
                    <div><Text type="secondary">区间：</Text>{validation.train_range}</div>
                    <div>总收益：<Text strong>{validation.in_sample?.total_return?.toFixed(2)}%</Text></div>
                    <div>年化：{validation.in_sample?.annual_return?.toFixed(2)}%</div>
                    <div>夏普：{validation.in_sample?.sharpe_ratio ?? '—'}</div>
                    <div>回撤：{validation.in_sample?.max_drawdown?.toFixed(2)}%</div>
                  </Card>
                </Col>
                <Col span={8}>
                  <Card size="small" title="样本外（未参与调参）">
                    <div><Text type="secondary">区间：</Text>{validation.test_range}</div>
                    <div>总收益：<Text strong>{validation.out_sample?.total_return?.toFixed(2)}%</Text></div>
                    <div>年化：{validation.out_sample?.annual_return?.toFixed(2)}%</div>
                    <div>夏普：{validation.out_sample?.sharpe_ratio ?? '—'}</div>
                    <div>回撤：{validation.out_sample?.max_drawdown?.toFixed(2)}%</div>
                  </Card>
                </Col>
                <Col span={8}>
                  <Card size="small" title="保持率（样本外/样本内）">
                    {(() => {
                      const r = validation.retention || {}
                      const pct = (v: any) => (v === null || v === undefined ? '—' : `${(v * 100).toFixed(1)}%`)
                      return (
                        <>
                          <div>收益保持：<Text strong>{pct(r.total_return)}</Text></div>
                          <div>年化保持：{pct(r.annual_return)}</div>
                          <div>夏普保持：{pct(r.sharpe_ratio)}</div>
                          <div style={{ marginTop: 8 }}>
                            <Text type="secondary" style={{ fontSize: 12 }}>
                              保持率低于 60% 提示衰减，低于 30% 判定为严重过拟合
                            </Text>
                          </div>
                        </>
                      )
                    })()}
                  </Card>
                </Col>
              </Row>
              <div style={{ marginTop: 8 }}>
                <Text type="secondary" style={{ fontSize: 12 }}>
                  切分方式：按时间顺序前 {Math.round((validation.train_ratio ?? 0.7) * 100)}% 用于调参，
                  后 {100 - Math.round((validation.train_ratio ?? 0.7) * 100)}% 完全不参与调参，仅用于检验。
                </Text>
              </div>
            </>
          )}
        </Card>
      )}

      {paramNames.length >= 2 && heatmap && (
        <Card title="参数敏感性热力图" style={{ marginTop: 16 }} size="small">
          <div style={{ marginBottom: 12, display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center' }}>
            <span>横轴：</span>
            <Select value={heatX} onChange={setHeatX} style={{ width: 150 }}
              options={paramNames.map((p) => ({ value: p, label: p }))} />
            <span>纵轴：</span>
            <Select value={heatY} onChange={setHeatY} style={{ width: 150 }}
              options={paramNames.map((p) => ({ value: p, label: p }))} />
            <span>配色指标：</span>
            <Select value={heatMetric} onChange={setHeatMetric} style={{ width: 150 }}
              options={[
                { value: 'sharpe_ratio', label: '夏普比率' },
                { value: 'total_return', label: '总收益率' },
                { value: 'annual_return', label: '年化收益' },
                { value: 'max_drawdown', label: '最大回撤' },
                { value: 'win_rate', label: '胜率' },
              ]} />
          </div>
          <HeatmapView heatmap={heatmap} heatX={heatX} heatY={heatY} heatMetric={heatMetric} bestParams={bestParams} />
          <div style={{ marginTop: 8, fontSize: 12, color: '#888' }}>
            其余参数固定为最优组合取值；颜色蓝→红表示该指标由低到高。金色边框为全局最优参数所在单元格。
          </div>
        </Card>
      )}

      {results.length > 0 && (
        <Card title={`优化结果（${results.length} 组）`} style={{ marginTop: 16 }}>
          <Table
            columns={columns}
            dataSource={results}
            rowKey={(_, idx) => String(idx)}
            size="small"
            scroll={{ y: 500 }}
            pagination={{ pageSize: 20, showSizeChanger: true }}
          />
        </Card>
      )}
    </Spin>
  )
}
