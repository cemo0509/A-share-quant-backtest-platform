import { useEffect, useState, useRef } from 'react'
import { Card, Table, Tag, Spin, Button, Input, Space, Typography, message } from 'antd'
import { ReloadOutlined, PlusOutlined } from '@ant-design/icons'
import { getRealtimeQuotes } from '../services/api'

const { Title } = Typography
const { Search } = Input

interface QuoteData {
  symbol: string
  name: string
  sector?: string
  price: number
  open: number
  high: number
  low: number
  pre_close: number
  change_amount: number
  change_pct: number
  volume: number
  amount: number
  amplitude?: number
  avg_price?: number
  turnover_rate?: number
  change_speed?: number
  volume_ratio?: number
  total_share?: number
  float_share?: number
  total_market_cap?: number
  float_market_cap?: number
  pe_ratio?: number
  pb_ratio?: number
  bid_price?: number
  ask_price?: number
  limit_up?: number
  limit_down?: number
  commission_ratio?: number
  commission_diff?: number
  inner_volume?: number
  outer_volume?: number
  io_ratio?: number
  bid1_volume?: number
  ask1_volume?: number
  // 涨跌统计
  change_3d?: number
  change_6d?: number
  turnover_3d?: number
  turnover_6d?: number
  consecutive_up?: number
  change_mtd?: number
  change_ytd?: number
  change_1m?: number
  change_1y?: number
  update_time?: string
}

export default function RealtimeQuotes() {
  const [quotes, setQuotes] = useState<QuoteData[]>([])
  const [loading, setLoading] = useState(false)
  const [symbols, setSymbols] = useState<string[]>(() => {
    // 从 localStorage 读取保存的股票列表
    const saved = localStorage.getItem('realtime_symbols')
    if (saved) {
      try {
        return JSON.parse(saved)
      } catch {
        return ['000001', '000002', '600000']
      }
    }
    return ['000001', '000002', '600000']
  })
  const [newSymbol, setNewSymbol] = useState('')
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // symbols 变化时保存到 localStorage
  useEffect(() => {
    localStorage.setItem('realtime_symbols', JSON.stringify(symbols))
  }, [symbols])

  // 获取实时行情
  const fetchQuotes = async () => {
    if (symbols.length === 0) {
      setQuotes([])
      return
    }

    setLoading(true)
    try {
      const res = await getRealtimeQuotes(symbols)
      if (res?.data?.status === 'ok' && Array.isArray(res.data.data)) {
        setQuotes(res.data.data)
      } else {
        setQuotes([])
        message.error('获取实时行情失败：后端返回异常')
      }
    } catch {
      setQuotes([])
      message.error('获取实时行情失败，请检查后端服务是否已启动')
    } finally {
      setLoading(false)
    }
  }

  // 初始加载和定时刷新
  useEffect(() => {
    fetchQuotes()
    
    // 每30秒刷新一次
    timerRef.current = setInterval(fetchQuotes, 30000)
    
    return () => {
      if (timerRef.current) {
        clearInterval(timerRef.current)
      }
    }
  }, [symbols])

  // 添加股票
  const addSymbol = () => {
    if (!newSymbol) return
    
    if (symbols.includes(newSymbol)) {
      message.warning('该股票已存在')
      return
    }
    
    setSymbols([...symbols, newSymbol])
    setNewSymbol('')
  }

  // 删除股票
  const removeSymbol = (symbol: string) => {
    setSymbols(symbols.filter(s => s !== symbol))
  }

  // 表格列定义
  const columns = [
    {
      title: '股票',
      dataIndex: 'symbol',
      key: 'symbol',
      width: 140,
      render: (_: any, record: QuoteData) => `${record.name} ${record.symbol}`,
    },
    {
      title: '最新价',
      dataIndex: 'price',
      key: 'price',
      width: 100,
      render: (price: number) => price != null ? price.toFixed(2) : '-',
    },
    {
      title: '涨跌幅',
      dataIndex: 'change_pct',
      key: 'change_pct',
      width: 100,
      render: (v: number) => {
        if (v == null) return '-'
        const color = v >= 0 ? '#f5222d' : '#52c41a'
        const sign = v >= 0 ? '+' : ''
        return <span style={{ color }}>{sign}{v.toFixed(2)}%</span>
      },
    },
    {
      title: '涨跌额',
      dataIndex: 'change_amount',
      key: 'change_amount',
      width: 100,
      render: (v: number) => {
        if (v == null) return '-'
        const color = v >= 0 ? '#f5222d' : '#52c41a'
        const sign = v >= 0 ? '+' : ''
        return <span style={{ color }}>{sign}{v.toFixed(2)}</span>
      },
    },
    {
      title: '成交量',
      dataIndex: 'volume',
      key: 'volume',
      width: 120,
      render: (volume: number) => volume != null ? (volume / 10000).toFixed(2) + '万' : '-',
    },
    {
      title: '成交额',
      dataIndex: 'amount',
      key: 'amount',
      width: 120,
      render: (amount: number) => amount != null ? (amount / 100000000).toFixed(2) + '亿' : '-',
    },
    {
      title: '3日涨幅',
      dataIndex: 'change_3d',
      key: 'change_3d',
      width: 85,
      render: (v: number) => {
        if (v == null) return '-'
        const color = v >= 0 ? '#f5222d' : '#52c41a'
        return <span style={{ color }}>{v >= 0 ? '+' : ''}{v.toFixed(2)}%</span>
      },
    },
    {
      title: '本月涨幅',
      dataIndex: 'change_mtd',
      key: 'change_mtd',
      width: 85,
      render: (v: number) => {
        if (v == null) return '-'
        const color = v >= 0 ? '#f5222d' : '#52c41a'
        return <span style={{ color }}>{v >= 0 ? '+' : ''}{v.toFixed(2)}%</span>
      },
    },
    {
      title: '连涨',
      dataIndex: 'consecutive_up',
      key: 'consecutive_up',
      width: 60,
      render: (v: number) => v != null && v > 0 ? <span style={{ color: '#f5222d' }}>{v}天</span> : '-',
    },
    {
      title: '操作',
      key: 'action',
      width: 80,
      render: (_: any, record: QuoteData) => (
        <Button
          type="link"
          danger
          size="small"
          onClick={() => removeSymbol(record.symbol)}
        >
          删除
        </Button>
      ),
    },
  ]

  return (
    <Card
      title={
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span>实时行情</span>
          <Space>
            <Button
              icon={<ReloadOutlined />}
              onClick={fetchQuotes}
              loading={loading}
              size="small"
            >
              刷新
            </Button>
          </Space>
        </div>
      }
    >
      <div style={{ marginBottom: 16 }}>
        <Space>
          <Search
            placeholder="输入股票代码，如 000001"
            value={newSymbol}
            onChange={e => setNewSymbol(e.target.value)}
            onSearch={addSymbol}
            enterButton={<PlusOutlined />}
            size="small"
            style={{ width: 300 }}
          />
          <span style={{ color: '#999', fontSize: '12px' }}>
            按回车或点击+添加
          </span>
        </Space>
      </div>

      <Spin spinning={loading}>
        <Table
          dataSource={quotes}
          columns={columns}
          rowKey="symbol"
          size="small"
          pagination={false}
          scroll={{ y: 400 }}
        />
      </Spin>

      {quotes.length === 0 && !loading && (
        <div style={{ textAlign: 'center', padding: '20px', color: '#999' }}>
          暂无实时行情数据，请添加股票代码
        </div>
      )}
    </Card>
  )
}
