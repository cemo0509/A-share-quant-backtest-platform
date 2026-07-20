import { useEffect, useRef, useState } from 'react'
import {
  Card, Form, Select, Button, DatePicker, Space, message, Table, Tag,
  Progress, Checkbox, InputNumber, Row, Col, Statistic, Empty, Modal
} from 'antd'
const { RangePicker } = DatePicker
import {
  SearchOutlined, PlusOutlined, ExportOutlined, ExperimentOutlined
} from '@ant-design/icons'
import dayjs from 'dayjs'
import { getStrategies, scanStocks, addToWatchlist, getWatchlist, prepareData, type StockScanReq, type DataPrepareReq } from '../api'
import { useNavigate } from 'react-router-dom'
import type { StrategyItem } from '../types'

// 复用 API 模块统一的 baseURL
const API_BASE = import.meta.env.VITE_API_BASE_URL || 'http://127.0.0.1:8000/api'
// 注：此处 SSE/轮询使用原生 fetch，因 EventSource 不支持自定义 headers。
// 如后续统一为 axios，可替换 fetch 调用。

interface ScanResult {
  symbol: string
  name: string
  price: number
  change_pct: number
  signal_strength: number
  signal_detail: any
  sector: string
  market_cap: number
}

export default function StockScan() {
  const [strategies, setStrategies] = useState<StrategyItem[]>([])
  const [screeningStrategies, setScreeningStrategies] = useState<StrategyItem[]>([])
  const [selectedStrategy, setSelectedStrategy] = useState<string>('')
  const [scanRange, setScanRange] = useState<string>('all')
  // 0 表示扫描范围内全部股票（全市场），非 0 为上限
  const [maxStocks, setMaxStocks] = useState<number>(0)
  const [scanDate, setScanDate] = useState<string>(dayjs().format('YYYYMMDD'))
  // 区间模式：[start, end]，为空表示单日模式
  const [rangeDates, setRangeDates] = useState<[string, string] | null>(null)
  const [loading, setLoading] = useState(false)
  const [progress, setProgress] = useState(0)
  const [progressText, setProgressText] = useState('')
  const [results, setResults] = useState<ScanResult[]>([])
  const [selectedRowKeys, setSelectedRowKeys] = useState<string[]>([])
  const [scanInfo, setScanInfo] = useState({ total_scanned: 0, total_matched: 0, strategy_name: '', date_label: '' })
  const [watchlist, setWatchlist] = useState<any[]>([])
  const navigate = useNavigate()
  const eventSourceRef = useRef<EventSource | null>(null)
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  // ===== 数据缓存（独立入口） =====
  const [prepModalOpen, setPrepModalOpen] = useState(false)
  const [prepRange, setPrepRange] = useState<string>('all')
  const [prepDates, setPrepDates] = useState<[string, string] | null>(null)
  const [prepLoading, setPrepLoading] = useState(false)
  const [prepProgress, setPrepProgress] = useState(0)
  const [prepText, setPrepText] = useState('')
  const [prepDone, setPrepDone] = useState(false)
  const prepEventSourceRef = useRef<EventSource | null>(null)
  const prepPollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const prepScanIdRef = useRef<string>('')  // 跟踪当前任务的 scan_id，用于取消

  useEffect(() => {
    getStrategies().then(res => {
      const all = res.data.data || []
      setStrategies(all)
      // 只显示选股策略和混合策略
      const screening = all.filter((s: StrategyItem) => s.category === 'screening' || s.category === 'hybrid')
      setScreeningStrategies(screening)
      if (screening.length) setSelectedStrategy(screening[0].key)
    }).catch(() => message.warning('策略列表加载失败'))

    getWatchlist().then(res => {
      setWatchlist(res.data.data || [])
    }).catch(() => message.warning('自选池加载失败'))
  }, [])

  const openPrepModal = () => {
    // 打开前清理旧监听与状态，保证每次打开都是干净初始态，
    // 避免上次「后台运行并关闭」残留 prepLoading=true 导致重开后卡死。
    if (prepEventSourceRef.current) {
      prepEventSourceRef.current.close()
      prepEventSourceRef.current = null
    }
    if (prepPollRef.current) {
      clearInterval(prepPollRef.current)
      prepPollRef.current = null
    }
    setPrepLoading(false)
    setPrepDone(false)
    setPrepProgress(0)
    setPrepText('')
    setPrepModalOpen(true)
  }

  const closePrepModal = () => {
    // 关闭 Modal 时先通知后端取消任务，再断开前端监听并重置 UI 状态。
    const sid = prepScanIdRef.current
    if (sid && prepLoading) {
      // 异步发送取消请求（不阻塞 UI 关闭）
      fetch(`${API_BASE}/stock-scan/cancel?scan_id=${encodeURIComponent(sid)}`, { method: 'POST' })
        .catch(() => { /* 忽略取消请求失败 */ })
    }
    if (prepEventSourceRef.current) {
      prepEventSourceRef.current.close()
      prepEventSourceRef.current = null
    }
    if (prepPollRef.current) {
      clearInterval(prepPollRef.current)
      prepPollRef.current = null
    }
    setPrepModalOpen(false)
    setPrepLoading(false)
    setPrepDone(false)
    setPrepProgress(0)
    setPrepText('')
    prepScanIdRef.current = ''
  }

  const handlePrepare = async () => {
    if (prepLoading) return
    // 清理上一次的监听（防止旧轮询残留干扰新任务）
    if (prepEventSourceRef.current) {
      prepEventSourceRef.current.close()
      prepEventSourceRef.current = null
    }
    if (prepPollRef.current) {
      clearInterval(prepPollRef.current)
      prepPollRef.current = null
    }
    if (!prepDates || !prepDates[0] || !prepDates[1]) {
      message.warning('请选择数据日期区间')
      return
    }
    setPrepLoading(true)
    setPrepProgress(0)
    setPrepDone(false)
    setPrepText('正在启动数据缓存...')

    const req: DataPrepareReq = {
      stock_range: prepRange,
      start_date: prepDates[0],
      end_date: prepDates[1],
      period: 'daily',
    }

    try {
      const res = await prepareData(req)
      const data = res.data
      if (data.status !== 'success' || !data.prepare_id) {
        message.warning(data.detail || '启动失败')
        setPrepLoading(false)
        return
      }
      const pid = data.prepare_id
      prepScanIdRef.current = pid  // 记录 scan_id，关闭时用于取消
      const total = data.total
      setPrepText(`正在下载数据: 0/${total}`)

      const sseUrl = `${API_BASE}/stock-scan/progress?scan_id=${pid}`
      const es = new EventSource(sseUrl)
      prepEventSourceRef.current = es
      es.onmessage = (ev) => {
        try {
          const p = JSON.parse(ev.data)
          if (p.error) {
            message.error(p.error)
            es.close()
            setPrepLoading(false)
            return
          }
          const done = p.prepare_done || 0
          const pt = p.prepare_total || total || 0
          setPrepProgress(pt > 0 ? Math.round((done / pt) * 100) : 0)
          setPrepText(`正在下载数据: ${done}/${pt}` + (p.prepare_failed ? `（失败 ${p.prepare_failed}）` : ''))
          if (p.finished) {
            es.close()
            setPrepLoading(false)
            setPrepDone(true)
            setPrepProgress(100)
            prepScanIdRef.current = ''
            setPrepText(`缓存完成！共 ${pt} 只，本次下载 ${p.prepare_fetched || 0}，已存在 ${p.prepare_cached || 0}，失败 ${p.prepare_failed || 0}`)
            message.success('数据缓存完成，之后扫描/回测将直接使用本地数据')
          }
        } catch { /* ignore */ }
      }
      es.onerror = () => {
        // SSE 断开（缓存完成会 close），若仍 loading 则降级轮询
        es.close()
        if (!prepDone) pollPrep(pid, total)
      }
    } catch (e: any) {
      message.error(e?.response?.data?.detail || '启动数据缓存失败')
      setPrepLoading(false)
    }
  }

  const pollPrep = (pid: string, total: number) => {
    if (prepPollRef.current) clearInterval(prepPollRef.current)
    prepPollRef.current = setInterval(async () => {
      try {
        const res = await fetch(`${API_BASE}/stock-scan/result?scan_id=${pid}`)
        const data = await res.json()
        if (data.status === 'success') {
          const pt = data.prepare_total || total || 0
          setPrepProgress(100)
          setPrepText(`缓存完成！共 ${pt} 只，失败 ${data.prepare_failed || 0}`)
          setPrepDone(true)
          setPrepLoading(false)
          if (prepPollRef.current) clearInterval(prepPollRef.current)
          prepPollRef.current = null
          message.success('数据缓存完成')
        } else if (data.status === 'pending') {
          const done = data.prepare_done || 0
          const pt = data.prepare_total || total || 0
          setPrepProgress(pt > 0 ? Math.round((done / pt) * 100) : 0)
          setPrepText(`正在下载数据: ${done}/${pt}`)
        }
      } catch { /* ignore */ }
    }, 1500)
  }

  const handleScan = async () => {
    if (!selectedStrategy) {
      message.warning('请先选择选股策略')
      return
    }

    // 清理上一次的资源
    cleanup()

    setLoading(true)
    setProgress(0)
    setProgressText('正在提交扫描任务...')
    setResults([])

    const req: StockScanReq = {
      strategy_type: selectedStrategy,
      stock_range: scanRange,
      max_stocks: maxStocks,
      // 默认先批量下载时间范围内全部股票数据到本地缓存，再本地筛选，
      // 避免扫描时并发联网导致后端崩溃（核心稳定性修复）
      prepare_first: true,
    }
    // 区间模式：传入 start_date / end_date；否则走单日模式（scan_date）
    if (rangeDates) {
      req.start_date = rangeDates[0]
      req.end_date = rangeDates[1]
    } else {
      req.scan_date = scanDate
    }

    try {
      // 1. 提交扫描任务
      const res = await scanStocks(req)
      const data = res.data

      if (data.status !== 'success' || !data.scan_id) {
        message.warning(data.detail || '扫描失败')
        setLoading(false)
        return
      }

      const scanId = data.scan_id
      const dateLabel = data.date_mode === 'range'
        ? `${data.start_date}~${data.end_date}`
        : (data.scan_date || scanDate)
      setScanInfo({
        total_scanned: data.total_stocks,
        total_matched: 0,
        strategy_name: data.strategy_name,
        date_label: dateLabel,
      })

      // 2. 使用 SSE 监听实时进度
      const sseUrl = `${API_BASE}/stock-scan/progress?scan_id=${scanId}`
      const es = new EventSource(sseUrl)
      eventSourceRef.current = es

      es.onmessage = (event) => {
        try {
          const p = JSON.parse(event.data)
          if (p.error) {
            message.error(p.error)
            es.close()
            setLoading(false)
            return
          }
          setProgress(p.progress_pct || 0)
          // 两阶段提示：数据预热（下载） / 本地筛选
          if (p.phase === 'prepare') {
            const pd = p.prepare_done || 0
            const pt = p.prepare_total || 0
            setProgressText(`正在下载数据: ${pd}/${pt}（下载完成后进入本地筛选，无需联网）`)
          } else {
            setProgressText(`正在筛选: ${p.scanned}/${p.total}，匹配 ${p.matched} 只`)
          }

          // 后端推送的日期区间（优先使用，保证与后端一致）
          if (p.date_mode === 'range') {
            setScanInfo(prev => ({ ...prev, date_label: `${p.start_date}~${p.end_date}` }))
          } else if (p.scan_date) {
            setScanInfo(prev => ({ ...prev, date_label: p.scan_date }))
          }

          if (p.finished) {
            es.close()
            // 获取最终结果
            fetchResults(scanId)
          }
        } catch {
          // 忽略解析错误
        }
      }

      es.onerror = () => {
        // SSE 连接失败，降级为轮询
        es.close()
        pollResults(scanId)
      }
    } catch (e: any) {
      setProgress(0)
      setProgressText('')
      message.error(e?.response?.data?.detail || '扫描失败，请检查后端')
      setLoading(false)
    }
  }

  const fetchResults = async (scanId: string) => {
    try {
      const res = await fetch(`${API_BASE}/stock-scan/result?scan_id=${scanId}`)
      const data = await res.json()
      if (data.status === 'success') {
        setResults(data.results || [])
        setScanInfo(prev => ({ ...prev, total_matched: data.matched }))
        setProgress(100)
        setProgressText('')
        message.success(`扫描完成！共扫描 ${data.total} 只，匹配 ${data.matched} 只`)
      }
    } catch (e) {
      message.error('获取结果失败')
    } finally {
      setLoading(false)
    }
  }

  const pollResults = (scanId: string) => {
    // 降级方案：轮询获取进度和结果
    pollTimerRef.current = setInterval(async () => {
      try {
        const res = await fetch(`${API_BASE}/stock-scan/result?scan_id=${scanId}`)
        const data = await res.json()

        if (data.status === 'success') {
          setResults(data.results || [])
          setScanInfo(prev => ({ ...prev, total_matched: data.matched }))
          setProgress(100)
          setProgressText('')
          setLoading(false)
          if (pollTimerRef.current) clearInterval(pollTimerRef.current)
          message.success(`扫描完成！共扫描 ${data.total} 只，匹配 ${data.matched} 只`)
        } else if (data.status === 'pending') {
          setProgress(data.progress_pct || 0)
          if (data.phase === 'prepare') {
            setProgressText(`正在下载数据: ${data.prepare_done || 0}/${data.prepare_total || 0}`)
          } else {
            setProgressText(`正在筛选: ${data.scanned}/${data.total}，匹配 ${data.matched} 只`)
          }
        }
      } catch {
        // 轮询失败忽略，继续等待
      }
    }, 1000)
  }

  const cleanup = () => {
    if (eventSourceRef.current) {
      eventSourceRef.current.close()
      eventSourceRef.current = null
    }
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current)
      pollTimerRef.current = null
    }
  }

  // 组件卸载时清理
  useEffect(() => {
    return () => cleanup()
  }, [])

  const handleAddToWatchlist = async (symbol: string, name: string) => {
    try {
      await addToWatchlist({ symbol, name })
      message.success(`已添加 ${name}(${symbol}) 到自选池`)
      // 刷新自选池
      const res = await getWatchlist()
      setWatchlist(res.data.data || [])
    } catch (e) {
      message.error('添加失败')
    }
  }

  const handleBatchAdd = async () => {
    for (const key of selectedRowKeys) {
      const item = results.find(r => r.symbol === key)
      if (item) {
        await addToWatchlist({ symbol: item.symbol, name: item.name })
      }
    }
    message.success(`已添加 ${selectedRowKeys.length} 只股票到自选池`)
    setSelectedRowKeys([])
    const res = await getWatchlist()
    setWatchlist(res.data.data || [])
  }

  const handleExportCSV = () => {
    const header = '代码,名称,现价,涨跌幅%,信号强度,行业,市值(亿)\n'
    const rows = results.map(r =>
      `${r.symbol},${r.name},${r.price},${r.change_pct},${r.signal_strength},${r.sector},${r.market_cap}`
    ).join('\n')
    const blob = new Blob([header + rows], { type: 'text/csv;charset=utf-8-sig' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `选股结果_${(scanInfo.date_label || scanDate).replace(/[~]/g, '_')}.csv`
    a.click()
    URL.revokeObjectURL(url)
    message.success('导出成功')
  }

  const signalStars = (strength: number) => {
    if (strength >= 0.8) return '★★★★★'
    if (strength >= 0.6) return '★★★★'
    if (strength >= 0.4) return '★★★'
    if (strength >= 0.2) return '★★'
    return '★'
  }

  const columns = [
    {
      title: '代码',
      dataIndex: 'symbol',
      width: 120,
      render: (v: string) => <a onClick={() => navigate(`/stock/${v}`)}>{v}</a>,
    },
    { title: '名称', dataIndex: 'name', width: 100 },
    {
      title: '现价',
      dataIndex: 'price',
      width: 80,
      render: (v: number) => v?.toFixed(2) || '-',
    },
    {
      title: '涨跌%',
      dataIndex: 'change_pct',
      width: 80,
      render: (v: number) => (
        <span style={{ color: v > 0 ? '#cf1322' : v < 0 ? '#3f8600' : '#666' }}>
          {v > 0 ? '+' : ''}{v?.toFixed(2)}%
        </span>
      ),
    },
    {
      title: '信号强度',
      dataIndex: 'signal_strength',
      width: 100,
      render: (v: number) => <span>{signalStars(v)}</span>,
    },
    { title: '行业', dataIndex: 'sector', width: 100 },
    {
      title: '市值(亿)',
      dataIndex: 'market_cap',
      width: 100,
      render: (v: number) => v > 0 ? v.toFixed(1) : '-',
    },
    {
      title: '操作',
      width: 180,
      render: (_: any, record: ScanResult) => (
        <Space>
          <Button size="small" onClick={() => navigate(`/stock/${record.symbol}`)}>详情</Button>
          <Button size="small" type="primary" ghost
            onClick={() => handleAddToWatchlist(record.symbol, record.name)}>
            加自选
          </Button>
        </Space>
      ),
    },
  ]

  const isInWatchlist = (symbol: string) => watchlist.some(w => w.symbol === symbol)

  return (
    <div>
      <h2 style={{ marginBottom: 16 }}>选股池</h2>

      <Card style={{ marginBottom: 16 }}>
        <Row gutter={16} align="middle">
          <Col span={6}>
            <Form.Item label="选股策略" style={{ marginBottom: 0 }}>
              <Select
                value={selectedStrategy}
                onChange={setSelectedStrategy}
                style={{ width: '100%' }}
                options={screeningStrategies.map(s => ({
                  label: `${s.name} ${s.category === 'screening' ? '📊' : '📈'}`,
                  value: s.key,
                }))}
              />
            </Form.Item>
          </Col>
          <Col span={4}>
            <Form.Item label="扫描范围" style={{ marginBottom: 0 }}>
              <Select
                value={scanRange}
                onChange={setScanRange}
                style={{ width: '100%' }}
                options={[
                  { label: '全部A股', value: 'all' },
                  { label: '沪深300', value: 'hs300' },
                  { label: '中证500', value: 'zz500' },
                ]}
              />
            </Form.Item>
          </Col>
          <Col span={6}>
            <Form.Item label="最多扫描" style={{ marginBottom: 0 }} tooltip="0 或留空表示扫描范围内全部股票（全市场）">
              <InputNumber
                min={0} max={6000} value={maxStocks} onChange={v => setMaxStocks(v ?? 0)}
                placeholder="全部"
                style={{ width: '100%' }}
                addonAfter={
                  <Button
                    type="link"
                    size="small"
                    style={{ padding: 0, height: 'auto' }}
                    onClick={() => setMaxStocks(0)}
                  >
                    全部
                  </Button>
                }
              />
            </Form.Item>
          </Col>
          <Col span={4}>
            <Form.Item label="日期区间" style={{ marginBottom: 0 }} tooltip="不选则为单日模式（默认今天），选区间则按区间扫描">
              <RangePicker
                value={rangeDates ? [dayjs(rangeDates[0]), dayjs(rangeDates[1])] : null}
                onChange={d => {
                  if (d && d[0] && d[1]) {
                    setRangeDates([d[0].format('YYYYMMDD'), d[1].format('YYYYMMDD')])
                  } else {
                    setRangeDates(null)
                  }
                }}
                style={{ width: '100%' }}
              />
            </Form.Item>
          </Col>
          <Col span={6}>
            <Space>
              <Button type="primary" icon={<SearchOutlined />} onClick={handleScan} loading={loading}>
                开始扫描
              </Button>
              <Button icon={<ExperimentOutlined />} onClick={openPrepModal}>
                缓存数据
              </Button>
              <Button icon={<ExportOutlined />} onClick={handleExportCSV} disabled={results.length === 0}>
                导出CSV
              </Button>
            </Space>
          </Col>
        </Row>

        {loading && (
          <div style={{ marginTop: 16 }}>
            <Progress percent={Math.round(progress)} status={progress >= 100 ? 'success' : 'active'} />
            {progressText && <div style={{ textAlign: 'center', marginTop: 4, color: '#666' }}>{progressText}</div>}
          </div>
        )}
      </Card>

      {results.length > 0 && (
        <>
          <Row gutter={16} style={{ marginBottom: 16 }}>
            <Col span={6}>
              <Card size="small">
                <Statistic title="扫描股票数" value={scanInfo.total_scanned} />
              </Card>
            </Col>
            <Col span={6}>
              <Card size="small">
                <Statistic title="匹配股票数" value={scanInfo.total_matched} valueStyle={{ color: '#3f8600' }} />
              </Card>
            </Col>
            <Col span={6}>
              <Card size="small">
                <Statistic title="使用策略" value={scanInfo.strategy_name} />
              </Card>
            </Col>
            <Col span={6}>
              <Card size="small">
                <Statistic title="扫描日期" value={scanInfo.date_label || scanDate} />
              </Card>
            </Col>
          </Row>

          <Card>
            <div style={{ marginBottom: 12 }}>
              <Space>
                <Checkbox
                  checked={selectedRowKeys.length === results.length}
                  indeterminate={selectedRowKeys.length > 0 && selectedRowKeys.length < results.length}
                  onChange={e => {
                    setSelectedRowKeys(e.target.checked ? results.map(r => r.symbol) : [])
                  }}
                >
                  全选
                </Checkbox>
                <Button size="small" onClick={handleBatchAdd} disabled={selectedRowKeys.length === 0}>
                  批量加入自选池 ({selectedRowKeys.length})
                </Button>
              </Space>
            </div>
            <Table
              rowKey="symbol"
              columns={columns}
              dataSource={results}
              size="small"
              pagination={{ pageSize: 20, showSizeChanger: true }}
              rowSelection={{
                selectedRowKeys,
                onChange: (keys: any) => setSelectedRowKeys(keys as string[]),
              }}
              scroll={{ x: 800 }}
            />
          </Card>
        </>
      )}

      {!loading && results.length === 0 && (
        <Card>
          <Empty description="选择策略后点击「开始扫描」，系统将自动筛选符合条件的股票" />
        </Card>
      )}

      <Modal
        title="缓存股票数据"
        open={prepModalOpen}
        onCancel={closePrepModal}
        onOk={handlePrepare}
        okText={prepLoading ? '缓存中...' : '开始缓存'}
        confirmLoading={prepLoading}
        cancelText={prepLoading ? '后台运行并关闭' : '关闭'}
        maskClosable={!prepLoading}
      >
        <p style={{ color: '#888', marginTop: 0 }}>
          提前把指定范围内全部股票的 K 线下载到本地缓存。缓存完成后，扫描与回测将直接读取本地数据，<b>不再联网</b>，全市场扫描可秒级完成且不会因并发网络导致后端崩溃。
        </p>
        <Form layout="vertical">
          <Form.Item label="缓存范围" style={{ marginBottom: 12 }}>
            <Select
              value={prepRange}
              onChange={setPrepRange}
              style={{ width: '100%' }}
              options={[
                { label: '全部A股', value: 'all' },
                { label: '沪深300', value: 'hs300' },
                { label: '中证500', value: 'zz500' },
              ]}
            />
          </Form.Item>
          <Form.Item label="数据日期区间" style={{ marginBottom: 12 }} tooltip="缓存该区间内全部交易日的历史 K 线">
            <RangePicker
              value={prepDates ? [dayjs(prepDates[0]), dayjs(prepDates[1])] : null}
              onChange={d => {
                if (d && d[0] && d[1]) {
                  setPrepDates([d[0].format('YYYYMMDD'), d[1].format('YYYYMMDD')])
                } else {
                  setPrepDates(null)
                }
              }}
              style={{ width: '100%' }}
            />
          </Form.Item>
        </Form>
        {(prepLoading || prepDone) && (
          <div style={{ marginTop: 8 }}>
            <Progress percent={prepProgress} status={prepDone ? 'success' : 'active'} />
            <div style={{ textAlign: 'center', marginTop: 4, color: '#666', fontSize: 13 }}>{prepText}</div>
          </div>
        )}
      </Modal>
    </div>
  )
}
