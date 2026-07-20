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

    chart.setOption({
      tooltip: { trigger: 'axis' },
      xAxis: { type: 'category', data: dates, axisLabel: { rotate: 30 } },
      yAxis: { type: 'value', name: '资金' },
      series: [
        {
          name: '账户价值',
          type: 'line',
          data: values,
          smooth: true,
          showSymbol: false,
          lineStyle: { width: 2 },
          areaStyle: { opacity: 0.1 },
        },
      ],
      grid: { left: 60, right: 30, top: 30, bottom: 50 },
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
