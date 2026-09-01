import { Card, Table, Typography, Tag, Space } from 'antd'
import { useStore } from '../stores'
import type { BenchmarkItem } from '../stores'

const { Text } = Typography

/**
 * 基准对比面板（P0-10）
 *
 * 核心问题：一个策略回测出「年化 20%」，如果同期买入持有是 25%，
 * 那这个策略其实是失败的——但没有基准时完全看不出来。
 * 本面板把策略与两条基准并列，并突出显示**超额收益**。
 */
export default function BenchmarkPanel() {
  const { result } = useStore()
  if (!result) return null

  const bm = result.benchmarks
  if (!bm || (!bm.buy_hold && !bm.hs300)) return null

  const strategy = result.metrics
  // A 股约定：盈利=红，亏损=绿
  const colorOf = (v?: number | null) =>
    v === null || v === undefined ? undefined : v >= 0 ? '#cf1322' : '#3f8600'

  const rows: Array<{
    key: string
    name: string
    total_return: number
    annual_return: number
    max_drawdown: number
    excess: number | null
    isStrategy?: boolean
  }> = [
    {
      key: 'strategy',
      name: '本策略',
      total_return: strategy.total_return,
      annual_return: strategy.annual_return,
      max_drawdown: strategy.max_drawdown,
      excess: null,
      isStrategy: true,
    },
  ]

  if (bm.buy_hold) {
    rows.push({
      key: 'buy_hold',
      name: bm.buy_hold.name,
      total_return: bm.buy_hold.total_return,
      annual_return: bm.buy_hold.annual_return,
      max_drawdown: bm.buy_hold.max_drawdown,
      excess: bm.excess_vs_buy_hold,
    })
  }
  if (bm.hs300) {
    rows.push({
      key: 'hs300',
      name: bm.hs300.name,
      total_return: bm.hs300.total_return,
      annual_return: bm.hs300.annual_return,
      max_drawdown: bm.hs300.max_drawdown,
      excess: bm.excess_vs_hs300,
    })
  }

  const columns = [
    {
      title: '',
      dataIndex: 'name',
      render: (v: string, r: typeof rows[0]) =>
        r.isStrategy ? <Text strong>{v}</Text> : <Text type="secondary">{v}</Text>,
    },
    {
      title: '总收益',
      dataIndex: 'total_return',
      render: (v: number) => <span style={{ color: colorOf(v) }}>{v.toFixed(2)}%</span>,
    },
    {
      title: '年化收益',
      dataIndex: 'annual_return',
      render: (v: number) => <span style={{ color: colorOf(v) }}>{v.toFixed(2)}%</span>,
    },
    {
      title: '最大回撤',
      dataIndex: 'max_drawdown',
      render: (v: number) => <span style={{ color: '#3f8600' }}>-{v.toFixed(2)}%</span>,
    },
    {
      title: '超额收益',
      dataIndex: 'excess',
      render: (v: number | null) =>
        v === null || v === undefined ? (
          <Text type="secondary">—</Text>
        ) : (
          <Space size={4}>
            <span style={{ color: colorOf(v), fontWeight: 600 }}>
              {v >= 0 ? '+' : ''}
              {v.toFixed(2)}%
            </span>
            <Tag color={v >= 0 ? 'red' : 'green'} style={{ marginInlineEnd: 0 }}>
              {v >= 0 ? '跑赢' : '跑输'}
            </Tag>
          </Space>
        ),
    },
  ]

  // 结论提示：是否跑赢买入持有（最核心的判断）
  const excessBH = bm.excess_vs_buy_hold
  const beatBuyHold = excessBH !== null && excessBH !== undefined && excessBH > 0

  return (
    <Card title="基准对比" style={{ marginTop: 16 }}>
      <Table
        columns={columns}
        dataSource={rows}
        rowKey="key"
        pagination={false}
        size="small"
      />
      {excessBH !== null && excessBH !== undefined && (
        <div style={{ marginTop: 12 }}>
          {beatBuyHold ? (
            <Text type="success">
              策略跑赢买入持有 {excessBH.toFixed(2)} 个百分点，说明择时带来了正贡献。
            </Text>
          ) : (
            <Text type="warning">
              策略跑输买入持有 {Math.abs(excessBH).toFixed(2)} 个百分点——
              同期「什么都不做、一直持有」反而赚得更多，该策略未创造价值。
            </Text>
          )}
        </div>
      )}
      {bm.hs300 === null && (
        <div style={{ marginTop: 8 }}>
          <Text type="secondary" style={{ fontSize: 12 }}>
            沪深300 基准暂不可用（通常是网络无法获取指数数据），不影响回测结果。
          </Text>
        </div>
      )}
    </Card>
  )
}
