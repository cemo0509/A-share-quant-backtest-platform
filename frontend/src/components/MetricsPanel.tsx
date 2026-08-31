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
  // 扩展风险指标同样可能为 null（数据不足/回撤为 0 等），统一显示「—」
  const fmt = (v?: number | null) => (v === null || v === undefined ? '—' : v)

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
            value={m.sharpe_ratio ?? '—'}
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
          <Statistic title="盈利笔数" value={m.win_trades} valueStyle={{ color: UP }} />
        </Card>
      </Col>
      <Col span={8}>
        <Card>
          <Statistic title="亏损笔数" value={m.loss_trades} valueStyle={{ color: DOWN }} />
        </Card>
      </Col>
      {/* ---- 扩展风险指标（Q-08）：波动/Sortino/Calmar/回撤修复期/换手频率 ---- */}
      <Col span={8}>
        <Card>
          <Statistic title="年化波动率" value={fmt(m.volatility)} suffix={m.volatility != null ? '%' : ''} />
        </Card>
      </Col>
      <Col span={8}>
        <Card>
          <Statistic title="索提诺比率" value={fmt(m.sortino_ratio)} />
        </Card>
      </Col>
      <Col span={8}>
        <Card>
          <Statistic title="卡玛比率" value={fmt(m.calmar_ratio)} />
        </Card>
      </Col>
      <Col span={8}>
        <Card>
          <Statistic title="回撤修复期" value={m.max_drawdown_days ?? '—'} suffix={m.max_drawdown_days != null ? '天' : ''} />
        </Card>
      </Col>
      <Col span={8}>
        <Card>
          <Statistic title="年化交易次数" value={fmt(m.trades_per_year)} suffix={m.trades_per_year != null ? '次/年' : ''} />
        </Card>
      </Col>
    </Row>
  )
}
