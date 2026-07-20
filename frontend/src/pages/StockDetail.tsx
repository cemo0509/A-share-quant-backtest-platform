import { useEffect, useState, useRef } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import {
  Card, Tabs, Button, Space, message, Spin, Descriptions, Tag, Table, Row, Col, theme
} from 'antd'
import { ArrowLeftOutlined, StarOutlined, StarFilled } from '@ant-design/icons'
import * as echarts from 'echarts'
import { getKline, getIntraday, getIndicators, getRealtimeQuotes, getWatchlist, addToWatchlist, removeFromWatchlist, getSignals } from '../api'
import { useStore, resolveDark } from '../stores'

/** 外部 iframe 组件，带加载失败回退 + 超时兜底 */
function ExternalIframe({ src, title, fallback }: { src: string; title: string; fallback: string }) {
  const { token } = theme.useToken()
  const [iframeError, setIframeError] = useState(false)
  const [iframeLoading, setIframeLoading] = useState(true)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  // 超时兜底：东方财富等站点被 X-Frame-Options 拦截时浏览器不触发 onError，
  // 也无超时事件，会长期空白/转圈。这里用定时器在超时后强制回退提示。
  const TIMEOUT = 8000
  const startTimer = () => {
    if (timerRef.current) clearTimeout(timerRef.current)
    timerRef.current = setTimeout(() => {
      setIframeError(true)
      setIframeLoading(false)
    }, TIMEOUT)
  }
  const stopTimer = () => {
    if (timerRef.current) {
      clearTimeout(timerRef.current)
      timerRef.current = null
    }
  }

  useEffect(() => {
    // src 变化时重置状态并启动超时计时
    setIframeError(false)
    setIframeLoading(true)
    startTimer()
    return stopTimer
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [src])

  const handleRetry = () => {
    setIframeError(false)
    setIframeLoading(true)
    startTimer()
  }

  return (
    <div style={{ position: 'relative', height: 600 }}>
      {iframeLoading && !iframeError && (
        <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', background: token.colorBgContainer }}>
          <Spin tip="正在加载外部数据..." />
        </div>
      )}
      {iframeError ? (
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '100%', color: token.colorTextSecondary, flexDirection: 'column', gap: 8 }}>
          <span>{fallback}</span>
          <Button size="small" onClick={handleRetry}>重试</Button>
        </div>
      ) : (
        <iframe
          src={src}
          style={{ width: '100%', height: '100%', border: 'none', display: iframeLoading ? 'none' : 'block', background: token.colorBgContainer }}
          title={title}
          onLoad={() => { stopTimer(); setIframeLoading(false) }}
          onError={() => { stopTimer(); setIframeError(true); setIframeLoading(false) }}
        />
      )}
    </div>
  )
}

export default function StockDetail() {
  const { symbol } = useParams<{ symbol: string }>()
  const navigate = useNavigate()
  const [loading, setLoading] = useState(true)
  const [klineData, setKlineData] = useState<any[]>([])
  const [intradayData, setIntradayData] = useState<any[]>([])
  const [indicators, setIndicators] = useState<any>({})
  const [realtimeInfo, setRealtimeInfo] = useState<any>(null)
  const [activeTab, setActiveTab] = useState('kline')
  const [klinePeriod, setKlinePeriod] = useState('daily')
  const [indicatorType, setIndicatorType] = useState('macd')
  const [inWatchlist, setInWatchlist] = useState(false)
  const [signalStrategy, setSignalStrategy] = useState('macd')
  const mode = useStore((s) => s.mode)
  const isDark = resolveDark(mode)
  const [signals, setSignals] = useState<any[]>([])

  const klineChartRef = useRef<HTMLDivElement>(null)
  const intradayChartRef = useRef<HTMLDivElement>(null)
  const klineChart = useRef<echarts.ECharts | null>(null)
  const intradayChart = useRef<echarts.ECharts | null>(null)

  // 加载数据
  useEffect(() => {
    if (!symbol) return
    loadData()
    checkWatchlist()
  }, [symbol, klinePeriod, signalStrategy])

  const loadData = async () => {
    setLoading(true)
    const errors: string[] = []

    // 独立请求：每个接口失败不影响其他
    const run = async <T,>(label: string, fn: () => Promise<T>, setter: (data: T) => void) => {
      try {
        const res = await fn()
        setter(res)
      } catch (e: any) {
        const msg = e?.response?.data?.detail || e?.message || '未知错误'
        errors.push(`${label}: ${msg}`)
      }
    }

    await Promise.all([
      // K线数据
      run('K线', async () => {
        const res = await getKline({ symbol: symbol!, period: klinePeriod, limit: 200, adjust: 'qfq' })
        setKlineData(res.data.data || [])
        return res
      }, () => {}),
      // 技术指标（周期/条数与 K 线一致，保证日期严格对齐）
      run('技术指标', async () => {
        const res = await getIndicators({ symbol: symbol!, period: klinePeriod, limit: 200 })
        setIndicators(res.data.data || {})
        return res
      }, () => {}),
      // 实时行情
      run('实时行情', async () => {
        const res = await getRealtimeQuotes([symbol!.replace('sh', '').replace('sz', '')])
        const rt = res.data.data?.[0]
        if (rt) {
          setRealtimeInfo({
            ...rt,
            change_pct: rt.change_pct ?? rt.pct_change ?? 0,
            change_amount: rt.change_amount ?? rt.change ?? 0,
          })
        }
        return res
      }, () => {}),
      // 策略信号（仅日线）
      run('策略信号', async () => {
        if (klinePeriod !== 'daily') return { data: { data: [] } }
        const res = await getSignals({ symbol: symbol!, strategy: signalStrategy })
        setSignals(res.data.data || [])
        return res
      }, () => {}),
      // 分时图数据
      run('分时', async () => {
        const res = await getIntraday(symbol!)
        setIntradayData(res.data.data || [])
        return res
      }, () => {}),
    ])

    if (errors.length > 0) {
      message.warning(`部分数据加载失败: ${errors.join('; ')}`, 5)
    }

    setLoading(false)
  }

  const checkWatchlist = async () => {
    try {
      const res = await getWatchlist()
      const list = res.data.data || []
      setInWatchlist(list.some((w: any) => w.symbol === symbol))
    } catch {
      // 自选池检查失败不阻塞主流程
    }
  }

  const toggleWatchlist = async () => {
    try {
      if (inWatchlist) {
        await removeFromWatchlist(symbol!)
        setInWatchlist(false)
        message.success('已从自选池移除')
      } else {
        await addToWatchlist({ symbol: symbol!, name: realtimeInfo?.name || symbol! })
        setInWatchlist(true)
        message.success('已添加到自选池')
      }
    } catch (e) {
      message.error('操作失败: ' + (e instanceof Error ? e.message : '未知错误'))
    }
  }

  // K线 + 成交量 + 技术指标（合并为同一图表，共用 X 轴与 dataZoom，缩放联动）
  useEffect(() => {
    if (!klineChartRef.current || klineData.length === 0) return

    // React 18 StrictMode 会双执行 useEffect；主题切换时强制重建实例
    klineChart.current?.dispose()
    klineChart.current = echarts.init(klineChartRef.current, isDark ? 'dark' : undefined)
    klineChart.current.resize()

    const dates = klineData.map((d: any) => d.date)
    const ohlc = klineData.map((d: any) => [d.open, d.close, d.low, d.high])
    const volumes = klineData.map((d: any) => d.volume)
    // 指标现在与 K 线使用同一周期、同一日期范围，直接按完整数组取用，不再尾部切片
    const ma5 = indicators.ma5 || []
    const ma10 = indicators.ma10 || []
    const ma20 = indicators.ma20 || []

    // 构建买卖点标记数据
    const buyPoints: any[] = []
    const sellPoints: any[] = []
    signals.forEach((s: any) => {
      const idx = dates.indexOf(s.date)
      if (idx >= 0) {
        if (s.type === 'buy') {
          buyPoints.push([idx, ohlc[idx][3] * 0.97])  // 买入标记在最低点下方
        } else {
          sellPoints.push([idx, ohlc[idx][2] * 1.03])  // 卖出标记在最高点上方
        }
      }
    })

    // 第三段：指标区（MACD/KDJ/RSI/...）
    const indicatorSeries: any[] = []
    const indicatorYAxis: any[] = []

    const pushIndicator = (name: string, data: any, color: string, extra: any = {}) => {
      indicatorSeries.push({
        name, type: 'line', data, xAxisIndex: 2, yAxisIndex: 2,
        smooth: true, showSymbol: false, lineStyle: { color, width: 1 }, ...extra,
      })
    }

    if (indicatorType === 'macd' && indicators.macd) {
      indicatorSeries.push({
        name: 'DIF', type: 'line', data: indicators.macd.dif || [], xAxisIndex: 2, yAxisIndex: 2,
        smooth: true, showSymbol: false, lineStyle: { color: '#2196f3' },
      })
      indicatorSeries.push({
        name: 'DEA', type: 'line', data: indicators.macd.dea || [], xAxisIndex: 2, yAxisIndex: 2,
        smooth: true, showSymbol: false, lineStyle: { color: '#ff9800' },
      })
      indicatorSeries.push({
        name: 'MACD柱', type: 'bar', data: indicators.macd.hist || [], xAxisIndex: 2, yAxisIndex: 2,
        itemStyle: { color: (p: any) => p.value >= 0 ? '#ef5350' : '#26a69a' },
      })
    } else if (indicatorType === 'kdj' && indicators.kdj) {
      pushIndicator('K', indicators.kdj.k || [], '#2196f3')
      pushIndicator('D', indicators.kdj.d || [], '#ff9800')
      pushIndicator('J', indicators.kdj.j || [], '#9c27b0')
    } else if (indicatorType === 'rsi') {
      pushIndicator('RSI6', indicators.rsi6 || [], '#2196f3')
      pushIndicator('RSI12', indicators.rsi12 || [], '#ff9800')
      pushIndicator('RSI24', indicators.rsi24 || [], '#9c27b0')
    } else if (indicatorType === 'wr') {
      pushIndicator('WR6', indicators.wr6 || [], '#2196f3')
      pushIndicator('WR10', indicators.wr10 || [], '#ff9800')
    } else if (indicatorType === 'obv') {
      pushIndicator('OBV', indicators.obv || [], '#2196f3', { areaStyle: {} })
    } else if (indicatorType === 'bias') {
      pushIndicator('BIAS6', indicators.bias6 || [], '#2196f3')
      pushIndicator('BIAS12', indicators.bias12 || [], '#ff9800')
      pushIndicator('BIAS24', indicators.bias24 || [], '#9c27b0')
    } else if (indicatorType === 'cci') {
      pushIndicator('CCI14', indicators.cci14 || [], '#2196f3')
    } else if (indicatorType === 'boll' && indicators.boll) {
      indicatorSeries.push({
        name: '上轨', type: 'line', data: indicators.boll.upper || [], xAxisIndex: 2, yAxisIndex: 2,
        showSymbol: false, lineStyle: { color: '#9c27b0', type: 'dashed' },
      })
      indicatorSeries.push({
        name: '中轨', type: 'line', data: indicators.boll.middle || [], xAxisIndex: 2, yAxisIndex: 2,
        showSymbol: false, lineStyle: { color: '#ff9800' },
      })
      indicatorSeries.push({
        name: '下轨', type: 'line', data: indicators.boll.lower || [], xAxisIndex: 2, yAxisIndex: 2,
        showSymbol: false, lineStyle: { color: '#9c27b0', type: 'dashed' },
      })
    }

    // 三段 grid：价格 / 成交量 / 指标，共用一根 X 轴（category 索引对齐）
    const grid = [
      { left: '8%', right: '3%', height: '46%', top: '4%' },
      { left: '8%', right: '3%', height: '16%', top: '54%' },
      { left: '8%', right: '3%', height: '20%', top: '74%' },
    ]

    // dataZoom 三个 grid 联动缩放（与东财/同花顺一致的联动体验）
    const dataZoom = [
      { type: 'inside', xAxisIndex: [0, 1, 2], start: 60, end: 100 },
      { type: 'slider', xAxisIndex: [0, 1, 2], start: 60, end: 100, bottom: 4, height: 16 },
    ]

    const option: any = {
      tooltip: { trigger: 'axis', axisPointer: { type: 'cross' } },
      legend: { data: ['MA5', 'MA10', 'MA20'], top: 0, right: 10, itemWidth: 14, itemHeight: 8 },
      grid,
      dataZoom,
      xAxis: [
        { type: 'category', data: dates, gridIndex: 0, axisLabel: { show: false }, boundaryGap: true },
        { type: 'category', data: dates, gridIndex: 1, axisLabel: { show: false }, boundaryGap: true },
        { type: 'category', data: dates, gridIndex: 2, boundaryGap: true },
      ],
      yAxis: [
        { type: 'value', gridIndex: 0, scale: true },
        { type: 'value', gridIndex: 1, scale: true },
        { type: 'value', gridIndex: 2, scale: true },
      ],
      series: [
        { name: 'K线', type: 'candlestick', data: ohlc, xAxisIndex: 0, yAxisIndex: 0,
          itemStyle: { color: '#ef5350', color0: '#26a69a', borderColor: '#ef5350', borderColor0: '#26a69a' } },
        { name: 'MA5', type: 'line', data: ma5, smooth: true, lineStyle: { color: '#ffcc00', width: 1 }, xAxisIndex: 0, yAxisIndex: 0 },
        { name: 'MA10', type: 'line', data: ma10, smooth: true, lineStyle: { color: '#ff6600', width: 1 }, xAxisIndex: 0, yAxisIndex: 0 },
        { name: 'MA20', type: 'line', data: ma20, smooth: true, lineStyle: { color: '#cc00ff', width: 1 }, xAxisIndex: 0, yAxisIndex: 0 },
        {
          name: '买入', type: 'scatter', data: buyPoints,
          xAxisIndex: 0, yAxisIndex: 0, symbol: 'triangle', symbolSize: 14,
          itemStyle: { color: '#f5222d' }, symbolRotate: 0, z: 10,
        },
        {
          name: '卖出', type: 'scatter', data: sellPoints,
          xAxisIndex: 0, yAxisIndex: 0, symbol: 'triangle', symbolSize: 14,
          itemStyle: { color: '#52c41a' }, symbolRotate: 180, z: 10,
        },
        { name: '成交量', type: 'bar', data: volumes, xAxisIndex: 1, yAxisIndex: 1,
          itemStyle: { color: (p: any) => ohlc[p.dataIndex]?.[1] >= ohlc[p.dataIndex]?.[0] ? '#ef5350' : '#26a69a' } },
        ...indicatorSeries,
      ],
    }

    try {
      klineChart.current.setOption(option, true)
    } catch (e) {
      console.error('[KLine] setOption failed', e)
    }

    return () => {
      try { klineChart.current?.dispose() } catch (_) {}
      klineChart.current = null
    }
  }, [klineData, indicators, indicatorType, signals, loading, isDark])

  // 分时图
  useEffect(() => {
    if (!intradayChartRef.current || intradayData.length === 0) return
    intradayChart.current?.dispose()
    intradayChart.current = echarts.init(intradayChartRef.current, isDark ? 'dark' : undefined)
    intradayChart.current.resize()

    const times = intradayData.map((d: any) => d.time?.slice(-5) || '')
    const prices = intradayData.map((d: any) => d.price)
    const option: any = {
      tooltip: { trigger: 'axis' },
      grid: { left: '8%', right: '3%', top: 20, bottom: 20 },
      xAxis: { type: 'category', data: times },
      yAxis: { type: 'value', scale: true },
      series: [{
        type: 'line', data: prices, smooth: true, showSymbol: false,
        areaStyle: { color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
          { offset: 0, color: 'rgba(239,83,80,0.3)' }, { offset: 1, color: 'rgba(239,83,80,0.02)' },
        ])},
        lineStyle: { color: '#ef5350' },
      }],
    }

    try {
      intradayChart.current.setOption(option, true)
    } catch (e) {
      console.error('[Intraday] setOption failed', e)
    }

    return () => {
      try { intradayChart.current?.dispose() } catch (_) {}
      intradayChart.current = null
    }
  }, [intradayData, loading, isDark])

  // 自适应
  useEffect(() => {
    const handleResize = () => {
      klineChart.current?.resize()
      intradayChart.current?.resize()
    }
    window.addEventListener('resize', handleResize)
    return () => window.removeEventListener('resize', handleResize)
  }, [])

  const emCode = symbol?.replace('sh', 'SH').replace('sz', 'SZ') || ''

  const indicatorButtons = [
    { key: 'macd', label: 'MACD' }, { key: 'kdj', label: 'KDJ' },
    { key: 'rsi', label: 'RSI' }, { key: 'boll', label: 'BOLL' },
    { key: 'wr', label: 'WR' }, { key: 'obv', label: 'OBV' },
    { key: 'bias', label: 'BIAS' }, { key: 'cci', label: 'CCI' },
  ]

  if (loading) {
    return <div style={{ textAlign: 'center', padding: 100 }}><Spin size="large" /></div>
  }

  const info = realtimeInfo || {}

  return (
    <div>
      {/* 顶部信息栏 */}
      <Card size="small" style={{ marginBottom: 16 }}>
        <Row align="middle" justify="space-between">
          <Col>
            <Space>
              <Button icon={<ArrowLeftOutlined />} onClick={() => navigate(-1)}>返回</Button>
              <span style={{ fontSize: 20, fontWeight: 700 }}>{symbol}</span>
              <span style={{ fontSize: 18 }}>{info.name || symbol}</span>
              <Tag color="blue">{info.sector || '未知'}</Tag>
              <span style={{ fontSize: 24, fontWeight: 700, color: (info.change_pct || 0) >= 0 ? '#cf1322' : '#3f8600' }}>
                {info.price?.toFixed(2) || '-'}
              </span>
              <span style={{ color: (info.change_pct || 0) >= 0 ? '#cf1322' : '#3f8600' }}>
                {info.change_amount > 0 ? '+' : ''}{info.change_amount?.toFixed(2) || '-'}
                {' '}({info.change_pct > 0 ? '+' : ''}{info.change_pct?.toFixed(2) || '-'}%)
              </span>
            </Space>
          </Col>
          <Col>
            <Button
              icon={inWatchlist ? <StarFilled /> : <StarOutlined />}
              onClick={toggleWatchlist}
              type={inWatchlist ? 'primary' : 'default'}
            >
              {inWatchlist ? '已自选' : '加入自选'}
            </Button>
          </Col>
        </Row>
      </Card>

      <Tabs activeKey={activeTab} onChange={setActiveTab} items={[
        {
          key: 'kline',
          label: 'K线图',
          children: (
            <Card>
              <Space style={{ marginBottom: 12 }}>
                {['daily', 'weekly', 'monthly'].map(p => (
                  <Button key={p} size="small" type={klinePeriod === p ? 'primary' : 'default'}
                    onClick={() => setKlinePeriod(p)}>
                    {p === 'daily' ? '日K' : p === 'weekly' ? '周K' : '月K'}
                  </Button>
                ))}
              </Space>
              <div ref={klineChartRef} style={{ height: 620 }} />
              <div style={{ marginTop: 8, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <Space>
                  <span style={{ fontSize: 12, color: '#999' }}>信号:</span>
                  {[
                    { key: 'macd', label: 'MACD' },
                    { key: 'kdj', label: 'KDJ' },
                    { key: 'rsi', label: 'RSI' },
                    { key: 'ma_cross', label: '均线交叉' },
                    { key: 'bollinger', label: '布林带' },
                  ].map(s => (
                    <Button key={s.key} size="small"
                      type={signalStrategy === s.key ? 'primary' : 'default'}
                      onClick={() => setSignalStrategy(s.key)}>
                      {s.label}
                    </Button>
                  ))}
                </Space>
              </div>
              <div style={{ marginTop: 8 }}>
                <Space>
                  <span style={{ fontSize: 12, color: '#999' }}>指标:</span>
                  {indicatorButtons.map(b => (
                    <Button key={b.key} size="small" type={indicatorType === b.key ? 'primary' : 'default'}
                      onClick={() => setIndicatorType(b.key)}>{b.label}</Button>
                  ))}
                </Space>
              </div>
            </Card>
          ),
        },
        {
          key: 'intraday',
          label: '分时图',
          children: (
            <Card>
              <div ref={intradayChartRef} style={{ height: 400 }} />
              {intradayData.length === 0 && (
                <div style={{ textAlign: 'center', color: '#999', marginTop: 20 }}>
                  分时数据仅在交易时段可用
                </div>
              )}
            </Card>
          ),
        },
        {
          key: 'info',
          label: '基本信息',
          children: (
            <Card>
              <Descriptions column={4} size="small" bordered>
                <Descriptions.Item label="最新">{info.price?.toFixed(2)}</Descriptions.Item>
                <Descriptions.Item label="今开">{info.open?.toFixed(2)}</Descriptions.Item>
                <Descriptions.Item label="最高">{info.high?.toFixed(2)}</Descriptions.Item>
                <Descriptions.Item label="最低">{info.low?.toFixed(2)}</Descriptions.Item>
                <Descriptions.Item label="涨跌">{info.change_amount?.toFixed(2)}</Descriptions.Item>
                <Descriptions.Item label="昨收">{info.pre_close?.toFixed(2)}</Descriptions.Item>
                <Descriptions.Item label="涨幅%">{info.change_pct?.toFixed(2)}%</Descriptions.Item>
                <Descriptions.Item label="振幅%">{info.amplitude?.toFixed(2)}%</Descriptions.Item>
                <Descriptions.Item label="总量">{info.volume?.toLocaleString()}</Descriptions.Item>
                <Descriptions.Item label="成交额">{info.amount?.toLocaleString()}</Descriptions.Item>
                <Descriptions.Item label="换手%">{info.turnover_rate?.toFixed(2)}%</Descriptions.Item>
                <Descriptions.Item label="量比">{info.volume_ratio?.toFixed(2)}</Descriptions.Item>
                <Descriptions.Item label="均价">{info.avg_price?.toFixed(2)}</Descriptions.Item>
                <Descriptions.Item label="市盈率">{info.pe_ratio?.toFixed(2)}</Descriptions.Item>
                <Descriptions.Item label="市净率">{info.pb_ratio?.toFixed(2)}</Descriptions.Item>
                <Descriptions.Item label="总市值(亿)">{info.total_market_cap?.toFixed(1)}</Descriptions.Item>
                <Descriptions.Item label="流通市值(亿)">{info.float_market_cap?.toFixed(1)}</Descriptions.Item>
                <Descriptions.Item label="涨停价">{info.limit_up?.toFixed(2)}</Descriptions.Item>
                <Descriptions.Item label="跌停价">{info.limit_down?.toFixed(2)}</Descriptions.Item>
                <Descriptions.Item label="委比%">{info.commission_ratio?.toFixed(2)}%</Descriptions.Item>
                <Descriptions.Item label="委差">{info.commission_diff?.toLocaleString()}</Descriptions.Item>
                <Descriptions.Item label="内盘">{info.inner_volume?.toLocaleString()}</Descriptions.Item>
                <Descriptions.Item label="外盘">{info.outer_volume?.toLocaleString()}</Descriptions.Item>
                {/* 涨跌统计 */}
                <Descriptions.Item label="3日涨幅%">
                  <span style={{ color: (info.change_3d || 0) >= 0 ? '#cf1322' : '#3f8600' }}>
                    {info.change_3d != null ? `${info.change_3d >= 0 ? '+' : ''}${info.change_3d.toFixed(2)}%` : '-'}
                  </span>
                </Descriptions.Item>
                <Descriptions.Item label="6日涨幅%">
                  <span style={{ color: (info.change_6d || 0) >= 0 ? '#cf1322' : '#3f8600' }}>
                    {info.change_6d != null ? `${info.change_6d >= 0 ? '+' : ''}${info.change_6d.toFixed(2)}%` : '-'}
                  </span>
                </Descriptions.Item>
                <Descriptions.Item label="本月涨幅%">
                  <span style={{ color: (info.change_mtd || 0) >= 0 ? '#cf1322' : '#3f8600' }}>
                    {info.change_mtd != null ? `${info.change_mtd >= 0 ? '+' : ''}${info.change_mtd.toFixed(2)}%` : '-'}
                  </span>
                </Descriptions.Item>
                <Descriptions.Item label="今年涨幅%">
                  <span style={{ color: (info.change_ytd || 0) >= 0 ? '#cf1322' : '#3f8600' }}>
                    {info.change_ytd != null ? `${info.change_ytd >= 0 ? '+' : ''}${info.change_ytd.toFixed(2)}%` : '-'}
                  </span>
                </Descriptions.Item>
                <Descriptions.Item label="近一月涨幅%">
                  <span style={{ color: (info.change_1m || 0) >= 0 ? '#cf1322' : '#3f8600' }}>
                    {info.change_1m != null ? `${info.change_1m >= 0 ? '+' : ''}${info.change_1m.toFixed(2)}%` : '-'}
                  </span>
                </Descriptions.Item>
                <Descriptions.Item label="近一年涨幅%">
                  <span style={{ color: (info.change_1y || 0) >= 0 ? '#cf1322' : '#3f8600' }}>
                    {info.change_1y != null ? `${info.change_1y >= 0 ? '+' : ''}${info.change_1y.toFixed(2)}%` : '-'}
                  </span>
                </Descriptions.Item>
                <Descriptions.Item label="连涨天数">{info.consecutive_up || 0}天</Descriptions.Item>
                <Descriptions.Item label="3日换手%">{info.turnover_3d?.toFixed(2) || '-'}%</Descriptions.Item>
                <Descriptions.Item label="6日换手%">{info.turnover_6d?.toFixed(2) || '-'}%</Descriptions.Item>
                <Descriptions.Item label="更新时间">{info.update_time || '-'}</Descriptions.Item>
              </Descriptions>
            </Card>
          ),
        },
        {
          key: 'finance',
          label: '财务',
          children: (
            <Card>
              <ExternalIframe
                src={`https://emweb.securities.eastmoney.com/pc_hsf10/pages/index.html?type=web&code=${emCode}&color=r#/cwfx`}
                title="财务分析"
                fallback="财务数据加载失败，请检查网络连接后刷新重试"
              />
            </Card>
          ),
        },
        {
          key: 'notice',
          label: '公告',
          children: (
            <Card>
              <ExternalIframe
                src={`https://data.eastmoney.com/notices/stock/${symbol?.replace('sh', '').replace('sz', '')}.html`}
                title="公司公告"
                fallback="公告数据加载失败，请检查网络连接后刷新重试"
              />
            </Card>
          ),
        },
        {
          key: 'report',
          label: '研报',
          children: (
            <Card>
              <ExternalIframe
                src={`https://data.eastmoney.com/report/stock/${symbol?.replace('sh', '').replace('sz', '')}.html`}
                title="券商研报"
                fallback="研报数据加载失败，请检查网络连接后刷新重试"
              />
            </Card>
          ),
        },
      ]} />
    </div>
  )
}
