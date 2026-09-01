import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
  Card, Table, Button, Space, Popconfirm, Empty, message, Tag, Typography,
  Tooltip, Spin,
} from 'antd'
import {
  DeleteOutlined, EyeOutlined, ReloadOutlined, ClearOutlined,
} from '@ant-design/icons'
import {
  listBacktestHistory, getBacktestHistory, deleteBacktestHistory,
  clearBacktestHistory, type BacktestHistoryItem,
} from '../api'
import { useStore } from '../stores'

const { Text } = Typography

/**
 * 回测历史（P0-9 持久化）
 *
 * 此前回测结果只存在前端内存，刷新即丢失，无法回答
 * 「上个月用双均线跑茅台的结果是多少」「这两个策略哪个更好」。
 * 本页提供历史列表、复盘（重新载入结果页）与删除。
 */
export default function History() {
  const [items, setItems] = useState<BacktestHistoryItem[]>([])
  const [loading, setLoading] = useState(false)
  const [loadingId, setLoadingId] = useState<string | null>(null)
  const navigate = useNavigate()
  const { setResult } = useStore()

  const load = async () => {
    setLoading(true)
    try {
      const res = await listBacktestHistory(200)
      setItems(res.data?.data || [])
    } catch {
      message.warning('回测历史加载失败')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [])

  // 复盘：把历史记录重新载入结果页
  const handleView = async (id: string) => {
    setLoadingId(id)
    try {
      const res = await getBacktestHistory(id)
      const rec = res.data?.data
      if (!rec?.result) {
        message.error('该记录无完整结果数据')
        return
      }
      setResult(rec.result)
      message.success('已载入该回测结果')
      navigate('/results')
    } catch {
      message.error('载入失败')
    } finally {
      setLoadingId(null)
    }
  }

  const handleDelete = async (id: string) => {
    try {
      await deleteBacktestHistory(id)
      message.success('已删除')
      load()
    } catch {
      message.error('删除失败')
    }
  }

  const handleClear = async () => {
    try {
      await clearBacktestHistory()
      message.success('已清空')
      load()
    } catch {
      message.error('清空失败')
    }
  }

  // A 股约定：盈利=红，亏损=绿
  const colorOf = (v?: number | null) =>
    v === null || v === undefined ? undefined : v >= 0 ? '#cf1322' : '#3f8600'

  const columns = [
    {
      title: '时间',
      dataIndex: 'created_at',
      width: 155,
      render: (v: string) => (v || '').replace('T', ' ').slice(0, 19),
    },
    {
      title: '策略',
      dataIndex: 'strategy_name',
      width: 120,
      render: (v: string) => v || '-',
    },
    { title: '股票', dataIndex: 'symbol', width: 80 },
    {
      title: '区间',
      width: 165,
      render: (_: unknown, r: BacktestHistoryItem) =>
        `${r.start_date} ~ ${r.end_date}`,
    },
    {
      title: '总收益',
      dataIndex: ['metrics', 'total_return'],
      width: 95,
      render: (v: number) => (
        <span style={{ color: colorOf(v) }}>
          {v >= 0 ? '+' : ''}{v?.toFixed(2)}%
        </span>
      ),
    },
    {
      title: '年化',
      dataIndex: ['metrics', 'annual_return'],
      width: 90,
      render: (v: number) => (
        <span style={{ color: colorOf(v) }}>{v?.toFixed(2)}%</span>
      ),
    },
    {
      title: '夏普',
      dataIndex: ['metrics', 'sharpe_ratio'],
      width: 75,
      render: (v: number | null) => (v === null || v === undefined ? '—' : v.toFixed(3)),
    },
    {
      title: '回撤',
      dataIndex: ['metrics', 'max_drawdown'],
      width: 85,
      render: (v: number) => <span style={{ color: '#3f8600' }}>-{v?.toFixed(2)}%</span>,
    },
    {
      title: '交易',
      dataIndex: ['metrics', 'total_trades'],
      width: 65,
    },
    {
      title: '数据来源',
      dataIndex: 'data_source',
      width: 90,
      render: (v: string) =>
        v === 'mock' ? (
          <Tooltip title="该次回测使用了模拟数据，结果不可作为策略有效性依据">
            <Tag color="red">模拟</Tag>
          </Tooltip>
        ) : (
          <Tag color="green">真实</Tag>
        ),
    },
    {
      title: '操作',
      width: 140,
      render: (_: unknown, r: BacktestHistoryItem) => (
        <Space size={4}>
          <Button
            size="small"
            icon={<EyeOutlined />}
            loading={loadingId === r.id}
            onClick={() => handleView(r.id)}
          >
            复盘
          </Button>
          <Popconfirm title="确认删除该记录？" onConfirm={() => handleDelete(r.id)}>
            <Button size="small" danger icon={<DeleteOutlined />} />
          </Popconfirm>
        </Space>
      ),
    },
  ]

  return (
    <div>
      <Card
        title="回测历史"
        extra={
          <Space>
            <Button icon={<ReloadOutlined />} onClick={load} loading={loading}>
              刷新
            </Button>
            {items.length > 0 && (
              <Popconfirm title="确认清空全部历史？此操作不可恢复" onConfirm={handleClear}>
                <Button danger icon={<ClearOutlined />}>清空</Button>
              </Popconfirm>
            )}
          </Space>
        }
      >
        {items.length === 0 && !loading ? (
          <Empty description="暂无回测历史，去「回测」页跑一次就会自动记录" />
        ) : (
          <Table
            columns={columns}
            dataSource={items}
            rowKey="id"
            size="small"
            loading={loading}
            pagination={{ pageSize: 15, showSizeChanger: true }}
            scroll={{ x: 1200 }}
          />
        )}
        {items.length > 0 && (
          <div style={{ marginTop: 12 }}>
            <Text type="secondary" style={{ fontSize: 12 }}>
              共 {items.length} 条记录。点击「复盘」可把历史结果重新载入结果页查看完整指标与资金曲线。
            </Text>
          </div>
        )}
      </Card>
    </div>
  )
}
