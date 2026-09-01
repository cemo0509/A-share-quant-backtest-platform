import { useEffect, useState } from 'react'
import {
  Card, Form, Input, InputNumber, Button, Select, DatePicker, Space, message,
  Spin, Row, Col, Tooltip, Typography,
} from 'antd'
import dayjs from 'dayjs'
import {
  getStrategies, runBacktest, type BacktestReq, POSITION_SIZING_OPTIONS,
} from '../api'
import { useStore } from '../stores'
import MetricsPanel from '../components/MetricsPanel'
import { useNavigate } from 'react-router-dom'
import type { StrategyItem } from '../types'

const { RangePicker } = DatePicker
const { Text } = Typography

export default function Backtest() {
  const [strategies, setStrategies] = useState<StrategyItem[]>([])
  const [selectedKey, setSelectedKey] = useState<string>('')
  const [paramValues, setParamValues] = useState<Record<string, number>>({})
  const [form] = Form.useForm()
  const { loading, setLoading, setResult, result } = useStore()
  const navigate = useNavigate()
  // 当前选择的仓位管理模式（用于条件显示对应参数）
  const sizingMode = Form.useWatch('position_sizing', form) || 'allin'
  const showPositionPercent = sizingMode === 'allin' || sizingMode === 'fixed' || sizingMode === 'volatility'

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
        // 仓位管理
        position_sizing: values.position_sizing,
        position_percent: values.position_percent,
        max_position: (values.max_position ?? 95) / 100,
        risk_percent: (values.risk_percent ?? 1) / 100,
        atr_multiplier: values.atr_multiplier,
        target_volatility: (values.target_volatility ?? 15) / 100,
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
            position_sizing: 'allin',
            position_percent: 95,
            max_position: 95,
            risk_percent: 1,
            atr_multiplier: 2,
            target_volatility: 15,
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

          {/* 仓位管理：接入 core.position_sizer（此前该模块已实现但引擎未引用） */}
          <Card
            size="small"
            title="仓位管理"
            style={{ marginBottom: 16 }}
            extra={
              <Text type="secondary" style={{ fontSize: 12 }}>
                控制每次买入使用多少资金
              </Text>
            }
          >
            <Row gutter={16}>
              <Col span={6}>
                <Form.Item label="仓位模式" name="position_sizing" tooltip="满仓=按百分比建仓；ATR=单笔亏损不超风险比例；目标波动率=波动越大仓位越小">
                  <Select options={POSITION_SIZING_OPTIONS.map((o) => ({
                    value: o.value,
                    label: <Tooltip title={o.desc}>{o.label}</Tooltip>,
                  }))} />
                </Form.Item>
              </Col>
              {/* 基础仓位百分比：allin / fixed / volatility 均适用 */}
              {showPositionPercent && (
                <Col span={4}>
                  <Form.Item label="基础仓位%" name="position_percent"
                    tooltip="买入时使用的可用资金百分比">
                    <InputNumber style={{ width: '100%' }} min={1} max={100} step={5} />
                  </Form.Item>
                </Col>
              )}
              {sizingMode === 'atr' && (
                <>
                  <Col span={5}>
                    <Form.Item label="单笔风险%" name="risk_percent"
                      tooltip="每笔交易最大亏损占总资金的比例（默认 1%）">
                      <InputNumber style={{ width: '100%' }} min={0.1} max={50} step={0.5} />
                    </Form.Item>
                  </Col>
                  <Col span={5}>
                    <Form.Item label="ATR 乘数" name="atr_multiplier"
                      tooltip="止损距离 = ATR × 乘数（默认 2 倍）">
                      <InputNumber style={{ width: '100%' }} min={0.5} max={10} step={0.5} />
                    </Form.Item>
                  </Col>
                </>
              )}
              {sizingMode === 'volatility' && (
                <Col span={5}>
                  <Form.Item label="目标波动率%" name="target_volatility"
                    tooltip="年化目标波动率（默认 15%）：实际波动高于目标则降仓，低于则加仓">
                    <InputNumber style={{ width: '100%' }} min={1} max={200} step={5} />
                  </Form.Item>
                </Col>
              )}
              <Col span={4}>
                <Form.Item label="仓位上限%" name="max_position"
                  tooltip="单笔建仓占用的资金上限">
                  <InputNumber style={{ width: '100%' }} min={1} max={100} step={5} />
                </Form.Item>
              </Col>
            </Row>
          </Card>

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
