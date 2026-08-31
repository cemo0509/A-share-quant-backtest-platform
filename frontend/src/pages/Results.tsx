import { Card, Empty, Typography, Button, Space, message, Alert } from 'antd'
import { DownloadOutlined } from '@ant-design/icons'
import { useStore } from '../stores'
import MetricsPanel from '../components/MetricsPanel'
import EquityCurve from '../components/EquityCurve'
import KLineChart from '../components/KLineChart'
import TradeTable from '../components/TradeTable'
import { exportResultJson, exportTradesCsv } from '../services/api'

const { Title } = Typography

export default function Results() {
  const { result } = useStore()

  if (!result) {
    return <Empty description="暂无回测结果，请先在「回测」页运行回测" />
  }

  // 导出 JSON
  const handleExportJson = async () => {
    try {
      await exportResultJson(result)
      message.success('JSON导出成功')
    } catch (e: any) {
      message.error('JSON导出失败: ' + (e.message || '未知错误'))
    }
  }

  // 导出 CSV
  const handleExportCsv = async () => {
    try {
      const trades = result.trades || []
      if (trades.length === 0) {
        message.warning('没有交易记录可导出')
        return
      }
      await exportTradesCsv(trades)
      message.success('CSV导出成功')
    } catch (e: any) {
      message.error('CSV导出失败: ' + (e.message || '未知错误'))
    }
  }

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Title level={3} style={{ margin: 0 }}>回测结果</Title>
        <Space>
          <Button icon={<DownloadOutlined />} onClick={handleExportJson}>导出 JSON</Button>
          <Button icon={<DownloadOutlined />} onClick={handleExportCsv}>导出交易 CSV</Button>
        </Space>
      </div>
      {/* 数据来源提示：模拟数据是随机生成的，必须醒目常驻提示，
          否则用户会把随机数跑出的收益/夏普误判为策略有效 */}
      {result.data_source === 'mock' ? (
        <Alert
          type="error"
          showIcon
          style={{ marginTop: 12 }}
          message="本次回测基于模拟数据"
          description="真实行情获取失败，已降级为随机生成的模拟K线。该结果（收益、夏普、回撤等）不反映任何真实市场规律，不可作为策略有效性依据。请检查网络后重新回测。"
        />
      ) : (
        <div style={{ marginTop: 12 }}>
          <Typography.Text type="success">数据来源：真实行情（AKShare 新浪源）</Typography.Text>
        </div>
      )}
      {result.trades && result.trades.length === 0 && (
        <Card style={{ marginTop: 16, background: '#fffbe6', borderColor: '#ffe58f' }}>
          <Typography.Text type="warning">
            当前回测区间未触发任何完整的买卖信号（无平仓交易）。
            {result.data_source === 'mock'
              ? '当前为模拟数据环境，数据波动可能不足以触发策略。'
              : '当前为真实行情，所选区间/参数下策略确实无信号。'}
            建议更换股票、拉长区间或调整策略参数（如缩短均线周期）后重试。
          </Typography.Text>
        </Card>
      )}
      <MetricsPanel />
      <Card title="K线走势（买卖点标记）" style={{ marginTop: 16 }}>
        <KLineChart />
      </Card>
      <Card title="资金曲线" style={{ marginTop: 16 }}>
        <EquityCurve />
      </Card>
      <Card title="交易明细" style={{ marginTop: 16 }}>
        <TradeTable />
      </Card>
    </div>
  )
}
