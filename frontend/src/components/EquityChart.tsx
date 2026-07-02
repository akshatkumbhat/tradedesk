import { useEffect, useRef } from 'react'
import {
  createChart,
  AreaSeries,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from 'lightweight-charts'

export function EquityChart({ points }: { points: { time: string; equity: number }[] }) {
  const ref = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const seriesRef = useRef<ISeriesApi<'Area'> | null>(null)

  useEffect(() => {
    if (!ref.current) return
    const chart = createChart(ref.current, {
      autoSize: true,
      layout: {
        background: { color: 'transparent' },
        textColor: '#6e6e73',
        fontFamily:
          '-apple-system, BlinkMacSystemFont, "SF Pro Text", "Helvetica Neue", sans-serif',
        attributionLogo: false,
      },
      grid: { vertLines: { visible: false }, horzLines: { color: 'rgba(0,0,0,0.05)' } },
      rightPriceScale: { borderVisible: false },
      timeScale: { borderVisible: false },
      crosshair: {
        vertLine: { color: 'rgba(0,0,0,0.2)', labelBackgroundColor: '#1d1d1f' },
        horzLine: { color: 'rgba(0,0,0,0.2)', labelBackgroundColor: '#1d1d1f' },
      },
    })
    seriesRef.current = chart.addSeries(AreaSeries, {
      lineColor: '#0071e3',
      topColor: 'rgba(0,113,227,0.18)',
      bottomColor: 'rgba(0,113,227,0.01)',
      lineWidth: 2,
    })
    chartRef.current = chart
    return () => {
      chart.remove()
      chartRef.current = null
      seriesRef.current = null
    }
  }, [])

  useEffect(() => {
    const chart = chartRef.current
    const series = seriesRef.current
    if (!chart || !series) return
    series.setData(
      points.map((p) => ({ time: (Date.parse(p.time) / 1000) as UTCTimestamp, value: p.equity })),
    )
    chart.timeScale().fitContent()
  }, [points])

  return <div ref={ref} className="w-full h-full" />
}
