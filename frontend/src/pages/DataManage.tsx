import { useEffect, useState } from 'react'
import { Card, Table, Button, Form, Input, DatePicker, Space, message, Popconfirm, Empty, Spin } from 'antd'
import dayjs from 'dayjs'
import { fetchData, getCache, clearCache } from '../api'

const { RangePicker } = DatePicker

interface CacheItem {
  file: string
  symbol: string
  period: string
  rows: number
  start: string | null
  end: string | null
  size_kb: number
}

export default function DataManage() {
  const [cache, setCache] = useState<CacheItem[]>([])
  const [loading, setLoading] = useState(false)
  const [tableLoading, setTableLoading] = useState(false)
  const [form] = Form.useForm()

  const load = () => {
    setTableLoading(true)
    getCache()
      .then((res) => setCache(res.data.data || []))
      .catch(() => message.warning('缓存列表加载失败'))
      .finally(() => setTableLoading(false))
  }

  useEffect(() => {
    load()
  }, [])

  const handleFetch = async () => {
    const values = await form.validateFields()
    setLoading(true)
    try {
      const res = await fetchData({
        symbol: values.symbol,
        start_date: values.range[0].format('YYYYMMDD'),
        end_date: values.range[1].format('YYYYMMDD'),
      })
      message.success(`下载完成：${res.data.data.rows} 条数据`)
      load()
    } catch (e: any) {
      const detail = e?.response?.data?.detail
      message.error(detail || (e?.code === 'ERR_NETWORK' ? '网络连接失败' : '下载失败'))
    } finally {
      setLoading(false)
    }
  }

  const handleClear = async (symbol?: string) => {
    try {
      await clearCache(symbol)
      message.success('已清理')
      load()
    } catch {
      message.error('清理失败')
    }
  }

  const columns = [
    { title: '文件', dataIndex: 'file' },
    { title: '代码', dataIndex: 'symbol' },
    { title: '周期', dataIndex: 'period' },
    { title: '数据量', dataIndex: 'rows' },
    { title: '起始', dataIndex: 'start' },
    { title: '结束', dataIndex: 'end' },
    { title: '大小(KB)', dataIndex: 'size_kb' },
    {
      title: '操作',
      render: (_: unknown, row: CacheItem) => (
        <Popconfirm title="确认删除该缓存？" onConfirm={() => handleClear(row.symbol)}>
          <Button size="small" danger>删除</Button>
        </Popconfirm>
      ),
    },
  ]

  return (
    <div>
      <Card title="下载股票数据" style={{ marginBottom: 16 }}>
        <Form form={form} layout="inline" initialValues={{ symbol: '000001', range: [dayjs('2023-01-01'), dayjs('2025-06-30')] }}>
          <Form.Item label="股票代码" name="symbol" rules={[{ required: true }]}>
            <Input placeholder="000001" />
          </Form.Item>
          <Form.Item label="日期范围" name="range" rules={[{ required: true }]}>
            <RangePicker />
          </Form.Item>
          <Form.Item>
            <Button type="primary" loading={loading} onClick={handleFetch}>下载并缓存</Button>
          </Form.Item>
        </Form>
      </Card>

      <Card
        title="本地数据缓存"
        extra={
          cache.length > 0 && (
            <Popconfirm title="确认清空全部缓存？" onConfirm={() => handleClear()}>
              <Button danger>清空全部</Button>
            </Popconfirm>
          )
        }
      >
        <Spin spinning={tableLoading}>
          {cache.length === 0 && !tableLoading ? (
            <Empty description="暂无缓存数据，请先下载股票数据" />
          ) : (
            <Table columns={columns} dataSource={cache} rowKey="file" pagination={false} size="small" />
          )}
        </Spin>
      </Card>
    </div>
  )
}
