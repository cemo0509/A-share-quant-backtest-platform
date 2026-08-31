import { useEffect, useRef } from 'react'
import { Modal, Card, Row, Col, Statistic, Table, Tag, Empty, Typography } from 'antd'
import * as echarts from 'echarts'
import type { BacktestResultData, EquityPoint } from '../stores'
import { useStore, resolveDark } from '../stores'

interface CompareResultDetailProps {
  visible: boolean
  result: BacktestResultData | null
  strategyName?: string
  onClose: () => void
}

const { Title } = Typography

export default function CompareResultDetail({ visible, result, strategyName, onClose }: CompareResultDetailProps) {
  const chartRef = useRef<HTMLDivElement>(null)
  const chartInstanceRef = useRef<echarts.ECharts | null>(null)
  const mode = useStore((s) => s.mode)
  const isDark = resolveDark(mode)

  useEffect(() => {
    if (!visible || !chartRef.current || !result?.equity_curve || result.equity_curve.length === 0) {
      chartInstanceRef.current?.dispose()
      chartInstanceRef.current = null
      return
    }

    const chart = echarts.init(chartRef.current, isDark ? 'dark' : undefined)
    chartInstanceRef.current = chart

    // 防御性时间排序：避免后端顺序变化导致曲线错乱
    const sorted = result.equity_curve.slice().sort((a, b) => a.date.localeCompare(b.date))
    const dates = sorted.map((p: EquityPoint) => p.date)
    const values = sorted.map((p: EquityPoint) => p.value)

    chart.setOption({
      tooltip: { trigger: 'axis' },
      xAxis: { type: 'category', data: dates, axisLabel: { rotate: 30 } },
      yAxis: { type: 'value', name: '资金' },
      series: [
        {
          name: '账户价值',
          type: 'line',
          data: values,
          smooth: true,
          showSymbol: false,
          lineStyle: { width: 2 },
          areaStyle: { opacity: 0.1 },
          itemStyle: { color: '#1890ff' },
        },
      ],
      grid: { left: 60, right: 30, top: 30, bottom: 50 },
    })

    const handleResize = () => chart.resize()
    window.addEventListener('resize', handleResize)

    return () => {
      window.removeEventListener('resize', handleResize)
      chart.dispose()
      chartInstanceRef.current = null
    }
  }, [visible, result, isDark])

  if (!result) return null

  const m = result.metrics || {}
  const positive = (m.total_return || 0) >= 0

  const tradeColumns = [
    { title: '日期', dataIndex: 'date', width: 120 },
    {
      title: '操作',
      dataIndex: 'action',
      width: 90,
      render: (a: string) => {
        const color = a === '买入' ? 'green' : a === '卖出' ? 'red' : a === '平仓' ? 'blue' : 'orange'
        return <Tag color={color}>{a}</Tag>
      },
    },
    { title: '价格', dataIndex: 'price', width: 100, render: (v?: number) => (v !== undefined ? v.toFixed(3) : '-') },
    { title: '数量', dataIndex: 'size', width: 90 },
    {
      title: '盈亏',
      dataIndex: 'pnl',
      // A 股约定：盈利=红，亏损=绿（与 StockScan/StockDetail 保持一致）
      render: (v?: number) =>
        v !== undefined ? <span style={{ color: v >= 0 ? '#cf1322' : '#3f8600' }}>{v.toFixed(2)}</span> : '-',
    },
  ]

  return (
    <Modal
      title={`${strategyName || '策略'} 回测详情`}
      open={visible}
      onCancel={onClose}
      footer={null}
      width={1000}
      destroyOnClose
    >
      <div style={{ maxHeight: '75vh', overflow: 'auto', paddingRight: 8 }}>
        <Title level={4} style={{ marginTop: 8 }}>绩效指标</Title>
        <Row gutter={[12, 12]}>
          <Col span={6}>
            <Card size="small">
              <Statistic
                title="总收益率"
                value={m.total_return || 0}
                precision={2}
                suffix="%"
                valueStyle={{ color: positive ? '#cf1322' : '#3f8600' }}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small">
              <Statistic title="年化收益" value={m.annual_return || 0} precision={2} suffix="%" />
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small">
              <Statistic
                title="最大回撤"
                value={m.max_drawdown || 0}
                precision={2}
                suffix="%"
                valueStyle={{ color: '#cf1322' }}
              />
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small">
              <Statistic title="夏普比率" value={m.sharpe_ratio || 0} precision={3} />
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small">
              <Statistic title="胜率" value={m.win_rate || 0} precision={2} suffix="%" />
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small">
              <Statistic title="盈亏比" value={m.profit_loss_ratio || 0} precision={3} />
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small">
              <Statistic title="总交易笔数" value={m.total_trades || 0} />
            </Card>
          </Col>
          <Col span={6}>
            <Card size="small">
              <Statistic title="盈利笔数" value={m.win_trades || 0} valueStyle={{ color: '#3f8600' }} />
            </Card>
          </Col>
        </Row>

        <Card title="资金曲线" size="small" style={{ marginTop: 16 }}>
          {result.equity_curve && result.equity_curve.length > 0 ? (
            <div ref={chartRef} style={{ width: '100%', height: 360 }} />
          ) : (
            <Empty description="暂无资金曲线数据" />
          )}
        </Card>

        <Card title="交易明细" size="small" style={{ marginTop: 16 }}>
          {result.trades && result.trades.length > 0 ? (
            <Table
              columns={tradeColumns}
              dataSource={result.trades}
              rowKey={(_, i) => String(i)}
              size="small"
              pagination={{ pageSize: 10, simple: true }}
              scroll={{ x: 640 }}
            />
          ) : (
            <Empty description="回测期间未触发任何交易" />
          )}
        </Card>
      </div>
    </Modal>
  )
}
