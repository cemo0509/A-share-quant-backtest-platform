import { useEffect, useRef, useState } from 'react'
import {
  Card, Button, Space, message, Table, Tag, Row, Col, Statistic,
  InputNumber, Select, Empty, Badge, Divider, Switch, Tooltip, Checkbox, Tabs, theme
} from 'antd'
import {
  PlayCircleOutlined, PauseCircleOutlined, ReloadOutlined,
  FilterOutlined, ExportOutlined, StarOutlined, StarFilled, DeleteOutlined
} from '@ant-design/icons'
import { useNavigate } from 'react-router-dom'
import {
  startMonitor, stopMonitor, getMonitorPool, getMonitorStatus,
  refineMonitorPool, getMonitorFactorDefs,
  getWatchlist, addToWatchlist, removeFromWatchlist
} from '../api'

interface PoolItem {
  symbol: string
  name: string
  price: number
  change_pct: number
  cci: number
  dif: number
  dea: number
  sector: string
  trigger_time: string
  kline_time?: string
}

interface WatchItem {
  symbol: string
  name: string
  added_at: string
  added_price: number
  notes: string
}

interface FactorParamDef {
  name: string
  label: string
  type: string
  default: any
  min?: number
  max?: number
  step?: number
  options?: { label: string; value: any }[]
}
interface FactorDef {
  key: string
  name: string
  enabled: boolean
  params: FactorParamDef[]
}
interface FactorCfg {
  enabled: boolean
  params: Record<string, any>
}

function renderParamInput(p: FactorParamDef, value: any, onChange: (v: any) => void) {
  if (p.type === 'select') {
    return (
      <Select size="small" style={{ width: 130 }} value={value}
        onChange={onChange}
        options={p.options?.map(o => ({ label: o.label, value: o.value }))} />
    )
  }
  if (p.type === 'int' || p.type === 'float') {
    return (
      <InputNumber size="small" style={{ width: 110 }} value={value}
        min={p.min} max={p.max} step={p.step}
        onChange={v => onChange(v ?? p.default)} />
    )
  }
  return <InputNumber size="small" style={{ width: 110 }} value={value} onChange={v => onChange(v ?? p.default)} />
}

export default function RealtimePool() {
  const { token } = theme.useToken()
  const [running, setRunning] = useState(false)
  const [pool, setPool] = useState<PoolItem[]>([])
  const [lastScan, setLastScan] = useState<string>('-')
  const [scanCount, setScanCount] = useState(0)
  const [loading, setLoading] = useState(false)
  const [activeTab, setActiveTab] = useState<'pool' | 'watch'>('pool')
  const [scanLogs, setScanLogs] = useState<string[]>([])
  const [candidates, setCandidates] = useState(0)

  // 监控参数
  const [interval_, setInterval_] = useState(60)
  const [minAmount, setMinAmount] = useState(5)
  const [period, setPeriod] = useState('30')
  const [maxStocks, setMaxStocks] = useState(200)
  const [combine, setCombine] = useState<'AND' | 'OR'>('AND')

  // 因子配置
  const [factorDefs, setFactorDefs] = useState<FactorDef[]>([])
  const [factorCfg, setFactorCfg] = useState<Record<string, FactorCfg>>({})

  // 二次筛选
  const [refineMinCci, setRefineMinCci] = useState<number>(0)
  const [refined, setRefined] = useState<PoolItem[] | null>(null)

  // 自选股
  const [watchlist, setWatchlist] = useState<WatchItem[]>([])
  const [watchLoading, setWatchLoading] = useState(false)

  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const navigate = useNavigate()

  const fetchPool = async () => {
    try {
      const res = await getMonitorPool()
      const data = res.data.data || {}
      setPool(data.pool || [])
      setLastScan(data.last_scan || '-')
      setScanCount(data.scan_count || 0)
      setRunning(!!data.running)
      setScanLogs(data.logs || [])
      setCandidates(data.candidates || 0)
    } catch {
      // 静默失败，继续轮询
    }
  }

  const fetchWatchlist = async () => {
    setWatchLoading(true)
    try {
      const res = await getWatchlist()
      setWatchlist(res.data.data || [])
    } catch {
      message.warning('自选股加载失败')
    } finally {
      setWatchLoading(false)
    }
  }

  // 初始化：加载因子定义 + 状态 + 启动轮询
  useEffect(() => {
    getMonitorFactorDefs().then(res => {
      const d = res.data.data || {}
      setFactorDefs(d.factors || [])
      const defaults: Record<string, FactorCfg> = d.defaults || {}
      // 默认启用 CCI + MACD（向后兼容旧习惯）
      if (Object.keys(defaults).length) {
        defaults.cci = defaults.cci || { enabled: true, params: { period: 14, direction: 'above', threshold: 100 } }
        defaults.macd = defaults.macd || { enabled: true, params: { signal: 'golden', zero_band: 0, fast: 12, slow: 26 } }
        setFactorCfg(defaults)
      }
    }).catch(() => message.warning('因子定义加载失败'))

    getMonitorStatus().then(res => {
      const st = res.data.data || {}
      setRunning(!!st.running)
      const p = st.params || {}
      if (p.period) setPeriod(p.period)
      if (p.min_amount_yi) setMinAmount(p.min_amount_yi)
      if (p.combine) setCombine(p.combine)
      if (p.factors) setFactorCfg(p.factors)
    }).catch(() => {})

    fetchPool()
    fetchWatchlist()
    pollRef.current = setInterval(fetchPool, 10000) // 每10秒轮询
    return () => {
      if (pollRef.current) clearInterval(pollRef.current)
    }
  }, [])

  const toggleFactor = (key: string, enabled: boolean) => {
    setFactorCfg(prev => ({ ...prev, [key]: { ...(prev[key] || { params: {} }), enabled } }))
  }
  const setFactorParam = (key: string, pname: string, value: any) => {
    setFactorCfg(prev => {
      const cur = prev[key] || { enabled: true, params: {} }
      return { ...prev, [key]: { ...cur, params: { ...cur.params, [pname]: value } } }
    })
  }

  const enabledCount = Object.values(factorCfg).filter(f => f.enabled).length

  const handleStart = async () => {
    if (enabledCount === 0) {
      message.warning('请至少启用一个选股因子')
      return
    }
    setLoading(true)
    try {
      await startMonitor({
        interval: interval_,
        period,
        min_amount: minAmount,
        max_stocks: maxStocks,
        combine,
        factors: factorCfg,
      })
      setRunning(true)
      message.success('监控已启动，盘中将按所选因子自动扫描')
      setTimeout(fetchPool, 1500)
    } catch {
      message.error('启动失败，请检查后端')
    } finally {
      setLoading(false)
    }
  }

  const handleStop = async () => {
    setLoading(true)
    try {
      await stopMonitor()
      setRunning(false)
      message.success('监控已停止')
    } catch {
      message.error('停止失败')
    } finally {
      setLoading(false)
    }
  }

  const handleRefine = async () => {
    try {
      const res = await refineMonitorPool({ min_cci: refineMinCci })
      setRefined(res.data.data?.pool || [])
      message.success(`二次筛选：${res.data.data?.count || 0} 只`)
    } catch {
      message.error('二次筛选失败')
    }
  }

  const clearRefine = () => setRefined(null)

  const handleAddWatch = async (item: PoolItem) => {
    try {
      await addToWatchlist({ symbol: item.symbol, name: item.name, added_price: item.price })
      message.success(`已加自选：${item.name}`)
      fetchWatchlist()
    } catch {
      message.error('加自选失败')
    }
  }

  const handleRemoveWatch = async (symbol: string) => {
    try {
      await removeFromWatchlist(symbol)
      message.success('已移除自选')
      fetchWatchlist()
    } catch {
      message.error('移除失败')
    }
  }

  const handleExport = () => {
    const list = refined || pool
    const header = '代码,名称,现价,涨跌幅,CCI,DIF,DEA,行业,触发时间\n'
    const rows = list.map(r =>
      `${r.symbol},${r.name},${r.price},${r.change_pct},${r.cci},${r.dif},${r.dea},${r.sector},${r.trigger_time}`
    ).join('\n')
    const blob = new Blob([header + rows], { type: 'text/csv;charset=utf-8-sig' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `实时选股池_${new Date().toISOString().slice(0, 10)}.csv`
    a.click()
    URL.revokeObjectURL(url)
    message.success('导出成功')
  }

  const poolColumns = [
    {
      title: '代码', dataIndex: 'symbol', width: 110,
      render: (v: string) => <a onClick={() => navigate(`/stock/${v}`)}>{v}</a>,
    },
    { title: '名称', dataIndex: 'name', width: 100 },
    {
      title: '现价', dataIndex: 'price', width: 90,
      sorter: (a: PoolItem, b: PoolItem) => a.price - b.price,
      render: (v: number) => v?.toFixed(2) || '-',
    },
    {
      title: '涨跌幅', dataIndex: 'change_pct', width: 100,
      sorter: (a: PoolItem, b: PoolItem) => a.change_pct - b.change_pct,
      defaultSortOrder: 'descend' as const,
      render: (v: number) => (
        <Tag color={v > 0 ? 'red' : v < 0 ? 'green' : 'default'}>
          {v > 0 ? '+' : ''}{v?.toFixed(2)}%
        </Tag>
      ),
    },
    {
      title: 'CCI', dataIndex: 'cci', width: 90,
      sorter: (a: PoolItem, b: PoolItem) => a.cci - b.cci,
      render: (v: number) => <Tag color={v > 100 ? 'red' : 'default'}>{v?.toFixed(1)}</Tag>,
    },
    { title: 'DIF', dataIndex: 'dif', width: 90, render: (v: number) => v?.toFixed(4) },
    { title: 'DEA', dataIndex: 'dea', width: 90, render: (v: number) => v?.toFixed(4) },
    { title: '行业', dataIndex: 'sector', width: 100 },
    { title: '触发时间', dataIndex: 'trigger_time', width: 100 },
    {
      title: '操作', width: 130,
      render: (_: any, r: PoolItem) => (
        <Space size={4}>
          <Button size="small" icon={<StarOutlined />} onClick={() => handleAddWatch(r)}>自选</Button>
          <Button size="small" onClick={() => navigate(`/stock/${r.symbol}`)}>详情</Button>
        </Space>
      ),
    },
  ]

  const watchColumns = [
    {
      title: '代码', dataIndex: 'symbol', width: 110,
      render: (v: string) => <a onClick={() => navigate(`/stock/${v}`)}>{v}</a>,
    },
    { title: '名称', dataIndex: 'name', width: 120 },
    {
      title: '加入时价格', dataIndex: 'added_price', width: 110,
      render: (v: number) => v ? v.toFixed(2) : '-',
    },
    { title: '加入时间', dataIndex: 'added_at', width: 160 },
    { title: '备注', dataIndex: 'notes', width: 140, render: (v: string) => v || '-' },
    {
      title: '操作', width: 140,
      render: (_: any, r: WatchItem) => (
        <Space size={4}>
          <Button size="small" onClick={() => navigate(`/stock/${r.symbol}`)}>详情</Button>
          <Button size="small" danger icon={<DeleteOutlined />} onClick={() => handleRemoveWatch(r.symbol)}>移除</Button>
        </Space>
      ),
    },
  ]

  const displayList = refined || pool

  return (
    <div>
      <Row justify="space-between" align="middle" style={{ marginBottom: 16 }}>
        <Col>
          <h2 style={{ margin: 0 }}>
            实时选股池（可组合指标）{' '}
            <Badge
              status={running ? 'processing' : 'default'}
              text={running ? '监控中' : '已停止'}
            />
          </h2>
        </Col>
        <Col>
          <Space>
            <Button icon={<ReloadOutlined />} onClick={() => activeTab === 'pool' ? fetchPool() : fetchWatchlist()}>刷新</Button>
            {activeTab === 'pool' && (running ? (
              <Button danger icon={<PauseCircleOutlined />} onClick={handleStop} loading={loading}>
                停止监控
              </Button>
            ) : (
              <Button type="primary" icon={<PlayCircleOutlined />} onClick={handleStart} loading={loading}>
                启动监控
              </Button>
            ))}
          </Space>
        </Col>
      </Row>

      <Tabs activeKey={activeTab} onChange={(k) => setActiveTab(k as any)} items={[
        {
          key: 'pool',
          label: '实时选股池',
          children: (
            <>
              {/* 基础参数 */}
              <Card size="small" style={{ marginBottom: 12 }}>
                <Row gutter={16} align="middle">
                  <Col span={3}>
                    <div style={{ marginBottom: 4, color: token.colorTextSecondary }}>扫描间隔(秒)</div>
                    <InputNumber min={10} max={600} value={interval_} onChange={v => setInterval_(v || 60)}
                      style={{ width: '100%' }} disabled={running} />
                  </Col>
                  <Col span={3}>
                    <div style={{ marginBottom: 4, color: token.colorTextSecondary }}>成交额≥(亿)</div>
                    <InputNumber min={1} max={50} step={0.5} value={minAmount}
                      onChange={v => setMinAmount(v || 5)} style={{ width: '100%' }} disabled={running} />
                  </Col>
                  <Col span={3}>
                    <div style={{ marginBottom: 4, color: token.colorTextSecondary }}>最多扫描(只)</div>
                    <InputNumber min={10} max={6000} step={10} value={maxStocks}
                      onChange={v => setMaxStocks(v || 200)} style={{ width: '100%' }} disabled={running} />
                  </Col>
                  <Col span={4}>
                    <div style={{ marginBottom: 4, color: token.colorTextSecondary }}>选股周期(分钟)</div>
                    <Select
                      value={period}
                      onChange={(v: string) => {
                        const n = String(v).trim()
                        if (n && /^\d+$/.test(n) && Number(n) >= 1) setPeriod(n)
                      }}
                      style={{ width: '100%' }}
                      disabled={running}
                      showSearch
                      placeholder="选周期或输入分钟数"
                      // @ts-ignore antd Select combobox 模式支持自由输入
                      combobox
                      options={[
                        { label: '1分钟', value: '1' },
                        { label: '5分钟', value: '5' },
                        { label: '15分钟', value: '15' },
                        { label: '30分钟', value: '30' },
                        { label: '45分钟', value: '45' },
                        { label: '60分钟', value: '60' },
                        { label: '90分钟', value: '90' },
                        { label: '120分钟', value: '120' },
                        { label: '240分钟(4小时)', value: '240' },
                      ]}
                    />
                  </Col>
                  <Col span={4}>
                    <div style={{ marginBottom: 4, color: token.colorTextSecondary }}>多因子组合方式</div>
                    <Select value={combine} onChange={setCombine} style={{ width: '100%' }} disabled={running}
                      options={[
                        { label: 'AND（全部满足）', value: 'AND' },
                        { label: 'OR（任一满足）', value: 'OR' },
                      ]} />
                  </Col>
                  <Col span={7}>
                    <div style={{ color: token.colorTextTertiary, fontSize: 12, marginTop: 20 }}>
                      已启用 {enabledCount} 个因子；最多可扫 6000 只（覆盖全市场）。监控仅在交易时段运行，页面每10秒自动刷新
                    </div>
                  </Col>
                </Row>
              </Card>

              {/* 因子勾选面板 */}
              <Card size="small" style={{ marginBottom: 12 }} title="选股因子（可自由组合，勾选启用）">
                <Row gutter={[12, 12]}>
                  {factorDefs.map(f => {
                    const cfg = factorCfg[f.key] || { enabled: f.enabled, params: {} }
                    return (
                      <Col span={12} key={f.key}>
                        <Card size="small" style={{ borderColor: cfg.enabled ? token.colorPrimary : token.colorBorderSecondary }}>
                          <Row align="middle">
                            <Col flex="auto">
                              <Checkbox checked={cfg.enabled}
                                onChange={e => toggleFactor(f.key, e.target.checked)}
                                disabled={running}>
                                <b>{f.name}</b>
                              </Checkbox>
                            </Col>
                          </Row>
                          {cfg.enabled && (
                            <Row gutter={8} style={{ marginTop: 8 }}>
                              {f.params.map(p => (
                                <Col key={p.name}>
                                  <div style={{ fontSize: 12, color: token.colorTextTertiary, marginBottom: 2 }}>{p.label}</div>
                                  {renderParamInput(p, cfg.params?.[p.name] ?? p.default,
                                    v => setFactorParam(f.key, p.name, v))}
                                </Col>
                              ))}
                            </Row>
                          )}
                        </Card>
                      </Col>
                    )
                  })}
                </Row>
              </Card>

              <Row gutter={16} style={{ marginBottom: 16 }}>
                <Col span={6}><Card size="small"><Statistic title="池内标的" value={pool.length} valueStyle={{ color: '#cf1322' }} /></Card></Col>
                <Col span={6}><Card size="small"><Statistic title="上次扫描" value={lastScan} valueStyle={{ fontSize: 16 }} /></Card></Col>
                <Col span={6}><Card size="small"><Statistic title="累计扫描次数" value={scanCount} /></Card></Col>
                <Col span={6}><Card size="small"><Statistic title="选股周期" value={`${period} 分钟`} /></Card></Col>
              </Row>

              <Card>
                <div style={{ marginBottom: 12 }}>
                  <Space>
                    <span style={{ color: token.colorTextSecondary }}>结果内二次筛选：CCI ≥</span>
                    <InputNumber min={0} max={500} value={refineMinCci} onChange={v => setRefineMinCci(v || 0)} style={{ width: 100 }} />
                    <Button icon={<FilterOutlined />} onClick={handleRefine}>精筛</Button>
                    {refined && <Button onClick={clearRefine}>取消筛选</Button>}
                    <Divider type="vertical" />
                    <Button icon={<ExportOutlined />} onClick={handleExport} disabled={displayList.length === 0}>导出CSV</Button>
                    {refined && <Tag color="blue">已筛选：{refined.length} 只</Tag>}
                  </Space>
                </div>
                {displayList.length > 0 ? (
                  <Table
                    rowKey="symbol"
                    columns={poolColumns}
                    dataSource={displayList}
                    size="small"
                    pagination={{ pageSize: 20, showSizeChanger: true }}
                    scroll={{ x: 1100 }}
                  />
                ) : (
                  <Empty description={running ? '监控中，等待符合条件的标的...' : '点击「启动监控」开始盘中实时选股'}>
                    {running && candidates > 0 && (
                      <div style={{ color: '#999', fontSize: 13, marginTop: 8, lineHeight: 1.8 }}>
                        <p>已扫描 <b>{candidates}</b> 只股票，无匹配结果</p>
                        {scanLogs.length > 0 && scanLogs.map((log, i) => (
                          <p key={i} style={{ margin: 0 }}>{log}</p>
                        ))}
                        <p style={{ marginTop: 4, color: '#faad14' }}>
                          建议: 降低 CCI 阈值、增加 MACD 回溯根数、或切换为 OR 模式
                        </p>
                      </div>
                    )}
                  </Empty>
                )}
              </Card>
            </>
          ),
        },
        {
          key: 'watch',
          label: (
            <span>
              <StarFilled style={{ color: '#faad14', marginRight: 4 }} />
              自选股 ({watchlist.length})
            </span>
          ),
          children: (
            <Card>
              {watchlist.length > 0 ? (
                <Table
                  rowKey="symbol"
                  columns={watchColumns}
                  dataSource={watchlist}
                  size="small"
                  loading={watchLoading}
                  pagination={{ pageSize: 20, showSizeChanger: true }}
                  scroll={{ x: 800 }}
                />
              ) : (
                <Empty description="暂无自选股，可在「实时选股池」中点击「自选」添加" />
              )}
            </Card>
          ),
        },
      ]} />
    </div>
  )
}
