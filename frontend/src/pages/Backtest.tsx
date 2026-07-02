import { useEffect, useState } from 'react'
import { api, ApiError, type BacktestResult, type StrategyInfo } from '../api'
import { ConnectPrompt } from '../components/ConnectPrompt'
import { EquityChart } from '../components/EquityChart'

const fmtUsd = (n: number) =>
  n.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 })
const fmtPct = (n: number | null) => (n === null ? '—' : `${n >= 0 ? '+' : ''}${n.toFixed(2)}%`)
const fmtDate = (iso: string) => new Date(iso).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: '2-digit' })

function Tile({ label, value, tone }: { label: string; value: string; tone?: 'gain' | 'loss' }) {
  return (
    <div className="card px-5 py-4 flex-1 min-w-32">
      <div className="text-[12px] font-medium text-ink-soft mb-0.5">{label}</div>
      <div className={`text-[20px] font-semibold tracking-tight ${tone === 'gain' ? 'text-[#248a3d]' : tone === 'loss' ? 'text-loss' : ''}`}>
        {value}
      </div>
    </div>
  )
}

export function Backtest() {
  const [strategies, setStrategies] = useState<StrategyInfo[]>([])
  const [strategyId, setStrategyId] = useState('')
  const [symbol, setSymbol] = useState('AAPL')
  const [timeframe, setTimeframe] = useState('1Day')
  const [params, setParams] = useState<Record<string, number>>({})
  const [result, setResult] = useState<BacktestResult | null>(null)
  const [running, setRunning] = useState(false)
  const [needsKeys, setNeedsKeys] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    api.strategies().then(({ strategies: s }) => {
      setStrategies(s)
      if (s.length && !strategyId) {
        setStrategyId(s[0].id)
        setParams({ ...s[0].params })
      }
    })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  const selected = strategies.find((s) => s.id === strategyId)

  const pick = (id: string) => {
    setStrategyId(id)
    const s = strategies.find((x) => x.id === id)
    if (s) setParams({ ...s.params })
    setResult(null)
    setError(null)
  }

  const run = async () => {
    setRunning(true)
    setError(null)
    try {
      const r = await api.backtest({ strategy_id: strategyId, symbol: symbol.toUpperCase(), timeframe, params })
      setResult(r)
      setNeedsKeys(false)
    } catch (e) {
      if (e instanceof ApiError && e.status === 503) setNeedsKeys(true)
      else setError(e instanceof Error ? e.message : String(e))
    } finally {
      setRunning(false)
    }
  }

  if (needsKeys) return <ConnectPrompt />

  return (
    <div className="px-8 pb-8 space-y-5">
      {/* controls */}
      <div className="card p-5 flex flex-wrap items-end gap-4">
        <label className="flex flex-col gap-1.5">
          <span className="text-[12px] font-medium text-ink-soft">Strategy</span>
          <select
            value={strategyId}
            onChange={(e) => pick(e.target.value)}
            className="px-3 py-2 rounded-xl bg-canvas text-[13.5px] font-medium outline-none focus:ring-2 focus:ring-accent/40"
          >
            {strategies.map((s) => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1.5">
          <span className="text-[12px] font-medium text-ink-soft">Symbol</span>
          <input
            value={symbol}
            onChange={(e) => setSymbol(e.target.value)}
            spellCheck={false}
            className="w-28 px-3 py-2 rounded-xl bg-canvas text-[13.5px] font-semibold uppercase outline-none focus:ring-2 focus:ring-accent/40"
          />
        </label>
        <label className="flex flex-col gap-1.5">
          <span className="text-[12px] font-medium text-ink-soft">Timeframe</span>
          <select
            value={timeframe}
            onChange={(e) => setTimeframe(e.target.value)}
            className="px-3 py-2 rounded-xl bg-canvas text-[13.5px] font-medium outline-none focus:ring-2 focus:ring-accent/40"
          >
            {['1Day', '1Hour', '15Min'].map((tf) => <option key={tf}>{tf}</option>)}
          </select>
        </label>
        {selected &&
          Object.keys(selected.params).map((k) => (
            <label key={k} className="flex flex-col gap-1.5">
              <span className="text-[12px] font-medium text-ink-soft">{k.replaceAll('_', ' ')}</span>
              <input
                type="number"
                value={params[k] ?? ''}
                onChange={(e) => setParams({ ...params, [k]: Number(e.target.value) })}
                className="w-24 px-3 py-2 rounded-xl bg-canvas text-[13.5px] font-medium outline-none focus:ring-2 focus:ring-accent/40"
              />
            </label>
          ))}
        <button
          onClick={run}
          disabled={running || !strategyId || !symbol.trim()}
          className="ml-auto px-5 py-2.5 rounded-xl bg-accent text-white text-[13.5px] font-semibold hover:bg-accent/90 active:scale-[0.98] transition disabled:opacity-40"
        >
          {running ? 'Running…' : 'Run Backtest'}
        </button>
      </div>

      {error && <div className="card p-4 text-[13px] text-loss">{error}</div>}

      {result && (
        <>
          <div className="flex flex-wrap gap-4">
            <Tile label="Total Return" value={fmtPct(result.stats.total_return_pct)} tone={result.stats.total_return_pct >= 0 ? 'gain' : 'loss'} />
            <Tile label="CAGR" value={fmtPct(result.stats.cagr_pct)} />
            <Tile label="Sharpe" value={result.stats.sharpe === null ? '—' : result.stats.sharpe.toFixed(2)} />
            <Tile label="Max Drawdown" value={`−${result.stats.max_drawdown_pct.toFixed(2)}%`} tone="loss" />
            <Tile label="Trades" value={String(result.stats.num_trades)} />
            <Tile label="Win Rate" value={fmtPct(result.stats.win_rate_pct)} />
          </div>

          <div className="card p-4 h-80">
            <EquityChart points={result.equity_curve} />
          </div>

          <div className="card p-6">
            <h2 className="text-[15px] font-semibold mb-4">
              Trades <span className="text-ink-soft font-normal">({fmtUsd(result.stats.initial_cash)} → {fmtUsd(result.stats.final_equity)})</span>
            </h2>
            {result.trades.length === 0 ? (
              <p className="text-[13px] text-ink-soft">No trades were made.</p>
            ) : (
              <table className="w-full text-[13px]">
                <thead>
                  <tr className="text-left text-ink-soft">
                    <th className="font-medium pb-3">Entry</th>
                    <th className="font-medium pb-3">Exit</th>
                    <th className="font-medium pb-3 text-right">Qty</th>
                    <th className="font-medium pb-3 text-right">Entry Px</th>
                    <th className="font-medium pb-3 text-right">Exit Px</th>
                    <th className="font-medium pb-3 text-right">P&L</th>
                    <th className="font-medium pb-3 text-right">Return</th>
                  </tr>
                </thead>
                <tbody>
                  {result.trades.map((t, i) => (
                    <tr key={i} className="border-t border-black/5">
                      <td className="py-2.5">{fmtDate(t.entry_time)}</td>
                      <td className="py-2.5">{fmtDate(t.exit_time)}</td>
                      <td className="py-2.5 text-right">{t.qty}</td>
                      <td className="py-2.5 text-right">{t.entry_price.toFixed(2)}</td>
                      <td className="py-2.5 text-right">{t.exit_price.toFixed(2)}</td>
                      <td className={`py-2.5 text-right font-medium ${t.pnl >= 0 ? 'text-[#248a3d]' : 'text-loss'}`}>
                        {t.pnl >= 0 ? '+' : ''}{t.pnl.toFixed(2)}
                      </td>
                      <td className={`py-2.5 text-right ${t.return_pct >= 0 ? 'text-[#248a3d]' : 'text-loss'}`}>
                        {fmtPct(t.return_pct)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </>
      )}
    </div>
  )
}
