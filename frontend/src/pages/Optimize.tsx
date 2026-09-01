import { useEffect, useState } from 'react'
import { Card, Form, Input, InputNumber, Button, Select, DatePicker, Space, message, Spin, Table, Tag, Typography, Alert, Row, Col } from 'antd'
import dayjs from 'dayjs'
import { getStrategies, runOptimize, getOptimizeMetrics, type OptimizeResultItem } from '../services/api'
import { useNavigate } from 'react-router-dom'
import type { StrategyItem } from '../types'

const { RangePicker } = DatePicker
const { Title, Text } = Typography

const { TextArea } = Input

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

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      if (!paramGridText.trim()) {
        message.error('请输入参数网格')
        return
      }

      let paramGrid: Record<string, number[]>
      try {
        paramGrid = JSON.parse(paramGridText)
      } catch {
        message.error('参数网格 JSON 格式错误')
        return
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

          <Form.Item label="参数网格（JSON格式）">
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
          </Form.Item>

          <Space>
            <Button type="primary" onClick={handleSubmit} loading={loading}>
              开始优化
            </Button>
          </Space>
        </Form>
      </Card>

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
