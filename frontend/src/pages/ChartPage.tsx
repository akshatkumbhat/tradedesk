import { useEffect, useState } from 'react'
import { api, ApiError, type Bar } from '../api'
import { CandleChart } from '../components/CandleChart'
import { ConnectPrompt } from '../components/ConnectPrompt'
import { useApp } from '../store'

const TIMEFRAMES = ['1Day', '1Hour', '15Min', '5Min'] as const

export function ChartPage() {
  const { symbol, setSymbol } = useApp()
  const [input, setInput] = useState(symbol)
  const [timeframe, setTimeframe] = useState<(typeof TIMEFRAMES)[number]>('1Day')
  const [bars, setBars] = useState<Bar[]>([])
  const [needsKeys, setNeedsKeys] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    let alive = true
    setLoading(true)
    api
      .bars(symbol, timeframe)
      .then((b) => {
        if (!alive) return
        setBars(b)
        setNeedsKeys(false)
        setError(b.length === 0 ? `No data for “${symbol}”.` : null)
      })
      .catch((e) => {
        if (!alive) return
        if (e instanceof ApiError && e.status === 503) setNeedsKeys(true)
        else setError(e instanceof Error ? e.message : String(e))
      })
      .finally(() => alive && setLoading(false))
    return () => {
      alive = false
    }
  }, [symbol, timeframe])

  if (needsKeys) return <ConnectPrompt />

  return (
    <div className="px-8 pb-8 h-[calc(100%-90px)] flex flex-col gap-4">
      <div className="flex items-center gap-3">
        <form
          onSubmit={(e) => {
            e.preventDefault()
            if (input.trim()) setSymbol(input.trim().toUpperCase())
          }}
        >
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Symbol"
            spellCheck={false}
            className="w-36 px-4 py-2 rounded-xl bg-white text-[14px] font-semibold tracking-wide uppercase shadow-[0_1px_3px_rgba(0,0,0,0.06)] outline-none focus:ring-2 focus:ring-accent/40"
          />
        </form>
        <div className="flex bg-black/[0.05] rounded-xl p-1">
          {TIMEFRAMES.map((tf) => (
            <button
              key={tf}
              onClick={() => setTimeframe(tf)}
              className={`px-3.5 py-1.5 rounded-lg text-[12.5px] font-medium transition-colors ${
                timeframe === tf ? 'bg-white shadow-[0_1px_3px_rgba(0,0,0,0.1)]' : 'text-ink-soft hover:text-ink'
              }`}
            >
              {tf}
            </button>
          ))}
        </div>
        {loading && <span className="text-[12px] text-ink-soft">Loading…</span>}
        {error && <span className="text-[12px] text-loss">{error}</span>}
      </div>
      <div className="card flex-1 p-4 min-h-0">
        {bars.length > 0 && <CandleChart bars={bars} />}
      </div>
    </div>
  )
}
