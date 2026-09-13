import { useEffect, useMemo, useState } from 'react'
import {
  Card, Button, Select, DatePicker, Space, message, Table, Typography, Empty,
} from 'antd'
import { SearchOutlined, StarOutlined } from '@ant-design/icons'
import dayjs from 'dayjs'
import { useNavigate } from 'react-router-dom'
import FactorEditor from '../components/factor-editor/FactorEditor'
import { getVisualIndicators, runScreener } from '../api'
import type { VisualIndicatorTree } from '../api'
import { VisualRule, createGroup, collectLeaves } from '../components/visual-editor/types'

const { RangePicker } = DatePicker
const { Title, Text } = Typography

export default function FactorScreener() {
  const navigate = useNavigate()
  const [tree, setTree] = useState<VisualIndicatorTree | null>(null)
  const [rule, setRule] = useState<VisualRule>(() => createGroup('AND'))
  const [stockRange, setStockRange] = useState<string>('hs300')
  const [rangeDates, setRangeDates] = useState<[dayjs.Dayjs, dayjs.Dayjs] | null>(null)
  const [results, setResults] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [scanInfo, setScanInfo] = useState<{ total: number; matched: number } | null>(null)

  useEffect(() => {
    getVisualIndicators()
      .then((res) => setTree(res.data.data || {}))
      .catch(() => message.error('指标库加载失败'))
  }, [])

  const leaves = useMemo(() => collectLeaves(rule.items || []), [rule.items])

  const handleScan = async () => {
    if (!leaves.length) {
      message.warning('请至少添加一个筛选条件')
      return
    }
    setLoading(true)
    try {
      const req: any = { rule, stock_range: stockRange }
      if (rangeDates) {
        req.start_date = rangeDates[0].format('YYYYMMDD')
        req.end_date = rangeDates[1].format('YYYYMMDD')
      }
      const res = await runScreener(req)
      const d = res.data
      setResults(d.data || [])
      setScanInfo({ total: d.total_scanned, matched: d.matched })
      if ((d.data || []).length === 0) {
        message.info(`扫描 ${d.total_scanned} 只，无符合当前条件的股票`)
      } else {
        message.success(`筛选完成：扫描 ${d.total_scanned} 只，匹配 ${d.matched} 只`)
      }
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '筛选失败')
    } finally {
      setLoading(false)
    }
  }

  const columns = [
    {
      title: '代码', dataIndex: 'symbol', key: 'symbol', width: 120,
      render: (v: string) => <a onClick={() => navigate(`/stock/${v}`)}>{v}</a>,
    },
    { title: '名称', dataIndex: 'name', key: 'name', width: 120 },
    {
      title: '现价', dataIndex: 'price', key: 'price', width: 100,
      render: (v: number) => v?.toFixed(2),
    },
    {
      title: '涨幅%', dataIndex: 'change_pct', key: 'change_pct', width: 100,
      render: (v: number) => (
        <span style={{ color: v >= 0 ? '#f5222d' : '#52c41a', fontWeight: 600 }}>
          {v >= 0 ? '+' : ''}{v}%
        </span>
      ),
    },
    { title: '行业', dataIndex: 'sector', key: 'sector', width: 140 },
    {
      title: '操作', key: 'action', width: 110,
      render: (_: any, r: any) => (
        <Button size="small" type="link" icon={<StarOutlined />}
          onClick={() => navigate(`/stock/${r.symbol}`)}>
          详情
        </Button>
      ),
    },
  ]

  if (!tree) return <Empty description="加载中…" style={{ padding: 48 }} />

  return (
    <div>
      <Title level={3}>因子选股</Title>
      <Text type="secondary">
        自由组合因子条件，实时筛出符合的股票。首次扫描某范围需下载数据（较慢），之后改条件秒级刷新。
      </Text>

      <Card size="small" style={{ margin: '12px 0' }}>
        <Space wrap>
          <span style={{ fontSize: 13 }}>范围</span>
          <Select
            size="small" style={{ width: 120 }} value={stockRange} onChange={setStockRange}
            options={[
              { value: 'hs300', label: '沪深300' },
              { value: 'zz500', label: '中证500' },
              { value: 'all', label: '全市场' },
            ]}
          />
          <span style={{ fontSize: 13 }}>日期区间</span>
          <RangePicker size="small" value={rangeDates} onChange={(v: any) => setRangeDates(v)} />
          <Button
            type="primary" size="small" icon={<SearchOutlined />}
            loading={loading} onClick={handleScan}
          >
            开始筛选
          </Button>
          {scanInfo && (
            <Text type="secondary" style={{ fontSize: 12 }}>
              匹配 {scanInfo.matched} / 共扫描 {scanInfo.total} 只
            </Text>
          )}
        </Space>
      </Card>

      <Card size="small" style={{ marginBottom: 12 }} bodyStyle={{ padding: 0 }}>
        <FactorEditor rule={rule} tree={tree} onChange={setRule} />
      </Card>

      <Card title={`筛选结果（${results.length} 只）`} size="small">
        {results.length === 0 ? (
          <Empty description="添加条件后点「开始筛选」，符合的股票会显示在这里" />
        ) : (
          <Table
            dataSource={results}
            columns={columns}
            rowKey="symbol"
            size="small"
            pagination={{ pageSize: 20, showSizeChanger: true }}
            loading={loading}
          />
        )}
      </Card>
    </div>
  )
}
