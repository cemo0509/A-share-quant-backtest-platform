import { Card, Col, Row, Statistic } from 'antd'
import {
  ArrowUpOutlined,
  ArrowDownOutlined,
  TrophyOutlined,
} from '@ant-design/icons'
import { useStore } from '../stores'

// A 股约定：涨/盈利=红，跌/亏损=绿。
// 此前本组件用「绿涨红跌」（国际惯例），与 StockScan/StockDetail 等页面的
// 「红涨绿跌」相反，跨页面扫视时极易把方向看反。全平台统一为 A 股约定。
const UP = '#cf1322'
const DOWN = '#3f8600'

export default function MetricsPanel() {
  const { result } = useStore()
  if (!result) return null
  const m = result.metrics

  const positive = m.total_return >= 0
  // 夏普在数据不足时为 null（无法计算），显示「—」而非 0，
  // 避免把「算不出来」误读成「风险调整收益为 0」。
  const sharpeKnown = m.sharpe_ratio !== null && m.sharpe_ratio !== undefined

  return (
    <Row gutter={[16, 16]}>
      <Col span={4}>
        <Card>
          <Statistic
            title="总收益率"
            value={m.total_return}
            precision={2}
            suffix="%"
            valueStyle={{ color: positive ? UP : DOWN }}
            prefix={positive ? <ArrowUpOutlined /> : <ArrowDownOutlined />}
          />
        </Card>
      </Col>
      <Col span={4}>
        <Card>
          <Statistic title="年化收益" value={m.annual_return} precision={2} suffix="%" />
        </Card>
      </Col>
      <Col span={4}>
        <Card>
          <Statistic
            title="最大回撤"
            value={m.max_drawdown}
            precision={2}
            suffix="%"
            valueStyle={{ color: '#cf1322' }}
            prefix={<ArrowDownOutlined />}
          />
        </Card>
      </Col>
      <Col span={4}>
        <Card>
          <Statistic
            title="夏普比率(年化)"
            value={sharpeKnown ? m.sharpe_ratio : '—'}
            precision={sharpeKnown ? 3 : undefined}
          />
        </Card>
      </Col>
      <Col span={4}>
        <Card>
          <Statistic title="胜率" value={m.win_rate} precision={2} suffix="%" prefix={<TrophyOutlined />} />
        </Card>
      </Col>
      <Col span={4}>
        <Card>
          <Statistic title="盈亏比" value={m.profit_loss_ratio} precision={3} />
        </Card>
      </Col>
      <Col span={8}>
        <Card>
          <Statistic title="总交易笔数" value={m.total_trades} />
        </Card>
      </Col>
      <Col span={8}>
        <Card>
          <Statistic title="盈利笔数" value={m.win_trades} valueStyle={{ color: '#3f8600' }} />
        </Card>
      </Col>
      <Col span={8}>
        <Card>
          <Statistic title="亏损笔数" value={m.loss_trades} valueStyle={{ color: '#cf1322' }} />
        </Card>
      </Col>
    </Row>
  )
}
