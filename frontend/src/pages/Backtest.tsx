import { useEffect, useState } from 'react'
import { Card, Form, Input, InputNumber, Button, Select, DatePicker, Space, message, Spin, Row, Col } from 'antd'
import dayjs from 'dayjs'
import { getStrategies, runBacktest, type BacktestReq } from '../api'
import { useStore } from '../stores'
import MetricsPanel from '../components/MetricsPanel'
import { useNavigate } from 'react-router-dom'
import type { StrategyItem } from '../types'

const { RangePicker } = DatePicker

export default function Backtest() {
  const [strategies, setStrategies] = useState<StrategyItem[]>([])
  const [selectedKey, setSelectedKey] = useState<string>('')
  const [paramValues, setParamValues] = useState<Record<string, number>>({})
  const [form] = Form.useForm()
  const { loading, setLoading, setResult, result } = useStore()
  const navigate = useNavigate()

  useEffect(() => {
    getStrategies()
      .then((res) => {
        const list = res.data.data || []
        // v3.0: 只显示 trading 和 hybrid 策略
        const tradingList = list.filter(
          (s: StrategyItem) => s.category === 'trading' || s.category === 'hybrid'
        )
        setStrategies(tradingList.length > 0 ? tradingList : list)
        if (tradingList.length) {
          setSelectedKey(tradingList[0].key)
          initParams(tradingList[0])
        }
      })
      .catch(() => message.warning('策略列表加载失败，请确认后端已启动'))
  }, [])

  const initParams = (s: StrategyItem) => {
    const pv: Record<string, number> = {}
    s.params.forEach((p) => (pv[p.name] = p.default))
    setParamValues(pv)
  }

  const onSelectStrategy = (key: string) => {
    setSelectedKey(key)
    const s = strategies.find((x) => x.key === key)
    if (s) initParams(s)
  }

  const currentStrategy = strategies.find((s) => s.key === selectedKey)

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      const req: BacktestReq = {
        strategy: selectedKey,
        symbol: values.symbol,
        start_date: values.range[0].format('YYYYMMDD'),
        end_date: values.range[1].format('YYYYMMDD'),
        params: paramValues,
        cash: values.cash,
        commission: values.commission,
        slippage: values.slippage,
        adjust: values.adjust,
      }
      setLoading(true)
      const res = await runBacktest(req)
      setResult(res.data.data)
      message.success('回测完成')
      navigate('/results')
    } catch (e: any) {
      const detail = e?.response?.data?.detail
      const msg = detail || (e?.code === 'ERR_NETWORK' ? '网络连接失败，请检查后端是否已启动' : '回测失败')
      message.error(msg)
    } finally {
      setLoading(false)
    }
  }

  return (
    <Spin spinning={loading}>
      <Card title="回测配置">
        <Form
          form={form}
          layout="vertical"
          initialValues={{
            symbol: '000001',
            range: [dayjs('2024-01-01'), dayjs('2025-06-30')],
            cash: 1000000,
            commission: 0.0003,
            slippage: 0.001,
            adjust: 'qfq',
          }}
        >
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
            <Col span={3}>
              <Form.Item label="复权方式" name="adjust" tooltip="前复权：以最新价为基准调整历史价（推荐）；后复权：以上市价为基准；不复权：原始价格">
                <Select
                  options={[
                    { value: 'qfq', label: '前复权' },
                    { value: 'hfq', label: '后复权' },
                    { value: '', label: '不复权' },
                  ]}
                />
              </Form.Item>
            </Col>
          </Row>

          <Form.Item label="选择策略">
            <Select
              value={selectedKey}
              onChange={onSelectStrategy}
              options={strategies.map((s) => ({ value: s.key, label: `${s.name} — ${s.description}` }))}
            />
          </Form.Item>

          {currentStrategy && currentStrategy.params.length > 0 && (
            <Card size="small" title={`${currentStrategy.name} 参数`} style={{ marginBottom: 16 }}>
              <Row gutter={16}>
                {currentStrategy.params.map((p) => (
                  <Col span={6} key={p.name}>
                    <Form.Item label={p.label}>
                      <InputNumber
                        style={{ width: '100%' }}
                        value={paramValues[p.name]}
                        min={p.min}
                        max={p.max}
                        step={p.type === 'float' ? 0.1 : 1}
                        onChange={(v) => setParamValues({ ...paramValues, [p.name]: v as number })}
                      />
                    </Form.Item>
                  </Col>
                ))}
              </Row>
            </Card>
          )}

          <Space>
            <Button type="primary" onClick={handleSubmit}>
              运行回测
            </Button>
          </Space>
        </Form>
      </Card>

      {result && (
        <Card title="最近回测指标" style={{ marginTop: 16 }}>
          <MetricsPanel />
        </Card>
      )}
    </Spin>
  )
}
