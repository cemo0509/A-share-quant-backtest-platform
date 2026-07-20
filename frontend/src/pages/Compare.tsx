// 策略比较页面
import { useEffect, useState } from 'react'
import { Card, Form, Select, DatePicker, InputNumber, Input, Button, message, Spin, Table, Typography } from 'antd'
import dayjs from 'dayjs'
import { getStrategies, compareStrategies } from '../services/api'
import type { StrategyItem } from '../types'
import CompareResultDetail from '../components/CompareResultDetail'
import type { BacktestResultData } from '../stores'

const { RangePicker } = DatePicker
const { Title, Text } = Typography

interface CompareResult {
  strategy: string
  status: string
  data?: any
  detail?: string
}

export default function Compare() {
  const [strategies, setStrategies] = useState<StrategyItem[]>([])
  const [selectedStrategies, setSelectedStrategies] = useState<string[]>([])
  const [loading, setLoading] = useState(false)
  const [results, setResults] = useState<CompareResult[]>([])
  const [detailVisible, setDetailVisible] = useState(false)
  const [detailResult, setDetailResult] = useState<BacktestResultData | null>(null)
  const [detailName, setDetailName] = useState('')
  const [form] = Form.useForm()

  useEffect(() => {
    getStrategies()
      .then((res) => {
        const list = res.data.data || []
        setStrategies(list)
      })
      .catch(() => message.warning('策略列表加载失败，请确认后端已启动'))
  }, [])

  const handleSubmit = async () => {
    try {
      const values = await form.validateFields()
      
      if (selectedStrategies.length < 2) {
        message.warning('请至少选择2个策略进行比较')
        return
      }
      
      setLoading(true)
      
      const req = {
        strategies: selectedStrategies,
        symbol: values.symbol,
        start_date: values.range[0].format('YYYYMMDD'),
        end_date: values.range[1].format('YYYYMMDD'),
        cash: values.cash,
        commission: values.commission,
        slippage: values.slippage,
      }
      
      const res = await compareStrategies(req)
      setResults(res.data.data)
      message.success('策略比较完成')
      
    } catch (e: any) {
      const detail = e?.response?.data?.detail
      const msg = detail || (e?.code === 'ERR_NETWORK' ? '网络连接失败，请检查后端是否已启动' : '比较失败')
      message.error(msg)
    } finally {
      setLoading(false)
    }
  }

  // 表格列定义
  const columns = [
    {
      title: '策略',
      dataIndex: 'strategy',
      key: 'strategy',
      render: (text: string) => {
        const s = strategies.find(x => x.key === text)
        return s ? s.name : text
      }
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (status: string) => (
        <Text type={status === 'ok' ? 'success' : 'danger'}>
          {status === 'ok' ? '成功' : '失败'}
        </Text>
      )
    },
    {
      title: '总收益率',
      key: 'total_return',
      render: (record: CompareResult) => {
        if (record.status !== 'ok' || !record.data) return '-'
        const metrics = record.data.metrics || {}
        const totalReturn = metrics.total_return || 0
        return <Text type={totalReturn >= 0 ? 'success' : 'danger'}>{totalReturn.toFixed(2)}%</Text>
      }
    },
    {
      title: '夏普比率',
      key: 'sharpe_ratio',
      render: (record: CompareResult) => {
        if (record.status !== 'ok' || !record.data) return '-'
        const metrics = record.data.metrics || {}
        const sharpe = metrics.sharpe_ratio || 0
        return sharpe.toFixed(2)
      }
    },
    {
      title: '最大回撤',
      key: 'max_drawdown',
      render: (record: CompareResult) => {
        if (record.status !== 'ok' || !record.data) return '-'
        const metrics = record.data.metrics || {}
        const drawdown = metrics.max_drawdown || 0
        return <Text type="danger">{drawdown.toFixed(2)}%</Text>
      }
    },
    {
      title: '交易次数',
      key: 'total_trades',
      render: (record: CompareResult) => {
        if (record.status !== 'ok' || !record.data) return '-'
        const metrics = record.data.metrics || {}
        return metrics.total_trades || 0
      }
    },
    {
      title: '操作',
      key: 'action',
      render: (record: CompareResult) => {
        if (record.status !== 'ok') return '-'
        return (
          <Button 
            type="link" 
            onClick={() => {
              const s = strategies.find(x => x.key === record.strategy)
              setDetailName(s ? s.name : record.strategy)
              setDetailResult(record.data || null)
              setDetailVisible(true)
            }}
          >
            查看详情
          </Button>
        )
      }
    }
  ]

  return (
    <Spin spinning={loading}>
      <Card title="策略比较">
        <Form
          form={form}
          layout="vertical"
          initialValues={{
            symbol: '000001',
            range: [dayjs('2024-01-01'), dayjs('2024-12-31')],
            cash: 1000000,
            commission: 0.0003,
            slippage: 0.001,
          }}
        >
          <Form.Item label="选择策略（至少2个）" required>
            <Select
              mode="multiple"
              placeholder="请选择要比较的策略"
              value={selectedStrategies}
              onChange={setSelectedStrategies}
              style={{ width: '100%' }}
            >
              {strategies.map(s => (
                <Select.Option key={s.key} value={s.key}>
                  {s.name} - {s.description}
                </Select.Option>
              ))}
            </Select>
          </Form.Item>
          
          <Form.Item label="股票代码" name="symbol" rules={[{ required: true }]}>
            <Input placeholder="如 000001" />
          </Form.Item>
          
          <Form.Item label="回测时间" name="range" rules={[{ required: true }]}>
            <RangePicker style={{ width: '100%' }} />
          </Form.Item>
          
          <Form.Item label="初始资金" name="cash">
            <InputNumber min={10000} max={10000000} step={10000} style={{ width: '100%' }} />
          </Form.Item>
          
          <Form.Item>
            <Button type="primary" onClick={handleSubmit} loading={loading}>
              开始比较
            </Button>
          </Form.Item>
        </Form>
      </Card>
      
      {results.length > 0 && (
        <Card title="比较结果" style={{ marginTop: 16 }}>
          <Table
            dataSource={results}
            columns={columns}
            rowKey="strategy"
            pagination={false}
          />
        </Card>
      )}

      <CompareResultDetail
        visible={detailVisible}
        result={detailResult}
        strategyName={detailName}
        onClose={() => setDetailVisible(false)}
      />
    </Spin>
  )
}
