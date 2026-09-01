import { useEffect, useRef } from 'react'
import * as echarts from 'echarts'
import { Empty } from 'antd'
import { useStore, resolveDark } from '../stores'

export default function EquityCurve() {
  const ref = useRef<HTMLDivElement>(null)
  const chartRef = useRef<echarts.ECharts | null>(null)
  const result = useStore((s) => s.result)
  const mode = useStore((s) => s.mode)
  const isDark = resolveDark(mode)

  useEffect(() => {
    if (!ref.current) return
    if (!result || !result.equity_curve || result.equity_curve.length === 0) {
      // 清理旧图表
      chartRef.current?.dispose()
      chartRef.current = null
      return
    }

    // 主题切换时需重建实例（echarts.init 的主题参数不可动态改）
    chartRef.current?.dispose()
    chartRef.current = echarts.init(ref.current, isDark ? 'dark' : undefined)
    const chart = chartRef.current

    const dates = result.equity_curve.map((p) => p.date)
    const values = result.equity_curve.map((p) => p.value)

    // 基准曲线（P0-10）：把「买入持有」和「沪深300」画在同一张图，
    // 策略线跑不赢基准一目了然。基准可能缺失（如网络拉不到指数），需容错。
    const series: any[] = [
      {
        name: '策略',
        type: 'line',
        data: values,
        smooth: true,
        showSymbol: false,
        lineStyle: { width: 2 },
        areaStyle: { opacity: 0.1 },
      },
    ]

    const bm = result.benchmarks
    if (bm?.buy_hold?.equity_curve?.length) {
      series.push({
        name: '买入持有',
        type: 'line',
        data: bm.buy_hold.equity_curve.map((p: any) => p.value),
        smooth: true,
        showSymbol: false,
        lineStyle: { width: 1.5, type: 'dashed' },
      })
    }
    if (bm?.hs300?.equity_curve?.length) {
      series.push({
        name: '沪深300',
        type: 'line',
        data: bm.hs300.equity_curve.map((p: any) => p.value),
        smooth: true,
        showSymbol: false,
        lineStyle: { width: 1.5, type: 'dotted' },
      })
    }

    chart.setOption({
      tooltip: { trigger: 'axis' },
      legend: series.length > 1 ? { top: 0 } : undefined,
      xAxis: { type: 'category', data: dates, axisLabel: { rotate: 30 } },
      yAxis: { type: 'value', name: '资金' },
      series,
      grid: { left: 60, right: 30, top: series.length > 1 ? 50 : 30, bottom: 50 },
    })

    const handleResize = () => {
      if (ref.current) chart.resize()
    }
    window.addEventListener('resize', handleResize)
    return () => {
      window.removeEventListener('resize', handleResize)
    }
  }, [result, isDark])

  // 组件卸载时清理
  useEffect(() => {
    return () => {
      chartRef.current?.dispose()
    }
  }, [])

  if (!result || !result.equity_curve || result.equity_curve.length === 0) {
    return <Empty description="暂无资金曲线数据" />
  }

  return <div ref={ref} style={{ width: '100%', height: 360 }} />
}
