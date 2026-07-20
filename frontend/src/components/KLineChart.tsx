import { useEffect, useRef } from 'react'
import { Empty } from 'antd'
import { useStore, resolveDark } from '../stores'
import { createChart, type IChartApi, type ISeriesApi, ColorType, CrosshairMode } from 'lightweight-charts'
import type { KLineBar, TradeRecord } from '../stores'

export default function KLineChart() {
  const ref = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const result = useStore((s) => s.result)
  const mode = useStore((s) => s.mode)
  const isDark = resolveDark(mode)

  useEffect(() => {
    if (!ref.current) return
    if (!result || !result.kline || result.kline.length === 0) {
      chartRef.current?.remove()
      chartRef.current = null
      return
    }

    // 清理旧图表
    if (chartRef.current) {
      try { chartRef.current.remove() } catch (_) {}
    }

    const kline: KLineBar[] = result.kline
    const trades: TradeRecord[] = result.trades || []

    // 明暗主题配色
    const palette = isDark
      ? {
          background: '#1e1e1e',
          text: '#d4d4d4',
          grid: '#333',
          border: '#555',
        }
      : {
          background: '#ffffff',
          text: '#333333',
          grid: '#eee',
          border: '#ccc',
        }

    const chart = createChart(ref.current, {
      layout: {
        background: { type: ColorType.Solid, color: palette.background },
        textColor: palette.text,
      },
      grid: {
        vertLines: { color: palette.grid },
        horzLines: { color: palette.grid },
      },
      crosshair: {
        mode: CrosshairMode.Normal,
      },
      rightPriceScale: {
        borderColor: palette.border,
      },
      timeScale: {
        borderColor: palette.border,
        timeVisible: true,
        secondsVisible: false,
      },
    })
    chartRef.current = chart

    // 转换 K 线数据格式
    const candlestickData = kline.map((bar) => {
      // 使用日期字符串格式（YYYY-MM-DD），这是 lightweight-charts 推荐的格式
      return {
        time: bar.date,
        open: bar.open,
        high: bar.high,
        low: bar.low,
        close: bar.close,
      }
    })

    const candlestick = chart.addCandlestickSeries({
      upColor: '#ef5350',
      downColor: '#26a69a',
      borderUpColor: '#ef5350',
      borderDownColor: '#26a69a',
      wickUpColor: '#ef5350',
      wickDownColor: '#26a69a',
    })
    candlestick.setData(candlestickData)

    // 添加买卖点标记
    const buyMarkers: Array<{ time: string; position: 'belowBar'; color: string; shape: 'arrowUp'; text: string }> = []
    const sellMarkers: Array<{ time: string; position: 'aboveBar'; color: string; shape: 'arrowDown'; text: string }> = []

    trades.forEach((t) => {
      if (t.action === '买入') {
        buyMarkers.push({
          time: t.date,
          position: 'belowBar',
          color: '#3f8600',
          shape: 'arrowUp',
          text: `买 ${t.price}`,
        })
      } else if (t.action === '卖出') {
        sellMarkers.push({
          time: t.date,
          position: 'aboveBar',
          color: '#cf1322',
          shape: 'arrowDown',
          text: `卖 ${t.price}`,
        })
      }
    })

    candlestick.setMarkers([...buyMarkers, ...sellMarkers])

    // 自适应大小
    const handleResize = () => {
      if (ref.current) chart.applyOptions({ width: ref.current.clientWidth })
    }
    const observer = new ResizeObserver(handleResize)
    observer.observe(ref.current)
    if (ref.current) chart.applyOptions({ width: ref.current.clientWidth })

    return () => {
      observer.disconnect()
      try { chart.remove() } catch (_) {}
    }
  }, [result, isDark])

  if (!result || !result.kline || result.kline.length === 0) {
    return <Empty description="暂无K线数据" />
  }

  return <div ref={ref} style={{ width: '100%', height: 400 }} />
}
