import { Card, Empty, Typography, Button, Space, message, Alert } from 'antd'
import { DownloadOutlined } from '@ant-design/icons'
import { useStore } from '../stores'
import MetricsPanel from '../components/MetricsPanel'
import BenchmarkPanel from '../components/BenchmarkPanel'
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
      ) : result.data_source === 'real' ? (
        <div style={{ marginTop: 12 }}>
          <Typography.Text type="success">数据来源：真实行情（AKShare 新浪源）</Typography.Text>
        </div>
      ) : (
        // S-03：data_source 缺省（undefined 或未知值）时不得宣称「真实行情」。
        // 与后端「不确定就不标真实」的原则保持一致——缺省即宣称真实会把
        // 未回填的旧缓存结果包装成可信数据，是本次审计要堵的错误模式。
        <Alert
          type="warning"
          showIcon
          style={{ marginTop: 12 }}
          message="数据来源未知"
          description="无法确认本次回测使用的是真实行情还是模拟数据（可能是旧版本缓存的结果，或该字段未回填）。请勿据此做决策，建议重新回测一次以明确数据来源。"
        />
      )}
      {/* A 股规则防线提示（Q-07）：策略试图 T+1 当日卖出或做空时被引擎拦截，
          用户需要知道信号被拦截过，否则会误以为策略按预期执行 */}
      {result.constraints &&
        (result.constraints.t1_sell_blocked > 0 || result.constraints.short_sell_blocked > 0) && (
        <Alert
          type="warning"
          showIcon
          style={{ marginTop: 12 }}
          message="部分交易信号因 A 股交易规则被拦截"
          description={
            <>
              {result.constraints.t1_sell_blocked > 0 && (
                <div>T+1 约束：拦截 {result.constraints.t1_sell_blocked} 次「当日买入当日卖出」。</div>
              )}
              {result.constraints.short_sell_blocked > 0 && (
                <div>禁止做空：拦截 {result.constraints.short_sell_blocked} 次「无持仓卖出」。</div>
              )}
              <div>被拦截的信号未成交，回测结果已按真实 A 股规则修正。</div>
            </>
          }
        />
      )}
      {result.trades && result.trades.length === 0 && (
        <Card style={{ marginTop: 16, background: '#fffbe6', borderColor: '#ffe58f' }}>
          <Typography.Text type="warning">
            当前回测区间未触发任何完整的买卖信号（无平仓交易）。
            {result.data_source === 'mock'
              ? '当前为模拟数据环境，数据波动可能不足以触发策略。'
              : result.data_source === 'real'
                ? '当前为真实行情，所选区间/参数下策略确实无信号。'
                : '数据来源未知，无法判断是策略本就无信号还是数据异常。'}
            建议更换股票、拉长区间或调整策略参数（如缩短均线周期）后重试。
          </Typography.Text>
        </Card>
      )}
      <MetricsPanel />
      <BenchmarkPanel />
      <Card title="K线走势（买卖点标记）" style={{ marginTop: 16 }}>
        <KLineChart />
      </Card>
      <Card title="资金曲线（含基准对比）" style={{ marginTop: 16 }}>
        <EquityCurve />
      </Card>
      <Card title="交易明细" style={{ marginTop: 16 }}>
        <TradeTable />
      </Card>
    </div>
  )
}
