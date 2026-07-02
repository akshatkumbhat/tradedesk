import { useEffect, useRef } from 'react'
import {
  createChart,
  CandlestickSeries,
  HistogramSeries,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from 'lightweight-charts'
import type { Bar } from '../api'

export function CandleChart({ bars }: { bars: Bar[] }) {
  const ref = useRef<HTMLDivElement>(null)
  const chartRef = useRef<IChartApi | null>(null)
  const candlesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const volumeRef = useRef<ISeriesApi<'Histogram'> | null>(null)

  // Chart and series are created once; the data effect below only calls setData.
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
      grid: {
        vertLines: { visible: false },
        horzLines: { color: 'rgba(0,0,0,0.05)' },
      },
      rightPriceScale: { borderVisible: false },
      timeScale: { borderVisible: false },
      crosshair: {
        vertLine: { color: 'rgba(0,0,0,0.2)', labelBackgroundColor: '#1d1d1f' },
        horzLine: { color: 'rgba(0,0,0,0.2)', labelBackgroundColor: '#1d1d1f' },
      },
    })
    candlesRef.current = chart.addSeries(CandlestickSeries, {
      upColor: '#34c759',
      downColor: '#ff3b30',
      borderVisible: false,
      wickUpColor: '#34c759',
      wickDownColor: '#ff3b30',
    })
    volumeRef.current = chart.addSeries(HistogramSeries, {
      priceFormat: { type: 'volume' },
      priceScaleId: 'vol',
      color: 'rgba(0,0,0,0.12)',
    })
    chart.priceScale('vol').applyOptions({ scaleMargins: { top: 0.82, bottom: 0 } })
    chartRef.current = chart
    return () => {
      chart.remove()
      chartRef.current = null
      candlesRef.current = null
      volumeRef.current = null
    }
  }, [])

  useEffect(() => {
    const chart = chartRef.current
    const candles = candlesRef.current
    const volume = volumeRef.current
    if (!chart || !candles || !volume) return
    const toTs = (iso: string) => (Date.parse(iso) / 1000) as UTCTimestamp
    candles.setData(
      bars.map((b) => ({ time: toTs(b.time), open: b.open, high: b.high, low: b.low, close: b.close })),
    )
    volume.setData(bars.map((b) => ({ time: toTs(b.time), value: b.volume })))
    chart.timeScale().fitContent()
  }, [bars])

  return <div ref={ref} className="w-full h-full" />
}
