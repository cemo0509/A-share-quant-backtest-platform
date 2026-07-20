import { Card, Col, Row, Statistic } from 'antd'
import {
  ArrowUpOutlined,
  ArrowDownOutlined,
  TrophyOutlined,
} from '@ant-design/icons'
import { useStore } from '../stores'

export default function MetricsPanel() {
  const { result } = useStore()
  if (!result) return null
  const m = result.metrics

  const positive = m.total_return >= 0

  return (
    <Row gutter={[16, 16]}>
      <Col span={4}>
        <Card>
          <Statistic
            title="总收益率"
            value={m.total_return}
            precision={2}
            suffix="%"
            valueStyle={{ color: positive ? '#3f8600' : '#cf1322' }}
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
          <Statistic title="夏普比率" value={m.sharpe_ratio} precision={3} />
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
