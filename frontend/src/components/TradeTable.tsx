import { Table, Tag, Empty } from 'antd'
import { useStore } from '../stores'

export default function TradeTable() {
  const { result } = useStore()
  if (!result) return null

  if (!result.trades || result.trades.length === 0) {
    return <Empty description="回测期间未触发任何交易" />
  }

  const columns = [
    {
      title: '日期',
      dataIndex: 'date',
      width: 120,
    },
    {
      title: '操作',
      dataIndex: 'action',
      width: 80,
      render: (a: string) => {
        const color = a === '买入' ? 'green' : a === '卖出' ? 'red' : 'orange'
        return <Tag color={color}>{a}</Tag>
      },
    },
    { title: '价格', dataIndex: 'price', width: 100, render: (v: number) => v?.toFixed(3) },
    { title: '数量', dataIndex: 'size', width: 100 },
    {
      title: '盈亏',
      dataIndex: 'pnl',
      // A 股约定：盈利=红，亏损=绿（与 StockScan/StockDetail 保持一致）
      render: (v?: number) =>
        v !== undefined ? (
          <span style={{ color: v >= 0 ? '#cf1322' : '#3f8600' }}>{v.toFixed(2)}</span>
        ) : (
          '-'
        ),
    },
  ]

  return (
    <Table
      columns={columns}
      dataSource={result.trades}
      rowKey={(_, i) => String(i)}
      size="small"
      pagination={{ pageSize: 20 }}
    />
  )
}
